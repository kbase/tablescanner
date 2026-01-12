"""
TableScanner FastAPI Application

Main application factory module for the TableScanner service.
Provides REST API endpoints for querying BERDL table data.

Run with: uv run fastapi dev app/main.py
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router
from app.config import settings


def create_app() -> FastAPI:
    """
    Application factory function.

    Creates and configures the FastAPI application with:
    - Static file serving for viewer.html
    - API routes

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    # Configure root_path for KBase dynamic services
    # KBase services are often deployed at /services/service_name
    # Pydantic Settings management or manual environ check can handle this.
    import os
    root_path = os.environ.get("KB_SERVICE_ROOT_PATH", "")
    

    description = """
    ## TableScanner API

    A FastAPI service for querying BERDL table data from KBase.

    ### Features
    - List pangenomes from BERDLTables objects
    - List tables within a pangenome
    - Query table data with filtering, sorting, and pagination
    - Local caching for performance

    ### Authentication
    Pass your KBase auth token in the `Authorization` header.
    """

    tags_metadata = [
        {
            "name": "General",
            "description": "Health check and general service information.",
        },
        {
            "name": "Object Access",
            "description": "API endpoints for accessing data via KBase workspace object references (UPAs).",
        },
        {
            "name": "Handle Access",
            "description": "API endpoints for accessing data via Blobstore handle references (KBH_...).",
        },
        {
            "name": "Cache Management",
            "description": "Operations for managing and inspecting the local SQLite cache.",
        },
        {
            "name": "Legacy",
            "description": "Older endpoints maintained for backwards compatibility with existing clients.",
        },
    ]

    app = FastAPI(
        title="TableScanner",
        root_path=root_path,
        description=description,
        version="1.0.0",
        openapi_tags=tags_metadata,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Add CORS middleware to allow cross-origin requests
    # This is necessary when viewer.html is opened from file:// or different origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store settings in app state for access throughout the application
    app.state.settings = settings

    # Include API routes
    app.include_router(router)

    # Mount static files directory for viewer.html
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


# Create app instance for uvicorn
app = create_app()
