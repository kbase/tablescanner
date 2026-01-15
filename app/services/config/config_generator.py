"""
Config Generator.

Generates DataTables_Viewer-compatible JSON configurations from
analyzed database schemas and AI-enhanced column inferences.

Output matches the DataTypeConfig interface from the viewer's schema.ts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ..ai.ai_provider import AIProvider, ColumnInference, get_ai_provider
from ..data.schema_analyzer import SchemaAnalyzer, TableProfile
from ..data.fingerprint import DatabaseFingerprint

logger = logging.getLogger(__name__)


# =============================================================================
# CATEGORY DEFINITIONS
# =============================================================================

@dataclass
class CategoryConfig:
    """Category configuration matching viewer CategorySchema."""
    id: str
    name: str
    icon: str = "bi-folder"
    color: str = "#6366f1"
    description: str = ""
    defaultVisible: bool = True
    order: int = 1
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
            "defaultVisible": self.defaultVisible,
            "order": self.order,
        }


# Standard categories used across configs
STANDARD_CATEGORIES: dict[str, CategoryConfig] = {
    "core": CategoryConfig(
        id="core",
        name="Core Info",
        icon="bi-database",
        color="#6366f1",
        description="Essential identifiers and names",
        order=1,
    ),
    "functional": CategoryConfig(
        id="functional",
        name="Functional Annotation",
        icon="bi-gear",
        color="#22c55e",
        description="Function and product information",
        order=2,
    ),
    "external": CategoryConfig(
        id="external",
        name="External Links",
        icon="bi-box-arrow-up-right",
        color="#06b6d4",
        description="Links to external databases",
        order=3,
    ),
    "sequence": CategoryConfig(
        id="sequence",
        name="Sequence Data",
        icon="bi-text-left",
        color="#f59e0b",
        description="DNA, RNA, and protein sequences",
        order=4,
    ),
    "expression": CategoryConfig(
        id="expression",
        name="Expression Values",
        icon="bi-graph-up",
        color="#ef4444",
        description="Gene expression measurements",
        order=5,
    ),
    "statistics": CategoryConfig(
        id="statistics",
        name="Statistics",
        icon="bi-calculator",
        color="#8b5cf6",
        description="Statistical measures and significance",
        order=6,
    ),
    "experimental": CategoryConfig(
        id="experimental",
        name="Experimental Parameters",
        icon="bi-sliders",
        color="#f59e0b",
        description="Experimental conditions",
        order=7,
    ),
    "media": CategoryConfig(
        id="media",
        name="Media Composition",
        icon="bi-droplet",
        color="#3b82f6",
        description="Growth media and supplements",
        order=8,
    ),
    "metadata": CategoryConfig(
        id="metadata",
        name="System Metadata",
        icon="bi-info-circle",
        color="#64748b",
        description="System tags and metadata",
        defaultVisible=False,
        order=10,
    ),
    "data": CategoryConfig(
        id="data",
        name="Data",
        icon="bi-table",
        color="#94a3b8",
        description="General data columns",
        order=9,
    ),
}


# =============================================================================
# CONFIG GENERATOR
# =============================================================================

@dataclass
class GenerationResult:
    """Result from config generation."""
    config: dict
    fingerprint: str
    tables_analyzed: int
    columns_inferred: int
    ai_provider_used: str | None
    generation_time_ms: float
    cache_hit: bool


class ConfigGenerator:
    """
    Generates DataTables_Viewer-compatible configurations.
    
    Combines schema analysis with AI-enhanced inference to produce
    complete JSON configs matching the viewer's DataTypeConfig schema.
    """
    
    def __init__(
        self,
        ai_provider: AIProvider | None = None,
        config_dir: str | Path | None = None,
    ) -> None:
        """
        Initialize the config generator.
        
        Args:
            ai_provider: AI provider for enhanced inference (auto if None)
            config_dir: Directory for caching generated configs
        """
        self._ai_provider = ai_provider
        self._schema_analyzer = SchemaAnalyzer(sample_size=10)
        self._fingerprinter = DatabaseFingerprint(config_dir)
    
    def generate(
        self,
        db_path: Path,
        handle_ref: str | None = None,
        force_regenerate: bool = False,
        ai_preference: str = "auto",
    ) -> GenerationResult:
        """
        Generate a complete viewer config for a database.
        
        Args:
            db_path: Path to the SQLite database
            handle_ref: Optional KBase handle reference for identification
            force_regenerate: Skip cache and regenerate
            ai_preference: AI provider preference
            
        Returns:
            GenerationResult with config and metadata
        """
        import time
        start_time = time.time()
        
        # Analyze database schema
        profiles = self._schema_analyzer.analyze_database(db_path)
        
        # Compute fingerprint
        fingerprint = self._fingerprinter.compute_from_profiles(profiles)
        if handle_ref:
            safe_handle = handle_ref.replace("/", "_").replace(":", "_")
            fingerprint = f"{safe_handle}_{fingerprint}"
        
        # Check cache
        if not force_regenerate:
            cached = self._fingerprinter.get_cached_config(fingerprint)
            if cached:
                logger.info(f"Using cached config for {fingerprint}")
                return GenerationResult(
                    config=cached,
                    fingerprint=fingerprint,
                    tables_analyzed=len(profiles),
                    columns_inferred=sum(len(t.columns) for t in profiles),
                    ai_provider_used=None,
                    generation_time_ms=(time.time() - start_time) * 1000,
                    cache_hit=True,
                )
        
        # Get AI provider
        ai_provider = self._ai_provider or get_ai_provider(ai_preference)
        provider_name = ai_provider.name if ai_provider else None
        
        # Generate config
        config = self._build_config(
            profiles=profiles,
            fingerprint=fingerprint,
            handle_ref=handle_ref,
            ai_provider=ai_provider,
        )
        
        # Cache the result
        self._fingerprinter.cache_config(fingerprint, config)
        
        generation_time = (time.time() - start_time) * 1000
        
        return GenerationResult(
            config=config,
            fingerprint=fingerprint,
            tables_analyzed=len(profiles),
            columns_inferred=sum(len(t.columns) for t in profiles),
            ai_provider_used=provider_name,
            generation_time_ms=generation_time,
            cache_hit=False,
        )
    
    def generate_for_table(
        self,
        db_path: Path,
        table_name: str,
        ai_preference: str = "auto",
    ) -> dict:
        """
        Generate config for a single table.
        
        Args:
            db_path: Path to the SQLite database
            table_name: Name of the table
            ai_preference: AI provider preference
            
        Returns:
            TableSchema-compatible dict
        """
        profile = self._schema_analyzer.analyze_table(db_path, table_name)
        ai_provider = self._ai_provider or get_ai_provider(ai_preference)
        
        return self._build_table_config(profile, ai_provider)
    
    # ─── Private Methods ────────────────────────────────────────────────────
    
    def _build_config(
        self,
        profiles: list[TableProfile],
        fingerprint: str,
        handle_ref: str | None,
        ai_provider: AIProvider,
    ) -> dict:
        """Build complete DataTypeConfig."""
        
        # Collect all categories used across tables
        used_categories: set[str] = set()
        tables: dict[str, dict] = {}
        
        for profile in profiles:
            table_config = self._build_table_config(profile, ai_provider)
            tables[profile.name] = table_config
            
            # Track categories
            for col in table_config.get("columns", []):
                for cat in col.get("categories", []):
                    used_categories.add(cat)
        
        # Build shared categories list
        shared_categories = [
            STANDARD_CATEGORIES[cat_id].to_dict()
            for cat_id in sorted(used_categories)
            if cat_id in STANDARD_CATEGORIES
        ]
        
        # Determine name
        name = f"Auto-Generated: {handle_ref}" if handle_ref else f"Auto-Generated Config"
        
        return {
            "id": f"auto_{fingerprint}",
            "name": name,
            "description": f"Automatically generated configuration for {len(profiles)} tables",
            "version": "1.0.0",
            "icon": "bi-database",
            "color": "#6366f1",
            "defaults": {
                "pageSize": 50,
                "density": "default",
                "showRowNumbers": True,
                "enableSelection": True,
                "enableExport": True,
            },
            "sharedCategories": shared_categories,
            "tables": tables,
        }
    
    def _build_table_config(
        self,
        profile: TableProfile,
        ai_provider: AIProvider,
    ) -> dict:
        """Build TableSchema-compatible config for a table."""
        
        # Get AI-enhanced column inferences
        inferences = ai_provider.analyze_columns(profile, profile.columns)
        
        # Build column configs
        columns: list[dict] = []
        for inference in inferences:
            col_config = self._build_column_config(inference)
            columns.append(col_config)
        
        # Determine table icon based on name
        icon = self._infer_table_icon(profile.name)
        
        return {
            "displayName": self._format_table_name(profile.name),
            "description": f"{profile.row_count:,} rows × {profile.column_count} columns",
            "icon": icon,
            "settings": {
                "defaultSortColumn": columns[0]["column"] if columns else None,
                "defaultSortOrder": "asc",
            },
            "columns": columns,
        }
    
    def _build_column_config(self, inference: ColumnInference) -> dict:
        """Build ColumnSchema-compatible config from inference."""
        config: dict[str, Any] = {
            "column": inference.column,
            "displayName": inference.display_name,
            "dataType": inference.data_type,
            "categories": inference.categories,
            "sortable": inference.sortable,
            "filterable": inference.filterable,
        }
        
        # Optional fields
        if inference.copyable:
            config["copyable"] = True
        
        if inference.width != "auto":
            config["width"] = inference.width
        
        if inference.pin:
            config["pin"] = inference.pin
        
        if inference.transform:
            config["transform"] = inference.transform
        
        return config
    
    def _format_table_name(self, name: str) -> str:
        """Convert table name to display name."""
        import re
        # Replace underscores and handle camelCase
        formatted = re.sub(r"_", " ", name)
        formatted = re.sub(r"([a-z])([A-Z])", r"\1 \2", formatted)
        return formatted.title()
    
    def _infer_table_icon(self, name: str) -> str:
        """Infer Bootstrap icon based on table name."""
        name_lower = name.lower()
        
        icons = {
            "gene": "bi-diagram-3",
            "protein": "bi-droplet-half",
            "condition": "bi-thermometer-half",
            "expression": "bi-graph-up",
            "sample": "bi-eyedropper",
            "experiment": "bi-flask",
            "metabolite": "bi-hexagon",
            "pathway": "bi-diagram-2",
            "reaction": "bi-arrow-left-right",
            "compound": "bi-gem",
            "annotation": "bi-tag",
            "sequence": "bi-text-left",
            "alignment": "bi-align-start",
            "variant": "bi-layers",
            "phenotype": "bi-person-badge",
            "trait": "bi-clipboard-data",
            "media": "bi-droplet",
            "strain": "bi-bug",
        }
        
        for keyword, icon in icons.items():
            if keyword in name_lower:
                return icon
        
        return "bi-table"
