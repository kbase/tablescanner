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
    - CORS middleware for browser access
    - Static file serving for viewer.html
    - API routes

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI(
        title="TableScanner",
        description="""
## TableScanner API

A FastAPI service for querying BERDL table data from KBase.

### Features
- List pangenomes from BERDLTables objects
- List tables within a pangenome
- Query table data with filtering, sorting, and pagination
- Local caching for performance

### Authentication
Pass your KBase auth token in the `Authorization` header.
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Enable CORS for browser-based access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for development
        allow_credentials=True,
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
