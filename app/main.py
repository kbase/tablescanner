"""
TableScanner FastAPI Application

Main application factory module for the TableScanner service.
Provides REST API endpoints for querying BERDL table data.

Run with: uv run fastapi dev app/main.py
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router
from app.config import settings
from app.exceptions import TableNotFoundError, InvalidFilterError


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
    # Pydantic Settings management or manual environ check can handle this.
    root_path = os.environ.get("KB_SERVICE_ROOT_PATH", "")
    

    description = """
    ## TableScanner API

    A FastAPI service for querying tabular data from KBase SQLite databases.
    Provides a comprehensive DataTables Viewer-compatible API with advanced
    query capabilities, type-aware filtering, and performance optimizations.

    ### Features
    - List tables in KBase objects
    - Query table data with filtering, sorting, and pagination
    - Type-aware filtering with automatic numeric conversion
    - Advanced filter operators (eq, ne, gt, gte, lt, lte, like, ilike, in, not_in, between, is_null, is_not_null)
    - Aggregations with GROUP BY support
    - Full-text search (FTS5)
    - Column statistics and schema information
    - Query result caching for performance
    - Local database caching
    - Connection pooling with automatic lifecycle management

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
    # Update CORS middleware to allow requests from the frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store settings in app state for access throughout the application
    app.state.settings = settings

    # Exception Handlers
    @app.exception_handler(TableNotFoundError)
    async def table_not_found_handler(request: Request, exc: TableNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidFilterError)
    async def invalid_filter_handler(request: Request, exc: InvalidFilterError):
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc)},
        )

    # Include API routes
    app.include_router(router)

    # Mount static files directory for viewer.html
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


# Create app instance for uvicorn
app = create_app()
