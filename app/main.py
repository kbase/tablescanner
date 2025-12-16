"""
TableScanner FastAPI Application

Main application factory module.
"""

from fastapi import FastAPI
from app.routes import router
from app.config import settings


def create_app() -> FastAPI:
    """
    Application factory function.

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI(
        title="TableScanner",
        description="API for table scanning operations",
        version="1.0.0",
        root_path=settings.ROOT_PATH
    )

    # Store settings in app state for access throughout the application
    app.state.settings = settings

    # Include routes
    app.include_router(router)

    return app


# Create app instance for uvicorn
app = create_app()
