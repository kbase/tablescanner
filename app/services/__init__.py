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

from .data.type_inference import TypeInferenceEngine, InferredType, DataType
from .data.schema_analyzer import SchemaAnalyzer, ColumnProfile, TableProfile
from .ai.ai_provider import (
    AIProvider,
    AIProviderFactory,
    get_ai_provider,
    list_ai_providers,
    ColumnInference,
    ProviderStatus,
)
from .data.fingerprint import DatabaseFingerprint
from .config.config_generator import ConfigGenerator, GenerationResult
from .ai.prompts import build_table_config_prompt, detect_value_patterns, compute_numeric_stats
from .data.validation import validate_config, validate_table_config, validate_ai_response, sanitize_config

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
    # Prompts
    "build_table_config_prompt",
    "detect_value_patterns",
    "compute_numeric_stats",
    # Validation
    "validate_config",
    "validate_table_config",
    "validate_ai_response",
    "sanitize_config",
]
