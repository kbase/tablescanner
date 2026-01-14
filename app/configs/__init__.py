"""
Built-in Fallback Configs Package.

Contains pre-built DataTables Viewer configurations for known KBase object types.
These are used when AI generation fails or for fast config matching.
"""

from .fallback_registry import (
    get_fallback_config,
    get_fallback_config_id,
    has_fallback_config,
    load_config_file,
    list_available_configs,
    get_config_for_tables,
    clear_cache,
)

__all__ = [
    "get_fallback_config",
    "get_fallback_config_id",
    "has_fallback_config",
    "load_config_file",
    "list_available_configs",
    "get_config_for_tables",
    "clear_cache",
]
