import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_name: str = os.getenv("ATLAS_SERVICE_NAME", "metadata-knowledge")
    log_level: str = os.getenv("ATLAS_LOG_LEVEL", "INFO")
    schema_version: str = os.getenv("ATLAS_METADATA_SCHEMA_VERSION", "1.0")


settings = Settings()
