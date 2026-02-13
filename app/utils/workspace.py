import os
import sys
import logging
import time
import shutil
import requests
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from app.config import settings
from app.utils.cache import get_upa_cache_path

# Add KBUtilLib to path if needed (for potential future use or type hinting)
try:
    current_file = Path(__file__).resolve()
    root_dir = current_file.parent.parent.parent
    lib_path = root_dir / "lib" / "KBUtilLib" / "src"
    if lib_path.exists() and str(lib_path) not in sys.path:
        sys.path.append(str(lib_path))
except Exception:
    pass

logger = logging.getLogger(__name__)


class KBaseClient:
    """
    KBase API client.
    
    Uses direct API calls with requests.Session(trust_env=False) to ensure
    robust connectivity and bypass potential proxy/network stalling issues
    observed with standard library usage in this environment.
    """
    
    def __init__(
        self,
        token: str | None,
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
        self._handle_cache: dict[str, str] = {}  # KBH_xxx -> Shock node UUID
        
    def _workspace_auth_header(self) -> str:
        """Return Authorization header value.
        
        KBase workspace API expects just the token string, NOT "Bearer <token>".
        This method ensures we send the raw token without any prefix.
        """
        if not self.token:
            return ""
        # Ensure we strip any Bearer prefix that might have been passed incorrectly
        token = self.token.strip()
        if token.startswith("Bearer "):
            token = token[7:].strip()
        return token

    def _get_endpoints(self) -> dict[str, str]:
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
    
    def get_object(self, ref: str, ws: int | None = None) -> dict[str, Any]:
        """
        Get workspace object data.
        """
        import time
        # Build reference
        if ws and "/" not in str(ref):
            ref = f"{ws}/{ref}"
        
        logger.info(f"[_get_object] Starting request for {ref}")
        start_time = time.time()
            
        headers = {
            "Authorization": self._workspace_auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "method": "Workspace.get_objects2",
            "params": [{"objects": [{"ref": ref}]}],
            "version": "1.1",
            "id": f"tablescanner-{uuid4()}"
        }
        
        endpoints = self._get_endpoints()
        workspace_url = endpoints["workspace"]
        
        # Use (connect, read) timeouts
        timeout_connect, timeout_read = 10, 60
        
        try:
            # Use a session to ensure clean connection handling and bypass proxies
            with requests.Session() as session:
                session.trust_env = False  # Critical for avoiding stalls
                response = session.post(
                    workspace_url,
                    json=payload,
                    headers=headers,
                    timeout=(timeout_connect, timeout_read)
                )
            
            if response.status_code != 200:
                logger.error(f"Workspace error: {response.status_code} - {response.text[:200]}")
                response.raise_for_status()
                
            result = response.json()
            
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                raise ValueError(f"Workspace API error: {error_msg}")
                
            data_list = result.get("result", [{}])[0].get("data", [])
            if not data_list:
                raise ValueError(f"No data for: {ref}")
                
            return data_list[0]
            
        except Exception as e:
            logger.error(f"[_get_object] Failed for {ref}: {e}")
            raise

    def get_object_info(self, ref: str) -> dict[str, Any]:
        """
        Get object info. (Legacy wrapper returning data to match previous behavior).
        """
        return self.get_object(ref)

    def get_object_type(self, ref: str) -> str:
        """
        Get object type string.
        """
        headers = {
            "Authorization": self._workspace_auth_header(),
            "Content-Type": "application/json"
        }
        payload = {
            "method": "Workspace.get_object_info3",
            "params": [{"objects": [{"ref": ref}]}],
            "version": "1.1",
            "id": f"tablescanner-type-{uuid4()}"
        }
        
        endpoints = self._get_endpoints()
        try:
            with requests.Session() as s:
                s.trust_env = False
                resp = s.post(
                    endpoints["workspace"],
                    json=payload,
                    headers=headers,
                    timeout=(10, 25)
                )
                resp.raise_for_status()
                result = resp.json()
                
            infos = result.get("result", [{}])[0].get("infos", [])
            if infos and infos[0] and len(infos[0]) > 2:
                return infos[0][2]
        except Exception as e:
            logger.warning(f"Error getting type for {ref}: {e}")
            
        return "Unknown"
        
    def _resolve_handle(self, handle_ref: str, endpoints: dict[str, str]) -> str:
        """Resolve handle to Shock node ID."""
        if handle_ref in self._handle_cache:
            return self._handle_cache[handle_ref]
        
        # KBase handle service expects just the token (no Bearer/OAuth prefix)
        token = self.token or ""
        if token.startswith("Bearer "):
            token = token[7:].strip()
        auth_header = {"Authorization": token, "Content-Type": "application/json"}
        
        # Try fetch_handles_by
        payload = {
            "method": "AbstractHandle.fetch_handles_by",
            "params": [{"elements": [handle_ref], "field_name": "hid"}],
            "version": "1.1",
            "id": str(uuid4())
        }
        
        try:
            with requests.Session() as s:
                s.trust_env = False
                resp = s.post(
                    endpoints["handle"],
                    json=payload,
                    headers=auth_header,
                    timeout=(10, 25)
                )
                resp.raise_for_status()
                handles = resp.json().get("result", [[]])[0]
                if handles:
                    node_id = handles[0].get("id")
                    if node_id:
                        self._handle_cache[handle_ref] = node_id
                        return node_id
        except Exception as e:
            logger.warning(f"Handle resolution failed: {e}")
            
        raise ValueError(f"Could not resolve handle {handle_ref}")

    def download_blob_file(self, handle_ref: str, target_path: str) -> str:
        """
        Download file from blobstore.
        
        KBase Shock API requires "OAuth <token>" format (not just token).
        """
        endpoints = self._get_endpoints()
        shock_id = self._resolve_handle(handle_ref, endpoints)
        
        # Shock API requires "OAuth <token>" format
        token = self.token or ""
        if token.startswith("Bearer "):
            token = token[7:].strip()
        if token.startswith("OAuth "):
            token = token[6:].strip()
        headers = {"Authorization": f"OAuth {token}"}
        download_url = f"{endpoints['shock']}/node/{shock_id}?download_raw"
        
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with requests.Session() as s:
                s.trust_env = False
                with s.get(download_url, headers=headers, stream=True, timeout=(10, 300)) as r:
                    r.raise_for_status()
                    with open(target_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            
            return target_path
        except Exception as e:
            logger.error(f"Download failed for {handle_ref}: {e}")
            raise
    
    def get_object_with_type(self, ref: str) -> tuple[dict[str, Any], str]:
        obj_type = self.get_object_type(ref)
        obj_data = self.get_object(ref)
        return obj_data, obj_type


# =============================================================================
# HIGH-LEVEL FUNCTIONS
# =============================================================================

def get_berdl_table_data(
    berdl_table_id: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> dict[str, Any]:
    client = KBaseClient(auth_token, kb_env)
    return client.get_object(berdl_table_id)


def get_object_type(
    berdl_table_id: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> str:
    if berdl_table_id.startswith("local:"):
        return "LocalDatabase"
    client = KBaseClient(auth_token, kb_env)
    return client.get_object_type(berdl_table_id)

def get_object_info(
    object_ref: str,
    auth_token: str,
    kb_env: str = "appdev"
) -> dict[str, Any]:
    client = KBaseClient(auth_token, kb_env)
    return client.get_object(object_ref)


def download_db(
    berdl_table_id: str,
    auth_token: str,
    cache_dir: Path,
    kb_env: str = "appdev"
) -> Path:
    cache_dir = Path(cache_dir)
    db_dir = get_upa_cache_path(cache_dir, berdl_table_id)
    db_path = db_dir / "tables.db"
    
    if db_path.exists():
        return db_path
    
    client = KBaseClient(auth_token, kb_env)
    obj_data = client.get_object(berdl_table_id)
    
    if "pangenome_data" not in obj_data and "data" in obj_data:
        obj_data = obj_data["data"]
        
    pangenome_data = obj_data.get("pangenome_data", [])
    if not pangenome_data:
         raise ValueError(f"No pangenomes found in {berdl_table_id}")

    handle_ref = pangenome_data[0].get("sqllite_tables_handle_ref")
    if not handle_ref:
        raise ValueError(f"No handle reference found in {berdl_table_id}")
    
    db_dir.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
    
    try:
        client.download_blob_file(handle_ref, str(temp_path))
        temp_path.rename(db_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    
    return db_path


def download_multi_dbs(
    berdl_table_id: str,
    auth_token: str,
    cache_dir: Path,
    kb_env: str = "appdev"
) -> list[dict]:
    cache_dir = Path(cache_dir)
    base_dir = get_upa_cache_path(cache_dir, berdl_table_id)
    
    client = KBaseClient(auth_token, kb_env)
    obj_data = client.get_object(berdl_table_id)
    if "pangenome_data" not in obj_data and "data" in obj_data:
        obj_data = obj_data["data"]
        
    pangenome_data = obj_data.get("pangenome_data", [])
    if not pangenome_data:
        raise ValueError(f"No pangenomes found in {berdl_table_id}")
    
    databases = []
    
    for idx, pg in enumerate(pangenome_data):
        handle_ref = pg.get("sqllite_tables_handle_ref")
        if not handle_ref:
            continue
            
        db_name = pg.get("pangenome_id") or f"db_{idx}"
        db_display_name = pg.get("pangenome_taxonomy") or db_name
        
        db_dir = base_dir / db_name
        db_path = db_dir / "tables.db"
        
        if db_path.exists():
            databases.append({
                "db_name": db_name,
                "db_display_name": db_display_name,
                "db_path": db_path,
                "handle_ref": handle_ref
            })
            continue
            
        db_dir.mkdir(parents=True, exist_ok=True)
        temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
        
        try:
            client.download_blob_file(handle_ref, str(temp_path))
            temp_path.rename(db_path)
            databases.append({
                "db_name": db_name,
                "db_display_name": db_display_name,
                "db_path": db_path,
                "handle_ref": handle_ref
            })
        except Exception as e:
            logger.error(f"Failed to download {db_name}: {e}")
            if temp_path.exists():
                temp_path.unlink()
            continue
            
    return databases


def download_db_multi(
    berdl_table_id: str,
    db_name: str,
    auth_token: str,
    cache_dir: Path,
    kb_env: str = "appdev"
) -> dict[str, Any]:
    cache_dir = Path(cache_dir)
    base_dir = get_upa_cache_path(cache_dir, berdl_table_id)
    
    # Fast path: check cache first
    db_dir = base_dir / db_name
    db_path = db_dir / "tables.db"
    
    if db_path.exists():
        return {
            "db_name": db_name,
            "db_display_name": db_name,
            "db_path": db_path,
            "handle_ref": None
        }
        
    client = KBaseClient(auth_token, kb_env)
    
    obj_data = client.get_object(berdl_table_id)
    if "pangenome_data" not in obj_data and "data" in obj_data:
        obj_data = obj_data["data"]
        
    pangenome_data = obj_data.get("pangenome_data", [])
    
    target_pg = None
    for pg in pangenome_data:
        if pg.get("pangenome_id") == db_name:
            target_pg = pg
            break
            
    if not target_pg:
        raise ValueError(f"Database {db_name} not found in {berdl_table_id}")
        
    handle_ref = target_pg.get("sqllite_tables_handle_ref")
    if not handle_ref:
        raise ValueError(f"No handle for database {db_name}")
        
    db_display_name = target_pg.get("pangenome_taxonomy") or db_name
    
    db_dir.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_suffix(f".{uuid4().hex}.tmp")
    
    try:
        client.download_blob_file(handle_ref, str(temp_path))
        temp_path.rename(db_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
        
    return {
        "db_name": db_name,
        "db_display_name": db_display_name,
        "db_path": db_path,
        "handle_ref": handle_ref
    }
