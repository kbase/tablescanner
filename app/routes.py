"""
TableScanner API Routes

Contains all API endpoint definitions.
"""

from pathlib import Path
from fastapi import APIRouter, Request, HTTPException

from app.models import SearchRequest
from app.services.minio_service import download_from_minio
from app.services.cache_service import get_cache_paths, save_to_cache, is_cached
from app.services.sqlite_service import convert_to_sqlite, query_sqlite

router = APIRouter()


@router.get("/")
async def root(request: Request):
    """Root endpoint returning service information."""
    settings = request.app.state.settings
    return {
        "service": "TableScanner",
        "version": "1.0.0",
        "status": "running",
        "cache_dir": settings.CACHE_DIR
    }


@router.post("/search")
def search(request: Request, search_request: SearchRequest):
    """
    Search endpoint with flexible querying.

    Args:
        search_request: Search parameters including pangenome_id, table_name, limit, order_by, filters

    Returns:
        A dictionary with search results
    """
    settings = request.app.state.settings
    token = settings.KB_SERVICE_AUTH_TOKEN
    cache_dir = Path(settings.CACHE_DIR)

    # TODO: Use the users token instead of a static one

    # TODO: Get workspace data to retrieve filename
    data = workspace.get(search_request.pangenome_id, {'auth': token})
    filename = data.get('filename', f'{search_request.pangenome_id}.bin')

    # Get cache paths
    cache_file_path, sqlite_file_path = get_cache_paths(cache_dir, search_request.pangenome_id, filename)

    # Download and cache if not already cached
    if not is_cached(cache_file_path):
        # Download binary file from MinIO
        # TODO: Get MinIO URL from workspace data or settings
        minio_url = data.get('minio_url')
        if not minio_url:
            raise HTTPException(
                status_code=404,
                detail=f"MinIO URL not found for id: {search_request.pangenome_id}"
            )

        binary_data = download_from_minio(minio_url, token)
        save_to_cache(cache_file_path, binary_data)

    # Convert to SQLite if not already converted
    if not is_cached(sqlite_file_path):
        convert_to_sqlite(cache_file_path, sqlite_file_path)

    # Query the SQLite file with parameters
    from app.services.sqlite_service import get_table_data
    results = get_table_data(
        sqlite_file_path,
        table_name=search_request.table_name,
        limit=search_request.limit,
        order_by=search_request.order_by,
        filters=search_request.filters,
    )

    #TODO use a return model when we figure out what we want to return
    return {
        "pangenome_id": search_request.pangenome_id,
        "table_name": search_request.table_name,
        "status": "success",
        "cache_file": str(cache_file_path),
        "sqlite_file": str(sqlite_file_path),
        "row_count": len(results),
        "results": results
    }
