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


import time
import logging
from pathlib import Path
from uuid import uuid4
from app.utils.workspace import KBaseClient

from fastapi import APIRouter, HTTPException, Header, Query

from app.models import (
    TableDataRequest,
    TableDataResponse,
    PangenomesResponse,
    PangenomeInfo,
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
    list_pangenomes_from_object,
    download_pangenome_db,
    get_object_type,
)
from app.utils.sqlite import (
    list_tables,
    get_table_data,
    get_table_columns,
    get_table_row_count,
    validate_table_exists,
    ensure_indices,
)
from app.services.data.query_service import (
    get_query_service,
    FilterSpec,
    AggregationSpec,
)
from app.services.data.schema_service import get_schema_service
from app.services.data.statistics_service import get_statistics_service
from app.services.data.connection_pool import get_connection_pool
from app.utils.cache import (
    is_cached,
    clear_cache,
    list_cached_items,
)
from app.config import settings

# Configure module logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_auth_token(authorization: str | None = None) -> str:
    """Extract auth token from header or settings."""
    if authorization:
        if authorization.startswith("Bearer "):
            return authorization[7:]
        return authorization
    
    if settings.KB_SERVICE_AUTH_TOKEN:
        return settings.KB_SERVICE_AUTH_TOKEN
    
    raise HTTPException(
        status_code=401,
        detail="Authorization token required"
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
    
    **Example:**
    ```bash
    curl "http://127.0.0.1:8000/health"
    ```
    """
    from datetime import datetime
    
    try:
        pool = get_connection_pool()
        cache_stats = pool.get_stats()
        
        return HealthResponse(
            status="ok",
            timestamp=datetime.utcnow().isoformat() + "Z",
            mode="cached_sqlite",
            data_dir=str(settings.CACHE_DIR),
            config_dir=str(Path(settings.CACHE_DIR) / "configs"),
            cache={
                "databases_cached": cache_stats["total_connections"],
                "databases": cache_stats["connections"]
            }
        )
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HANDLE-BASED ENDPOINTS (Primary REST API per diagram)
# /{handle_ref}/tables - List tables
# /{handle_ref}/tables/{table}/schema - Table schema
# /{handle_ref}/tables/{table}/data - Table data with pagination
# =============================================================================

@router.get("/handle/{handle_ref}/tables", tags=["Handle Access"], response_model=TableListResponse)
async def list_tables_by_handle(
    handle_ref: str,
    kb_env: str = Query("appdev", description="KBase environment"),
    authorization: str | None = Header(None)
):
    """
    List all tables in a SQLite database accessed via handle reference.
    
    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \
         "https://appdev.kbase.us/services/berdl_table_scanner/handle/KBH_248028/tables"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        # Download SQLite from handle
        client = KBaseClient(token, kb_env, cache_dir)
        
        # Cache path based on handle
        safe_handle = handle_ref.replace(":", "_").replace("/", "_")
        db_dir = cache_dir / "handles"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"{safe_handle}.db"
        
        # Atomic download to prevent race conditions
        if not db_path.exists():
            temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                client.download_blob_file(handle_ref, temp_path)
                temp_path.rename(db_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
        
        # List tables
        table_names = list_tables(db_path)
        tables = []
        for name in table_names:
            try:
                columns = get_table_columns(db_path, name)
                row_count = get_table_row_count(db_path, name)
                tables.append({
                    "name": name,
                    "row_count": row_count,
                    "column_count": len(columns)
                })
            except Exception as e:
                logger.warning("Error getting table info for %s", name, exc_info=True)
                tables.append({"name": name})
        
        return {
            "handle_ref": handle_ref,
            "tables": tables,
            "db_path": str(db_path)
        }
        
    except Exception as e:
        logger.error(f"Error listing tables from handle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/handle/{handle_ref}/tables/{table_name}/schema", tags=["Handle Access"], response_model=TableSchemaResponse)
async def get_table_schema_by_handle(
    handle_ref: str,
    table_name: str,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Get schema (columns) for a table accessed via handle reference.

    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \
         "https://appdev.kbase.us/services/berdl_table_scanner/handle/KBH_248028/tables/Genes/schema"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        client = KBaseClient(token, kb_env, cache_dir)
        
        safe_handle = handle_ref.replace(":", "_").replace("/", "_")
        db_dir = cache_dir / "handles"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"{safe_handle}.db"
        
        if not db_path.exists():
            temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                client.download_blob_file(handle_ref, temp_path)
                temp_path.rename(db_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
        
        if not validate_table_exists(db_path, table_name):
            available = list_tables(db_path)
            raise HTTPException(404, f"Table '{table_name}' not found. Available: {available}")
        
        columns = get_table_columns(db_path, table_name)
        row_count = get_table_row_count(db_path, table_name)
        
        return {
            "handle_ref": handle_ref,
            "table_name": table_name,
            "columns": columns,
            "row_count": row_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/handle/{handle_ref}/tables/{table_name}/data", tags=["Handle Access"], response_model=TableDataResponse)
async def get_table_data_by_handle(
    handle_ref: str,
    table_name: str,
    limit: int = Query(100, ge=1, le=500000),
    offset: int = Query(0, ge=0),
    sort_column: str | None = Query(None),
    sort_order: str | None = Query("ASC"),
    search: str | None = Query(None, description="Global search term"),
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Query table data from SQLite via handle reference.
    
    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \
         "https://appdev.kbase.us/services/berdl_table_scanner/handle/KBH_248028/tables/Genes/data?limit=5"
    ```
    """
    start_time = time.time()
    
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        client = KBaseClient(token, kb_env, cache_dir)
        
        safe_handle = handle_ref.replace(":", "_").replace("/", "_")
        db_dir = cache_dir / "handles"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"{safe_handle}.db"
        
        if not db_path.exists():
            temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                client.download_blob_file(handle_ref, temp_path)
                temp_path.rename(db_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
        
        if not validate_table_exists(db_path, table_name):
            available = list_tables(db_path)
            raise HTTPException(404, f"Table '{table_name}' not found. Available: {available}")
        
        # Query data
        headers, data, total_count, filtered_count, db_query_ms, conversion_ms = get_table_data(
            sqlite_file=db_path,
            table_name=table_name,
            limit=limit,
            offset=offset,
            sort_column=sort_column,
            sort_order=sort_order,
            search_value=search,
        )
        
        response_time_ms = (time.time() - start_time) * 1000
        
        return {
            "handle_ref": handle_ref,
            "table_name": table_name,
            "headers": headers,
            "data": data,
            "row_count": len(data),
            "total_count": total_count,
            "filtered_count": filtered_count,
            "response_time_ms": response_time_ms,
            "db_query_ms": db_query_ms
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# OBJECT-BASED ENDPOINTS (via KBase workspace object reference)
# /object/{ws_ref}/pangenomes - List pangenomes from BERDLTables object
# /object/{ws_ref}/pangenomes/{pg_id}/tables - List tables for a pangenome
# /object/{ws_ref}/pangenomes/{pg_id}/tables/{table}/data - Query data
# =============================================================================

@router.get("/object/{ws_ref:path}/pangenomes", tags=["Object Access"], response_model=PangenomesResponse)
async def list_pangenomes_by_object(
    ws_ref: str,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    List pangenomes from a BERDLTables/GenomeDataLakeTables object.

    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \
         "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/pangenomes"
    ```
    """
    try:
        token = get_auth_token(authorization)
        berdl_table_id = ws_ref
        
        pangenomes = list_pangenomes_from_object(
            berdl_table_id=berdl_table_id,
            auth_token=token,
            kb_env=kb_env
        )
        
        return {
            "berdl_table_id": berdl_table_id,
            "pangenomes": pangenomes
        }
        
    except Exception as e:
        logger.error(f"Error listing pangenomes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/object/{ws_ref:path}/tables", tags=["Object Access"], response_model=TableListResponse)
async def list_tables_by_object(
    ws_ref: str,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    List tables for a BERDLTables object.
    
    Returns table list along with viewer config info (fingerprint/URL if cached).
    Compatible with DataTables Viewer API format.

    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \\
         "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        berdl_table_id = ws_ref
        
        db_path = download_pangenome_db(
            berdl_table_id=berdl_table_id,
            auth_token=token,
            cache_dir=cache_dir,
            kb_env=kb_env
        )
        
        table_names = list_tables(db_path)
        tables = []
        schemas = {}
        total_rows = 0
        
        # Use schema service for better column type information
        schema_service = get_schema_service()
        
        for name in table_names:
            try:
                columns = get_table_columns(db_path, name)
                row_count = get_table_row_count(db_path, name)
                
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
                    table_schema = schema_service.get_table_schema(db_path, name)
                    schemas[name] = {
                        col["name"]: col["type"]
                        for col in table_schema["columns"]
                    }
                except Exception:
                    # Fallback to default type
                    schemas[name] = {col: "TEXT" for col in columns}
            except Exception as e:
                logger.warning("Error getting table info for %s", name, exc_info=True)
                tables.append({"name": name, "displayName": name})
        
        # Get object type
        try:
            object_type = get_object_type(berdl_table_id, token, kb_env)
        except Exception:
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
        except Exception:
            pass
        
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
        
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/object/{ws_ref:path}/tables/{table_name}/data", tags=["Object Access"], response_model=TableDataResponse)
async def get_table_data_by_object(
    ws_ref: str,
    table_name: str,
    limit: int = Query(100, ge=1, le=500000),
    offset: int = Query(0, ge=0),
    sort_column: str | None = Query(None),
    sort_order: str | None = Query("ASC"),
    search: str | None = Query(None),
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Query table data from a BERDLTables object.

    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \
         "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/data?limit=5"
    ```
    """
    start_time = time.time()
    
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        berdl_table_id = ws_ref
        
        db_path = download_pangenome_db(
            berdl_table_id=berdl_table_id,
            auth_token=token,
            cache_dir=cache_dir,
            kb_env=kb_env
        )
        
        if not validate_table_exists(db_path, table_name):
            available = list_tables(db_path)
            raise HTTPException(404, f"Table '{table_name}' not found. Available: {available}")
        
        headers, data, total_count, filtered_count, db_query_ms, conversion_ms = get_table_data(
            sqlite_file=db_path,
            table_name=table_name,
            limit=limit,
            offset=offset,
            sort_column=sort_column,
            sort_order=sort_order,
            search_value=search,
        )
        
        response_time_ms = (time.time() - start_time) * 1000
        
        # Get object type
        try:
            object_type = get_object_type(berdl_table_id, token, kb_env)
        except Exception:
            object_type = None
        
        return {
            "berdl_table_id": berdl_table_id,
            "table_name": table_name,
            "headers": headers,
            "data": data,
            "row_count": len(data),
            "total_count": total_count,
            "filtered_count": filtered_count,
            "response_time_ms": response_time_ms,
            "db_query_ms": db_query_ms,
            "sqlite_file": str(db_path),
            "object_type": object_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# LEGACY ENDPOINTS (for backwards compatibility)
# =============================================================================

@router.get("/pangenomes", response_model=PangenomesResponse, tags=["Legacy"])
async def get_pangenomes(
    berdl_table_id: str = Query(..., description="BERDLTables object reference"),
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    List pangenomes from BERDLTables object.
    
    Returns:
        - pangenomes: List of pangenome info
        - pangenome_count: Total number of pangenomes
    """
    try:
        token = get_auth_token(authorization)
        
        # Support comma-separated list of IDs
        berdl_ids = [bid.strip() for bid in berdl_table_id.split(",") if bid.strip()]
        
        all_pangenomes: list[dict] = []
        
        for bid in berdl_ids:
            try:
                pangenomes = list_pangenomes_from_object(bid, token, kb_env)
                # Tag each pangenome with its source ID
                for pg in pangenomes:
                    pg["source_berdl_id"] = bid
                all_pangenomes.extend(pangenomes)
            except Exception as e:
                logger.error(f"Error fetching pangenomes for {bid}: {e}")
                # Continue fetching others even if one fails
                continue
                
        pangenome_list = [PangenomeInfo(**pg) for pg in all_pangenomes]
        
        return PangenomesResponse(
            pangenomes=pangenome_list,
            pangenome_count=len(pangenome_list)
        )
    except Exception as e:
        logger.error(f"Error in get_pangenomes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables", response_model=TableListResponse, tags=["Legacy"])
async def get_tables(
    berdl_table_id: str = Query(..., description="BERDLTables object reference"),
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """List tables for a BERDLTable object (auto-resolves pangenome)."""
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        db_path = download_pangenome_db(berdl_table_id, token, cache_dir, kb_env)
        table_names = list_tables(db_path)
        
        tables = []
        for name in table_names:
            try:
                columns = get_table_columns(db_path, name)
                row_count = get_table_row_count(db_path, name)
                tables.append(TableInfo(name=name, row_count=row_count, column_count=len(columns)))
            except Exception:
                tables.append(TableInfo(name=name))
        
        return TableListResponse(tables=tables)
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/table-data", response_model=TableDataResponse, tags=["Legacy"])
async def query_table_data(
    request: TableDataRequest,
    authorization: str | None = Header(None)
):
    """
    Query table data using a JSON body. Recommended for programmatic access.

    **Example:**
    ```bash
    curl -X POST -H "Authorization: $KB_TOKEN" -H "Content-Type: application/json" \
         -d '{
               "berdl_table_id": "76990/7/2",
               "table_name": "Metadata_Conditions",
               "limit": 5"
             }' \
         "https://appdev.kbase.us/services/berdl_table_scanner/table-data"
    ```
    """
    start_time = time.time()
    
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        kb_env = getattr(request, 'kb_env', 'appdev') or 'appdev'
        
        # Determine filters (support both query_filters and col_filter)
        filters = request.col_filter if request.col_filter else request.query_filters
        
        # Download (or get cached) DB - auto-resolves ID if None
        try:
            db_path = download_pangenome_db(
                request.berdl_table_id, token, cache_dir, kb_env
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        
        if not validate_table_exists(db_path, request.table_name):
            available = list_tables(db_path)
            raise ValueError(f"Table '{request.table_name}' not found. Available: {available}")
        
        try:
            ensure_indices(db_path, request.table_name)
        except:
            pass
        
        headers, data, total_count, filtered_count, db_query_ms, conversion_ms = get_table_data(
            sqlite_file=db_path,
            table_name=request.table_name,
            limit=request.limit,
            offset=request.offset,
            sort_column=request.sort_column,
            sort_order=request.sort_order,
            search_value=request.search_value,
            query_filters=filters,
            columns=request.columns,
            order_by=request.order_by
        )
        
        response_time_ms = (time.time() - start_time) * 1000
        
        return TableDataResponse(
            headers=headers,
            data=data,
            row_count=len(data),
            total_count=total_count,
            filtered_count=filtered_count,
            table_name=request.table_name,
            response_time_ms=response_time_ms,
            db_query_ms=db_query_ms,
            conversion_ms=conversion_ms,
            source="Cache" if is_cached(db_path) else "Downloaded",
            cache_file=str(db_path),
            sqlite_file=str(db_path)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying table data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# CACHE MANAGEMENT
# =============================================================================

@router.post("/clear-cache", response_model=CacheResponse, tags=["Cache Management"])
async def clear_pangenome_cache(
    berdl_table_id: str | None = Query(None)
):
    """Clear cached databases."""
    try:
        cache_dir = get_cache_dir()
        result = clear_cache(cache_dir, berdl_table_id)
        return CacheResponse(status="success", message=result.get("message", "Cache cleared"))
    except Exception as e:
        return CacheResponse(status="error", message=str(e))


@router.get("/cache", tags=["Cache Management"])
async def list_cache():
    """List cached items."""
    cache_dir = get_cache_dir()
    items = list_cached_items(cache_dir)
    return {"cache_dir": str(cache_dir), "items": items, "total": len(items)}




# =============================================================================
# DATATABLES VIEWER API ENDPOINTS
# =============================================================================


@router.get("/schema/{db_name}/tables/{table_name}", response_model=TableSchemaInfo, tags=["Object Access"])
async def get_table_schema_datatables(
    db_name: str,
    table_name: str,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Get table schema information for DataTables Viewer API.
    
    Returns column types, constraints, and indexes.
    
    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \
         "http://127.0.0.1:8000/schema/local/76990_7_2/tables/Genes"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        # Parse db_name (format: local/db_name or handle/KBH_xxx)
        if db_name.startswith("local/"):
            # Object-based database
            berdl_table_id = db_name.replace("local/", "")
            db_path = download_pangenome_db(
                berdl_table_id=berdl_table_id,
                auth_token=token,
                cache_dir=cache_dir,
                kb_env=kb_env
            )
        elif db_name.startswith("handle/"):
            # Handle-based database
            handle_ref = db_name.replace("handle/", "")
            client = KBaseClient(token, kb_env, cache_dir)
            safe_handle = handle_ref.replace(":", "_").replace("/", "_")
            db_dir = cache_dir / "handles"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / f"{safe_handle}.db"
            
            if not db_path.exists():
                temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
                try:
                    client.download_blob_file(handle_ref, temp_path)
                    temp_path.rename(db_path)
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise
        else:
            raise HTTPException(status_code=400, detail=f"Invalid db_name format: {db_name}")
        
        if not validate_table_exists(db_path, table_name):
            available = list_tables(db_path)
            raise HTTPException(404, f"Table '{table_name}' not found. Available: {available}")
        
        schema_service = get_schema_service()
        schema = schema_service.get_table_schema(db_path, table_name)
        
        return schema
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema/{db_name}/tables", tags=["Object Access"])
async def get_all_tables_schema_datatables(
    db_name: str,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Get schema information for all tables in a database.
    
    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \
         "http://127.0.0.1:8000/schema/local/76990_7_2/tables"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        # Parse db_name (same logic as single table endpoint)
        if db_name.startswith("local/"):
            berdl_table_id = db_name.replace("local/", "")
            db_path = download_pangenome_db(
                berdl_table_id=berdl_table_id,
                auth_token=token,
                cache_dir=cache_dir,
                kb_env=kb_env
            )
        elif db_name.startswith("handle/"):
            handle_ref = db_name.replace("handle/", "")
            client = KBaseClient(token, kb_env, cache_dir)
            safe_handle = handle_ref.replace(":", "_").replace("/", "_")
            db_dir = cache_dir / "handles"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / f"{safe_handle}.db"
            
            if not db_path.exists():
                temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
                try:
                    client.download_blob_file(handle_ref, temp_path)
                    temp_path.rename(db_path)
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise
        else:
            raise HTTPException(status_code=400, detail=f"Invalid db_name format: {db_name}")
        
        schema_service = get_schema_service()
        schemas = schema_service.get_all_tables_schema(db_path)
        
        return schemas
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting all schemas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/object/{db_name}/tables/{table_name}/stats", response_model=TableStatisticsResponse, tags=["Object Access"])
async def get_table_statistics(
    db_name: str,
    table_name: str,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Get column statistics for a table.
    
    Returns pre-computed statistics including null_count, distinct_count,
    min, max, mean, median, stddev, and sample values.
    
    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \
         "http://127.0.0.1:8000/object/local/76990_7_2/tables/Genes/stats"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        # Parse db_name
        if db_name.startswith("local/"):
            berdl_table_id = db_name.replace("local/", "")
            db_path = download_pangenome_db(
                berdl_table_id=berdl_table_id,
                auth_token=token,
                cache_dir=cache_dir,
                kb_env=kb_env
            )
        elif db_name.startswith("handle/"):
            handle_ref = db_name.replace("handle/", "")
            client = KBaseClient(token, kb_env, cache_dir)
            safe_handle = handle_ref.replace(":", "_").replace("/", "_")
            db_dir = cache_dir / "handles"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / f"{safe_handle}.db"
            
            if not db_path.exists():
                temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
                try:
                    client.download_blob_file(handle_ref, temp_path)
                    temp_path.rename(db_path)
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise
        else:
            # Try as berdl_table_id directly
            db_path = download_pangenome_db(
                berdl_table_id=db_name,
                auth_token=token,
                cache_dir=cache_dir,
                kb_env=kb_env
            )
        
        if not validate_table_exists(db_path, table_name):
            available = list_tables(db_path)
            raise HTTPException(404, f"Table '{table_name}' not found. Available: {available}")
        
        stats_service = get_statistics_service()
        stats = stats_service.get_table_statistics(db_path, table_name)
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/aggregate/{db_name}/tables/{table_name}", response_model=TableDataQueryResponse, tags=["Object Access"])
async def execute_aggregation(
    db_name: str,
    table_name: str,
    request: AggregationQueryRequest,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Execute aggregation query with GROUP BY.
    
    **Example:**
    ```bash
    curl -X POST -H "Authorization: $KB_TOKEN" -H "Content-Type: application/json" \
         -d '{
               "group_by": ["category"],
               "aggregations": [
                 {"column": "value", "function": "sum", "alias": "total"}
               ],
               "filters": [{"column": "value", "operator": "gt", "value": 100}]
             }' \
         "http://127.0.0.1:8000/api/aggregate/local/76990_7_2/tables/Data"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        # Parse db_name
        if db_name.startswith("local/"):
            berdl_table_id = db_name.replace("local/", "")
            db_path = download_pangenome_db(
                berdl_table_id=berdl_table_id,
                auth_token=token,
                cache_dir=cache_dir,
                kb_env=kb_env
            )
        elif db_name.startswith("handle/"):
            handle_ref = db_name.replace("handle/", "")
            client = KBaseClient(token, kb_env, cache_dir)
            safe_handle = handle_ref.replace(":", "_").replace("/", "_")
            db_dir = cache_dir / "handles"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / f"{safe_handle}.db"
            
            if not db_path.exists():
                temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
                try:
                    client.download_blob_file(handle_ref, temp_path)
                    temp_path.rename(db_path)
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise
        else:
            # Try as berdl_table_id directly
            db_path = download_pangenome_db(
                berdl_table_id=db_name,
                auth_token=token,
                cache_dir=cache_dir,
                kb_env=kb_env
            )
        
        if not validate_table_exists(db_path, table_name):
            available = list_tables(db_path)
            raise HTTPException(404, f"Table '{table_name}' not found. Available: {available}")
        
        # Convert request to query service format
        query_service = get_query_service()
        
        filters = None
        if request.filters:
            filters = [
                FilterSpec(
                    column=f.column,
                    operator=f.operator,
                    value=f.value,
                    value2=f.value2
                )
                for f in request.filters
            ]
        
        aggregations = [
            AggregationSpec(
                column=a.column,
                function=a.function,
                alias=a.alias
            )
            for a in request.aggregations
        ]
        
        result = query_service.execute_query(
            db_path=db_path,
            table_name=table_name,
            limit=request.limit,
            offset=request.offset,
            filters=filters,
            aggregations=aggregations,
            group_by=request.group_by
        )
        
        return TableDataQueryResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing aggregation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/table-data", response_model=TableDataQueryResponse, tags=["Legacy"])
async def query_table_data_enhanced(
    request: TableDataQueryRequest,
    authorization: str | None = Header(None)
):
    """
    Enhanced table data query endpoint with full DataTables Viewer API support.
    
    Supports type-aware filtering, aggregations, and comprehensive metadata.
    
    **Example:**
    ```bash
    curl -X POST -H "Authorization: $KB_TOKEN" -H "Content-Type: application/json" \
         -d '{
               "berdl_table_id": "local/76990_7_2",
               "table_name": "Genes",
               "limit": 100,
               "offset": 0,
               "filters": [
                 {"column": "contigs", "operator": "gt", "value": "50"}
               ]
             }' \
         "http://127.0.0.1:8000/table-data"
    ```
    """
    start_time = time.time()
    
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        kb_env = "appdev"  # Default, could be from request
        
        # Parse berdl_table_id
        if request.berdl_table_id.startswith("local/"):
            berdl_table_id = request.berdl_table_id.replace("local/", "")
        else:
            berdl_table_id = request.berdl_table_id
        
        # Download (or get cached) DB
        try:
            db_path = download_pangenome_db(
                berdl_table_id, token, cache_dir, kb_env
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        
        if not validate_table_exists(db_path, request.table_name):
            available = list_tables(db_path)
            raise HTTPException(404, f"Table '{request.table_name}' not found. Available: {available}")
        
        # Convert request to query service format
        query_service = get_query_service()
        
        # Convert filters
        filters = None
        if request.filters:
            filters = [
                FilterSpec(
                    column=f.column,
                    operator=f.operator,
                    value=f.value,
                    value2=f.value2
                )
                for f in request.filters
            ]
        elif request.col_filter:
            # Legacy col_filter format
            filters = [
                FilterSpec(
                    column=col,
                    operator="like",
                    value=val
                )
                for col, val in request.col_filter.items()
            ]
        
        # Convert aggregations
        aggregations = None
        if request.aggregations:
            aggregations = [
                AggregationSpec(
                    column=a.column,
                    function=a.function,
                    alias=a.alias
                )
                for a in request.aggregations
            ]
        
        # Execute query
        result = query_service.execute_query(
            db_path=db_path,
            table_name=request.table_name,
            limit=request.limit,
            offset=request.offset,
            columns=request.columns,
            sort_column=request.sort_column,
            sort_order=request.sort_order,
            search_value=request.search_value,
            filters=filters,
            aggregations=aggregations,
            group_by=request.group_by
        )
        
        return TableDataQueryResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying table data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
