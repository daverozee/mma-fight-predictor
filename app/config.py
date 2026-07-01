from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MMA Fight Predictor"
    app_env: str = "development"
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./storage/app.db"
    model_path: str = "./storage/model.joblib"
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None
    sentiment_search_results: int = 5
    fighter_article_results: int = 3
    data_import_interval_seconds: int = 21_600
    data_import_run_on_startup: bool = True
    balldontlie_api_key: str | None = None
    balldontlie_fights_import_enabled: bool = True
    balldontlie_fights_per_page: int = 100
    balldontlie_fights_max_pages: int = 250
    balldontlie_fights_pause_seconds: float = 0.0
    historical_fight_results_url: str | None = None
    historical_fight_results_format: str = "winner-loser"
    historical_fight_results_events_url: str | None = None
    historical_fight_results_source: str = "configured-fight-history"
    media_seed_limit: int = 500
    media_wikimedia_lookup_limit: int = 25
    media_verification_limit: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
