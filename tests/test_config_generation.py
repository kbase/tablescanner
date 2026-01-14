"""
Tests for Config Generation and Validation.

Tests the new prompts, validation, and type inference improvements
for the TableScanner-DataTables Viewer integration.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_db():
    """Create a sample SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create sample gene table
    cursor.execute("""
        CREATE TABLE genes (
            gene_id TEXT PRIMARY KEY,
            gene_name TEXT,
            product TEXT,
            strand TEXT,
            start_pos INTEGER,
            end_pos INTEGER,
            uniref_90 TEXT,
            go_terms TEXT,
            sequence TEXT
        )
    """)
    
    # Insert sample data
    cursor.executemany("""
        INSERT INTO genes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        ("GENE001", "dnaA", "replication initiator", "+", 100, 500, 
         "UniRef:UniRef90_A0A1B2C3", "GO:0008150", "ATCGATCGATCGATCGATCGATCG"),
        ("GENE002", "dnaN", "DNA polymerase III", "-", 600, 1200,
         "UniRef:UniRef90_D4E5F6", "GO:0003677", "GCTAGCTAGCTAGCTAGCTAGCTA"),
        ("GENE003", "dnaK", "heat shock protein", "+", 1300, 2100,
         None, None, "TTAATTAATTAATTAATTAATTAA"),
    ])
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture
def sample_config():
    """Sample valid config for testing validation."""
    return {
        "id": "test_config",
        "name": "Test Configuration",
        "version": "1.0.0",
        "tables": {
            "genes": {
                "displayName": "Genes",
                "columns": [
                    {
                        "column": "gene_id",
                        "displayName": "Gene ID",
                        "dataType": "id",
                        "categories": ["core"],
                        "pin": "left"
                    },
                    {
                        "column": "gene_name",
                        "displayName": "Gene Name",
                        "dataType": "string",
                        "categories": ["core"]
                    }
                ]
            }
        }
    }


# =============================================================================
# VALIDATION TESTS
# =============================================================================

class TestValidation:
    """Tests for config validation module."""
    
    def test_validate_valid_config(self, sample_config):
        """Valid config should pass validation."""
        from app.services.validation import validate_config
        
        is_valid, error = validate_config(sample_config)
        assert is_valid is True
        assert error is None
    
    def test_validate_missing_required_fields(self):
        """Config missing required fields should fail."""
        from app.services.validation import validate_config
        
        # Missing 'tables'
        invalid = {"id": "test", "name": "Test"}
        is_valid, error = validate_config(invalid)
        assert is_valid is False
        assert "tables" in error.lower()
    
    def test_validate_empty_tables(self):
        """Config with empty tables should fail."""
        from app.services.validation import validate_config
        
        invalid = {"id": "test", "name": "Test", "tables": {}}
        is_valid, error = validate_config(invalid)
        assert is_valid is False
    
    def test_validate_column_missing_name(self, sample_config):
        """Column without 'column' key should fail."""
        from app.services.validation import validate_column_config
        
        invalid_col = {"displayName": "Test"}
        is_valid, error = validate_column_config(invalid_col)
        assert is_valid is False
        assert "column" in error.lower()
    
    def test_sanitize_config(self, sample_config):
        """Sanitization should normalize config."""
        from app.services.validation import sanitize_config
        
        # Config without version
        raw = dict(sample_config)
        del raw["version"]
        
        sanitized = sanitize_config(raw)
        assert sanitized["version"] == "1.0.0"


# =============================================================================
# PROMPT TESTS
# =============================================================================

class TestPrompts:
    """Tests for prompt engineering module."""
    
    def test_detect_uniref_pattern(self):
        """Should detect UniRef prefix pattern."""
        from app.services.prompts import detect_value_patterns
        
        values = ["UniRef:UniRef90_A0A1B2", "UniRef:UniRef90_C3D4E5"]
        patterns = detect_value_patterns(values)
        
        assert any("UniRef" in p for p in patterns)
    
    def test_detect_go_pattern(self):
        """Should detect GO term pattern."""
        from app.services.prompts import detect_value_patterns
        
        values = ["GO:0008150", "GO:0003677", "GO:0006412"]
        patterns = detect_value_patterns(values)
        
        assert any("GO" in p for p in patterns)
    
    def test_detect_sequence_pattern(self):
        """Should detect DNA sequence pattern."""
        from app.services.prompts import detect_value_patterns
        
        values = ["ATCGATCGATCGATCGATCGATCGATCG", "GCTAGCTAGCTAGCTAGCTAGCTAGCTA"]
        patterns = detect_value_patterns(values)
        
        assert any("sequence" in p.lower() for p in patterns)
    
    def test_detect_strand_pattern(self):
        """Should detect strand indicator pattern."""
        from app.services.prompts import detect_value_patterns
        
        values = ["+", "-", "+", "+", "-"]
        patterns = detect_value_patterns(values)
        
        assert any("strand" in p.lower() for p in patterns)
    
    def test_compute_numeric_stats(self):
        """Should compute basic numeric statistics."""
        from app.services.prompts import compute_numeric_stats
        
        values = [1.5, 2.5, 3.5, 4.5, 5.5]
        stats = compute_numeric_stats(values)
        
        assert stats is not None
        assert stats["min"] == 1.5
        assert stats["max"] == 5.5
        assert stats["count"] == 5
        assert stats["has_decimals"] is True
    
    def test_compute_numeric_stats_non_numeric(self):
        """Should return None for non-numeric values."""
        from app.services.prompts import compute_numeric_stats
        
        values = ["abc", "def", "ghi"]
        stats = compute_numeric_stats(values)
        
        assert stats is None
    
    def test_build_prompt_structure(self):
        """Generated prompt should have expected sections."""
        from app.services.prompts import build_table_config_prompt
        
        prompt = build_table_config_prompt(
            table_name="genes",
            schema_info=[{"name": "gene_id", "type": "TEXT"}],
            sample_values={"gene_id": ["GENE001", "GENE002"]},
            detected_patterns={"gene_id": ["no_special_pattern"]},
            statistics={},
            row_count=100
        )
        
        assert "genes" in prompt
        assert "Sample Values" in prompt
        assert "Detected Patterns" in prompt
        assert "JSON" in prompt


# =============================================================================
# TYPE INFERENCE TESTS
# =============================================================================

class TestTypeInference:
    """Tests for enhanced type inference patterns."""
    
    def test_uniref_chain_transform(self):
        """UniRef columns should get chain transformer."""
        from app.services.type_inference import TypeInferenceEngine
        
        engine = TypeInferenceEngine()
        result = engine.infer_from_name("uniref_90")
        
        assert result is not None
        assert result.transform is not None
        assert result.transform.type == "chain"
    
    def test_strand_badge_transform(self):
        """Strand columns should get badge transformer."""
        from app.services.type_inference import TypeInferenceEngine
        
        engine = TypeInferenceEngine()
        result = engine.infer_from_name("strand")
        
        assert result is not None
        assert result.transform is not None
        assert result.transform.type == "badge"
        assert "colorMap" in result.transform.options
    
    def test_pfam_chain_transform(self):
        """Pfam columns should get chain transformer."""
        from app.services.type_inference import TypeInferenceEngine
        
        engine = TypeInferenceEngine()
        result = engine.infer_from_name("pfam_domain")
        
        assert result is not None
        assert result.transform is not None
        assert result.transform.type == "chain"
    
    def test_go_ontology_transform(self):
        """GO columns should get ontology transformer."""
        from app.services.type_inference import TypeInferenceEngine
        
        engine = TypeInferenceEngine()
        result = engine.infer_from_name("GO_terms")
        
        assert result is not None
        assert result.transform is not None
        assert result.transform.type == "ontology"


# =============================================================================
# FINGERPRINT TESTS
# =============================================================================

class TestFingerprint:
    """Tests for database fingerprinting."""
    
    def test_compute_fingerprint(self, sample_db):
        """Should compute consistent fingerprint."""
        from app.services.fingerprint import DatabaseFingerprint
        
        fp_service = DatabaseFingerprint()
        fp1 = fp_service.compute(sample_db)
        fp2 = fp_service.compute(sample_db)
        
        assert fp1 == fp2
        assert len(fp1) == 16  # SHA256 prefix
    
    def test_cache_and_retrieve(self, sample_config):
        """Should cache and retrieve configs."""
        from app.services.fingerprint import DatabaseFingerprint
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            fp_service = DatabaseFingerprint(config_dir=tmpdir)
            
            fingerprint = "test_fingerprint_123"
            fp_service.cache_config(fingerprint, sample_config)
            
            retrieved = fp_service.get_cached_config(fingerprint)
            
            assert retrieved is not None
            assert retrieved["id"] == sample_config["id"]
    
    def test_clear_cache(self, sample_config):
        """Should clear cached configs."""
        from app.services.fingerprint import DatabaseFingerprint
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            fp_service = DatabaseFingerprint(config_dir=tmpdir)
            
            fingerprint = "test_to_delete"
            fp_service.cache_config(fingerprint, sample_config)
            
            assert fp_service.is_cached(fingerprint) is True
            
            deleted = fp_service.clear_cache(fingerprint)
            assert deleted == 1
            
            assert fp_service.is_cached(fingerprint) is False


# =============================================================================
# CONFIG GENERATOR TESTS
# =============================================================================

class TestConfigGenerator:
    """Tests for config generator."""
    
    def test_generate_config(self, sample_db):
        """Should generate valid config from database."""
        from app.services.config_generator import ConfigGenerator
        from app.services.validation import validate_config
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = ConfigGenerator(config_dir=tmpdir)
            result = generator.generate(
                db_path=sample_db,
                handle_ref="test/test/1",
                force_regenerate=True,
                ai_preference="rules-only"
            )
            
            assert result.tables_analyzed > 0
            assert result.config is not None
            
            # Validate generated config
            is_valid, error = validate_config(result.config)
            assert is_valid is True, f"Validation failed: {error}"
    
    def test_cache_hit(self, sample_db):
        """Second generation should use cache."""
        from app.services.config_generator import ConfigGenerator
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = ConfigGenerator(config_dir=tmpdir)
            
            # First generation
            result1 = generator.generate(
                db_path=sample_db,
                handle_ref="test/test/1",
                ai_preference="rules-only"
            )
            assert result1.cache_hit is False
            
            # Second generation (should hit cache)
            result2 = generator.generate(
                db_path=sample_db,
                handle_ref="test/test/1",
                ai_preference="rules-only"
            )
            assert result2.cache_hit is True


# =============================================================================
# FALLBACK REGISTRY TESTS
# =============================================================================

class TestFallbackRegistry:
    """Tests for fallback config registry."""
    
    def test_berdl_object_type_match(self):
        """BERDL object type should match berdl_tables config."""
        from app.configs import get_fallback_config_id, has_fallback_config
        
        assert has_fallback_config("KBaseGeneDataLakes.BERDLTables-1.0") is True
        assert get_fallback_config_id("KBaseGeneDataLakes.BERDLTables-1.0") == "berdl_tables"
    
    def test_genome_data_tables_match(self):
        """GenomeDataTables should match genome_data_tables config."""
        from app.configs import get_fallback_config_id, has_fallback_config
        
        assert has_fallback_config("KBaseFBA.GenomeDataLakeTables-1.0") is True
        assert get_fallback_config_id("KBaseFBA.GenomeDataLakeTables-1.0") == "genome_data_tables"
    
    def test_unknown_object_type(self):
        """Unknown object type should return None."""
        from app.configs import get_fallback_config_id, has_fallback_config
        
        assert has_fallback_config("SomeUnknown.Type-1.0") is False
        assert get_fallback_config_id("SomeUnknown.Type-1.0") is None
    
    def test_load_berdl_config(self):
        """Should load and parse berdl_tables.json."""
        from app.configs import get_fallback_config
        
        config = get_fallback_config("KBaseGeneDataLakes.BERDLTables-1.0")
        
        assert config is not None
        assert config["id"] == "berdl_tables"
        assert "tables" in config
        assert "genome_features" in config["tables"]
    
    def test_load_genome_data_tables_config(self):
        """Should load and parse genome_data_tables.json."""
        from app.configs import get_fallback_config
        
        config = get_fallback_config("KBaseFBA.GenomeDataLakeTables-1.0")
        
        assert config is not None
        assert config["id"] == "genome_data_tables"
        assert "tables" in config
        assert "Genes" in config["tables"]
    
    def test_list_available_configs(self):
        """Should list all available configs."""
        from app.configs import list_available_configs
        
        configs = list_available_configs()
        
        assert len(configs) >= 2
        config_ids = [c["id"] for c in configs]
        assert "berdl_tables" in config_ids
        assert "genome_data_tables" in config_ids
    
    def test_config_cache(self):
        """Configs should be cached after first load."""
        from app.configs import get_fallback_config, clear_cache
        
        # Clear cache first
        clear_cache()
        
        # First load
        config1 = get_fallback_config("KBaseGeneDataLakes.BERDLTables-1.0")
        
        # Second load (should use cache)
        config2 = get_fallback_config("KBaseGeneDataLakes.BERDLTables-1.0")
        
        assert config1 is config2  # Same object reference


# =============================================================================
# ENHANCED RESPONSE TESTS
# =============================================================================

class TestEnhancedResponses:
    """Tests for enhanced API response models."""
    
    def test_config_response_has_new_fields(self):
        """ConfigGenerationResponse should have all new fields."""
        from app.models import ConfigGenerationResponse
        
        # Check field names exist
        fields = ConfigGenerationResponse.model_fields
        assert "fallback_used" in fields
        assert "fallback_reason" in fields
        assert "config_source" in fields
        assert "db_schema" in fields  # Note: aliased to "schema" in JSON
        assert "ai_available" in fields
        assert "ai_error" in fields
        assert "api_version" in fields
    
    def test_table_list_response_has_new_fields(self):
        """TableListResponse should have all new fields."""
        from app.models import TableListResponse
        
        fields = TableListResponse.model_fields
        assert "schemas" in fields
        assert "has_builtin_config" in fields
        assert "builtin_config_id" in fields
        assert "database_size_bytes" in fields
        assert "total_rows" in fields
        assert "api_version" in fields
    
    def test_backward_compatibility(self):
        """Old clients should still work with minimal fields."""
        from app.models import ConfigGenerationResponse
        
        # Create response with only required fields
        response = ConfigGenerationResponse(
            status="generated",
            fingerprint="test_fp",
            config_url="/config/test",
            config={"id": "test", "tables": {}},
            tables_analyzed=1,
            columns_inferred=5,
            generation_time_ms=100.0,
            cache_hit=False,
        )
        
        # Should have default values for new fields
        assert response.fallback_used is False
        assert response.api_version == "2.0"
        assert response.ai_available is True

