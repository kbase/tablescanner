
import sys
import logging
from pathlib import Path
from typing import Any
import requests
from app.utils.cache import get_upa_cache_path
from uuid import uuid4

# Add KBUtilLib to path
LIB_PATH = Path(__file__).parent.parent.parent / "lib" / "KBUtilLib" / "src"
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

# Try conditional imports at top level
try:
    from kbutillib.kb_ws_utils import KBWSUtils
    from kbutillib.notebook_utils import NotebookUtils
    HAS_KBUTILLIB = True
except ImportError:
    HAS_KBUTILLIB = False
    # Define dummy classes if needed for type hinting or logic check
    KBWSUtils = object
    NotebookUtils = object

from app.config import settings

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# KBASE UTILITY CLASS (USING KBUtilLib)
# =============================================================================

class KBaseClient:
    """
    KBase API client using KBUtilLib.
    
    Uses NotebookUtils and KBWSUtils with kb_version parameter
    to target the correct KBase environment (appdev, ci, prod).
    """
    
    def __init__(
        self,
        token: str,
        kb_env: str = "appdev",
        cache_dir: Path | None = None
    ):
        """
        Initialize KBase client.
        
        Args:
            token: KBase authentication token
            kb_env: Environment (appdev, ci, prod)
            cache_dir: Local cache directory
        """
        self.token = token
        self.kb_env = kb_env
        self.cache_dir = cache_dir or Path("/tmp/tablescanner_cache")
        self._client = None
        self._use_kbutillib = False
        
        # Try to initialize KBUtilLib
        self._init_client()
        
    def _init_client(self):
        """Initialize the appropriate client."""
        # Disable KBUtilLib for now - use direct API calls with proper timeouts.
        # KBUtilLib can hang indefinitely and does not respect timeouts; if
        # KBUtilLib-based initialization is needed in the future, refer to
        # version control history for the previous implementation details.
        logger.info(f"Using direct API calls (KBUtilLib disabled) for {self.kb_env}")
        self._use_kbutillib = False
            
    def get_object(self, ref: str, ws: int | None = None) -> dict[str, Any]:
        """
        Get workspace object data.
        
        Args:
            ref: Object reference or name
            ws: Workspace ID (optional if ref is full reference)
            
        Returns:
            Object data dictionary
        """
        # Prefer fallback path which has proper timeout handling
        # KBUtilLib can hang indefinitely, so we use direct API calls
        return self._get_object_fallback(ref, ws)
    
    def download_blob_file(self, handle_ref: str, target_path: Path) -> Path:
        """
        Download file from blobstore using handle reference.
        
        Args:
            handle_ref: Handle ID (KBH_xxxxx format)
            target_path: Where to save the file
            
        Returns:
            Path to downloaded file
        """
        # Ensure directory exists
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self._use_kbutillib and self._client:
            try:
                # Ensure KBUtilLib has the token set
                if hasattr(self._client, 'save_token'):
                    self._client.save_token(self.token, namespace="kbase")
                result = self._client.download_blob_file(handle_ref, str(target_path))
                if result:
                    return Path(result)
            except Exception as e:
                logger.warning(f"KBUtilLib download_blob_file failed: {e}. Using fallback.", exc_info=True)
                
        return Path(self._download_blob_fallback(handle_ref, str(target_path)))
    
    # =========================================================================
    # FALLBACK METHODS (Direct API calls)
    # =========================================================================
    
    def _workspace_auth_header(self) -> str:
        """Return Authorization header value for KBase Workspace API. Workspace expects Bearer token."""
        t = self.token or ""
        if t.startswith("Bearer ") or t.startswith("OAuth "):
            return t
        return f"Bearer {t}" if t else ""

    def _get_endpoints(self) -> dict[str, str]:
        """Get endpoints for current environment."""
        # If the requested env matches the configured env, use the configured URLs
        if self.kb_env == settings.KB_ENV:
            return {
                "workspace": settings.WORKSPACE_URL,
                "shock": settings.BLOBSTORE_URL,
                "handle": f"{settings.KBASE_ENDPOINT}/handle_service", 
            }

        # Fallback for other environments
        endpoints = {
            "appdev": {
                "workspace": "https://appdev.kbase.us/services/ws",
                "shock": "https://appdev.kbase.us/services/shock-api",
                "handle": "https://appdev.kbase.us/services/handle_service",
            },
            "ci": {
                "workspace": "https://ci.kbase.us/services/ws",
                "shock": "https://ci.kbase.us/services/shock-api",
                "handle": "https://ci.kbase.us/services/handle_service",
            },
            "prod": {
                "workspace": "https://kbase.us/services/ws",
                "shock": "https://kbase.us/services/shock-api",
                "handle": "https://kbase.us/services/handle_service",
            },
        }
        return endpoints.get(self.kb_env, endpoints["appdev"])
    
    def _get_object_fallback(self, ref: str, ws: int | None = None) -> dict[str, Any]:
        """Get workspace object via direct API call."""
        import time
        # Build reference
        if ws and "/" not in str(ref):
            ref = f"{ws}/{ref}"
        
        logger.info(f"[_get_object_fallback] Starting request for {ref}")
        start_time = time.time()
            
        headers = {
            "Authorization": self._workspace_auth_header(),
            "Content-Type": "application/json"
        }
        payload = {
            "method": "Workspace.get_objects2",
            "params": [{"objects": [{"ref": ref}]}],
            "version": "1.1",
            "id": "tablescanner-1"
        }
        
        endpoints = self._get_endpoints()
        workspace_url = endpoints["workspace"]
        logger.info(f"[_get_object_fallback] Calling {workspace_url} with timeout=30")
        
        try:
            request_start = time.time()
            response = requests.post(
                workspace_url,
                json=payload,
                headers=headers,
                timeout=30  # Reduced from 60 to fail faster
            )
            request_elapsed = time.time() - request_start
            logger.info(f"[_get_object_fallback] Request completed in {request_elapsed:.2f}s, status={response.status_code}")
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                error_code = result["error"].get("code", "Unknown")
                logger.error(f"Workspace API error for {ref}: [{error_code}] {error_msg}")
                raise ValueError(f"Workspace API error: [{error_code}] {error_msg}")
        except requests.exceptions.HTTPError as e:
            # Capture response body for better error messages
            error_detail = f"HTTP {e.response.status_code}"
            try:
                error_body = e.response.json()
                if "error" in error_body:
                    error_detail = error_body["error"].get("message", str(error_body))
                else:
                    error_detail = str(error_body)
            except Exception:
                error_detail = e.response.text[:500] if e.response.text else str(e)
            logger.error(f"Workspace API HTTP error for {ref}: {error_detail}")
            raise ValueError(f"Workspace service error: {error_detail}")
        except requests.exceptions.Timeout as e:
            elapsed = time.time() - start_time
            logger.error(f"[_get_object_fallback] Workspace API timeout for {ref} after {elapsed:.2f}s: {e}")
            raise ValueError(f"Workspace API timeout: Request took longer than 30 seconds")
        except requests.exceptions.RequestException as e:
            elapsed = time.time() - start_time
            logger.error(f"[_get_object_fallback] Workspace API request failed for {ref} after {elapsed:.2f}s: {e}")
            raise ValueError(f"Failed to connect to workspace service: {str(e)}")
            
        data_list = result.get("result", [{}])[0].get("data", [])
        if not data_list:
            raise ValueError(f"No data for: {ref}")
            
        return data_list[0]

    def get_object_with_type(self, ref: str, ws: int | None = None) -> tuple[dict[str, Any], str]:
        """
        Get workspace object data along with its type.
        
        Args:
            ref: Object reference or name
            ws: Workspace ID (optional if ref is full reference)
            
        Returns:
            Tuple of (object_data, object_type)
            object_type is the full KBase type string (e.g., "KBaseFBA.GenomeDataLakeTables-2.0")
        """
        # Build reference
        if ws and "/" not in str(ref):
            ref = f"{ws}/{ref}"
        
        # First get the object type using get_object_info3
        object_type = self._get_object_type(ref)
        
        # Then get the data using standard method
        obj_data = self.get_object(ref)
        
        return obj_data, object_type
    
    def _get_object_type(self, ref: str) -> str:
        """
        Get the KBase object type using Workspace.get_object_info3.
        
        Args:
            ref: Object reference
            
        Returns:
            Object type string (e.g., "KBaseFBA.GenomeDataLakeTables-2.0")
        """
        headers = {
            "Authorization": self._workspace_auth_header(),
            "Content-Type": "application/json"
        }
        
        payload = {
            "method": "Workspace.get_object_info3",
            "params": [{"objects": [{"ref": ref}]}],
            "version": "1.1",
            "id": "tablescanner-type"
        }
        
        endpoints = self._get_endpoints()
        try:
            response = requests.post(
                endpoints["workspace"],
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                logger.warning(f"Error getting object type for {ref}: {error_msg}")
                return "Unknown"
        except requests.exceptions.HTTPError as e:
            error_detail = f"HTTP {e.response.status_code}"
            try:
                error_body = e.response.json()
                if "error" in error_body:
                    error_detail = error_body["error"].get("message", str(error_body))
            except Exception:
                error_detail = e.response.text[:200] if e.response.text else str(e)
            logger.warning(f"Error getting object type for {ref}: {error_detail}")
            return "Unknown"
        except Exception as e:
            logger.warning(f"Error getting object type for {ref}: {e}")
            return "Unknown"
        
        # get_object_info3 returns: {"result": [{"infos": [[objid, name, type, ...]]}]}
        infos = result.get("result", [{}])[0].get("infos", [])
        if infos and infos[0] and len(infos[0]) > 2:
            return infos[0][2]
        
        return "Unknown"
        
    def get_object_type_only(self, ref: str) -> str:
        """
        Public method to get object type without fetching full data.
        
        Args:
            ref: Object reference
            
        Returns:
            Object type string
        """
        return self._get_object_type(ref)
    
    def _download_blob_fallback(self, handle_ref: str, target_path: str) -> str:
        """Download from blobstore via direct API."""
        endpoints = self._get_endpoints()
        headers = {"Authorization": f"OAuth {self.token}"}
        
        # Resolve handle to shock ID
        handle_payload = {
            "method": "AbstractHandle.hids_to_handles",
            "params": [[handle_ref]],
            "version": "1.1",
            "id": "tablescanner-2"
        }
        
        shock_id = handle_ref  # Default to handle_ref
        try:
            resp = requests.post(
                endpoints["handle"],
                json=handle_payload,
                headers={"Authorization": f"OAuth {self.token}", "Content-Type": "application/json"},
                timeout=30
            )
            resp.raise_for_status()
            handles = resp.json().get("result", [[]])[0]
            if handles:
                shock_id = handles[0].get("id", handle_ref)
        except Exception as e:
            logger.warning(f"Handle resolution failed, using handle_ref directly: {e}")
            
        # Download from shock
        download_url = f"{endpoints['shock']}/node/{shock_id}?download_raw"
        
        response = requests.get(
            download_url,
            headers=headers,
            stream=True,
            timeout=300
        )
        response.raise_for_status()
        
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)
                
        logger.info(f"Downloaded {handle_ref} to {target_path}")
        return target_path


# =============================================================================
# HIGH-LEVEL FUNCTIONS
# =============================================================================

def get_berdl_table_data(
    berdl_table_id: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> dict[str, Any]:
    """
    Fetch BERDLTables object and extract database information.

    BERDLTables structure:
    {
        "pangenome_data": [
            {
                "pangenome_id": "pg_123",
                "pangenome_taxonomy": "Escherichia coli",
                "sqllite_tables_handle_ref": "KBH_xxxxx",
                ...
            }
        ]
    }

    Args:
        berdl_table_id: KBase workspace reference (e.g., "76990/ADP1Test")
        auth_token: KBase authentication token
        kb_env: KBase environment

    Returns:
        Object data dictionary with pangenome_data
    """
    import time
    logger.debug(f"[get_berdl_table_data] Fetching object {berdl_table_id}")
    start_time = time.time()
    
    client = KBaseClient(auth_token, kb_env)
    obj = client.get_object(berdl_table_id)
    
    elapsed = time.time() - start_time
    logger.debug(f"[get_berdl_table_data] Got object in {elapsed:.2f}s")
    
    # Handle nested data structures
    if isinstance(obj, dict) and "data" in obj:
        return obj["data"]
    return obj


def get_object_type(
    berdl_table_id: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> str:
    """
    Get the KBase object type for a workspace object.

    Args:
        berdl_table_id: KBase workspace reference (e.g., "76990/7/2")
        auth_token: KBase authentication token
        kb_env: KBase environment

    Returns:
        Object type string (e.g., "KBaseGeneDataLakes.BERDLTables-1.0")
    """
    if berdl_table_id.startswith("local:"):
        return "LocalDatabase"
        
    client = KBaseClient(auth_token, kb_env)
    return client.get_object_type_only(berdl_table_id)



def download_db(
    berdl_table_id: str,
    auth_token: str,
    cache_dir: Path,
    kb_env: str = "appdev"
) -> Path:
    """
    Download the SQLite database for a BERDLTables object (single-database case).
    
    Uses UPA-based cache structure: `{cache_dir}/{sanitized_upa}/tables.db`
    where slashes in the UPA are replaced with underscores.
    
    Implements atomic file operations to prevent race conditions:
    1. Download to temp file with UUID suffix
    2. Atomic rename to final path
    
    Args:
        berdl_table_id: KBase UPA reference (e.g., "76990/7/2")
        auth_token: KBase authentication token
        cache_dir: Local cache directory
        kb_env: KBase environment (appdev, ci, prod)
        
    Returns:
        Path to the SQLite database file
    """

    
    cache_dir = Path(cache_dir)
    db_dir = get_upa_cache_path(cache_dir, berdl_table_id)
    db_path = db_dir / "tables.db"
    
    # Fast path: return cached file if exists
    if db_path.exists():
        logger.info(f"Using cached database: {db_path}")
        return db_path
    
    # Fetch object metadata to get handle reference
    obj_data = get_berdl_table_data(berdl_table_id, auth_token, kb_env)
    pangenome_data = obj_data.get("pangenome_data", [])
    
    if not pangenome_data:
         raise ValueError(f"No pangenomes found in {berdl_table_id}")

    # Take the first (and only expected) handle for the single-DB case
    handle_ref = pangenome_data[0].get("sqllite_tables_handle_ref")
    if not handle_ref:
        raise ValueError(f"No handle reference found in {berdl_table_id}")
    
    # Create cache directory
    db_dir.mkdir(parents=True, exist_ok=True)
    
    # Download to temp file to prevent race conditions
    temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
    
    try:
        client = KBaseClient(auth_token, kb_env, cache_dir)
        client.download_blob_file(handle_ref, temp_path)
        
        # Atomic rename to final path
        temp_path.rename(db_path)
        logger.info(f"Downloaded database to: {db_path}")
        
    except Exception:
        # Cleanup temp file on failure
        temp_path.unlink(missing_ok=True)
        raise
    
    return db_path


def download_multi_dbs(
    berdl_table_id: str,
    auth_token: str,
    cache_dir: Path,
    kb_env: str = "appdev"
) -> list[dict]:
    """
    Download ALL SQLite databases for a BERDLTables object that contains multiple databases.
    
    Each database is stored in: `{cache_dir}/{sanitized_upa}/{db_name}/tables.db`
    
    Optimized: Only downloads databases that aren't already cached.
    
    Args:
        berdl_table_id: KBase UPA reference (e.g., "76990/7/2")
        auth_token: KBase authentication token
        cache_dir: Local cache directory
        kb_env: KBase environment (appdev, ci, prod)
        
    Returns:
        List of dicts with db_name, db_display_name, db_path, handle_ref
    """
    import time
    cache_dir = Path(cache_dir)
    base_dir = get_upa_cache_path(cache_dir, berdl_table_id)
    
    logger.info(f"[download_multi_dbs] Starting for {berdl_table_id}")
    start_time = time.time()
    
    # Fetch object metadata to get all database handles
    logger.debug(f"[download_multi_dbs] Fetching object metadata...")
    obj_data = get_berdl_table_data(berdl_table_id, auth_token, kb_env)
    logger.debug(f"[download_multi_dbs] Got object metadata in {time.time() - start_time:.2f}s")
    
    pangenome_data = obj_data.get("pangenome_data", [])
    if not pangenome_data:
        raise ValueError(f"No pangenomes found in {berdl_table_id}")
    
    logger.info(f"[download_multi_dbs] Found {len(pangenome_data)} databases")
    
    databases = []
    client = KBaseClient(auth_token, kb_env, cache_dir)
    
    # Pre-check cache to avoid unnecessary downloads
    cached_count = 0
    download_count = 0
    
    for idx, pg in enumerate(pangenome_data):
        handle_ref = pg.get("sqllite_tables_handle_ref")
        if not handle_ref:
            logger.warning(f"Database {idx+1} missing handle_ref: {pg.get('pangenome_id', 'unknown')}")
            continue
            
        # Use pangenome_id as the db_name (this is what the object provides),
        # or generate one from handle as a fallback.
        db_name = pg.get("pangenome_id") or f"db_{handle_ref.replace('KBH_', '')}"
        db_display_name = pg.get("pangenome_taxonomy") or db_name
        
        # Create per-database subdirectory
        db_dir = base_dir / db_name
        db_path = db_dir / "tables.db"
        
        # Fast path: use cached file if exists
        if db_path.exists():
            logger.debug(f"[download_multi_dbs] Using cached: {db_name}")
            cached_count += 1
            databases.append({
                "db_name": db_name,
                "db_display_name": db_display_name,
                "db_path": db_path,
                "handle_ref": handle_ref
            })
            continue
        
        # Download missing database
        logger.info(f"[download_multi_dbs] Downloading {db_name} ({idx+1}/{len(pangenome_data)})...")
        db_dir.mkdir(parents=True, exist_ok=True)
        temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
        
        download_start = time.time()
        try:
            client.download_blob_file(handle_ref, temp_path)
            temp_path.rename(db_path)
            download_elapsed = time.time() - download_start
            logger.info(f"[download_multi_dbs] Downloaded {db_name} in {download_elapsed:.2f}s")
            download_count += 1
        except Exception as e:
            temp_path.unlink(missing_ok=True)
            logger.error(f"[download_multi_dbs] Failed to download {db_name}: {e}", exc_info=True)
            continue
        
        databases.append({
            "db_name": db_name,
            "db_display_name": db_display_name,
            "db_path": db_path,
            "handle_ref": handle_ref
        })
    
    total_elapsed = time.time() - start_time
    logger.info(f"[download_multi_dbs] Completed: {len(databases)} databases ({cached_count} cached, {download_count} downloaded) in {total_elapsed:.2f}s")
    
    if not databases:
        raise ValueError(f"Failed to download any databases from {berdl_table_id}")
    
    return databases


def download_db_multi(
    berdl_table_id: str,
    db_name: str,
    auth_token: str,
    cache_dir: Path,
    kb_env: str = "appdev"
) -> dict[str, Any]:
    """
    Download ONE SQLite database for a specific database within a multi-database BERDLTables object.

    This avoids the expensive `download_multi_dbs()` behavior for endpoints that only need a
    single database (e.g. `/db/{db_name}/tables`, `/db/{db_name}/tables/{table}/data`).

    Cache layout (same as multi-download):
      {cache_dir}/{sanitized_upa}/{db_name}/tables.db

    Args:
        berdl_table_id: KBase workspace reference (UPA)
        db_name: The pangenome_id / database name to download (as returned by `/databases`)
        auth_token: KBase auth token
        cache_dir: Cache directory
        kb_env: KBase environment

    Returns:
        Dict with db_name, db_display_name, db_path, handle_ref
    """
    cache_dir = Path(cache_dir)
    base_dir = get_upa_cache_path(cache_dir, berdl_table_id)

    # Fast path: if already cached, return without hitting Workspace/Shock
    db_dir = base_dir / db_name
    db_path = db_dir / "tables.db"
    if db_path.exists():
        return {
            "db_name": db_name,
            "db_display_name": db_name,
            "db_path": db_path,
            "handle_ref": None,
        }

    # Resolve the database handle for the requested db_name
    obj_data = get_berdl_table_data(berdl_table_id, auth_token, kb_env)
    pangenome_data = obj_data.get("pangenome_data", [])
    if not pangenome_data:
        raise ValueError(f"No pangenomes found in {berdl_table_id}")

    target_pg: dict[str, Any] | None = None
    available: list[str] = []
    for pg in pangenome_data:
        pg_id = pg.get("pangenome_id")
        if pg_id:
            available.append(pg_id)
        if pg_id == db_name:
            target_pg = pg
            break

    if not target_pg:
        raise ValueError(f"Database '{db_name}' not found in object. Available: {available}")

    handle_ref = target_pg.get("sqllite_tables_handle_ref")
    if not handle_ref:
        raise ValueError(f"Pangenome '{db_name}' missing sqllite_tables_handle_ref")

    db_display_name = target_pg.get("pangenome_taxonomy") or db_name

    # Download atomically
    db_dir.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
    client = KBaseClient(auth_token, kb_env, cache_dir)
    try:
        client.download_blob_file(handle_ref, temp_path)
        temp_path.rename(db_path)
        logger.info(f"Downloaded database '{db_name}' to: {db_path}")
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return {
        "db_name": db_name,
        "db_display_name": db_display_name,
        "db_path": db_path,
        "handle_ref": handle_ref,
    }




def get_object_info(
    object_ref: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> dict[str, Any]:
    """
    Get basic object info without full data.

    Args:
        object_ref: KBase workspace reference
        auth_token: KBase authentication token  
        kb_env: KBase environment

    Returns:
        Object metadata
    """
    client = KBaseClient(auth_token, kb_env)
    return client.get_object(object_ref)

