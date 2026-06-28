from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MMA Fight Predictor"
    app_env: str = "development"
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./storage/app.db"
    model_path: str = "./storage/model.joblib"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
