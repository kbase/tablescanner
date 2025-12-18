
import json
import time
import shutil
import logging
from pathlib import Path
from typing import Any
from datetime import datetime

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# CACHE PATH UTILITIES
# =============================================================================

def sanitize_id(id_string: str) -> str:
    """
    Sanitize an ID string for use as a filesystem path.
    
    Args:
        id_string: Raw ID (may contain / : and other special chars)
        
    Returns:
        Safe string for filesystem use
    """
    return id_string.replace("/", "_").replace(":", "_").replace(" ", "_")


def get_upa_cache_path(
    cache_dir: Path,
    berdl_table_id: str
) -> Path:
    """
    Get cache directory for a UPA-based object.
    
    Args:
        cache_dir: Base cache directory
        berdl_table_id: Object UPA (e.g., "76990/ADP1Test")
        
    Returns:
        Path to the object's cache directory
    """
    safe_id = sanitize_id(berdl_table_id)
    return cache_dir / safe_id


# NOTE: clear_cache was previously defined here but is now unified below.

# Legacy support - to be removed
def get_cache_paths(
    cache_dir: Path,
    berdl_table_id: str,
    pangenome_id: str
) -> tuple[Path, Path]:
    """Deprecated: Use get_upa_cache_path instead."""
    safe_berdl = sanitize_id(berdl_table_id)
    safe_pg = sanitize_id(pangenome_id)
    
    cache_subdir = cache_dir / safe_berdl
    sqlite_path = cache_subdir / f"{safe_pg}.db"
    
    return cache_subdir, sqlite_path


def get_metadata_path(cache_subdir: Path) -> Path:
    """Get path to cache metadata file."""
    return cache_subdir / "metadata.json"


# =============================================================================
# CACHE MANAGEMENT
# =============================================================================

def ensure_cache_dir(cache_path: Path) -> None:
    """
    Ensure cache directory exists.

    Args:
        cache_path: Path to cache file (directory will be created from parent)
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)


def save_to_cache(cache_path: Path, data: bytes) -> None:
    """
    Save binary data to cache file.

    Args:
        cache_path: Path where file should be saved
        data: Binary data to save
    """
    ensure_cache_dir(cache_path)
    cache_path.write_bytes(data)
    logger.info(f"Saved {len(data)} bytes to cache: {cache_path}")


def is_cached(cache_path: Path, max_age_hours: int = 24) -> bool:
    """
    Check if file exists in cache and is not expired.

    Args:
        cache_path: Path to cache file
        max_age_hours: Maximum age in hours before cache expires

    Returns:
        True if valid cache exists, False otherwise
    """
    if not cache_path.exists():
        return False
    
    # Check age
    mtime = cache_path.stat().st_mtime
    age_hours = (time.time() - mtime) / 3600
    
    if age_hours > max_age_hours:
        logger.info(f"Cache expired ({age_hours:.1f}h > {max_age_hours}h): {cache_path}")
        return False
    
    logger.debug(f"Valid cache ({age_hours:.1f}h old): {cache_path}")
    return True


def get_cache_info(cache_path: Path) -> dict[str, Any] | None:
    """
    Get information about a cached file.
    
    Args:
        cache_path: Path to cache file
        
    Returns:
        Dictionary with cache info, or None if not cached
    """
    if not cache_path.exists():
        return None
    
    stat = cache_path.stat()
    return {
        "path": str(cache_path),
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "age_hours": (time.time() - stat.st_mtime) / 3600
    }


# =============================================================================
# CACHE METADATA
# =============================================================================




def load_cache_metadata(cache_subdir: Path) -> dict[str, Any] | None:
    """
    Load cache metadata.
    
    Args:
        cache_subdir: Cache subdirectory
        
    Returns:
        Metadata dictionary, or None if not found
    """
    metadata_path = get_metadata_path(cache_subdir)
    if not metadata_path.exists():
        return None
    
    with open(metadata_path) as f:
        return json.load(f)


# =============================================================================
# CACHE CLEANUP
# =============================================================================

def clear_cache(cache_dir: Path, berdl_table_id: str | None = None) -> dict[str, Any]:
    """
    Clear cached files.
    
    Args:
        cache_dir: Base cache directory
        berdl_table_id: Specific BERDLTable to clear (None for all)
        
    Returns:
        Summary of cleanup operation
    """
    if berdl_table_id:
        # Clear specific cache
        safe_id = sanitize_id(berdl_table_id)
        cache_path = cache_dir / safe_id
        
        if cache_path.exists():
            shutil.rmtree(cache_path)
            return {
                "status": "success",
                "message": f"Cleared cache for {berdl_table_id}",
                "path": str(cache_path)
            }
        else:
            return {
                "status": "success",
                "message": "Cache already empty"
            }
    else:
        # Clear all caches
        if cache_dir.exists():
            count = sum(1 for _ in cache_dir.iterdir() if _.is_dir())
            shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            return {
                "status": "success",
                "message": f"Cleared {count} cached items",
                "path": str(cache_dir)
            }
        else:
            return {
                "status": "success",
                "message": "Cache directory does not exist"
            }


def cleanup_old_caches(cache_dir: Path, max_age_days: int = 7) -> dict[str, Any]:
    """
    Remove cache directories older than max_age_days.
    
    Args:
        cache_dir: Base cache directory
        max_age_days: Maximum age in days
        
    Returns:
        Summary of cleanup operation
    """
    if not cache_dir.exists():
        return {"status": "success", "removed": 0}
    
    now = time.time()
    max_age_seconds = max_age_days * 24 * 3600
    removed = []
    
    for subdir in cache_dir.iterdir():
        if not subdir.is_dir():
            continue
        
        try:
            mtime = subdir.stat().st_mtime
            if now - mtime > max_age_seconds:
                shutil.rmtree(subdir)
                removed.append(subdir.name)
                logger.info(f"Removed old cache: {subdir.name}")
        except Exception as e:
            logger.warning(f"Failed to clean {subdir}: {e}")
    
    return {
        "status": "success",
        "removed": len(removed),
        "items": removed
    }


def list_cached_items(cache_dir: Path) -> list[dict[str, Any]]:
    """
    List all cached BERDLTable items.
    
    Args:
        cache_dir: Base cache directory
        
    Returns:
        List of cached item info
    """
    items = []
    
    if not cache_dir.exists():
        return items
    
    for subdir in sorted(cache_dir.iterdir()):
        if not subdir.is_dir():
            continue
        
        metadata = load_cache_metadata(subdir)
        db_files = list(subdir.glob("*.db"))
        
        item = {
            "id": subdir.name,
            "berdl_table_id": metadata.get("berdl_table_id") if metadata else subdir.name,
            "databases": len(db_files),
            "total_size_bytes": sum(f.stat().st_size for f in db_files),
            "pangenomes": list(metadata.get("pangenomes", {}).keys()) if metadata else []
        }
        items.append(item)
    
    return items
