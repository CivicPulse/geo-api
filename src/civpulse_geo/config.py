from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        arbitrary_types_allowed=True,
    )

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

    # Observability settings (Phase 22)
    log_format: str = "auto"  # auto|json|text (D-01)
    otel_enabled: bool = True
    otel_exporter_endpoint: str = "http://tempo:4317"

    @property
    def is_json_logging(self) -> bool:
        if self.log_format == "json":
            return True
        if self.log_format == "text":
            return False
        # auto: JSON when not local
        return self.environment != "local"

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
