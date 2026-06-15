from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    STABLFY_SOCIAL_BASE_URL: str = "https://stablfy-social.onrender.com"
    STABLFY_PICKS_API_KEY: str = ""
    PF_API_BASE_URL: str = "https://api.puntingform.com.au/v2"
    PF_API_KEY: str = ""
    RACING_DB_BASE_URL: str = "https://racing-db.onrender.com"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_API_KEY: str = ""
    STABLE_BRAIN_BASE_URL: str = "https://system-builder.onrender.com"
    STABLE_BRAIN_API_KEY: str = ""
    UPSTREAM_TIMEOUT_SECONDS: float = 10.0
    PF_TIMEOUT_SECONDS: float = 30.0
    GEMINI_TIMEOUT_SECONDS: float = 60.0
    STABLE_BRAIN_TIMEOUT_SECONDS: float = 60.0
    ASK_MAX_TOOL_ROUNDS: int = 6

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
