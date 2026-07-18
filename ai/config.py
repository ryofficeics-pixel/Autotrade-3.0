"""
AI Configuration System
Loads settings from YAML + environment variables
Backward compatible - when AI_ENABLED=false, all AI bypassed
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMConfig(BaseModel):
    """LLM provider configuration (OpenAI-compatible)"""
    base_url: str = "https://openagentic.id/api/v1"
    api_key: str = Field(default="")
    timeout: int = 15


class ModelsConfig(BaseModel):
    """Model selection for different AI tasks"""
    class FilterModels(BaseModel):
        primary: str = "deepseek-v4-pro"
        fallback: str = "deepseek-v4-flash"
        fallback_2: str = "deepseek-v4-free"
    
    class ReasoningModels(BaseModel):
        primary: str = "claude-sonnet-4.6"
        fallback_1: str = "claude-sonnet-4.5-thinking"
        fallback_2: str = "deepseek-v4-pro"
        fallback_3: str = "deepseek-v4-flash"
        fallback_4: str = "deepseek-v4-free"
    
    filter: FilterModels = Field(default_factory=FilterModels)
    reasoning: ReasoningModels = Field(default_factory=ReasoningModels)


class ThresholdsConfig(BaseModel):
    """Decision thresholds for AI filtering"""
    ds_reject: int = 70        # < 70 → auto reject
    ds_escalate: int = 90      # >= 90 → direct approve (optional)


class HealthConfig(BaseModel):
    """Health tracking configuration"""
    auto_disable_after_failures: int = 5
    check_interval: int = 300  # seconds


class AIConfig(BaseModel):
    """Core AI configuration"""
    enabled: bool = True
    mode: Literal["legacy", "hybrid", "ai_full"] = "hybrid"
    timeout: int = 15
    cache_minutes: int = 5
    
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)


class RiskConfig(BaseModel):
    """Risk engine hard limits (AI may never bypass)"""
    max_daily_loss: float = 10.0
    max_consecutive_losses: int = 3
    max_open_positions: int = 5
    max_position_size: float = 50.0
    max_leverage: int = 1
    cooldown_after_losses: int = 1800
    emergency_shutdown_loss: float = 20.0


class FeaturesConfig(BaseModel):
    """Feature store configuration"""
    enabled: bool = True
    indicators: list[str] = Field(default_factory=lambda: [
        "RSI", "MACD", "ATR", "EMA_TREND", "VOLUME_SPIKE"
    ])
    market_data: list[str] = Field(default_factory=lambda: [
        "BTC_REGIME", "BTC_DOMINANCE", "FUNDING_RATE"
    ])


class TelegramConfig(BaseModel):
    """Telegram notifications"""
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class MonitoringConfig(BaseModel):
    """Monitoring and alerting"""
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    notifications: list[str] = Field(default_factory=lambda: [
        "trade_open", "trade_close", "tp_hit", "sl_hit",
        "ai_rejection", "model_fallback", "ai_disabled",
        "api_failure", "emergency_shutdown"
    ])


class DatabaseConfig(BaseModel):
    """Analytics database configuration"""
    path: str = "database/ai_analytics.db"
    retention_days: int = 90


class Config(BaseSettings):
    """
    Complete Autotrade-3.1-AI configuration
    
    Load order:
    1. config/config.ai.yaml
    2. Environment variables (override YAML)
    3. Pydantic defaults (fallback)
    """
    ai: AIConfig = Field(default_factory=AIConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    
    class Config:
        env_nested_delimiter = '__'
        case_sensitive = False


def load_config(config_path: str | Path | None = None) -> Config:
    """
    Load configuration from YAML + environment variables
    
    Args:
        config_path: Path to config.ai.yaml (defaults to config/config.ai.yaml)
    
    Returns:
        Config object with all settings
    
    Environment variable examples:
        OPENAI_API_KEY=sk-...
        AI__ENABLED=true
        AI__MODE=hybrid
        AI__MODELS__FILTER__PRIMARY=deepseek-v4-pro
    """
    # Load .env file first
    from dotenv import load_dotenv
    load_dotenv()
    
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "config.ai.yaml"
    else:
        config_path = Path(config_path)
    
    # Load YAML if it exists
    yaml_data = {}
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            raw = yaml.safe_load(f)
            if raw:
                yaml_data = raw
    
    # Substitute ${VAR} placeholders with env vars
    yaml_str = yaml.dump(yaml_data)
    for match in set([s for s in yaml_str.split('${') if '}' in s]):
        var_name = match.split('}')[0]
        env_value = os.getenv(var_name, '')
        yaml_str = yaml_str.replace(f'${{{var_name}}}', env_value)
    
    yaml_data = yaml.safe_load(yaml_str) or {}
    
    # Merge with environment variables (env takes precedence)
    return Config(**yaml_data)


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get global config instance (singleton pattern)"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: str | Path | None = None) -> Config:
    """Reload configuration from file"""
    global _config
    _config = load_config(config_path)
    return _config
