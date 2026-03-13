from functools import lru_cache
from pathlib import Path
from typing import Annotated
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: Annotated[List[str], NoDecode] = ["http://localhost:3000"]
    cors_origin_regex: str = r"^https?://(localhost|127(?:\.\d{1,3}){3}|\[::1\])(:\d+)?$"
    cors_allow_credentials: bool = True

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_chat_model: str = Field(
        default="gpt-4.1-mini",
        validation_alias="OPENAI_CHAT_MODEL",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias="OPENAI_EMBEDDING_MODEL",
    )

    tavily_api_key: str = ""
    serper_api_key: str = ""
    exa_api_key: str = Field(default="", validation_alias="EXA_API_KEY")

    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "stock_research"
    mcp_servers_json: str = Field(default="{}", validation_alias="MCP_SERVERS_JSON")
    a2a_agents_json: str = Field(default="{}", validation_alias="A2A_AGENTS_JSON")
    outbound_timeout_sec: int = Field(default=20, validation_alias="OUTBOUND_TIMEOUT_SEC")
    sec_user_agent: str = Field(
        default="DeepResearchStockAssistant/0.1 (ops@example.com)",
        validation_alias="SEC_USER_AGENT",
    )
    sec_max_filings: int = Field(default=4, validation_alias="SEC_MAX_FILINGS")
    sec_request_retries: int = Field(default=2, validation_alias="SEC_REQUEST_RETRIES")
    sec_retry_backoff_ms: int = Field(default=400, validation_alias="SEC_RETRY_BACKOFF_MS")
    sec_ticker_cache_ttl_sec: int = Field(default=21600, validation_alias="SEC_TICKER_CACHE_TTL_SEC")
    sec_filing_excerpt_chars: int = Field(default=900, validation_alias="SEC_FILING_EXCERPT_CHARS")

    model_config = SettingsConfigDict(
        env_file=(str(BASE_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> List[str]:
        """
        Purpose: Normalize CORS origins from env input into a list of strings.
        Args/Params:
        - `cls` (Any): Class reference for class-level behavior.
        - `value` (object): Input parameter used by this function.
        Returns:
        - `List[str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `parse_cors_origins(value=...)`
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ["http://localhost:3000"]
            if stripped.startswith("["):
                try:
                    import json

                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(origin).strip() for origin in parsed if str(origin).strip()]
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin) for origin in value]
        return ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """
    Purpose: Return a cached settings instance to avoid reparsing env on each request.
    Args/Params:
    - None.
    Returns:
    - `Settings`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `get_settings()`
    """
    return Settings()
