"""
Configuration settings for TableScanner application.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    KB_SERVICE_AUTH_TOKEN: str
    CACHE_DIR: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()