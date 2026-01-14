"""
Type Inference Engine.

Rule-based pattern detection for inferring column data types and rendering
configurations. This module provides fast, deterministic type inference
without requiring AI, and serves as the foundation for hybrid inference.

Works independently of AI providers and can serve as a fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal
from enum import Enum


class DataType(str, Enum):
    """Column data types matching DataTables_Viewer ColumnDataType."""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TIMESTAMP = "timestamp"
    JSON = "json"
    ARRAY = "array"
    SEQUENCE = "sequence"
    ID = "id"
    URL = "url"
    EMAIL = "email"
    ONTOLOGY = "ontology"
    PERCENTAGE = "percentage"
    FILESIZE = "filesize"
    DURATION = "duration"
    CURRENCY = "currency"
    COLOR = "color"
    IMAGE = "image"
    CUSTOM = "custom"


@dataclass
class TransformConfig:
    """Transform configuration for cell rendering."""
    type: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class InferredType:
    """Result of type inference for a column."""
    data_type: DataType
    display_name: str
    categories: list[str]
    transform: TransformConfig | None = None
    width: str = "auto"
    pin: Literal["left", "right"] | None = None
    sortable: bool = True
    filterable: bool = True
    copyable: bool = False
    confidence: float = 1.0
    source: Literal["rules", "ai", "hybrid"] = "rules"


# =============================================================================
# PATTERN DEFINITIONS
# =============================================================================

# Column name patterns mapped to inference results
NAME_PATTERNS: list[tuple[re.Pattern, dict[str, Any]]] = [
    # IDs - typically pinned left
    (re.compile(r"^(ID|id)$"), {
        "data_type": DataType.ID,
        "categories": ["core"],
        "pin": "left",
        "copyable": True,
        "width": "100px",
    }),
    (re.compile(r".*_ID$|.*_id$|.*Id$"), {
        "data_type": DataType.ID,
        "categories": ["core"],
        "copyable": True,
        "width": "120px",
    }),
    (re.compile(r"^Database_ID$|^database_id$"), {
        "data_type": DataType.ID,
        "categories": ["core"],
        "copyable": True,
        "width": "130px",
    }),
    
    # UniRef IDs - need chain transformer to strip prefix
    (re.compile(r"^uniref_\d+$|^UniRef_\d+$|^uniref\d+$"), {
        "data_type": DataType.ID,
        "categories": ["external"],
        "copyable": True,
        "width": "140px",
        "transform": TransformConfig(
            type="chain",
            options={
                "transforms": [
                    {"type": "replace", "options": {"find": "UniRef:", "replace": ""}},
                    {"type": "link", "options": {
                        "urlTemplate": "https://www.uniprot.org/uniref/{value}",
                        "target": "_blank",
                        "icon": "bi-link-45deg"
                    }}
                ]
            }
        ),
    }),
    
    # External database references with link transforms
    (re.compile(r"^Uniprot.*|^uniprot.*|.*UniProt.*"), {
        "data_type": DataType.ID,
        "categories": ["external"],
        "width": "100px",
        "transform": TransformConfig(
            type="link",
            options={
                "urlTemplate": "https://www.uniprot.org/uniprotkb/{value}",
                "target": "_blank",
                "icon": "bi-link-45deg"
            }
        ),
    }),
    (re.compile(r"^KEGG.*|^kegg.*"), {
        "data_type": DataType.ID,
        "categories": ["external"],
        "width": "90px",
        "transform": TransformConfig(
            type="link",
            options={
                "urlTemplate": "https://www.genome.jp/entry/{value}",
                "target": "_blank"
            }
        ),
    }),
    (re.compile(r"^GO_.*|^go_.*"), {
        "data_type": DataType.ONTOLOGY,
        "categories": ["functional"],
        "width": "180px",
        "transform": TransformConfig(
            type="ontology",
            options={
                "prefix": "GO",
                "urlTemplate": "https://amigo.geneontology.org/amigo/term/{value}",
                "style": "badge"
            }
        ),
    }),
    
    # Pfam domain IDs
    (re.compile(r"^pfam.*|^Pfam.*|^PF\d+"), {
        "data_type": DataType.ID,
        "categories": ["ontology"],
        "width": "100px",
        "transform": TransformConfig(
            type="chain",
            options={
                "transforms": [
                    {"type": "replace", "options": {"find": "pfam:", "replace": ""}},
                    {"type": "link", "options": {
                        "urlTemplate": "https://www.ebi.ac.uk/interpro/entry/pfam/{value}",
                        "target": "_blank",
                        "icon": "bi-link-45deg"
                    }}
                ]
            }
        ),
    }),
    
    # NCBI protein IDs (RefSeq)
    (re.compile(r"^ncbi.*|.*_ncbi.*|^NP_.*|^WP_.*|^XP_.*"), {
        "data_type": DataType.ID,
        "categories": ["external"],
        "copyable": True,
        "width": "120px",
        "transform": TransformConfig(
            type="link",
            options={
                "urlTemplate": "https://www.ncbi.nlm.nih.gov/protein/{value}",
                "target": "_blank",
                "icon": "bi-link-45deg"
            }
        ),
    }),
    
    # Strand indicator (+/-)
    (re.compile(r"^strand$|^Strand$|.*_strand$"), {
        "data_type": DataType.STRING,
        "categories": ["core"],
        "width": "80px",
        "transform": TransformConfig(
            type="badge",
            options={
                "colorMap": {
                    "+": {"color": "#22c55e", "bgColor": "#dcfce7"},
                    "-": {"color": "#ef4444", "bgColor": "#fee2e2"},
                    ".": {"color": "#94a3b8", "bgColor": "#f1f5f9"}
                }
            }
        ),
    }),
    
    # Sequences
    (re.compile(r".*Sequence.*|.*_seq$|.*_Seq$"), {
        "data_type": DataType.SEQUENCE,
        "categories": ["sequence"],
        "sortable": False,
        "filterable": False,
        "copyable": True,
        "width": "150px",
        "transform": TransformConfig(
            type="sequence",
            options={"maxLength": 20, "showCopyButton": True}
        ),
    }),
    
    # Function/product descriptions
    (re.compile(r".*function.*|.*Function.*|.*product.*|.*Product.*"), {
        "data_type": DataType.STRING,
        "categories": ["functional"],
        "width": "300px",
    }),
    
    # Statistical measures with special formatting
    (re.compile(r"^Log2FC$|.*log2.*fold.*|.*Log2.*Fold.*"), {
        "data_type": DataType.FLOAT,
        "categories": ["expression"],
        "width": "130px",
        "transform": TransformConfig(
            type="heatmap",
            options={
                "min": -4, "max": 4,
                "colorScale": "diverging",
                "showValue": True,
                "decimals": 2
            }
        ),
    }),
    (re.compile(r"^P[_-]?[Vv]alue$|^pvalue$|^p_value$"), {
        "data_type": DataType.FLOAT,
        "categories": ["statistics"],
        "width": "100px",
        "transform": TransformConfig(
            type="number",
            options={"notation": "scientific", "decimals": 2}
        ),
    }),
    (re.compile(r"^FDR$|^fdr$|^q[_-]?value$"), {
        "data_type": DataType.FLOAT,
        "categories": ["statistics"],
        "width": "100px",
        "transform": TransformConfig(
            type="number",
            options={"notation": "scientific", "decimals": 2}
        ),
    }),
    
    # Boolean indicators
    (re.compile(r"^Significant$|^is_.*|^has_.*"), {
        "data_type": DataType.BOOLEAN,
        "categories": ["statistics"],
        "width": "90px",
        "transform": TransformConfig(
            type="boolean",
            options={
                "trueIcon": "bi-check-circle-fill",
                "falseIcon": "bi-x-circle",
                "trueColor": "#22c55e",
                "falseColor": "#94a3b8"
            }
        ),
    }),
    
    # Temperature with unit
    (re.compile(r".*Temperature.*|.*_in_C$"), {
        "data_type": DataType.FLOAT,
        "categories": ["experimental"],
        "width": "120px",
        "transform": TransformConfig(
            type="number",
            options={"decimals": 1, "suffix": "°C"}
        ),
    }),
    
    # Concentration fields
    (re.compile(r".*Concentration.*|.*_in_mM$|.*_in_mg.*"), {
        "data_type": DataType.FLOAT,
        "categories": ["media"],
        "width": "120px",
        "transform": TransformConfig(
            type="number",
            options={"decimals": 2}
        ),
    }),
    
    # Name fields
    (re.compile(r"^Name$|^name$|.*_Name$|.*_name$"), {
        "data_type": DataType.STRING,
        "categories": ["core"],
        "width": "200px",
    }),
    
    # URL fields
    (re.compile(r".*_URL$|.*_url$|.*Link$|.*link$"), {
        "data_type": DataType.URL,
        "categories": ["external"],
        "width": "150px",
    }),
]

# Value patterns for detecting types from sample data
VALUE_PATTERNS: list[tuple[re.Pattern, DataType]] = [
    # URLs
    (re.compile(r"^https?://"), DataType.URL),
    # Email
    (re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$"), DataType.EMAIL),
    # GO terms
    (re.compile(r"^GO:\d{7}"), DataType.ONTOLOGY),
    # ISO dates
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), DataType.DATE),
    (re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"), DataType.DATETIME),
    # Colors
    (re.compile(r"^#[0-9a-fA-F]{6}$|^rgb\("), DataType.COLOR),
    # DNA/RNA sequences (long strings of ATCGU only)
    (re.compile(r"^[ATCGU]{20,}$", re.IGNORECASE), DataType.SEQUENCE),
    # Protein sequences (amino acid codes)
    (re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]{20,}$", re.IGNORECASE), DataType.SEQUENCE),
]


# =============================================================================
# TYPE INFERENCE ENGINE
# =============================================================================

class TypeInferenceEngine:
    """
    Rule-based type inference engine.
    
    Analyzes column names and sample values to infer data types,
    display configurations, and rendering transforms without AI.
    """
    
    def __init__(self) -> None:
        self._name_patterns = NAME_PATTERNS
        self._value_patterns = VALUE_PATTERNS
    
    def infer_from_name(self, column_name: str) -> InferredType | None:
        """
        Infer column type from column name patterns.
        
        Args:
            column_name: The name of the column
            
        Returns:
            InferredType if a pattern matches, None otherwise
        """
        for pattern, config in self._name_patterns:
            if pattern.match(column_name):
                return InferredType(
                    data_type=config.get("data_type", DataType.STRING),
                    display_name=self._format_display_name(column_name),
                    categories=config.get("categories", []),
                    transform=config.get("transform"),
                    width=config.get("width", "auto"),
                    pin=config.get("pin"),
                    sortable=config.get("sortable", True),
                    filterable=config.get("filterable", True),
                    copyable=config.get("copyable", False),
                    confidence=0.9,  # High confidence for name pattern match
                    source="rules",
                )
        return None
    
    def infer_from_values(
        self,
        column_name: str,
        sample_values: list[Any],
        sqlite_type: str = "TEXT"
    ) -> InferredType:
        """
        Infer column type from sample values.
        
        Args:
            column_name: The name of the column
            sample_values: List of sample values from the column
            sqlite_type: The SQLite column type
            
        Returns:
            InferredType with inferred configuration
        """
        # First, try name-based inference
        name_inference = self.infer_from_name(column_name)
        if name_inference:
            return name_inference
        
        # Filter out None/empty values for analysis
        valid_values = [v for v in sample_values if v is not None and str(v).strip()]
        
        if not valid_values:
            return self._default_inference(column_name, sqlite_type)
        
        # Check for boolean values
        if self._is_boolean(valid_values):
            return InferredType(
                data_type=DataType.BOOLEAN,
                display_name=self._format_display_name(column_name),
                categories=["metadata"],
                confidence=0.95,
            )
        
        # Check for numeric types based on SQLite type and values
        if sqlite_type in ("INTEGER", "REAL") or self._is_numeric(valid_values):
            return self._infer_numeric(column_name, valid_values, sqlite_type)
        
        # Check value patterns
        str_values = [str(v) for v in valid_values]
        for pattern, data_type in self._value_patterns:
            matches = sum(1 for v in str_values if pattern.match(v))
            if matches / len(str_values) > 0.5:  # >50% match threshold
                return InferredType(
                    data_type=data_type,
                    display_name=self._format_display_name(column_name),
                    categories=self._default_category(data_type),
                    confidence=0.8,
                )
        
        # Default to string
        return self._default_inference(column_name, sqlite_type)
    
    def infer(
        self,
        column_name: str,
        sample_values: list[Any] | None = None,
        sqlite_type: str = "TEXT"
    ) -> InferredType:
        """
        Full inference combining name and value analysis.
        
        Args:
            column_name: The name of the column
            sample_values: Optional list of sample values
            sqlite_type: The SQLite column type
            
        Returns:
            InferredType with best inference
        """
        if sample_values:
            return self.infer_from_values(column_name, sample_values, sqlite_type)
        
        name_inference = self.infer_from_name(column_name)
        if name_inference:
            return name_inference
        
        return self._default_inference(column_name, sqlite_type)
    
    # ─── Helper Methods ─────────────────────────────────────────────────────
    
    def _format_display_name(self, column_name: str) -> str:
        """Convert column name to human-readable display name."""
        # Replace underscores and handle camelCase
        name = re.sub(r"_", " ", column_name)
        name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
        # Title case but preserve acronyms
        words = name.split()
        formatted = []
        for word in words:
            if word.isupper() and len(word) <= 4:  # Likely acronym
                formatted.append(word)
            else:
                formatted.append(word.capitalize())
        return " ".join(formatted)
    
    def _is_boolean(self, values: list[Any]) -> bool:
        """Check if values represent boolean data."""
        bool_values = {"true", "false", "yes", "no", "1", "0", "t", "f", "y", "n"}
        str_values = {str(v).lower() for v in values}
        return str_values.issubset(bool_values) and len(str_values) <= 2
    
    def _is_numeric(self, values: list[Any]) -> bool:
        """Check if all values are numeric."""
        for v in values:
            if v is None:
                continue
            try:
                float(v)
            except (ValueError, TypeError):
                return False
        return True
    
    def _infer_numeric(
        self,
        column_name: str,
        values: list[Any],
        sqlite_type: str
    ) -> InferredType:
        """Infer numeric type details."""
        # Check if all values are integers
        is_integer = all(
            isinstance(v, int) or (isinstance(v, float) and v.is_integer())
            for v in values if v is not None
        )
        
        data_type = DataType.INTEGER if (sqlite_type == "INTEGER" or is_integer) else DataType.FLOAT
        
        return InferredType(
            data_type=data_type,
            display_name=self._format_display_name(column_name),
            categories=["data"],
            width="100px",
            transform=TransformConfig(
                type="number",
                options={"decimals": 0 if is_integer else 2}
            ) if data_type == DataType.FLOAT else None,
            confidence=0.85,
        )
    
    def _default_inference(self, column_name: str, sqlite_type: str) -> InferredType:
        """Return default string inference."""
        # Map SQLite types to data types
        type_map = {
            "INTEGER": DataType.INTEGER,
            "REAL": DataType.FLOAT,
            "BLOB": DataType.CUSTOM,
        }
        
        return InferredType(
            data_type=type_map.get(sqlite_type, DataType.STRING),
            display_name=self._format_display_name(column_name),
            categories=["data"],
            confidence=0.5,
        )
    
    def _default_category(self, data_type: DataType) -> list[str]:
        """Get default categories for a data type."""
        category_map = {
            DataType.ID: ["core"],
            DataType.URL: ["external"],
            DataType.EMAIL: ["external"],
            DataType.ONTOLOGY: ["functional"],
            DataType.SEQUENCE: ["sequence"],
            DataType.DATE: ["metadata"],
            DataType.DATETIME: ["metadata"],
        }
        return category_map.get(data_type, ["data"])
