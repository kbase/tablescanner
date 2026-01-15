#!/usr/bin/env python3
"""
Migration Script: Import Fallback Configs as Builtin Configs

This script migrates existing fallback JSON configs (berdl_tables.json, etc.)
into the Config Control Plane as published builtin configurations.

Usage:
    python scripts/migrate_fallback_configs.py

This ensures backward compatibility while transitioning to the unified
Config Control Plane architecture.
"""

import json
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.config_store import get_config_store
from app.models import ConfigCreateRequest, ConfigSourceType
from app.configs.fallback_registry import (
    list_available_configs,
    load_config_file,
    FALLBACK_CONFIG_PATTERNS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_object_type_for_config(config_filename: str) -> str | None:
    """
    Determine the KBase object type pattern for a config file.
    
    Args:
        config_filename: Name of the config file (e.g., "berdl_tables.json")
        
    Returns:
        Object type pattern or None
    """
    # Reverse lookup: find pattern that matches this filename
    for pattern, filename in FALLBACK_CONFIG_PATTERNS.items():
        if filename == config_filename:
            # Extract object type from pattern
            # Patterns like "KBaseGeneDataLakes\.BERDLTables.*"
            if "BERDLTables" in pattern:
                return "KBaseGeneDataLakes.BERDLTables-1.0"
            elif "GenomeDataTables" in pattern or "GenomeDataLakeTables" in pattern:
                return "KBaseFBA.GenomeDataLakeTables-1.0"
    
    return None


def migrate_fallback_configs() -> int:
    """
    Migrate all fallback configs to Config Control Plane as builtins.
    
    Returns:
        Number of configs migrated
    """
    store = get_config_store()
    configs = list_available_configs()
    
    migrated_count = 0
    
    for config_info in configs:
        filename = config_info["filename"]
        config_id = config_info["id"]
        config_data = load_config_file(filename)
        
        if not config_data:
            logger.warning(f"Skipping {filename}: failed to load")
            continue
        
        # Check if already migrated
        object_type = get_object_type_for_config(filename)
        source_ref = f"builtin:{config_id}"
        
        # Check for existing published builtin
        existing = store.resolve(source_ref, object_type=object_type)
        if existing and existing.state.value == "published":
            logger.info(f"Skipping {filename}: already migrated as {existing.id}")
            continue
        
        try:
            # Create as builtin config
            create_request = ConfigCreateRequest(
                source_type=ConfigSourceType.BUILTIN,
                source_ref=source_ref,
                config=config_data,
                object_type=object_type,
                change_summary=f"Migrated from fallback config: {filename}",
            )
            
            # Create draft
            record = store.create(create_request, "system:migration")
            logger.info(f"Created draft config: {record.id} for {filename}")
            
            # Auto-propose
            record = store.propose(record.id, "system:migration")
            logger.info(f"Proposed config: {record.id}")
            
            # Auto-publish
            record = store.publish(record.id, "system:migration")
            logger.info(f"Published builtin config: {record.id} ({config_id})")
            
            migrated_count += 1
            
        except Exception as e:
            logger.error(f"Failed to migrate {filename}: {e}", exc_info=True)
            continue
    
    return migrated_count


def main():
    """Main entry point."""
    logger.info("Starting fallback config migration...")
    
    try:
        count = migrate_fallback_configs()
        logger.info(f"Migration complete: {count} config(s) migrated")
        
        if count > 0:
            logger.info("\nMigrated configs are now available via:")
            logger.info("  GET /config/list?source_type=builtin&state=published")
            logger.info("  GET /config/resolve/{source_ref}?object_type={object_type}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
