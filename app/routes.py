"""
TableScanner API Routes.

REST API Structure (per architecture diagram):
- GET /{handle_ref}/tables - List tables in SQLite from handle
- GET /{handle_ref}/tables/{table}/schema - Get table schema
- GET /{handle_ref}/tables/{table}/data - Query table data with pagination
- GET /object/{ws_ref}/tables - List tables from KBase object
- GET /object/{ws_ref}/tables/{table}/data - Query via KBase object ref

Also supports legacy endpoints for backwards compatibility.
"""


import asyncio
import logging
import traceback
from datetime import datetime
from pathlib import Path
from app.utils.workspace import KBaseClient

from fastapi import APIRouter, HTTPException, Header, Query, Cookie

from app.models import (
    TableDataRequest,
    TableDataResponse,
    TableListResponse,
    TableInfo,
    CacheResponse,
    ServiceStatus,
    TableSchemaResponse,
    TableDataQueryRequest,
    TableDataQueryResponse,
    TableSchemaInfo,
    TableStatisticsResponse,
    AggregationQueryRequest,
    HealthResponse,
    FilterRequest,
    AggregationRequest,
)
from app.utils.workspace import (
    download_pangenome_db,
    get_object_type,
)
from app.utils.sqlite import (
    list_tables,
    get_table_columns,
    get_table_row_count,
    validate_table_exists,
)
from app.services.data.schema_service import get_schema_service
from app.services.data.connection_pool import get_connection_pool
from app.services.db_helper import (
    get_object_db_path,
    ensure_table_accessible,
)
from app.utils.async_utils import run_sync_in_thread
from app.utils.request_utils import TableRequestProcessor
from app.config import settings
from app.config_constants import MAX_LIMIT, DEFAULT_LIMIT

# Configure module logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_auth_token(
    authorization: str | None = None,
    kbase_session: str | None = None
) -> str:
    """
    Extract auth token from header, cookie, or settings.
    
    Priority:
    1. Authorization header (Bearer token or plain token)
    2. kbase_session cookie
    3. KB_SERVICE_AUTH_TOKEN from settings
    
    Args:
        authorization: Authorization header value
        kbase_session: kbase_session cookie value
        
    Returns:
        Authentication token string
        
    Raises:
        HTTPException: If no token is found
    """
    # Try Authorization header first
    if authorization:
        if authorization.startswith("Bearer "):
            return authorization[7:]
        return authorization
    
    # Try kbase_session cookie
    if kbase_session:
        return kbase_session
    
    # Fall back to service token from settings
    if settings.KB_SERVICE_AUTH_TOKEN:
        return settings.KB_SERVICE_AUTH_TOKEN
    
    raise HTTPException(
        status_code=401,
        detail="Authorization required. Provide token via Authorization header, kbase_session cookie, or configure KB_SERVICE_AUTH_TOKEN."
    )


def get_cache_dir() -> Path:
    """Get configured cache directory."""
    return Path(settings.CACHE_DIR)


# =============================================================================
# SERVICE STATUS
# =============================================================================

@router.get("/", response_model=ServiceStatus, tags=["General"])
async def root():
    """Service health check."""
    return ServiceStatus(
        service="TableScanner",
        version="1.0.0",
        status="running",
        cache_dir=str(settings.CACHE_DIR)
    )


@router.get("/health", response_model=HealthResponse, tags=["General"])
async def health_check():
    """
    Health check endpoint for DataTables Viewer API.
    
    Returns service status, cache information, and connection pool stats.
    """

    
    try:
        # Get connection pool stats (non-blocking)
        try:
            pool = get_connection_pool()
            cache_stats = pool.get_stats()
        except Exception as pool_error:
            logger.warning(f"Error getting pool stats: {pool_error}")
            cache_stats = {"total_connections": 0, "connections": []}
        
        return HealthResponse(
            status="ok",
            timestamp=datetime.utcnow().isoformat() + "Z",
            mode="cached_sqlite",
            data_dir=str(settings.CACHE_DIR),
            config_dir=str(Path(settings.CACHE_DIR) / "configs"),
            cache={
                "databases_cached": cache_stats.get("total_connections", 0),
                "databases": cache_stats.get("connections", [])
            }
        )
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# OBJECT-BASED ENDPOINTS (via KBase workspace object reference)
# /object/{ws_ref}/tables - List tables from KBase object
# /object/{ws_ref}/tables/{table}/data - Query data
# =============================================================================

@router.get("/object/{ws_ref:path}/tables", tags=["Object Access"], response_model=TableListResponse)
async def list_tables_by_object(
    ws_ref: str,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None),
    kbase_session: str | None = Cookie(None)
):
    """
    List tables for a BERDLTables object.
    
    Authentication can be provided via:
    - Authorization header (Bearer token or plain token)
    - kbase_session cookie
    - KB_SERVICE_AUTH_TOKEN environment variable (for service-to-service)
    """

    
    try:
        token = get_auth_token(authorization, kbase_session)
        cache_dir = get_cache_dir()
        berdl_table_id = ws_ref
        
        # Get database path (handles caching, download timeouts via helper)
        db_path = await get_object_db_path(berdl_table_id, token, kb_env, cache_dir)
        
        # List tables (run in thread)
        table_names = await run_sync_in_thread(list_tables, db_path)
        
        tables = []
        schemas = {}
        total_rows = 0
        
        # Use schema service for better column type information
        schema_service = get_schema_service()
        
        # Process tables
        for name in table_names:
            try:
                # Run lightweight checks in thread
                columns = await run_sync_in_thread(get_table_columns, db_path, name)
                row_count = await run_sync_in_thread(get_table_row_count, db_path, name)
                
                # Get display name (use table name as default)
                display_name = name.replace("_", " ").title()
                
                tables.append({
                    "name": name,
                    "displayName": display_name,
                    "row_count": row_count,
                    "column_count": len(columns)
                })
                total_rows += row_count or 0
                
                # Build schema map with actual types
                try:
                    table_schema = await run_sync_in_thread(
                        schema_service.get_table_schema, db_path, name
                    )
                    schemas[name] = {
                        col["name"]: col["type"]
                        for col in table_schema["columns"]
                    }
                except Exception:
                    # Fallback to default type
                    schemas[name] = {col: "TEXT" for col in columns}
            except Exception:
                logger.warning("Error getting table info for %s", name, exc_info=True)
                tables.append({"name": name, "displayName": name})
        
        # Get object type (non-blocking)
        try:
            # Use specific timeout for API call
            object_type = await asyncio.wait_for(
                run_sync_in_thread(get_object_type, berdl_table_id, token, kb_env),
                timeout=settings.KBASE_API_TIMEOUT_SECONDS
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Could not get object type (non-critical): {e}")
            object_type = None
        
        # Config-related fields (deprecated, kept for backward compatibility)
        config_fingerprint = None
        config_url = None
        has_cached_config = False
        has_builtin_config = False
        builtin_config_id = None
        
        # Get database size
        database_size = None
        try:
            database_size = db_path.stat().st_size if db_path.exists() else None
        except Exception as e:
            # Database size is informational; log and continue if it cannot be determined.
            logger.debug("Failed to get database size for %s: %s", db_path, e)
        
        # Format berdl_table_id for DataTables Viewer API (local/db_name format)
        berdl_table_id_formatted = f"local/{berdl_table_id.replace('/', '_')}"
        
        return {
            "berdl_table_id": berdl_table_id_formatted,
            "object_type": object_type or "LocalDatabase",
            "tables": tables,
            "source": "Local",
            "has_config": has_cached_config,
            "config_source": "static" if has_cached_config else None,
            "config_fingerprint": config_fingerprint,
            "config_url": config_url,
            "has_cached_config": has_cached_config,
            "schemas": schemas,
            "has_builtin_config": has_builtin_config,
            "builtin_config_id": builtin_config_id,
            "database_size_bytes": database_size,
            "total_rows": total_rows,
            "api_version": "2.0",
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is (don't convert to 500)
        raise
    except Exception as e:
        # Log full traceback for debugging
        logger.error(f"Error listing tables: {e}", exc_info=True)
        # Provide detailed error message
        # Always include the error message, add traceback in debug mode
        error_detail = str(e) if str(e) else f"Error: {type(e).__name__}"
        if settings.DEBUG:
            error_detail += f"\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


@router.get("/object/{ws_ref:path}/tables/{table_name}/data", tags=["Object Access"], response_model=TableDataResponse)
async def get_table_data_by_object(
    ws_ref: str,
    table_name: str,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    sort_column: str | None = Query(None),
    sort_order: str | None = Query("ASC"),
    search: str | None = Query(None),
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None),
    kbase_session: str | None = Cookie(None)
):
    """
    Query table data from a BERDLTables object.
    
    Authentication can be provided via:
    - Authorization header (Bearer token or plain token)
    - kbase_session cookie
    - KB_SERVICE_AUTH_TOKEN environment variable (for service-to-service)
    """
    try:
        token = get_auth_token(authorization, kbase_session)
        cache_dir = get_cache_dir()
        berdl_table_id = ws_ref
        
        # Get and validate DB access
        db_path = await get_object_db_path(berdl_table_id, token, kb_env, cache_dir)
        await ensure_table_accessible(db_path, table_name)
        
        result = await TableRequestProcessor.process_data_request(
            db_path=db_path,
            table_name=table_name,
            limit=limit,
            offset=offset,
            sort_column=sort_column,
            sort_order=sort_order or "ASC",
            search_value=search,
            handle_ref_or_id=berdl_table_id
        )

        return result
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is (don't convert to 500)
        raise
    except Exception as e:
        # Log full traceback for debugging
        logger.error(f"Error querying data: {e}", exc_info=True)
        # Provide detailed error message
        # Always include the error message, add traceback in debug mode
        error_detail = str(e) if str(e) else f"Error: {type(e).__name__}"
        if settings.DEBUG:
            error_detail += f"\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


# =============================================================================
# DATA ACCESS ENDPOINTS
# =============================================================================

@router.post("/table-data", response_model=TableDataResponse, tags=["Data Access"])
async def query_table_data(
    request: TableDataRequest,
    authorization: str | None = Header(None),
    kbase_session: str | None = Cookie(None)
):
    """
    Query table data using a JSON body. Recommended for programmatic access.
    
    Authentication can be provided via:
    - Authorization header (Bearer token or plain token)
    - kbase_session cookie
    - KB_SERVICE_AUTH_TOKEN environment variable (for service-to-service)
    """
    try:
        token = get_auth_token(authorization, kbase_session)
        cache_dir = get_cache_dir()
        kb_env = getattr(request, 'kb_env', 'appdev') or 'appdev'
        
        filters = request.col_filter if request.col_filter else request.query_filters
        
        try:
            db_path = download_pangenome_db(
                request.berdl_table_id, token, cache_dir, kb_env
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        
        if not validate_table_exists(db_path, request.table_name):
            available = list_tables(db_path)
            raise ValueError(f"Table '{request.table_name}' not found. Available: {available}")
            
        # Column parsing is now handled in process_data_request for both string and list formats
        
        effective_sort_col = request.sort_column
        effective_sort_dir = request.sort_order
        
        if not effective_sort_col and request.order_by:
            first_sort = request.order_by[0]
            effective_sort_col = first_sort.get("column")
            effective_sort_dir = first_sort.get("direction", "ASC").upper()
            
        return await TableRequestProcessor.process_data_request(
            db_path=db_path,
            table_name=request.table_name,
            limit=request.limit,
            offset=request.offset,
            sort_column=effective_sort_col,
            sort_order=effective_sort_dir or "ASC",
            search_value=request.search_value,
            columns=request.columns, # Now handles list or string
            filters=request.filters if request.filters else filters, # Prefer advanced filters, fall back to legacy dict
            aggregations=request.aggregations,
            group_by=request.group_by,
            handle_ref_or_id=request.berdl_table_id
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is (don't convert to 500)
        raise
    except Exception as e:
        # Log full traceback for debugging
        logger.error(f"Error querying data: {e}", exc_info=True)
        # Provide detailed error message
        # Always include the error message, add traceback in debug mode
        error_detail = str(e) if str(e) else f"Error: {type(e).__name__}"
        if settings.DEBUG:
            error_detail += f"\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)

