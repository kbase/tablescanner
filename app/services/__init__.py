"""
TableScanner Services Package.

This package contains the AI-powered schema inference and config generation services.

Modules:
    - type_inference: Rule-based pattern detection for column types
    - schema_analyzer: Database schema introspection and profiling
    - ai_provider: Scalable AI backend abstraction layer
    - config_generator: DataTables_Viewer config JSON generation
    - fingerprint: Database fingerprinting for caching
"""

from .type_inference import TypeInferenceEngine, InferredType, DataType
from .schema_analyzer import SchemaAnalyzer, ColumnProfile, TableProfile
from .ai_provider import (
    AIProvider,
    AIProviderFactory,
    get_ai_provider,
    list_ai_providers,
    ColumnInference,
    ProviderStatus,
)
from .fingerprint import DatabaseFingerprint
from .config_generator import ConfigGenerator, GenerationResult

__all__ = [
    # Type inference
    "TypeInferenceEngine",
    "InferredType",
    "DataType",
    # Schema analysis
    "SchemaAnalyzer",
    "ColumnProfile",
    "TableProfile",
    # AI providers
    "AIProvider",
    "AIProviderFactory",
    "get_ai_provider",
    "list_ai_providers",
    "ColumnInference",
    "ProviderStatus",
    # Fingerprinting
    "DatabaseFingerprint",
    # Config generation
    "ConfigGenerator",
    "GenerationResult",
]
