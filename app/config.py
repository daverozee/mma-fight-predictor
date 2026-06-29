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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
