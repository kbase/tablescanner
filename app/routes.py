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
    ConfigGenerationResponse,
    ProviderStatusResponse,
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
        
        for name in table_names:
            try:
                columns = get_table_columns(db_path, name)
                row_count = get_table_row_count(db_path, name)
                tables.append({
                    "name": name,
                    "row_count": row_count,
                    "column_count": len(columns)
                })
                total_rows += row_count or 0
                
                # Build schema map
                schemas[name] = {col: "TEXT" for col in columns}  # Default type
            except Exception as e:
                logger.warning("Error getting table info for %s", name, exc_info=True)
                tables.append({"name": name})
        
        # Get object type
        try:
            object_type = get_object_type(berdl_table_id, token, kb_env)
        except Exception:
            object_type = None
        
        # Check for cached viewer config
        config_fingerprint = None
        config_url = None
        has_cached_config = False
        try:
            from app.services.data.fingerprint import DatabaseFingerprint
            fp_service = DatabaseFingerprint()
            safe_ref = berdl_table_id.replace("/", "_").replace(":", "_")
            fingerprint = fp_service.compute(db_path)
            full_fingerprint = f"{safe_ref}_{fingerprint}"
            
            if fp_service.is_cached(full_fingerprint):
                config_fingerprint = full_fingerprint
                config_url = f"/config/generated/{full_fingerprint}"
                has_cached_config = True
        except Exception as e:
            logger.debug(f"Config fingerprint check: {e}")
        
        # Check for builtin fallback config
        has_builtin_config = False
        # Configs are now stored in DataTables Viewer, not here
        has_builtin_config = False
        builtin_config_id = None
        
        # Get database size
        database_size = None
        try:
            database_size = db_path.stat().st_size if db_path.exists() else None
        except Exception:
            pass
        
        return {
            "berdl_table_id": berdl_table_id,
            "tables": tables,
            "object_type": object_type,
            "source": "Cache" if (db_path.exists() and db_path.stat().st_size > 0) else "Downloaded",
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
# CONFIG GENERATION ENDPOINTS (AI-Powered Schema Inference)
# =============================================================================


@router.post(
    "/config/generate/{handle_ref}",
    response_model=ConfigGenerationResponse,
    tags=["Config Generation"]
)
async def generate_viewer_config(
    handle_ref: str,
    force_regenerate: bool = Query(False, description="Skip cache and regenerate"),
    ai_provider: str = Query("auto", description="AI provider: auto, openai, argo, ollama, rules-only"),
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Generate a DataTables_Viewer configuration for a SQLite database.
    
    This endpoint analyzes the database schema and sample values using
    AI-powered type inference to generate a viewer-compatible config.
    
    **Flow:**
    1. Download SQLite via handle_ref (uses existing cache)
    2. Compute database fingerprint
    3. Check config cache → return if exists (unless force_regenerate)
    4. Analyze schema and sample values
    5. Apply rule-based + AI type inference
    6. Generate viewer-compatible JSON config
    7. Cache and return
    
    **Example:**
    ```bash
    curl -X POST -H "Authorization: $KB_TOKEN" \\
         "http://127.0.0.1:8000/config/generate/KBH_248028"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        
        # Import config generator
        from app.services.config.config_generator import ConfigGenerator
        
        # Get database path (using existing handle logic)
        client = KBaseClient(token, kb_env, cache_dir)
        
        safe_handle = handle_ref.replace(":", "_").replace("/", "_")
        db_dir = cache_dir / "handles"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"{safe_handle}.db"
        
        # Download if not cached
        if not db_path.exists():
            temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                client.download_blob_file(handle_ref, temp_path)
                temp_path.rename(db_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
        
        # Generate config
        generator = ConfigGenerator()
        result = generator.generate(
            db_path=db_path,
            handle_ref=handle_ref,
            force_regenerate=force_regenerate,
            ai_preference=ai_provider,
        )
        
        return ConfigGenerationResponse(
            status="cached" if result.cache_hit else "generated",
            fingerprint=result.fingerprint,
            config_url=f"/config/generated/{result.fingerprint}",
            config=result.config,
            tables_analyzed=result.tables_analyzed,
            columns_inferred=result.columns_inferred,
            ai_provider_used=result.ai_provider_used,
            generation_time_ms=result.generation_time_ms,
            cache_hit=result.cache_hit,
        )
        
    except Exception as e:
        logger.error(f"Error generating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/generated/{fingerprint}", tags=["Config Generation"])
async def get_generated_config(fingerprint: str):
    """
    Retrieve a previously generated configuration by fingerprint.
    
    **Example:**
    ```bash
    curl "http://127.0.0.1:8000/config/generated/KBH_248028_abc123def456"
    ```
    """
    try:
        from app.services.data.fingerprint import DatabaseFingerprint
        
        fp = DatabaseFingerprint()
        config = fp.get_cached_config(fingerprint)
        
        if config is None:
            raise HTTPException(
                status_code=404,
                detail=f"Config not found for fingerprint: {fingerprint}"
            )
        
        return config
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/config/providers",
    response_model=list[ProviderStatusResponse],
    tags=["Config Generation"]
)
async def list_ai_providers():
    """
    List available AI providers and their status.
    
    Returns the availability and priority of each AI provider.
    Lower priority numbers indicate higher preference.
    
    **Example:**
    ```bash
    curl "http://127.0.0.1:8000/config/providers"
    ```
    """
    try:
        from app.services.ai.ai_provider import list_ai_providers
        
        providers = list_ai_providers()
        return [
            ProviderStatusResponse(
                name=p.name,
                available=p.available,
                priority=p.priority,
                error=p.error,
            )
            for p in providers
        ]
        
    except Exception as e:
        logger.error(f"Error listing providers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/cached", tags=["Config Generation"])
async def list_cached_configs():
    """
    List all cached generated configurations.
    
    **Example:**
    ```bash
    curl "http://127.0.0.1:8000/config/cached"
    ```
    """
    try:
        from app.services.data.fingerprint import DatabaseFingerprint
        
        fp = DatabaseFingerprint()
        cached = fp.list_cached()
        
        return {
            "configs": cached,
            "total": len(cached),
        }
        
    except Exception as e:
        logger.error(f"Error listing cached configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/config/cached/{fingerprint}", tags=["Config Generation"])
async def delete_cached_config(fingerprint: str):
    """
    Delete a specific cached configuration.
    
    Use this to invalidate a cached config and force regeneration on next request.
    
    **Example:**
    ```bash
    curl -X DELETE "http://127.0.0.1:8000/config/cached/76990_7_2_abc123"
    ```
    """
    try:
        from app.services.data.fingerprint import DatabaseFingerprint
        
        fp = DatabaseFingerprint()
        deleted = fp.clear_cache(fingerprint)
        
        if deleted > 0:
            return {"status": "success", "message": f"Deleted config: {fingerprint}"}
        else:
            raise HTTPException(status_code=404, detail=f"Config not found: {fingerprint}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/object/{ws_ref:path}/config/generate",
    response_model=ConfigGenerationResponse,
    tags=["Config Generation"]
)
async def generate_config_for_object(
    ws_ref: str,
    force_regenerate: bool = Query(False, description="Skip cache and regenerate"),
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Generate a DataTables_Viewer configuration for a KBase object.
    
    This is the object-based alternative to the handle-based config generation.
    It downloads the SQLite database from the workspace object and generates
    an AI-powered viewer configuration.
    
    **Flow:**
    1. Download SQLite from workspace object (uses existing cache)
    2. Compute database fingerprint
    3. Check config cache → return if exists (unless force_regenerate)
    4. Analyze schema and sample values
    5. Apply rule-based + Argo AI type inference
    6. Validate and cache generated config
    7. Return
    
    **Example:**
    ```bash
    curl -X POST -H "Authorization: $KB_TOKEN" \\
         "http://127.0.0.1:8000/object/76990/7/2/config/generate"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        berdl_table_id = ws_ref
        
        # Download database
        db_path = download_pangenome_db(
            berdl_table_id=berdl_table_id,
            auth_token=token,
            cache_dir=cache_dir,
            kb_env=kb_env
        )
        
        # Get object type for config metadata
        try:
            object_type = get_object_type(berdl_table_id, token, kb_env)
        except Exception:
            object_type = None
        
        # Generate config
        from app.services.config.config_generator import ConfigGenerator
        
        generator = ConfigGenerator()
        
        # Build schema info for response
        schema = {}
        table_schemas = {}
        total_rows = 0
        try:
            table_names = list_tables(db_path)
            for tbl in table_names:
                cols = get_table_columns(db_path, tbl)
                schema[tbl] = {c: "TEXT" for c in cols}
                total_rows += get_table_row_count(db_path, tbl) or 0
        except Exception as e:
            logger.warning(f"Error building schema: {e}")
        
        # Check if config already exists in DataTables Viewer
        from app.services.config_registry import get_config_registry
        from app.services.viewer_client import get_viewer_client
        
        registry = get_config_registry()
        viewer = get_viewer_client()
        
        # Check registry first
        if not force_regenerate and registry.has_config(object_type):
            # Verify with viewer
            if viewer.check_config_exists(object_type):
                logger.info(f"Config already exists for {object_type}, skipping generation")
                return ConfigGenerationResponse(
                    status="exists",
                    fingerprint="",
                    config_url="",
                    config={},
                    tables_analyzed=0,
                    columns_inferred=0,
                    ai_provider_used=None,
                    generation_time_ms=0,
                    cache_hit=True,
                )
            else:
                # Registry says it exists but viewer doesn't - update registry
                registry.mark_no_config(object_type)
        
        # Generate config with AI
        try:
            result = generator.generate(
                db_path=db_path,
                handle_ref=berdl_table_id,
                force_regenerate=True,  # Always generate fresh for new configs
                ai_preference="argo",
            )
            
            # Add object type to config
            if object_type and "objectType" not in result.config:
                result.config["objectType"] = object_type
            
            # Send config to DataTables Viewer
            try:
                viewer.send_config(
                    object_type=object_type,
                    source_ref=berdl_table_id,
                    config=result.config
                )
                # Mark as having config
                registry.mark_has_config(object_type)
                status = "generated_and_sent"
            except Exception as e:
                logger.error(f"Failed to send config to viewer: {e}")
                # Still return the config even if viewer send failed
                status = "generated_but_send_failed"
            
            return ConfigGenerationResponse(
                status=status,
                fingerprint=result.fingerprint,
                config_url="",
                config=result.config,
                tables_analyzed=result.tables_analyzed,
                columns_inferred=result.columns_inferred,
                ai_provider_used=result.ai_provider_used,
                generation_time_ms=result.generation_time_ms,
                cache_hit=False,
            )
            
        except Exception as gen_error:
            logger.error(f"Config generation failed: {gen_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Config generation failed: {gen_error}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating config for object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/object/{ws_ref:path}/config", tags=["Config Generation"])
async def get_config_for_object(
    ws_ref: str,
    kb_env: str = Query("appdev"),
    authorization: str | None = Header(None)
):
    """
    Get cached viewer config for a KBase object.
    
    Returns 404 if no config has been generated yet. Use the
    POST /object/{ws_ref}/config/generate endpoint to create one.
    
    **Example:**
    ```bash
    curl -H "Authorization: $KB_TOKEN" \\
         "http://127.0.0.1:8000/object/76990/7/2/config"
    ```
    """
    try:
        token = get_auth_token(authorization)
        cache_dir = get_cache_dir()
        berdl_table_id = ws_ref
        
        # Download database (needed for fingerprint computation)
        db_path = download_pangenome_db(
            berdl_table_id=berdl_table_id,
            auth_token=token,
            cache_dir=cache_dir,
            kb_env=kb_env
        )
        
        # Configs are now stored in DataTables Viewer
        # This endpoint is deprecated - configs should be retrieved from viewer
        raise HTTPException(
            status_code=404,
            detail=f"Configs are now stored in DataTables Viewer. Use POST /object/{ws_ref}/config/generate to create one, then retrieve from viewer."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting config for object: {e}")
        raise HTTPException(status_code=500, detail=str(e))
