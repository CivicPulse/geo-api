from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://civpulse:civpulse@localhost:5432/civpulse_geo"
    database_url_sync: str = "postgresql+psycopg2://civpulse:civpulse@localhost:5432/civpulse_geo"
    log_level: str = "INFO"
    environment: str = "development"
    max_batch_size: int = 100
    batch_concurrency_limit: int = 10


settings = Settings()
