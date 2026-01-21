"""
Configuration settings for TableScanner application.

Loads configuration from environment variables and .env file.
All KBase service URLs and authentication settings are managed here.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Create a .env file based on .env.example to configure locally.
    """

    # ==========================================================================
    # AUTHENTICATION
    # ==========================================================================
    KB_SERVICE_AUTH_TOKEN: str | None = Field(
        default=None,
        description="KBase authentication token for service-to-service API access (optional if using header/cookie auth)"
    )

    # ==========================================================================
    # CACHE SETTINGS
    # ==========================================================================
    CACHE_DIR: str = Field(
        default="/tmp/tablescanner_cache",
        description="Directory for caching downloaded files and SQLite databases"
    )
    CACHE_MAX_AGE_HOURS: int = Field(
        default=24,
        description="Maximum age of cached files in hours before re-download"
    )

    # ==========================================================================
    # KBASE SERVICE URLS
    # ==========================================================================
    WORKSPACE_URL: str = Field(
        default="https://kbase.us/services/ws",
        description="KBase Workspace service URL"
    )
    KBASE_ENDPOINT: str = Field(
        default="https://kbase.us/services",
        description="Base URL for KBase services"
    )
    BLOBSTORE_URL: str = Field(
        default="https://kbase.us/services/shock-api",
        description="KBase blobstore/shock service URL"
    )

    # ==========================================================================
    # APPLICATION SETTINGS
    # ==========================================================================
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode with verbose logging"
    )
    KB_ENV: str = Field(
        default="appdev",
        description="KBase environment (appdev, ci, prod)"
    )
    CORS_ORIGINS: list[str] = Field(
        default=["*"],
        description="List of allowed origins for CORS. Use ['*'] for all."
    )

    # Root path for proxy deployment (e.g., "/services/berdl_table_scanner")
    ROOT_PATH: str = ""
    
    # Timeout settings
    DOWNLOAD_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="Timeout in seconds for downloading databases"
    )
    KBASE_API_TIMEOUT_SECONDS: float = Field(
        default=10.0,
        description="Timeout in seconds for KBase API calls"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance - loaded at module import
settings = Settings()