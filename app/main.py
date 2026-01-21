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
from fastapi.security import HTTPBearer, APIKeyCookie

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
    Authentication can be provided in three ways (in order of priority):
    1. **Authorization header**: `Authorization: Bearer <token>` or `Authorization: <token>`
    2. **kbase_session cookie**: Set the `kbase_session` cookie with your KBase session token
    3. **Service token**: Configure `KB_SERVICE_AUTH_TOKEN` environment variable (for service-to-service calls)
    
    **Using Swagger UI**: Click the "Authorize" button (🔒) at the top of this page to enter your authentication token.
    - For **BearerAuth**: Enter your KBase token (Bearer prefix is optional)
    - For **CookieAuth**: Set the `kbase_session` cookie in your browser's developer tools
    
    Note: Cookie authentication may have limitations in Swagger UI due to browser security restrictions.
    For best results, use the Authorization header method.
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

    # Define security schemes for Swagger UI
    # These will show up in the "Authorize" button
    security_schemes = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Token",
            "description": "KBase authentication token. Enter your token (Bearer prefix optional)."
        },
        "CookieAuth": {
            "type": "apiKey",
            "in": "cookie",
            "name": "kbase_session",
            "description": "KBase session cookie. Set this in your browser's developer tools."
        }
    }

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
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        Global exception handler to catch any unhandled exceptions.
        Provides detailed error messages in debug mode.
        """
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        
        # Log the full exception with traceback
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        
        # Return detailed error in debug mode, generic message otherwise
        if settings.DEBUG:
            detail = f"{str(exc)}\n\nTraceback:\n{traceback.format_exc()}"
        else:
            detail = str(exc) if str(exc) else "An internal server error occurred"
        
        return JSONResponse(
            status_code=500,
            content={"detail": detail},
        )

    # Include API routes
    app.include_router(router)
    
    # Add security schemes to OpenAPI schema after routes are included
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=tags_metadata,
        )
        # Add security schemes to enable "Authorize" button in Swagger UI
        openapi_schema.setdefault("components", {})
        openapi_schema["components"]["securitySchemes"] = security_schemes

        # Mark secured endpoints so Swagger UI "Try it out" + generated curl include auth headers.
        # We only apply this to endpoints that actually use KBase auth.
        secured_paths_prefixes = (
            "/object/",
        )
        secured_exact_paths = {
            "/table-data",
        }
        security_requirement = [{"BearerAuth": []}, {"CookieAuth": []}]

        for path, methods in (openapi_schema.get("paths") or {}).items():
            needs_security = path in secured_exact_paths or any(
                path.startswith(prefix) for prefix in secured_paths_prefixes
            )
            if not needs_security:
                continue
            for method, operation in (methods or {}).items():
                if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                    continue
                if isinstance(operation, dict):
                    operation.setdefault("security", security_requirement)
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi

    # Mount static files directory for viewer.html
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


# Create app instance for uvicorn
app = create_app()
