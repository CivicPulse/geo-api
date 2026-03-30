from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://CHANGEME:CHANGEME@localhost:5432/civpulse_geo"
    database_url_sync: str = "postgresql+psycopg2://CHANGEME:CHANGEME@localhost:5432/civpulse_geo"
    log_level: str = "INFO"
    environment: str = "development"
    max_batch_size: int = 100
    batch_concurrency_limit: int = 10

    # Connection pool sizing (PERF-01)
    db_pool_size: int = 5            # connections per worker process
    db_max_overflow: int = 5         # additional connections under burst
    db_pool_recycle: int = 3600      # recycle connections after 1 hour (seconds)

    # Cascade feature flag (CASC-02, D-02)
    cascade_enabled: bool = True

    # Per-stage timeout budgets in ms (CASC-04, D-15)
    exact_match_timeout_ms: int = 2000
    tiger_timeout_ms: int = 3000        # Tiger PostGIS geocode() needs more time than HTTP providers
    census_timeout_ms: int = 2000       # Census HTTP provider (same as exact_match default)
    fuzzy_match_timeout_ms: int = 500
    consensus_timeout_ms: int = 200
    cascade_total_timeout_ms: int = 3000

    # LLM sidecar feature flag (LLM-01, D-09) — default off
    cascade_llm_enabled: bool = False
    ollama_url: str = "http://ollama:11434"
    llm_timeout_ms: int = 5000

    # Provider trust weights (CONS-02, D-08)
    weight_census: float = 0.90
    weight_openaddresses: float = 0.80
    weight_macon_bibb: float = 0.80
    weight_tiger_unrestricted: float = 0.40
    weight_tiger_restricted: float = 0.75
    weight_nad: float = 0.80


settings = Settings()
