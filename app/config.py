"""
Configuration settings for TableScanner application.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    KB_SERVICE_AUTH_TOKEN: str
    CACHE_DIR: str

    # KBase Workspace settings
    WORKSPACE_URL: str

    # Root path for proxy deployment (e.g., "/services/berdl_table_scanner")
    ROOT_PATH: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()