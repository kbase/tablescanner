"""
Utils module for TableScanner.

Contains business logic for:
- KBase Workspace API interactions via direct HTTP requests (using requests library)
- Blobstore/Shock downloading
- Local file caching with age-based expiration
- SQLite database querying with filtering/sorting/pagination
"""

from app.utils.workspace import (
    get_berdl_table_data,

    download_db,
    get_object_info,
    KBaseClient,
)
from app.utils.cache import (
    get_cache_paths,
    ensure_cache_dir,
    save_to_cache,
    is_cached,
    clear_cache,
    list_cached_items,
    cleanup_old_caches,
)
from app.utils.sqlite import (
    list_tables,
    get_table_columns,
    get_table_row_count,
    validate_table_exists,
)

__all__ = [
    # Workspace utilities
    "get_berdl_table_data",

    "download_db",
    "get_object_info",
    "KBaseClient",
    
    # Cache utilities
    "get_cache_paths",
    "ensure_cache_dir",
    "save_to_cache",
    "is_cached",
    "clear_cache",
    "list_cached_items",
    "cleanup_old_caches",
    
    # SQLite utilities
    "list_tables",
    "get_table_columns",
    "get_table_row_count",
    "validate_table_exists",
]
