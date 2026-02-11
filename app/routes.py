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
from datetime import datetime, timezone
from pathlib import Path as FilePath
from app.utils.workspace import KBaseClient
import shutil
import hashlib
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Header, Query, Cookie, Path, UploadFile, File
from app.exceptions import InvalidFilterError

from app.models import (
    TableDataRequest,
    TableDataResponse,
    TableListResponse,
    TableInfo,
    DatabaseInfo,
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
    UploadDBResponse,
)
from app.utils.workspace import (
    download_multi_dbs,
    download_db_multi,
    get_object_type,
)
from app.utils.sqlite import (
    list_tables,
    get_table_columns,
    get_table_row_count,
    validate_table_exists,
    get_table_statistics,
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
from app.utils.cache import load_cache_metadata, save_cache_metadata


# Configure module logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_auth_token(
    authorization: str | None = None,
    kbase_session: str | None = None,
    allow_anonymous: bool = False
) -> str:
    """
    Extract auth token from header or cookie.
    
    **User Authentication Required**: Each user must provide their own KBase token.
    The service does NOT use a shared token for production access.
    
    Priority:
    1. Authorization header (Bearer token or plain token)
    2. kbase_session cookie
    3. KB_SERVICE_AUTH_TOKEN from settings (LEGACY: for local testing only)
    
    Args:
        authorization: Authorization header value
        kbase_session: kbase_session cookie value
        allow_anonymous: If True, returns empty string instead of raising 401
        
    Returns:
        Authentication token string
        
    Raises:
        HTTPException: If no token is found and allow_anonymous is False
    """
    # Priority 1: User-provided Authorization header
    if authorization:
        if authorization.startswith("Bearer "):
            return authorization[7:]
        return authorization
    
    # Priority 2: User-provided kbase_session cookie
    if kbase_session:
        return kbase_session
    
    # Priority 3 (LEGACY/TESTING ONLY): Fall back to service token from settings
    # This is kept for local development and testing purposes.
    # In production deployments, users MUST provide their own token.
    if settings.KB_SERVICE_AUTH_TOKEN:
        logger.debug("Using KB_SERVICE_AUTH_TOKEN fallback (legacy/testing mode)")
        return settings.KB_SERVICE_AUTH_TOKEN
    
    # No token found
    if allow_anonymous:
        return ""
    
    raise HTTPException(
        status_code=401,
        detail="Authorization required. Provide your KBase token via the Authorization header or kbase_session cookie."
    )



async def _get_table_metadata(db_path, name, schema_service):
    """
    Helper to fetch metadata for a single table.
    """
    try:
        # Run lightweight checks in thread
        columns = await run_sync_in_thread(get_table_columns, db_path, name)
        row_count = await run_sync_in_thread(get_table_row_count, db_path, name)
        
        display_name = name.replace("_", " ").title()
        
        # Build schema map
        try:
             table_schema = await run_sync_in_thread(
                schema_service.get_table_schema, db_path, name
            )
             schema_map = {col["name"]: col["type"] for col in table_schema["columns"]}
        except Exception:
             schema_map = {col: "TEXT" for col in columns}

        return {
            "name": name,
            "displayName": display_name,
            "row_count": row_count,
            "column_count": len(columns),
            "schema": schema_map
        }
    except Exception:
        logger.warning("Error getting table info for %s", name, exc_info=True)
        return {"name": name, "displayName": name, "error_fallback": True}

def get_cache_dir() -> FilePath:
    """Get configured cache directory."""
    return FilePath(settings.CACHE_DIR)


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
            timestamp=datetime.now(timezone.utc).isoformat(),
            mode="cached_sqlite",
            data_dir=str(settings.CACHE_DIR),
            config_dir=str(FilePath(settings.CACHE_DIR) / "configs"),
            cache={
                "databases_cached": cache_stats.get("total_connections", 0),
                "databases": cache_stats.get("connections", [])
            }
        )
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# =============================================================================
# FILE UPLOAD ENDPOINTS
# =============================================================================

@router.post(
    "/upload",
    tags=["File Upload"],
    response_model=UploadDBResponse,
    summary="Upload a local SQLite database",
    description="""
    Upload a local SQLite database file (.db or .sqlite) for temporary use.
    Returns a handle that can be used inplace of a KBase workspace reference.
    
    The handle format is `local:{uuid}`.
    
    **Note**: Maximum file size is controlled by the `MAX_UPLOAD_SIZE_MB` setting.
    """
)
async def upload_database(
    file: UploadFile = File(..., description="SQLite database file")
):
    try:
        # Check file extension
        if not file.filename or not file.filename.endswith(('.db', '.sqlite', '.sqlite3')):
            raise HTTPException(
                status_code=400, 
                detail="File must be a SQLite database (.db, .sqlite, .sqlite3)"
            )
        
        # Check Content-Length header if available (early rejection for large files)
        max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file.size and file.size > max_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE_MB}MB, got {file.size / (1024*1024):.1f}MB"
            )
        
        # Validate SQLite header
        header = await file.read(16)
        await file.seek(0)
        
        if header != b"SQLite format 3\0":
            logger.warning(f"Invalid SQLite header for upload {file.filename}: {header}")
            raise HTTPException(status_code=400, detail="Invalid SQLite file format (header mismatch)")

        cache_dir = get_cache_dir()
        upload_dir = cache_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Check total upload directory size (Quota)
        try:
            total_uploads_size = sum(f.stat().st_size for f in upload_dir.glob("*.db") if f.is_file())
            max_storage_bytes = settings.MAX_UPLOAD_STORAGE_GB * 1024 * 1024 * 1024
            if total_uploads_size > max_storage_bytes:
                # Trigger cleanup if we're over quota
                from app.utils.cache import cleanup_old_caches
                cleanup_old_caches(cache_dir)
                # Re-check
                total_uploads_size = sum(f.stat().st_size for f in upload_dir.glob("*.db") if f.is_file())
                if total_uploads_size > max_storage_bytes:
                    raise HTTPException(
                        status_code=507, 
                        detail="Upload storage quota exceeded. Please try again later."
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking upload quota: {e}")

        # Stream the file to disk and calculate hash for deduplication
        file_hash = hashlib.sha256()
        temp_file_uuid = str(uuid4())
        temp_destination = upload_dir / f"{temp_file_uuid}.tmp"
        
        try:
            total_size = 0
            chunk_size = 1024 * 1024  # 1MB chunks
            with temp_destination.open("wb") as buffer:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    # Check size during streaming
                    if total_size > max_size_bytes:
                        buffer.close()
                        temp_destination.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE_MB}MB"
                        )
                    buffer.write(chunk)
                    file_hash.update(chunk)
        finally:
            await file.close()
            
        # Deduplication check
        final_hash = file_hash.hexdigest()
        handle = f"local:{final_hash}"
        final_destination = upload_dir / f"{final_hash}.db"
        
        if final_destination.exists():
            # Duplicate found, delete the temp file and return existing handle
            temp_destination.unlink(missing_ok=True)
            logger.info(f"Duplicate upload detected: {final_hash}. Using existing file.")
            return UploadDBResponse(
                handle=handle,
                filename=file.filename,
                size_bytes=final_destination.stat().st_size,
                message="Database already exists (deduplicated)"
            )
        else:
            # Atomic rename from temp to final hash-based name
            temp_destination.rename(final_destination)
            
        return UploadDBResponse(
            handle=handle,
            filename=file.filename,
            size_bytes=final_destination.stat().st_size,
            message="Database uploaded successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# =============================================================================
# OBJECT-BASED ENDPOINTS (via KBase workspace object reference)
# /object/{ws_ref}/tables - List tables from KBase object
# /object/{ws_ref}/tables/{table}/data - Query data
# =============================================================================

@router.get(
    "/object/{ws_ref:path}/tables",
    tags=["Object Access"],
    response_model=TableListResponse,
    summary="List tables in a BERDLTables object",
    description="""
    List all tables available in a BERDLTables object from KBase workspace.
    
    **Example Usage:**
    ```bash
    # Using curl with Authorization header
    curl -X GET \\
      "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables?kb_env=appdev" \\
      -H "Authorization: Bearer YOUR_KBASE_TOKEN" \\
      -H "accept: application/json"
    
    # Using curl with cookie
    curl -X GET \\
      "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables?kb_env=appdev" \\
      -H "Cookie: kbase_session=YOUR_KBASE_TOKEN" \\
      -H "accept: application/json"
    ```
    
    **Authentication:**
    - Authorization header: `Authorization: Bearer YOUR_TOKEN` or `Authorization: YOUR_TOKEN`
    - Cookie: `kbase_session=YOUR_TOKEN`
    - Environment variable: `KB_SERVICE_AUTH_TOKEN` (for service-to-service)
    """,
    responses={
        200: {
            "description": "Successfully retrieved table list",
            "content": {
                "application/json": {
                    "example": {
                        "berdl_table_id": "76990/7/2",
                        "object_type": "KBaseGeneDataLakes.BERDLTables-1.0",
                        "tables": [
                            {
                                "name": "Genes",
                                "displayName": "Genes",
                                "row_count": 3356,
                                "column_count": 18
                            },
                            {
                                "name": "Contigs",
                                "displayName": "Contigs",
                                "row_count": 42,
                                "column_count": 12
                            }
                        ]
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        404: {"description": "Object not found"},
        500: {"description": "Internal server error"}
    }
)
async def list_tables_by_object(
    ws_ref: str = Path(..., description="KBase workspace object reference (UPA format: workspace_id/object_id/version)", examples=["76990/7/2"]),
    kb_env: str = Query("appdev", description="KBase environment", examples=["appdev"]),
    authorization: str | None = Header(None, description="KBase authentication token (Bearer token or plain token)", examples=["Bearer YOUR_KBASE_TOKEN"]),
    kbase_session: str | None = Cookie(None, description="KBase session cookie", examples=["YOUR_KBASE_TOKEN"])
):

    
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
        # Parallelize metadata fetching
        tasks = [
            _get_table_metadata(db_path, name, schema_service) 
            for name in table_names
        ]
        
        results = await asyncio.gather(*tasks)
        
        for res in results:
            if "error_fallback" in res:
                tables.append({"name": res["name"], "displayName": res["displayName"]})
                continue
                
            tables.append({
                "name": res["name"],
                "displayName": res["displayName"],
                "row_count": res["row_count"],
                "column_count": res["column_count"]
            })
            total_rows += res["row_count"] or 0
            schemas[res["name"]] = res["schema"]
        
        # Get object type (with caching)
        object_type = None
        
        # 1. Try to load from cache
        try:
            # db_path is typically .../cache/sanitized_upa/tables.db
            # So cache_subdir is the parent directory
            cache_subdir = db_path.parent
            metadata = load_cache_metadata(cache_subdir)
            
            if metadata and "object_type" in metadata:
                object_type = metadata["object_type"]
                logger.debug(f"Using cached object type for {berdl_table_id}: {object_type}")
        except Exception as e:
            logger.warning(f"Error reading cache metadata: {e}")

        # 2. If not cached, fetch from API
        if not object_type:
            try:
                # Use specific timeout for API call
                object_type = await asyncio.wait_for(
                    run_sync_in_thread(get_object_type, berdl_table_id, token, kb_env),
                    timeout=settings.KBASE_API_TIMEOUT_SECONDS
                )
                
                # 3. Save to cache
                if object_type:
                    try:
                        save_cache_metadata(
                            db_path.parent, 
                            {
                                "berdl_table_id": berdl_table_id,
                                "object_type": object_type,
                                "last_checked": datetime.now(timezone.utc).isoformat()
                            }
                        )
                        logger.info(f"Cached object type for {berdl_table_id}")
                    except Exception as e:
                        logger.warning(f"Failed to cache metadata: {e}")
                        
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


@router.get(
    "/object/{ws_ref:path}/tables/{table_name}/data",
    tags=["Object Access"],
    response_model=TableDataResponse,
    summary="Query table data from a BERDLTables object",
    description="""
    Query data from a specific table in a BERDLTables object with filtering, sorting, and pagination.
    
    **Example Usage:**
    ```bash
    # Get first 10 rows from Genes table
    curl -X GET \\
      "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/data?limit=10&kb_env=appdev" \\
      -H "Authorization: Bearer YOUR_KBASE_TOKEN" \\
      -H "accept: application/json"
    
    # Search and sort
    curl -X GET \\
      "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/data?limit=20&offset=0&search=kinase&sort_column=gene_name&sort_order=ASC&kb_env=appdev" \\
      -H "Authorization: Bearer YOUR_KBASE_TOKEN" \\
      -H "accept: application/json"
    ```
    """,
    responses={
        200: {"description": "Successfully retrieved table data"},
        401: {"description": "Authentication required"},
        404: {"description": "Table not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_table_data_by_object(
    ws_ref: str = Path(..., description="KBase workspace object reference (UPA format)", examples=["76990/7/2"]),
    table_name: str = Path(..., description="Name of the table to query", examples=["Genes"]),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Maximum number of rows to return", examples=[10]),
    offset: int = Query(0, ge=0, description="Number of rows to skip (for pagination)", examples=[0]),
    sort_column: str | None = Query(None, description="Column name to sort by", examples=["gene_name"]),
    sort_order: str | None = Query("ASC", description="Sort order: ASC or DESC", examples=["ASC"]),
    search: str | None = Query(None, description="Global text search across all columns", examples=["kinase"]),
    kb_env: str = Query("appdev", description="KBase environment", examples=["appdev"]),
    authorization: str | None = Header(None, description="KBase authentication token", examples=["Bearer YOUR_KBASE_TOKEN"]),
    kbase_session: str | None = Cookie(None, description="KBase session cookie", examples=["YOUR_KBASE_TOKEN"])
):
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
        raise
    except Exception as e:
        logger.error(f"Error querying data: {e}", exc_info=True)
        error_detail = str(e) if str(e) else f"Error: {type(e).__name__}"
        if settings.DEBUG:
            error_detail += f"\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


@router.get(
    "/object/{ws_ref:path}/tables/{table_name}/stats",
    tags=["Object Access"],
    response_model=TableStatisticsResponse,
    summary="Get column statistics for a table",
    description="""
    Calculate statistics for all columns in a table (null counts, distinct counts, min/max, samples).
    This operation may be slow for large tables.
    """
)
async def get_table_stats(
    ws_ref: str = Path(..., description="KBase workspace object reference (UPA format)", examples=["76990/7/2"]),
    table_name: str = Path(..., description="Name of the table to analyze", examples=["Genes"]),
    kb_env: str = Query("appdev", description="KBase environment", examples=["appdev"]),
    authorization: str | None = Header(None, description="KBase authentication token", examples=["Bearer YOUR_KBASE_TOKEN"]),
    kbase_session: str | None = Cookie(None, description="KBase session cookie", examples=["YOUR_KBASE_TOKEN"])
):
    try:
        token = get_auth_token(authorization, kbase_session)
        cache_dir = get_cache_dir()
        berdl_table_id = ws_ref
        
        # Get and validate DB access
        db_path = await get_object_db_path(berdl_table_id, token, kb_env, cache_dir)
        await ensure_table_accessible(db_path, table_name)
        
        # Helper to run stats calculation in thread (CPU bound)
        # from app.utils.sqlite import get_table_statistics
        
        stats = await run_sync_in_thread(get_table_statistics, db_path, table_name)
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating stats: {e}", exc_info=True)
        error_detail = str(e) if str(e) else f"Error: {type(e).__name__}"
        if settings.DEBUG:
            error_detail += f"\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


# =============================================================================
# MULTI-DATABASE ENDPOINTS (Query-parameter routing)
# GET /databases?upa=... - List all databases in an object
# GET /db/{db_name}/tables?upa=... - List tables in a specific database
# GET /db/{db_name}/tables/{table}/data?upa=... - Query data from specific DB
# =============================================================================

@router.get(
    "/databases",
    tags=["Multi-Database"],
    response_model=TableListResponse,
    summary="List all databases in a workspace object",
    description="""
    List all databases available in a BERDLTables object.
    
    For multi-pangenome objects, this returns information about each database
    including its name, display name, and table list.
    
    **New in v2.1**: Supports objects with multiple pangenomes.
    
    **Note**: Use the `upa` query parameter to specify the workspace object reference.
    """,
    responses={
        200: {"description": "Successfully retrieved database list"},
        401: {"description": "Authentication required"},
        404: {"description": "Object not found"},
        500: {"description": "Internal server error"}
    }
)
async def list_databases_in_object(
    upa: str = Query(..., description="KBase workspace object reference (UPA format)", examples=["76990/7/2", "76990/Test2"]),
    kb_env: str = Query("appdev", description="KBase environment", examples=["appdev"]),
    authorization: str | None = Header(None, description="KBase authentication token"),
    kbase_session: str | None = Cookie(None, description="KBase session cookie")
):
    """List all databases within a workspace object."""
    logger.info(f"[list_databases_in_object] Starting for UPA={upa}, kb_env={kb_env}")
    try:
        token = get_auth_token(authorization, kbase_session)
        logger.info(f"[list_databases_in_object] Got token, length={len(token) if token else 0}")
        cache_dir = get_cache_dir()
        berdl_table_id = upa
        logger.info(f"[list_databases_in_object] About to call download_multi_dbs for {berdl_table_id}")
        
        # Download all databases from the object
        db_infos = await run_sync_in_thread(
            download_multi_dbs, berdl_table_id, token, cache_dir, kb_env
        )
        
        schema_service = get_schema_service()
        databases = []
        all_tables = []
        total_rows = 0
        
        for db_info in db_infos:
            db_path = db_info["db_path"]
            db_name = db_info["db_name"]
            db_display_name = db_info["db_display_name"]
            
            # List tables for this database
            table_names = await run_sync_in_thread(list_tables, db_path)
            
            # Get metadata for each table
            tasks = [
                _get_table_metadata(db_path, name, schema_service)
                for name in table_names
            ]
            results = await asyncio.gather(*tasks)
            
            db_tables = []
            db_schemas = {}
            db_total_rows = 0
            
            for res in results:
                if "error_fallback" in res:
                    db_tables.append(TableInfo(name=res["name"], row_count=None, column_count=None))
                    continue
                    
                db_tables.append(TableInfo(
                    name=res["name"],
                    row_count=res["row_count"],
                    column_count=res["column_count"]
                ))
                db_total_rows += res["row_count"] or 0
                db_schemas[res["name"]] = res["schema"]
                all_tables.append(TableInfo(
                    name=f"{db_name}/{res['name']}",  # Prefixed with db_name for disambiguation
                    row_count=res["row_count"],
                    column_count=res["column_count"]
                ))
            
            total_rows += db_total_rows
            databases.append(DatabaseInfo(
                db_name=db_name,
                db_display_name=db_display_name,
                tables=db_tables,
                row_count=db_total_rows,
                schemas=db_schemas
            ))
        
        # Get object type
        object_type = None
        try:
            object_type = await asyncio.wait_for(
                run_sync_in_thread(get_object_type, berdl_table_id, token, kb_env),
                timeout=settings.KBASE_API_TIMEOUT_SECONDS
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Could not get object type: {e}")
        
        return TableListResponse(
            berdl_table_id=berdl_table_id,
            object_type=object_type or "BERDLTables",
            tables=all_tables,  # Flattened list for backward compat
            databases=databases,
            has_multiple_databases=len(databases) > 1,
            total_rows=total_rows,
            source="Downloaded",
            api_version="2.1"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing databases: {e}", exc_info=True)
        error_detail = str(e) if str(e) else f"Error: {type(e).__name__}"
        if settings.DEBUG:
            error_detail += f"\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


@router.get(
    "/db/{db_name}/tables",
    tags=["Multi-Database"],
    response_model=TableListResponse,
    summary="List tables in a specific database",
    description="""
    List all tables in a specific database within a multi-database object.
    
    Use this endpoint when working with objects containing multiple pangenomes.
    The db_name should match one of the database names returned by /databases endpoint.
    
    **Note**: Use the `upa` query parameter to specify the workspace object reference.
    """,
    responses={
        200: {"description": "Successfully retrieved table list"},
        401: {"description": "Authentication required"},
        404: {"description": "Database not found"},
        500: {"description": "Internal server error"}
    }
)
async def list_tables_in_database(
    db_name: str = Path(..., description="Database name within the object", examples=["pg_ecoli_k12", "GCF_000368685.1"]),
    upa: str = Query(..., description="KBase workspace object reference (UPA format)", examples=["76990/7/2", "76990/Test2"]),
    kb_env: str = Query("appdev", description="KBase environment"),
    authorization: str | None = Header(None, description="KBase authentication token"),
    kbase_session: str | None = Cookie(None, description="KBase session cookie")
):
    """List tables in a specific database within an object."""
    try:
        token = get_auth_token(authorization, kbase_session)
        cache_dir = get_cache_dir()
        berdl_table_id = upa
        
        # Download ONLY the requested database (or use cache)
        try:
            target_db = await run_sync_in_thread(
                download_db_multi, berdl_table_id, db_name, token, cache_dir, kb_env
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        db_path = target_db["db_path"]
        schema_service = get_schema_service()
        
        # List and process tables
        table_names = await run_sync_in_thread(list_tables, db_path)
        tasks = [
            _get_table_metadata(db_path, name, schema_service)
            for name in table_names
        ]
        results = await asyncio.gather(*tasks)
        
        tables = []
        schemas = {}
        total_rows = 0
        
        for res in results:
            if "error_fallback" in res:
                tables.append(TableInfo(name=res["name"], row_count=None, column_count=None))
                continue
                
            tables.append(TableInfo(
                name=res["name"],
                row_count=res["row_count"],
                column_count=res["column_count"]
            ))
            total_rows += res["row_count"] or 0
            schemas[res["name"]] = res["schema"]
        
        return TableListResponse(
            berdl_table_id=f"{berdl_table_id}/{db_name}",
            object_type="BERDLTables",
            tables=tables,
            schemas=schemas,
            total_rows=total_rows,
            source="Cache" if target_db.get("was_cached") else "Downloaded",
            api_version="2.1"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tables in database: {e}", exc_info=True)
        error_detail = str(e) if str(e) else f"Error: {type(e).__name__}"
        if settings.DEBUG:
            error_detail += f"\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


@router.get(
    "/db/{db_name}/tables/{table_name}/data",
    tags=["Multi-Database"],
    response_model=TableDataResponse,
    summary="Query data from a specific database",
    description="""
    Query table data from a specific database within a multi-database object.
    
    This is the recommended endpoint for multi-pangenome objects as it
    explicitly specifies which database to query.
    
    **Note**: Use the `upa` query parameter to specify the workspace object reference.
    """,
    responses={
        200: {"description": "Successfully retrieved table data"},
        401: {"description": "Authentication required"},
        404: {"description": "Database or table not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_table_data_from_database(
    db_name: str = Path(..., description="Database name within the object", examples=["pg_ecoli_k12", "GCF_000368685.1"]),
    table_name: str = Path(..., description="Name of the table to query", examples=["Genes"]),
    upa: str = Query(..., description="KBase workspace object reference (UPA format)", examples=["76990/7/2", "76990/Test2"]),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Maximum rows to return"),
    offset: int = Query(0, ge=0, description="Number of rows to skip"),
    sort_column: str | None = Query(None, description="Column to sort by"),
    sort_order: str | None = Query("ASC", description="Sort order: ASC or DESC"),
    search: str | None = Query(None, description="Global text search"),
    kb_env: str = Query("appdev", description="KBase environment"),
    authorization: str | None = Header(None, description="KBase authentication token"),
    kbase_session: str | None = Cookie(None, description="KBase session cookie")
):
    """Query data from a specific table in a specific database."""
    try:
        token = get_auth_token(authorization, kbase_session)
        cache_dir = get_cache_dir()
        berdl_table_id = upa
        
        # Download ONLY the requested database (or use cache)
        try:
            target_db = await run_sync_in_thread(
                download_db_multi, berdl_table_id, db_name, token, cache_dir, kb_env
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        db_path = target_db["db_path"]
        
        # Validate table exists
        await ensure_table_accessible(db_path, table_name)
        
        result = await TableRequestProcessor.process_data_request(
            db_path=db_path,
            table_name=table_name,
            limit=limit,
            offset=offset,
            sort_column=sort_column,
            sort_order=sort_order or "ASC",
            search_value=search,
            handle_ref_or_id=f"{berdl_table_id}/{db_name}"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying data from database: {e}", exc_info=True)
        error_detail = str(e) if str(e) else f"Error: {type(e).__name__}"
        if settings.DEBUG:
            error_detail += f"\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


# =============================================================================
# DATA ACCESS ENDPOINTS
# =============================================================================

@router.post(
    "/table-data",
    response_model=TableDataResponse,
    tags=["Data Access"],
    summary="Query table data with advanced filtering (POST)",
    description="""
    Query table data using a JSON request body. Recommended for complex queries with multiple filters.
    
    **Example Usage:**
    ```bash
    # Simple query
    curl -X POST \\
      "https://appdev.kbase.us/services/berdl_table_scanner/table-data" \\
      -H "Authorization: Bearer YOUR_KBASE_TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{
        "berdl_table_id": "76990/7/2",
        "table_name": "Genes",
        "limit": 10,
        "offset": 0
      }'
    
    # Query with filters
    curl -X POST \\
      "https://appdev.kbase.us/services/berdl_table_scanner/table-data" \\
      -H "Authorization: Bearer YOUR_KBASE_TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{
        "berdl_table_id": "76990/7/2",
        "table_name": "Genes",
        "limit": 20,
        "query_filters": [
          {"column": "gene_name", "operator": "like", "value": "kinase"},
          {"column": "contigs", "operator": "gt", "value": 5}
        ],
        "sort": [{"column": "gene_name", "direction": "asc"}]
      }'
    ```
    """,
    responses={
        200: {"description": "Successfully retrieved table data"},
        401: {"description": "Authentication required"},
        404: {"description": "Table not found"},
        500: {"description": "Internal server error"}
    }
)
async def query_table_data(
    request: TableDataRequest,
    authorization: str | None = Header(None, description="KBase authentication token", examples=["Bearer YOUR_KBASE_TOKEN"]),
    kbase_session: str | None = Cookie(None, description="KBase session cookie", examples=["YOUR_KBASE_TOKEN"])
):
    try:
        token = get_auth_token(authorization, kbase_session)
        cache_dir = get_cache_dir()
        kb_env = getattr(request, 'kb_env', 'appdev') or 'appdev'
        
        filters = request.col_filter if request.col_filter else request.query_filters
        
        # Get and validate DB access (uses generic helper that supports local:)
        db_path = await get_object_db_path(request.berdl_table_id, token, kb_env, cache_dir)
        
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
    except InvalidFilterError:
        # Allow invalid filter errors to be handled by main app exception handler (422)
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

