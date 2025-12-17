"""
KBase Workspace and Blobstore utilities for retrieving BERDLTables objects.

This module uses KBUtilLib to interact with KBase services for:
- Fetching BERDLTables objects from Workspace
- Downloading SQLite databases from Blobstore
- Caching databases locally

Key Flow:
1. User provides berdl_table_id (workspace ref like "76990/ADP1Test")
2. Fetch object from Workspace API via KBUtilLib
3. Extract pangenome_data with handle_ref
4. Download SQLite from Blobstore using download_blob_file
5. Cache locally for efficient repeated queries

Requires: lib/KBUtilLib cloned locally
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests

# Add KBUtilLib to path
LIB_PATH = Path(__file__).parent.parent.parent / "lib" / "KBUtilLib" / "src"
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

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
        cache_dir: Optional[Path] = None
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
        try:
            from kbutillib.kb_ws_utils import KBWSUtils
            from kbutillib.notebook_utils import NotebookUtils
            
            # Create a proper combined class
            cache_dir = self.cache_dir
            kb_env = self.kb_env
            token = self.token
            
            class NotebookUtil(NotebookUtils, KBWSUtils):
                def __init__(self):
                    super().__init__(
                        notebook_folder=str(cache_dir),
                        name="TableScanner",
                        kb_version=kb_env,
                        token=token
                    )
            
            self._client = NotebookUtil()
            self._use_kbutillib = True
            logger.info(f"KBUtilLib client initialized for {self.kb_env}")
            
        except Exception as e:
            logger.warning(f"KBUtilLib not available: {e}. Using fallback.")
            self._use_kbutillib = False
            
    def get_object(self, ref: str, ws: Optional[int] = None) -> Dict[str, Any]:
        """
        Get workspace object data.
        
        Args:
            ref: Object reference or name
            ws: Workspace ID (optional if ref is full reference)
            
        Returns:
            Object data dictionary
        """
        if self._use_kbutillib and self._client:
            try:
                return self._client.get_object(ref, ws=ws)
            except Exception as e:
                logger.warning(f"KBUtilLib get_object failed: {e}. Using fallback.")
                return self._get_object_fallback(ref, ws)
        else:
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
                result = self._client.download_blob_file(handle_ref, str(target_path))
                if result:
                    return Path(result)
            except Exception as e:
                logger.warning(f"KBUtilLib download_blob_file failed: {e}. Using fallback.")
                
        return Path(self._download_blob_fallback(handle_ref, str(target_path)))
    
    # =========================================================================
    # FALLBACK METHODS (Direct API calls)
    # =========================================================================
    
    def _get_endpoints(self) -> Dict[str, str]:
        """Get endpoints for current environment."""
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
    
    def _get_object_fallback(self, ref: str, ws: Optional[int] = None) -> Dict[str, Any]:
        """Get workspace object via direct API call."""
        # Build reference
        if ws and "/" not in str(ref):
            ref = f"{ws}/{ref}"
            
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json"
        }
        
        payload = {
            "method": "Workspace.get_objects2",
            "params": [{"objects": [{"ref": ref}]}],
            "version": "1.1",
            "id": "tablescanner-1"
        }
        
        endpoints = self._get_endpoints()
        response = requests.post(
            endpoints["workspace"],
            json=payload,
            headers=headers,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            raise ValueError(result["error"].get("message", "Unknown error"))
            
        data_list = result.get("result", [{}])[0].get("data", [])
        if not data_list:
            raise ValueError(f"No data for: {ref}")
            
        return data_list[0]
    
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
                headers={"Authorization": self.token, "Content-Type": "application/json"},
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
) -> Dict[str, Any]:
    """
    Fetch BERDLTables object and extract pangenome information.

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
    client = KBaseClient(auth_token, kb_env)
    obj = client.get_object(berdl_table_id)
    
    # Handle nested data structures
    if isinstance(obj, dict) and "data" in obj:
        return obj["data"]
    return obj


def list_pangenomes_from_object(
    berdl_table_id: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> List[Dict[str, Any]]:
    """
    List all pangenomes from a BERDLTables object.

    Args:
        berdl_table_id: KBase workspace reference
        auth_token: KBase authentication token
        kb_env: KBase environment

    Returns:
        List of pangenome info dictionaries with:
        - pangenome_id
        - pangenome_taxonomy
        - handle_ref
        - user_genomes
        - berdl_genomes
    """
    obj_data = get_berdl_table_data(berdl_table_id, auth_token, kb_env)
    
    pangenome_data = obj_data.get("pangenome_data", [])
    
    pangenomes = []
    for pg in pangenome_data:
        pangenomes.append({
            "pangenome_id": pg.get("pangenome_id", ""),
            "pangenome_taxonomy": pg.get("pangenome_taxonomy", ""),
            "user_genomes": pg.get("user_genomes", []),
            "berdl_genomes": pg.get("berdl_genomes", []),
            "genome_count": len(pg.get("user_genomes", [])) + len(pg.get("berdl_genomes", [])),
            "handle_ref": pg.get("sqllite_tables_handle_ref", ""),
        })
    
    return pangenomes


def find_pangenome_handle(
    berdl_table_id: str,
    pangenome_id: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> str:
    """
    Find the handle_ref for a specific pangenome.

    Args:
        berdl_table_id: KBase workspace reference  
        pangenome_id: ID of pangenome to find
        auth_token: KBase authentication token
        kb_env: KBase environment

    Returns:
        Handle reference string (KBH_xxxxx)

    Raises:
        ValueError: If pangenome not found
    """
    pangenomes = list_pangenomes_from_object(berdl_table_id, auth_token, kb_env)
    
    for pg in pangenomes:
        if pg["pangenome_id"] == pangenome_id:
            return pg["handle_ref"]
    
    available = [pg["pangenome_id"] for pg in pangenomes]
    raise ValueError(f"Pangenome '{pangenome_id}' not found. Available: {available}")


def download_pangenome_db(
    berdl_table_id: str,
    pangenome_id: Optional[str],
    auth_token: str,
    cache_dir: Path,
    kb_env: str = "appdev"
) -> Path:
    """
    Download the SQLite database for a pangenome.
    If pangenome_id is None, it is auto-resolved from the BERDL object (1:1 mapping assumed).

    Checks cache first, downloads only if not present.
    """
    from app.utils.cache import is_cached, get_cache_paths
    
    cache_dir = Path(cache_dir)
    safe_id = berdl_table_id.replace("/", "_").replace(":", "_")
    db_dir = cache_dir / safe_id
    
    # 1. Resolve ID and Handle if not provided
    target_id = pangenome_id
    handle_ref = None
    
    # We always need the ID for the filename.
    # If pangenome_id is missing, we must fetch the object metadata to get it.
    # If pangenome_id IS provided, we might still need to fetch object to get the handle (unless cached).
    
    # Optimization: If pangenome_id is provided, check if file exists. 
    # If so, we don't need to fetch metadata.
    if target_id:
        db_path = db_dir / f"{target_id}.db"
        if db_path.exists():
            logger.info(f"Using cached database: {db_path}")
            return db_path

    # If not cached or ID unknown, we must fetch metadata
    pangenomes = list_pangenomes_from_object(berdl_table_id, auth_token, kb_env)
    if not pangenomes:
        raise ValueError(f"No pangenomes found in {berdl_table_id}")
        
    if target_id:
        # Verify and find handle
        found = next((p for p in pangenomes if p["pangenome_id"] == target_id), None)
        if not found:
            raise ValueError(f"Pangenome '{target_id}' not found in {berdl_table_id}")
        handle_ref = found["handle_ref"]
    else:
        # Auto-resolve: take the first one
        found = pangenomes[0]
        target_id = found["pangenome_id"]
        handle_ref = found["handle_ref"]
        
    # Re-check cache with resolved ID
    db_path = db_dir / f"{target_id}.db"
    if db_path.exists():
        logger.info(f"Using cached database: {db_path} (resolved ID: {target_id})")
        return db_path
    
    # Download
    client = KBaseClient(auth_token, kb_env, cache_dir)
    db_path = client.download_blob_file(handle_ref, db_path)
    
    logger.info(f"Downloaded database to: {db_path}")
    return db_path


def get_object_info(
    object_ref: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> Dict[str, Any]:
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
