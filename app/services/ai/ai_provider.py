"""
AI Provider Layer.

Scalable abstraction for AI-powered schema inference with multiple backend
support and automatic fallback. Supports:
- OpenAI API (GPT-4o-mini, GPT-4, etc.)
- Argo Gateway (ANL internal)
- Ollama (local LLMs)
- Claude Code CLI
- Rule-based fallback (no AI)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..data.schema_analyzer import ColumnProfile, TableProfile
from ..data.type_inference import DataType, InferredType, TransformConfig, TypeInferenceEngine

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ColumnInference:
    """AI-enhanced column inference result."""
    column: str
    data_type: str
    display_name: str
    categories: list[str]
    transform: dict | None = None
    width: str = "auto"
    pin: Literal["left", "right"] | None = None
    sortable: bool = True
    filterable: bool = True
    copyable: bool = False
    confidence: float = 1.0
    source: Literal["rules", "ai", "hybrid"] = "rules"
    reasoning: str = ""


@dataclass
class ProviderStatus:
    """Status of an AI provider."""
    name: str
    available: bool
    priority: int
    error: str | None = None


# =============================================================================
# ABSTRACT BASE
# =============================================================================

class AIProvider(ABC):
    """Abstract base class for AI providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        ...
    
    @property
    @abstractmethod
    def priority(self) -> int:
        """Provider priority (lower = higher priority)."""
        ...
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and responding."""
        ...
    
    @abstractmethod
    def analyze_columns(
        self,
        table: TableProfile,
        columns: list[ColumnProfile]
    ) -> list[ColumnInference]:
        """
        Analyze columns using AI.
        
        Args:
            table: Table profile with metadata
            columns: List of column profiles to analyze
            
        Returns:
            List of AI-enhanced column inferences
        """
        ...
    
    def get_status(self) -> ProviderStatus:
        """Get provider status."""
        try:
            available = self.is_available()
            return ProviderStatus(
                name=self.name,
                available=available,
                priority=self.priority,
            )
        except Exception as e:
            return ProviderStatus(
                name=self.name,
                available=False,
                priority=self.priority,
                error=str(e),
            )


# =============================================================================
# RULE-BASED PROVIDER (Fallback)
# =============================================================================

class RuleBasedProvider(AIProvider):
    """
    Rule-based inference without AI.
    
    Uses the TypeInferenceEngine for pattern-based type detection.
    Always available as a fallback.
    """
    
    def __init__(self) -> None:
        self._engine = TypeInferenceEngine()
    
    @property
    def name(self) -> str:
        return "rules-only"
    
    @property
    def priority(self) -> int:
        return 100  # Lowest priority (fallback)
    
    def is_available(self) -> bool:
        return True  # Always available
    
    def analyze_columns(
        self,
        table: TableProfile,
        columns: list[ColumnProfile]
    ) -> list[ColumnInference]:
        """Analyze columns using rule-based inference."""
        results: list[ColumnInference] = []
        
        for col in columns:
            inference = self._engine.infer(
                column_name=col.name,
                sample_values=col.sample_values,
                sqlite_type=col.sqlite_type,
            )
            
            results.append(ColumnInference(
                column=col.name,
                data_type=inference.data_type.value,
                display_name=inference.display_name,
                categories=inference.categories,
                transform=self._transform_to_dict(inference.transform),
                width=inference.width,
                pin=inference.pin,
                sortable=inference.sortable,
                filterable=inference.filterable,
                copyable=inference.copyable,
                confidence=inference.confidence,
                source="rules",
                reasoning="Pattern-based inference from column name and sample values",
            ))
        
        return results
    
    def _transform_to_dict(self, transform: TransformConfig | None) -> dict | None:
        """Convert TransformConfig to dict for JSON serialization."""
        if transform is None:
            return None
        return {
            "type": transform.type,
            "options": transform.options,
        }


# =============================================================================
# OPENAI PROVIDER
# =============================================================================

class OpenAIProvider(AIProvider):
    """
    OpenAI API provider.
    
    Uses GPT-4o-mini or other OpenAI models for intelligent schema inference.
    """
    
    SYSTEM_PROMPT = """You are an expert database schema analyst for a scientific data visualization system.
Your task is to analyze column metadata and sample values to determine optimal rendering configurations.

For each column, determine:
1. dataType: One of: string, number, integer, float, boolean, date, datetime, sequence, id, url, email, ontology, percentage
2. displayName: Human-readable name (Title Case)
3. categories: Category groupings like "core", "metadata", "external", "functional", "sequence", "statistics"
4. transform: Rendering transformation if applicable (links, badges, formatting)
5. confidence: 0.0-1.0 confidence score
6. reasoning: Brief explanation

Respond in valid JSON only. No additional text."""

    USER_PROMPT_TEMPLATE = """Analyze this table schema:

TABLE: {table_name}
ROW COUNT: {row_count}

COLUMNS:
{columns_json}

Return a JSON array of column configurations matching this schema:
[
  {{
    "column": "ColumnName",
    "dataType": "string",
    "displayName": "Column Name",
    "categories": ["core"],
    "transform": {{"type": "link", "options": {{"urlTemplate": "https://..."}}}},
    "width": "120px",
    "sortable": true,
    "filterable": true,
    "copyable": false,
    "confidence": 0.9,
    "reasoning": "Description of column appears to contain..."
  }}
]"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.temperature = temperature
        self._client = None
        self._rule_engine = TypeInferenceEngine()
    
    @property
    def name(self) -> str:
        return "openai"
    
    @property
    def priority(self) -> int:
        return 10
    
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            # Try to import openai and create client
            import openai
            self._client = openai.OpenAI(api_key=self.api_key)
            # Quick test with a minimal request
            return True
        except ImportError:
            logger.warning("OpenAI package not installed")
            return False
        except Exception as e:
            logger.warning(f"OpenAI not available: {e}")
            return False
    
    def analyze_columns(
        self,
        table: TableProfile,
        columns: list[ColumnProfile]
    ) -> list[ColumnInference]:
        """Analyze columns using OpenAI."""
        if not self._client:
            if not self.is_available():
                raise RuntimeError("OpenAI provider not available")
        
        # Prepare column data for prompt
        columns_data = []
        for col in columns:
            columns_data.append({
                "name": col.name,
                "type": col.sqlite_type,
                "samples": col.sample_values[:5],
                "null_ratio": round(col.null_ratio, 2),
                "unique_ratio": round(col.unique_ratio, 2),
                "patterns": col.detected_patterns,
            })
        
        prompt = self.USER_PROMPT_TEMPLATE.format(
            table_name=table.name,
            row_count=table.row_count,
            columns_json=json.dumps(columns_data, indent=2),
        )
        
        try:
            import openai
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Handle both array and object with "columns" key
            if isinstance(result, dict) and "columns" in result:
                ai_columns = result["columns"]
            elif isinstance(result, list):
                ai_columns = result
            else:
                logger.warning(f"Unexpected AI response format: {type(result)}")
                return self._fallback_inference(columns)
            
            return self._parse_ai_response(ai_columns, columns)
            
        except Exception as e:
            logger.error(f"OpenAI analysis failed: {e}")
            return self._fallback_inference(columns)
    
    def _parse_ai_response(
        self,
        ai_columns: list[dict],
        original_columns: list[ColumnProfile]
    ) -> list[ColumnInference]:
        """Parse AI response into ColumnInference objects."""
        results: list[ColumnInference] = []
        
        # Create lookup for original columns
        col_map = {col.name: col for col in original_columns}
        
        for ai_col in ai_columns:
            col_name = ai_col.get("column", "")
            if col_name not in col_map:
                continue
            
            results.append(ColumnInference(
                column=col_name,
                data_type=ai_col.get("dataType", "string"),
                display_name=ai_col.get("displayName", col_name),
                categories=ai_col.get("categories", ["data"]),
                transform=ai_col.get("transform"),
                width=ai_col.get("width", "auto"),
                pin=ai_col.get("pin"),
                sortable=ai_col.get("sortable", True),
                filterable=ai_col.get("filterable", True),
                copyable=ai_col.get("copyable", False),
                confidence=ai_col.get("confidence", 0.8),
                source="ai",
                reasoning=ai_col.get("reasoning", ""),
            ))
        
        # Fill in any missing columns with rule-based inference
        covered_cols = {r.column for r in results}
        for col in original_columns:
            if col.name not in covered_cols:
                rule_result = RuleBasedProvider().analyze_columns(
                    TableProfile(name=""), [col]
                )
                if rule_result:
                    results.append(rule_result[0])
        
        return results
    
    def _fallback_inference(self, columns: list[ColumnProfile]) -> list[ColumnInference]:
        """Fall back to rule-based inference."""
        return RuleBasedProvider().analyze_columns(
            TableProfile(name=""), columns
        )


# =============================================================================
# OLLAMA PROVIDER (Local LLM)
# =============================================================================

class OllamaProvider(AIProvider):
    """
    Ollama provider for local LLM inference.
    
    Uses locally running Ollama with models like llama3, codellama, etc.
    """
    
    def __init__(
        self,
        host: str | None = None,
        model: str = "llama3",
    ) -> None:
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model
        self._rule_engine = TypeInferenceEngine()
    
    @property
    def name(self) -> str:
        return "ollama"
    
    @property
    def priority(self) -> int:
        return 30
    
    def is_available(self) -> bool:
        try:
            import httpx
            response = httpx.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def analyze_columns(
        self,
        table: TableProfile,
        columns: list[ColumnProfile]
    ) -> list[ColumnInference]:
        """Analyze columns using Ollama."""
        # Ollama analysis similar to OpenAI but with local API
        # For now, fall back to rule-based to keep implementation focused
        return RuleBasedProvider().analyze_columns(table, columns)


# =============================================================================
# ARGO PROVIDER (ANL Internal)
# =============================================================================

class ArgoProvider(AIProvider):
    """
    ANL Argo Gateway provider.
    
    Wraps the existing ArgoUtils from KBUtilLib.
    """
    
    def __init__(
        self,
        user: str | None = None,
        model: str = "gpt4o",
        proxy_port: int = 1080,
    ) -> None:
        self.user = user or os.getenv("ARGO_USER", "")
        self.model = model
        self.proxy_port = proxy_port
        self._argo_client = None
    
    @property
    def name(self) -> str:
        return "argo"
    
    @property
    def priority(self) -> int:
        return 20
    
    def is_available(self) -> bool:
        if not self.user:
            return False
        try:
            # Try to import and initialize ArgoUtils
            from lib.KBUtilLib.src.kbutillib.argo_utils import ArgoUtils
            self._argo_client = ArgoUtils(
                model=self.model,
                user=self.user,
                proxy_port=self.proxy_port,
            )
            return self._argo_client.ping()
        except ImportError:
            logger.warning("ArgoUtils not available")
            return False
        except Exception as e:
            logger.warning(f"Argo not available: {e}")
            return False
    
    def analyze_columns(
        self,
        table: TableProfile,
        columns: list[ColumnProfile]
    ) -> list[ColumnInference]:
        """Analyze columns using Argo."""
        # Fall back to rule-based for now
        return RuleBasedProvider().analyze_columns(table, columns)


# =============================================================================
# CLAUDE CODE PROVIDER
# =============================================================================

class ClaudeCodeProvider(AIProvider):
    """
    Claude Code CLI provider.
    
    Uses Claude Code executable for local inference.
    """
    
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or os.getenv("CLAUDE_CODE_EXECUTABLE", "claude")
    
    @property
    def name(self) -> str:
        return "claude-code"
    
    @property
    def priority(self) -> int:
        return 25
    
    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [self.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def analyze_columns(
        self,
        table: TableProfile,
        columns: list[ColumnProfile]
    ) -> list[ColumnInference]:
        """Analyze columns using Claude Code."""
        # Fall back to rule-based for now
        return RuleBasedProvider().analyze_columns(table, columns)


# =============================================================================
# PROVIDER FACTORY
# =============================================================================

class AIProviderFactory:
    """
    Factory for creating AI providers with automatic fallback.
    
    Supports configuration via environment variables:
    - AI_PROVIDER: Preferred provider (auto, openai, argo, ollama, claude-code, rules-only)
    - AI_FALLBACK_CHAIN: Comma-separated fallback chain
    """
    
    DEFAULT_CHAIN = "openai,argo,ollama,rules-only"
    
    PROVIDERS = {
        "openai": OpenAIProvider,
        "argo": ArgoProvider,
        "ollama": OllamaProvider,
        "claude-code": ClaudeCodeProvider,
        "rules-only": RuleBasedProvider,
    }
    
    def __init__(self) -> None:
        self._instances: dict[str, AIProvider] = {}
    
    def get_provider(self, preference: str = "auto") -> AIProvider:
        """
        Get an available AI provider.
        
        Args:
            preference: Preferred provider or "auto" for automatic selection
            
        Returns:
            An available AIProvider instance
            
        Raises:
            RuntimeError: If no providers are available
        """
        if preference == "auto":
            preference = os.getenv("AI_PROVIDER", "auto")
        
        # If specific provider requested
        if preference != "auto" and preference in self.PROVIDERS:
            provider = self._get_or_create(preference)
            if provider.is_available():
                return provider
            logger.warning(f"Preferred provider '{preference}' not available, trying fallback chain")
        
        # Try fallback chain
        chain = os.getenv("AI_FALLBACK_CHAIN", self.DEFAULT_CHAIN)
        for provider_name in chain.split(","):
            provider_name = provider_name.strip()
            if provider_name in self.PROVIDERS:
                provider = self._get_or_create(provider_name)
                if provider.is_available():
                    logger.info(f"Using AI provider: {provider_name}")
                    return provider
        
        # Last resort: rule-based (always available)
        return self._get_or_create("rules-only")
    
    def list_providers(self) -> list[ProviderStatus]:
        """Get status of all providers."""
        statuses: list[ProviderStatus] = []
        for name in self.PROVIDERS:
            provider = self._get_or_create(name)
            statuses.append(provider.get_status())
        return sorted(statuses, key=lambda s: s.priority)
    
    def _get_or_create(self, name: str) -> AIProvider:
        """Get cached or create new provider instance."""
        if name not in self._instances:
            provider_class = self.PROVIDERS.get(name)
            if provider_class:
                self._instances[name] = provider_class()
        return self._instances[name]


# Module-level factory instance
_factory = AIProviderFactory()


def get_ai_provider(preference: str = "auto") -> AIProvider:
    """Get an available AI provider."""
    return _factory.get_provider(preference)


def list_ai_providers() -> list[ProviderStatus]:
    """List all AI providers and their status."""
    return _factory.list_providers()
