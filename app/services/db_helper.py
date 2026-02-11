"""
Database helper service to consolidate retrieval and validation logic.
Reduces code duplication in API routes.
"""
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.config import settings
from app.utils.workspace import KBaseClient, download_db
from app.utils.sqlite import validate_table_exists, list_tables
from app.utils.async_utils import run_sync_in_thread
from app.utils.cache import sanitize_id

logger = logging.getLogger(__name__)

async def get_handle_db_path(
    handle_ref: str,
    token: str,
    kb_env: str,
    cache_dir: Path
) -> Path:
    """
    Get (and download if needed) a SQLite database from a handle reference.
    
    Args:
        handle_ref: Handle reference string
        token: KBase auth token
        kb_env: KBase environment
        cache_dir: Cache directory path
        
    Returns:
        Path to the local SQLite database file
    """
    def _download_handle_db():
        # Cache path based on handle
        safe_handle = handle_ref.replace(":", "_").replace("/", "_")
        db_dir = cache_dir / "handles"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"{safe_handle}.db"
        
        # Atomic download if missing
        if not db_path.exists():
            client = KBaseClient(token, kb_env, cache_dir)
            temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                client.download_blob_file(handle_ref, temp_path)
                temp_path.rename(db_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
        return db_path

    try:
        return await run_sync_in_thread(_download_handle_db)
    except Exception as e:
        logger.error(f"Error accessing handle database {handle_ref}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to access database: {str(e)}")


async def get_object_db_path(
    berdl_table_id: str,
    token: str,
    kb_env: str,
    cache_dir: Path
) -> Path:
    """
    Get (and download if needed) a SQLite database from a BERDL object.
    
    Args:
        berdl_table_id: KBase workspace reference OR 'local:{uuid}' for uploaded files
        token: KBase auth token
        kb_env: KBase environment
        cache_dir: Cache directory path
        
    Returns:
        Path to the local SQLite database file
    """
    # Handle local uploads
    if berdl_table_id.startswith("local:"):
        # Expect format local:UUID
        handle_parts = berdl_table_id.split(":", 1)
        if len(handle_parts) != 2:
             raise HTTPException(status_code=400, detail="Invalid local database handle format")
             
        filename = getattr(sanitize_id, 'original', sanitize_id)(handle_parts[1])
        # Note: sanitize_id ensures only alphanumeric+._- chars
        
        # Double check against the original to ensure no unexpected chars werestripped silently that might imply malicious intent?
        # Actually sanitize_id already does a good job. But let's be strict.
        if filename != handle_parts[1]:
             # If sanitize changed it, it had bad chars
             raise HTTPException(status_code=400, detail="Invalid characters in local database handle")

        db_path = cache_dir / "uploads" / f"{filename}.db"
        
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"Local database not found: {berdl_table_id}")
            
        return db_path

    try:
        # download_db already handles caching logic
        return await run_sync_in_thread(
            download_db,
            berdl_table_id,
            token,
            cache_dir,
            kb_env
        )
    except TimeoutError:
        logger.error(f"Database download timed out for {berdl_table_id}")
        raise HTTPException(
            status_code=504,
            detail="Database download timed out. Please try again later."
        )
    except Exception as e:
        logger.error(f"Error accessing object database {berdl_table_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to access database: {str(e)}")


async def ensure_table_accessible(db_path: Path, table_name: str) -> bool:
    """
    Validate that a table exists in the database.
    Raises HTTPException 404 if not found.
    
    Args:
        db_path: Path to SQLite database
        table_name: Name of table to check
        
    Returns:
        True if exists
    """
    exists = await run_sync_in_thread(validate_table_exists, db_path, table_name)
    
    if not exists:
        available = await run_sync_in_thread(list_tables, db_path)
        raise HTTPException(
            status_code=404, 
            detail=f"Table '{table_name}' not found. Available: {available}"
        )
    return True
