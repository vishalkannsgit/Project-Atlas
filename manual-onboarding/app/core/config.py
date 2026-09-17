from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Project Atlas - Document Onboarding"
    API_V1_STR: str = "/api/v1"
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_DIR: str = "./storage_uploads"
    S3_ENDPOINT_URL: Optional[str] = None
    S3_BUCKET_NAME: str = "atlas-raw-documents"
    AWS_ACCESS_KEY_ID: Optional[str] = "minioadmin"
    AWS_SECRET_ACCESS_KEY: Optional[str] = "minioadmin"
    AWS_REGION: str = "us-east-1"
    DATABASE_URL: str = "sqlite+aiosqlite:///./atlas_documents.db"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_RAW_INGEST: str = "ingest.raw"
    KAFKA_ENABLED: bool = False
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024
    ALLOWED_MIME_TYPES: list[str] = ["application/pdf"]

settings = Settings()