import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- app ---
    APP_ENV: str = "development"
    API_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] | str = ["http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(i) for i in parsed]
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # --- database ---
    DATABASE_URL: str = "postgresql+asyncpg://idra:idra@localhost:5432/idra"
    DB_POOL_SIZE: int = 10
    DB_POOL_MAX_OVERFLOW: int = 5

    # --- auth ---
    JWT_SECRET: str = "change_me_32_bytes_minimum_secret_key_idra_2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    SEED_ADMIN_EMAIL: str = "admin@example.com"
    SEED_ADMIN_PASSWORD: str = "change_me"

    # --- llm ---
    LLM_BACKEND: str = "fake"  # gemini | ollama | fake
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    LLM_TIMEOUT_S: int = 25
    LLM_MAX_RETRIES: int = 1
    LLM_TEMPERATURE_REASONING: float = 0.2
    LLM_TEMPERATURE_PROSE: float = 0.4

    # --- rag ---
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    RAG_TOP_K: int = 8
    RAG_TOP_K_CITIZEN: int = 6
    RAG_SCORE_FLOOR: float = 0.35
    RAG_MAX_CONTEXT_TOKENS: int = 3000
    RAG_HYBRID_ENABLED: bool = False
    KB_STALE_YEARS: int = 10
    SITREP_TTL_HOURS: int = 24

    # --- gis ---
    STUDY_AREA_BBOX: str = "80.15,12.95,80.30,13.15"
    ROAD_GRAPH_PATH: str = "artifacts/road_graph.pkl"
    MAX_SNAP_DISTANCE_M: int = 500
    HAZARD_SOFT_PENALTY: float = 25.0
    DEFAULT_SHELTER_SEARCH_RADIUS_M: int = 10000
    DEFAULT_HOSPITAL_SEARCH_RADIUS_M: int = 15000

    # --- orchestration ---
    RUN_TOTAL_TIMEOUT_S: int = 120
    AGENT_TIMEOUT_ASSESSMENT_S: int = 30
    AGENT_TIMEOUT_PLANNING_S: int = 30
    AGENT_TIMEOUT_EVACUATION_S: int = 20
    AGENT_TIMEOUT_FACILITY_S: int = 10
    AGENT_TIMEOUT_RESOURCE_S: int = 20
    AGENT_TIMEOUT_SYNTHESIS_S: int = 20
    ASSESSMENT_CONFIDENCE_FLOOR: float = 0.5

    # --- reliability ---
    RATE_LIMIT_PUBLIC_PER_MIN: int = 10
    RATE_LIMIT_AUTH_PER_MIN: int = 60
    WEATHER_ENABLED: bool = False
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1"

    # Parsed BBOX helper
    @property
    def parsed_bbox(self) -> tuple[float, float, float, float]:
        """Returns (min_lon, min_lat, max_lon, max_lat)."""
        parts = [float(p.strip()) for p in self.STUDY_AREA_BBOX.split(",")]
        return (parts[0], parts[1], parts[2], parts[3])


settings = Settings()
