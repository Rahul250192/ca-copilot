from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, PostgresDsn, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "CA-Copilot Backend"
    API_V1_STR: str = "/api/v1"
    
    # In production, these must be set
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 

    DATABASE_URL: str
    OPENAI_API_KEY: Optional[str] = None
    
    # Supabase Storage
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_BUCKET: str = "knowledge-kits"

    BACKEND_CORS_ORIGINS: List[str] = []

    @validator("DATABASE_URL", pre=True)
    def fix_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            # Fix protocol for asyncpg
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgresql://") and "+asyncpg" not in v:
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            # Strip pgbouncer parameter as asyncpg doesn't support it
            if "pgbouncer=true" in v:
                v = v.replace("?pgbouncer=true", "")
                v = v.replace("&pgbouncer=true", "")
        return v

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")


settings = Settings()
