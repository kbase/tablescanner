"""
Database Fingerprinting.

Creates unique fingerprints from database schema structure for cache
invalidation. Fingerprints are based on schema characteristics, not data,
to enable efficient caching of generated configs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema_analyzer import SchemaAnalyzer, TableProfile

logger = logging.getLogger(__name__)


class DatabaseFingerprint:
    """
    Creates unique fingerprints from database schema structure.
    
    The fingerprint is based on:
    - Table names (sorted)
    - Column names and types for each table
    - Row counts (optional, for change detection)
    
    This allows caching generated configs and detecting when
    a database schema has changed.
    """
    
    def __init__(self, config_dir: str | Path | None = None) -> None:
        """
        Initialize fingerprinting service.
        
        Args:
            config_dir: Directory for storing cached configs
        """
        default_dir = os.getenv("GENERATED_CONFIG_DIR", "/tmp/tablescanner_configs")
        self.config_dir = Path(config_dir or default_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def compute(self, db_path: Path, include_row_counts: bool = False) -> str:
        """
        Compute fingerprint for a database.
        
        Args:
            db_path: Path to the SQLite database
            include_row_counts: Whether to include row counts in fingerprint
                               (makes fingerprint change when data changes)
                               
        Returns:
            SHA256 hex string (first 16 characters)
        """
        analyzer = SchemaAnalyzer(sample_size=0)  # No samples needed
        profiles = analyzer.analyze_database(db_path)
        
        return self.compute_from_profiles(profiles, include_row_counts)
    
    def compute_from_profiles(
        self,
        profiles: list[TableProfile],
        include_row_counts: bool = False
    ) -> str:
        """
        Compute fingerprint from table profiles.
        
        Args:
            profiles: List of TableProfile objects
            include_row_counts: Whether to include row counts
            
        Returns:
            SHA256 hex string (first 16 characters)
        """
        # Build deterministic schema representation
        schema_data: list[dict[str, Any]] = []
        
        for table in sorted(profiles, key=lambda t: t.name):
            table_data: dict[str, Any] = {
                "name": table.name,
                "columns": [
                    {"name": col.name, "type": col.sqlite_type}
                    for col in sorted(table.columns, key=lambda c: c.name)
                ],
            }
            if include_row_counts:
                table_data["row_count"] = table.row_count
            
            schema_data.append(table_data)
        
        # Create deterministic JSON string
        schema_json = json.dumps(schema_data, sort_keys=True, separators=(",", ":"))
        
        # Compute SHA256 hash
        hash_bytes = hashlib.sha256(schema_json.encode()).hexdigest()
        
        # Return first 16 characters for reasonable uniqueness + readability
        return hash_bytes[:16]
    
    def compute_for_handle(self, handle_ref: str, db_path: Path) -> str:
        """
        Compute fingerprint incorporating handle reference.
        
        This creates a unique ID that includes both the source
        handle and the schema structure.
        
        Args:
            handle_ref: The KBase handle reference
            db_path: Path to the SQLite database
            
        Returns:
            Combined fingerprint string
        """
        schema_fp = self.compute(db_path)
        # Sanitize handle ref for use in filenames
        safe_handle = handle_ref.replace("/", "_").replace(":", "_")
        return f"{safe_handle}_{schema_fp}"
    
    # ─── Cache Management ───────────────────────────────────────────────────
    
    def is_cached(self, fingerprint: str) -> bool:
        """Check if a config is cached for this fingerprint."""
        config_path = self._get_cache_path(fingerprint)
        return config_path.exists()
    
    def get_cached_config(self, fingerprint: str) -> dict | None:
        """
        Retrieve cached config for a fingerprint.
        
        Args:
            fingerprint: Database fingerprint
            
        Returns:
            Cached config dict or None if not found
        """
        config_path = self._get_cache_path(fingerprint)
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load cached config {fingerprint}: {e}")
            return None
    
    def cache_config(self, fingerprint: str, config: dict) -> Path:
        """
        Cache a generated config.
        
        Args:
            fingerprint: Database fingerprint
            config: Generated config to cache
            
        Returns:
            Path to the cached config file
        """
        config_path = self._get_cache_path(fingerprint)
        
        # Add metadata
        config_with_meta = {
            "_fingerprint": fingerprint,
            "_cached_at": self._get_timestamp(),
            **config,
        }
        
        with open(config_path, "w") as f:
            json.dump(config_with_meta, f, indent=2)
        
        logger.info(f"Cached config to {config_path}")
        return config_path
    
    def clear_cache(self, fingerprint: str | None = None) -> int:
        """
        Clear cached configs.
        
        Args:
            fingerprint: Specific fingerprint to clear, or None for all
            
        Returns:
            Number of configs cleared
        """
        if fingerprint:
            config_path = self._get_cache_path(fingerprint)
            if config_path.exists():
                config_path.unlink()
                return 1
            return 0
        
        # Clear all
        count = 0
        for config_file in self.config_dir.glob("*.json"):
            config_file.unlink()
            count += 1
        return count
    
    def list_cached(self) -> list[dict[str, Any]]:
        """List all cached configs with metadata."""
        cached: list[dict[str, Any]] = []
        
        for config_file in self.config_dir.glob("*.json"):
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                    cached.append({
                        "fingerprint": config.get("_fingerprint", config_file.stem),
                        "cached_at": config.get("_cached_at"),
                        "id": config.get("id"),
                        "name": config.get("name"),
                        "path": str(config_file),
                    })
            except (json.JSONDecodeError, OSError):
                continue
        
        return cached
    
    # ─── Private Methods ────────────────────────────────────────────────────
    
    def _get_cache_path(self, fingerprint: str) -> Path:
        """Get cache file path for a fingerprint."""
        return self.config_dir / f"{fingerprint}.json"
    
    def _get_timestamp(self) -> str:
        """Get current ISO timestamp."""
        return datetime.now(timezone.utc).isoformat()
