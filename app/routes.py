"""
TableScanner API Routes

Contains all API endpoint definitions.
"""

from pathlib import Path
from fastapi import APIRouter, Request, HTTPException

from app.models import SearchRequest
from app.utils.workspace import get_object_info
from app.utils.download import download_from_handle
from app.utils.cache import get_cache_paths, save_to_cache, is_cached
from app.utils.sqlite import convert_to_sqlite

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
    workspace_url = settings.WORKSPACE_URL

    # TODO: Use the users token instead of a static one

    # Get object info from KBase Workspace
    object_info = get_object_info(search_request.pangenome_id, token, workspace_url)
    filename = object_info.get('filename', f'{search_request.pangenome_id}.bin')
    handle_url = object_info.get('handle_url') or object_info.get('blobstore_url')

    if not handle_url:
        raise HTTPException(
            status_code=404,
            detail=f"No handle/blobstore URL found for id: {search_request.pangenome_id}"
        )

    # Get cache paths
    cache_file_path, sqlite_file_path = get_cache_paths(cache_dir, search_request.pangenome_id, filename)

    # Download and cache if not already cached
    if not is_cached(cache_file_path):
        # Download from handle/blobstore service
        binary_data = download_from_handle(handle_url, token)
        save_to_cache(cache_file_path, binary_data)

    # Convert to SQLite if not already converted
    if not is_cached(sqlite_file_path):
        convert_to_sqlite(cache_file_path, sqlite_file_path)

    # Query the SQLite file with parameters
    from app.utils.sqlite import get_table_data
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
