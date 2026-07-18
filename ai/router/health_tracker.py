"""
Model Health Tracker
Tracks per-model health metrics and auto-disables unhealthy models
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger("ai.router.health_tracker")


@dataclass
class ModelHealth:
    """Health statistics for a single model"""
    model_name: str
    
    # Counters
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    consecutive_failures: int = 0
    
    # Latency tracking (milliseconds)
    total_latency_ms: float = 0.0
    
    # State
    is_enabled: bool = True
    last_call_time: float = field(default_factory=time.time)
    disabled_at: float | None = None
    disabled_reason: str = ""
    
    @property
    def success_rate(self) -> float:
        """Success rate (0.0 - 1.0)"""
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls
    
    @property
    def avg_latency_ms(self) -> float:
        """Average latency in milliseconds"""
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency_ms / self.successful_calls
    
    def to_dict(self) -> dict:
        """Export as dict"""
        return {
            "model_name": self.model_name,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "consecutive_failures": self.consecutive_failures,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "is_enabled": self.is_enabled,
            "disabled_reason": self.disabled_reason,
            "last_call_time": self.last_call_time
        }


class HealthTracker:
    """
    Track health metrics for all AI models
    
    Features:
    - Per-model success/failure counts
    - Latency tracking
    - Consecutive failure detection
    - Auto-disable unhealthy models
    - Manual enable/disable
    
    Usage:
        tracker = HealthTracker(auto_disable_threshold=5)
        
        # Record success
        tracker.record_success("deepseek-v4-pro", latency_ms=1200)
        
        # Record failure
        tracker.record_failure("claude-sonnet-4.6", "timeout")
        
        # Check if model is healthy
        if tracker.is_healthy("deepseek-v4-pro"):
            # use model
            pass
        
        # Get all health stats
        stats = tracker.get_all_health()
    """
    
    def __init__(self, auto_disable_threshold: int = 5):
        """
        Initialize health tracker
        
        Args:
            auto_disable_threshold: Consecutive failures before auto-disable
        """
        self.auto_disable_threshold = auto_disable_threshold
        self._models: dict[str, ModelHealth] = {}
    
    def _get_or_create(self, model_name: str) -> ModelHealth:
        """Get or create model health record"""
        if model_name not in self._models:
            self._models[model_name] = ModelHealth(model_name=model_name)
        return self._models[model_name]
    
    def record_success(self, model_name: str, latency_ms: float):
        """
        Record successful call
        
        Args:
            model_name: Model name
            latency_ms: Call latency in milliseconds
        """
        health = self._get_or_create(model_name)
        health.total_calls += 1
        health.successful_calls += 1
        health.consecutive_failures = 0  # reset
        health.total_latency_ms += latency_ms
        health.last_call_time = time.time()
        
        logger.debug(f"{model_name} success (latency: {latency_ms:.0f}ms)")
    
    def record_failure(self, model_name: str, reason: str = ""):
        """
        Record failed call
        
        Args:
            model_name: Model name
            reason: Failure reason (timeout, api_error, etc.)
        """
        health = self._get_or_create(model_name)
        health.total_calls += 1
        health.failed_calls += 1
        health.consecutive_failures += 1
        health.last_call_time = time.time()
        
        logger.warning(f"{model_name} failure ({reason}): {health.consecutive_failures} consecutive")
        
        # Auto-disable if threshold exceeded
        if health.consecutive_failures >= self.auto_disable_threshold and health.is_enabled:
            health.is_enabled = False
            health.disabled_at = time.time()
            health.disabled_reason = f"Auto-disabled after {health.consecutive_failures} consecutive failures"
            logger.error(f"{model_name} auto-disabled: {health.disabled_reason}")
    
    def is_healthy(self, model_name: str) -> bool:
        """
        Check if model is healthy (enabled and not failing)
        
        Args:
            model_name: Model name
        
        Returns:
            True if model is healthy and enabled
        """
        if model_name not in self._models:
            return True  # assume healthy if never called
        
        health = self._models[model_name]
        return health.is_enabled
    
    def enable_model(self, model_name: str):
        """
        Manually enable a model
        
        Args:
            model_name: Model name
        """
        health = self._get_or_create(model_name)
        health.is_enabled = True
        health.consecutive_failures = 0
        health.disabled_at = None
        health.disabled_reason = ""
        logger.info(f"{model_name} manually enabled")
    
    def disable_model(self, model_name: str, reason: str = "manual"):
        """
        Manually disable a model
        
        Args:
            model_name: Model name
            reason: Disable reason
        """
        health = self._get_or_create(model_name)
        health.is_enabled = False
        health.disabled_at = time.time()
        health.disabled_reason = reason
        logger.info(f"{model_name} manually disabled: {reason}")
    
    def get_health(self, model_name: str) -> ModelHealth | None:
        """
        Get health stats for a specific model
        
        Args:
            model_name: Model name
        
        Returns:
            ModelHealth object or None if never called
        """
        return self._models.get(model_name)
    
    def get_all_health(self) -> dict[str, dict]:
        """
        Get health stats for all models
        
        Returns:
            Dict mapping model_name -> health stats dict
        """
        return {name: health.to_dict() for name, health in self._models.items()}
    
    def reset_model(self, model_name: str):
        """
        Reset health stats for a model
        
        Args:
            model_name: Model name
        """
        if model_name in self._models:
            del self._models[model_name]
            logger.info(f"{model_name} health stats reset")
    
    def reset_all(self):
        """Reset all health stats"""
        self._models.clear()
        logger.info("All model health stats reset")


# Global health tracker instance
_health_tracker: HealthTracker | None = None


def get_health_tracker() -> HealthTracker:
    """Get global health tracker instance (singleton pattern)"""
    global _health_tracker
    if _health_tracker is None:
        from ai.config import get_config
        config = get_config()
        _health_tracker = HealthTracker(
            auto_disable_threshold=config.ai.health.auto_disable_after_failures
        )
    return _health_tracker
