
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    PROJECT_NAME: str = "Publishing CMS"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "changeme_in_production_secret_key_12345"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost/cms_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Optional external AI Structuring service integration (disabled by default)
    # When AI_STRUCTURING_BASE_URL is set, the StructuringEngine can offload structuring
    # to an external service and pull the processed DOCX back into the CMS.
    AI_STRUCTURING_BASE_URL: str = ""
    AI_STRUCTURING_API_KEY: str = ""
    AI_STRUCTURING_DOCUMENT_TYPE: str = "Academic Document"
    AI_STRUCTURING_USE_MARKERS: bool = False
    AI_STRUCTURING_POLL_INTERVAL_SECONDS: int = 2
    AI_STRUCTURING_MAX_WAIT_SECONDS: int = 900
    AI_STRUCTURING_REQUEST_TIMEOUT_SECONDS: int = 30

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
