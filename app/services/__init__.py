"""
TableScanner Services Package.

This package contains data query and schema analysis services.

Modules:
    - connection_pool: Database connection pooling and management
    - query_service: Enhanced query execution with type-aware filtering
    - schema_service: Schema information retrieval
    - statistics_service: Column statistics computation
    - schema_analyzer: Database schema introspection and profiling
    - fingerprint: Database fingerprinting for caching
"""

from .data.schema_analyzer import SchemaAnalyzer, ColumnProfile, TableProfile
from .data.fingerprint import DatabaseFingerprint

__all__ = [
    # Schema analysis
    "SchemaAnalyzer",
    "ColumnProfile",
    "TableProfile",
    # Fingerprinting
    "DatabaseFingerprint",
]
