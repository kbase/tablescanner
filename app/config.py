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
    KB_SERVICE_AUTH_TOKEN: str = Field(
        ...,
        description="KBase authentication token for API access"
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
    VIEWER_API_URL: str = Field(
        default="http://localhost:3000/api",
        description="DataTables Viewer API base URL for sending generated configs"
    )
    BLOBSTORE_URL: str = Field(
        default="https://kbase.us/services/shock-api",
        description="KBase blobstore/shock service URL"
    )

    # ==========================================================================
    # AI PROVIDER CONFIGURATION
    # ==========================================================================
    AI_PROVIDER: str = Field(
        default="auto",
        description="Preferred AI provider: auto, openai, argo, ollama, claude-code, rules-only"
    )
    AI_FALLBACK_CHAIN: str = Field(
        default="openai,argo,ollama,rules-only",
        description="Comma-separated fallback chain of AI providers"
    )
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key for schema inference"
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model to use for inference"
    )
    OPENAI_TEMPERATURE: float = Field(
        default=0.1,
        description="Temperature for OpenAI responses (lower = more deterministic)"
    )
    
    # Argo Configuration (ANL internal)
    ARGO_USER: str = Field(
        default="",
        description="ANL Argo gateway username"
    )
    ARGO_MODEL: str = Field(
        default="gpt4o",
        description="Argo model to use"
    )
    ARGO_PROXY_PORT: int = Field(
        default=1080,
        description="Argo SOCKS proxy port"
    )
    
    # Ollama Configuration (local LLM)
    OLLAMA_HOST: str = Field(
        default="http://localhost:11434",
        description="Ollama server host URL"
    )
    OLLAMA_MODEL: str = Field(
        default="llama3",
        description="Ollama model to use"
    )
    
    # Claude Code Configuration
    CLAUDE_CODE_EXECUTABLE: str = Field(
        default="claude",
        description="Path to Claude Code CLI executable"
    )
    
    # Generated Config Storage
    GENERATED_CONFIG_DIR: str = Field(
        default="/tmp/tablescanner_configs",
        description="Directory for storing generated viewer configs"
    )

    # ==========================================================================
    # APPLICATION SETTINGS
    # ==========================================================================
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode with verbose logging"
    )

    # Root path for proxy deployment (e.g., "/services/berdl_table_scanner")
    ROOT_PATH: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance - loaded at module import
settings = Settings()