"""
DataTables Viewer Client.

Sends generated configs to DataTables Viewer for storage.
"""

from __future__ import annotations

import logging
import httpx
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class ViewerClient:
    """
    Client for sending configs to DataTables Viewer.
    
    When AI generates a config, it's sent to DataTables Viewer
    which stores and manages it.
    """
    
    def __init__(self, base_url: str | None = None):
        """
        Initialize viewer client.
        
        Args:
            base_url: DataTables Viewer API base URL
        """
        self.base_url = base_url or getattr(settings, "VIEWER_API_URL", "http://localhost:3000/api")
        self.timeout = 30.0
    
    def send_config(
        self,
        object_type: str,
        source_ref: str,
        config: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Send generated config to DataTables Viewer.
        
        Args:
            object_type: KBase object type
            source_ref: Source reference (e.g., "76990/7/2")
            config: Generated config JSON
            
        Returns:
            Response from viewer API
            
        Raises:
            Exception: If viewer API call fails
        """
        url = f"{self.base_url}/configs"
        
        payload = {
            "object_type": object_type,
            "source_ref": source_ref,
            "config": config,
            "source": "ai_generated"
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Sent config to viewer for {object_type}")
                return result
        except httpx.RequestError as e:
            logger.error(f"Failed to send config to viewer: {e}")
            raise Exception(f"Viewer API error: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"Viewer API returned error: {e.response.status_code}")
            raise Exception(f"Viewer API error: {e.response.status_code}")
    
    def check_config_exists(self, object_type: str) -> bool:
        """
        Check if config exists in DataTables Viewer.
        
        Args:
            object_type: KBase object type
            
        Returns:
            True if config exists, False otherwise
        """
        url = f"{self.base_url}/configs/check"
        params = {"object_type": object_type}
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params)
                if response.status_code == 404:
                    return False
                response.raise_for_status()
                result = response.json()
                return result.get("exists", False)
        except httpx.RequestError:
            logger.warning(f"Could not check config existence in viewer for {object_type}")
            return False
        except httpx.HTTPStatusError:
            return False


# Singleton instance
_viewer_client: ViewerClient | None = None


def get_viewer_client() -> ViewerClient:
    """Get or create the singleton ViewerClient instance."""
    global _viewer_client
    if _viewer_client is None:
        _viewer_client = ViewerClient()
    return _viewer_client
