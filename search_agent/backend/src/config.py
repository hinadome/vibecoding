from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # API Settings
    api_title: str = "Search Agent Multi-Modal API"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["*"]

    # Storage Settings
    qdrant_path: str = "./qdrant_data"
    chroma_path: str = "./chroma_data"

    # Database selection — accepted values: "qdrant", "chroma"
    primary_db: str = "chroma"
    fallback_db: str = "qdrant"

    # Models
    embedder_model: str = "all-MiniLM-L6-v2"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
settings = Settings()
