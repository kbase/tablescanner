"""
TableScanner FastAPI Application

Main application factory module.
"""

from fastapi import FastAPI
from app.routes import router


def create_app() -> FastAPI:
    """
    Application factory function.
    
    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI(
        title="TableScanner",
        description="API for table scanning operations",
        version="1.0.0"
    )
    
    # Include routes
    app.include_router(router)
    
    return app


# Create app instance for uvicorn
app = create_app()
