from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "TAVRYX"
    app_env: str = "production"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    gemini_fallback_model: str = "gemini-3.5-flash"
    gemini_timeout_seconds: float = Field(default=45.0, ge=10.0, le=120.0)
    caspian_api_key: str | None = None
    caspian_base_url: str = "https://api.trycaspianai.com"
    tavryx_db_path: str = "data/tavryx.db"
    tavryx_max_context_messages: int = Field(default=8, ge=2, le=30)
    tavryx_memory_limit: int = Field(default=30, ge=5, le=200)
    tavryx_max_output_tokens: int = Field(default=1200, ge=256, le=4000)
    tavryx_candidate_situations: int = Field(default=8, ge=3, le=20)
    tavryx_history_per_situation: int = Field(default=8, ge=3, le=20)
    tavryx_rate_limit_per_minute: int = Field(default=30, ge=5, le=120)
    tavryx_fast_thinking_level: str = "low"
    tavryx_complex_thinking_level: str = "medium"
    tavryx_critical_thinking_level: str = "medium"
    tavryx_api_token: str | None = None
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def db_path(self) -> Path:
        p = Path(self.tavryx_db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

@lru_cache
def get_settings():
    return Settings()

settings = get_settings()
