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

    # LLM sidecar feature flag (LLM-01, D-09) — default off
    cascade_llm_enabled: bool = False
    ollama_url: str = "http://ollama:11434"
    llm_timeout_ms: int = 5000

    # OSM sidecar service URLs (Phase 24 — INFRA-01, INFRA-02, INFRA-03)
    osm_nominatim_url: str = "http://nominatim:8080"
    osm_tile_url: str = "http://tile-server:8080"
    osm_valhalla_url: str = "http://valhalla:8002"

    # Provider trust weights (CONS-02, D-08)
    weight_census: float = 0.90
    weight_openaddresses: float = 0.80
    weight_macon_bibb: float = 0.80
    weight_tiger_unrestricted: float = 0.40
    weight_tiger_restricted: float = 0.75
    weight_nad: float = 0.80


settings = Settings()
