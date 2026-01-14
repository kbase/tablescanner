"""
Fallback Config Registry.

Maps KBase object types to built-in configuration files.
Used when AI generation fails or for known object types.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Directory containing built-in config files
CONFIG_DIR = Path(__file__).parent

# Object type patterns mapped to config file names
# Supports wildcards like "KBaseFBA.GenomeDataLakeTables-*"
FALLBACK_CONFIG_PATTERNS: dict[str, str] = {
    # BERDL/Pangenome tables
    r"KBaseGeneDataLakes\.BERDLTables.*": "berdl_tables.json",
    r"KBaseGeneDataLakes\.PangenomeTables.*": "berdl_tables.json",
    
    # Genome data tables
    r"KBaseFBA\.GenomeDataLakeTables.*": "genome_data_tables.json",
    r"KBase\.GenomeDataTables.*": "genome_data_tables.json",
    
    # Legacy patterns
    r".*BERDLTables.*": "berdl_tables.json",
    r".*GenomeDataTables.*": "genome_data_tables.json",
}

# Pre-compiled patterns for performance
_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern), filename)
    for pattern, filename in FALLBACK_CONFIG_PATTERNS.items()
]

# Cache loaded configs
_CONFIG_CACHE: dict[str, dict] = {}


def get_fallback_config(object_type: str | None) -> dict[str, Any] | None:
    """
    Get a built-in fallback config for the given object type.
    
    Args:
        object_type: KBase object type string (e.g., "KBaseGeneDataLakes.BERDLTables-1.0")
        
    Returns:
        Config dictionary if a fallback exists, None otherwise
    """
    if not object_type:
        return None
    
    # Try to match against patterns
    for pattern, filename in _COMPILED_PATTERNS:
        if pattern.match(object_type):
            return load_config_file(filename)
    
    return None


def get_fallback_config_id(object_type: str | None) -> str | None:
    """
    Get the config ID that would be used for fallback.
    
    Args:
        object_type: KBase object type string
        
    Returns:
        Config ID (filename without extension) if match found, None otherwise
    """
    if not object_type:
        return None
    
    for pattern, filename in _COMPILED_PATTERNS:
        if pattern.match(object_type):
            return filename.replace(".json", "")
    
    return None


def has_fallback_config(object_type: str | None) -> bool:
    """
    Check if a fallback config exists for the object type.
    
    Args:
        object_type: KBase object type string
        
    Returns:
        True if fallback exists
    """
    return get_fallback_config_id(object_type) is not None


def load_config_file(filename: str) -> dict[str, Any] | None:
    """
    Load a config file from the configs directory.
    
    Args:
        filename: Name of the config file (e.g., "berdl_tables.json")
        
    Returns:
        Parsed config dictionary, or None if not found
    """
    # Check cache first
    if filename in _CONFIG_CACHE:
        return _CONFIG_CACHE[filename]
    
    config_path = CONFIG_DIR / filename
    
    if not config_path.exists():
        logger.warning(f"Fallback config not found: {config_path}")
        return None
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Cache for future use
        _CONFIG_CACHE[filename] = config
        logger.debug(f"Loaded fallback config: {filename}")
        return config
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in fallback config {filename}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading fallback config {filename}: {e}")
        return None


def list_available_configs() -> list[dict[str, Any]]:
    """
    List all available built-in configs.
    
    Returns:
        List of config info dictionaries
    """
    configs = []
    
    for json_file in CONFIG_DIR.glob("*.json"):
        try:
            config = load_config_file(json_file.name)
            if config:
                configs.append({
                    "filename": json_file.name,
                    "id": config.get("id", json_file.stem),
                    "name": config.get("name", json_file.stem),
                    "version": config.get("version", "1.0.0"),
                    "tables": list(config.get("tables", {}).keys()),
                })
        except Exception as e:
            logger.warning(f"Error reading config {json_file}: {e}")
    
    return configs


def get_config_for_tables(table_names: list[str]) -> dict[str, Any] | None:
    """
    Try to find a fallback config that matches the given table names.
    
    Args:
        table_names: List of table names in the database
        
    Returns:
        Best matching config or None
    """
    if not table_names:
        return None
    
    table_set = set(t.lower() for t in table_names)
    best_match = None
    best_score = 0
    
    for json_file in CONFIG_DIR.glob("*.json"):
        config = load_config_file(json_file.name)
        if not config:
            continue
        
        config_tables = set(t.lower() for t in config.get("tables", {}).keys())
        
        # Calculate overlap score
        intersection = len(table_set & config_tables)
        if intersection > best_score:
            best_score = intersection
            best_match = config
    
    # Require at least 50% table match
    if best_match and best_score >= len(table_set) * 0.5:
        return best_match
    
    return None


def clear_cache() -> None:
    """Clear the config cache (useful for testing)."""
    _CONFIG_CACHE.clear()
