from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://civpulse:civpulse@localhost:5432/civpulse_geo"
    database_url_sync: str = "postgresql+psycopg2://civpulse:civpulse@localhost:5432/civpulse_geo"
    log_level: str = "INFO"
    environment: str = "development"
    max_batch_size: int = 100
    batch_concurrency_limit: int = 10

    # Cascade feature flag (CASC-02, D-02)
    cascade_enabled: bool = True

    # Per-stage timeout budgets in ms (CASC-04, D-15)
    exact_match_timeout_ms: int = 2000
    fuzzy_match_timeout_ms: int = 500
    consensus_timeout_ms: int = 200
    cascade_total_timeout_ms: int = 3000

    # Provider trust weights (CONS-02, D-08)
    weight_census: float = 0.90
    weight_openaddresses: float = 0.80
    weight_macon_bibb: float = 0.80
    weight_tiger_unrestricted: float = 0.40
    weight_tiger_restricted: float = 0.75
    weight_nad: float = 0.80


settings = Settings()
