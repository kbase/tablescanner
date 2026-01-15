"""
Simple Config Registry.

Tracks which object types have configs in DataTables Viewer.
Used to avoid regenerating configs that already exist.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class ConfigRegistry:
    """
    Simple registry tracking which object types have configs.
    
    This is just a tracking mechanism - actual configs are stored
    in DataTables Viewer. We only track what exists to avoid
    regenerating configs.
    """
    
    def __init__(self, db_path: Path | None = None):
        """Initialize registry."""
        self.db_path = db_path or Path(settings.CACHE_DIR) / "config_registry.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS config_registry (
            object_type TEXT PRIMARY KEY,
            has_config BOOLEAN DEFAULT 1,
            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_config_registry_type ON config_registry(object_type);
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(schema_sql)
            logger.debug(f"Initialized config registry at {self.db_path}")
    
    def has_config(self, object_type: str) -> bool:
        """
        Check if object type has a config in DataTables Viewer.
        
        Args:
            object_type: KBase object type (e.g., "KBaseGeneDataLakes.BERDLTables-1.0")
            
        Returns:
            True if config exists, False otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT has_config FROM config_registry WHERE object_type = ?",
                (object_type,)
            )
            row = cursor.fetchone()
            if row:
                return bool(row["has_config"])
            return False
    
    def mark_has_config(self, object_type: str) -> None:
        """
        Mark that object type has a config.
        
        Args:
            object_type: KBase object type
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO config_registry 
                   (object_type, has_config, last_checked) 
                   VALUES (?, 1, CURRENT_TIMESTAMP)""",
                (object_type,)
            )
            logger.debug(f"Marked {object_type} as having config")
    
    def mark_no_config(self, object_type: str) -> None:
        """
        Mark that object type does not have a config.
        
        Args:
            object_type: KBase object type
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO config_registry 
                   (object_type, has_config, last_checked) 
                   VALUES (?, 0, CURRENT_TIMESTAMP)""",
                (object_type,)
            )
            logger.debug(f"Marked {object_type} as not having config")
    
    def list_registered_types(self) -> list[str]:
        """List all registered object types."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT object_type FROM config_registry WHERE has_config = 1")
            return [row[0] for row in cursor.fetchall()]


# Singleton instance
_registry: ConfigRegistry | None = None


def get_config_registry() -> ConfigRegistry:
    """Get or create the singleton ConfigRegistry instance."""
    global _registry
    if _registry is None:
        _registry = ConfigRegistry()
    return _registry
