from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything here configures the DASHBOARD only. The trading engine itself is a real
    Freqtrade process (freqtrade trade --dry-run) - it has its own config file
    (config/config.dryrun.json) and is not configured through this app."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"

    # Freqtrade's own REST API server (enabled via api_server.enabled in
    # config/config.dryrun.json). This dashboard is an authenticated client of it, nothing more.
    freqtrade_api_url: str = "http://freqtrade:8080"
    freqtrade_api_username: str = "freqtrader"
    freqtrade_api_password: str = "changeme"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
