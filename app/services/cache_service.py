"""
Cache service for managing local file caching.
"""

from pathlib import Path
from typing import Tuple


def get_cache_paths(cache_dir: Path, id: str, filename: str) -> Tuple[Path, Path]:
    """
    Get cache file paths for a given ID and filename.

    Args:
        cache_dir: Base cache directory
        id: Object ID
        filename: Original filename

    Returns:
        Tuple of (cache_file_path, sqlite_file_path)
    """
    cache_file_path = cache_dir / id / filename
    sqlite_file_path = cache_dir / id / f"{Path(filename).stem}.db"
    return cache_file_path, sqlite_file_path


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


def is_cached(cache_path: Path) -> bool:
    """
    Check if file exists in cache.

    Args:
        cache_path: Path to cache file

    Returns:
        True if file exists, False otherwise
    """
    return cache_path.exists()