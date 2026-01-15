"""
Performance Tests for Config Control Plane.

Tests performance characteristics and benchmarks.
"""

import pytest
import tempfile
import time
from pathlib import Path

from app.services.config_store import ConfigStore
from app.services.config_resolver import get_config_resolver
from app.models import ConfigCreateRequest, ConfigSourceType, ConfigState


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    store = ConfigStore(db_path=db_path)
    
    # Create test configs
    for i in range(100):
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref=f"test/{i}/1",
            config={
                "id": f"config_{i}",
                "name": f"Config {i}",
                "version": "1.0.0",
                "tables": {
                    "Table1": {
                        "columns": {
                            f"col_{j}": {"width": "100px"}
                            for j in range(10)
                        }
                    }
                }
            },
            change_summary=f"Test config {i}"
        )
        record = store.create(request, "user:test")
        store.propose(record.id, "user:test")
        store.publish(record.id, "user:test")
    
    yield store, db_path
    
    if db_path.exists():
        db_path.unlink()


class TestResolutionPerformance:
    """Test resolution performance."""
    
    def test_single_resolution_performance(self, temp_db):
        """Test single resolution is fast."""
        store, db_path = temp_db
        resolver = get_config_resolver()
        resolver.store = store
        
        start = time.time()
        response = resolver.resolve("test/50/1")
        elapsed = (time.time() - start) * 1000
        
        assert response is not None
        assert elapsed < 100  # Should be < 100ms for single lookup
    
    def test_batch_resolution_performance(self, temp_db):
        """Test batch resolution performance."""
        store, db_path = temp_db
        resolver = get_config_resolver()
        resolver.store = store
        
        source_refs = [f"test/{i}/1" for i in range(50)]
        
        start = time.time()
        results = []
        for ref in source_refs:
            result = resolver.resolve(ref)
            results.append(result)
        elapsed = (time.time() - start) * 1000
        
        assert len(results) == 50
        assert elapsed < 2000  # Should be < 2s for 50 resolutions
        assert elapsed / 50 < 50  # Average < 50ms per resolution
    
    def test_fingerprint_resolution_performance(self, temp_db):
        """Test fingerprint-based resolution performance."""
        store, db_path = temp_db
        
        # Create config with fingerprint
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="test/fingerprint/1",
            config={"id": "fp_test", "name": "Fingerprint Test"},
            fingerprint="test_fingerprint_123"
        )
        record = store.create(request, "user:test")
        store.propose(record.id, "user:test")
        store.publish(record.id, "user:test")
        
        resolver = get_config_resolver()
        resolver.store = store
        
        start = time.time()
        response = resolver.resolve(
            "test/fingerprint/1",
            fingerprint="test_fingerprint_123"
        )
        elapsed = (time.time() - start) * 1000
        
        assert response is not None
        assert elapsed < 100  # Fingerprint lookup should be fast


class TestDatabasePerformance:
    """Test database query performance."""
    
    def test_list_performance(self, temp_db):
        """Test listing configs is fast."""
        store, db_path = temp_db
        
        start = time.time()
        configs, total = store.list_configs(page=1, per_page=20)
        elapsed = (time.time() - start) * 1000
        
        assert len(configs) == 20
        assert elapsed < 100  # Should be < 100ms
    
    def test_filtered_list_performance(self, temp_db):
        """Test filtered listing performance."""
        store, db_path = temp_db
        
        start = time.time()
        configs, total = store.list_configs(
            state=ConfigState.PUBLISHED,
            page=1,
            per_page=20
        )
        elapsed = (time.time() - start) * 1000
        
        assert elapsed < 150  # Filtered queries should still be fast
    
    def test_object_type_lookup_performance(self, temp_db):
        """Test object type lookup performance."""
        store, db_path = temp_db
        
        # Create config with object type
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.BUILTIN,
            source_ref="builtin:test",
            config={"id": "test", "name": "Test"},
            object_type="Test.ObjectType-1.0"
        )
        record = store.create(request, "user:test")
        store.propose(record.id, "user:test")
        store.publish(record.id, "user:test")
        
        start = time.time()
        resolved = store.resolve(
            "unknown_ref",
            object_type="Test.ObjectType-1.0"
        )
        elapsed = (time.time() - start) * 1000
        
        assert resolved is not None
        assert elapsed < 100  # Object type lookup should be fast


class TestConcurrentAccess:
    """Test concurrent access performance."""
    
    def test_concurrent_resolution(self, temp_db):
        """Test concurrent resolution requests."""
        import concurrent.futures
        
        store, db_path = temp_db
        resolver = get_config_resolver()
        resolver.store = store
        
        source_refs = [f"test/{i}/1" for i in range(20)]
        
        def resolve_one(ref):
            return resolver.resolve(ref)
        
        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(resolve_one, source_refs))
        elapsed = (time.time() - start) * 1000
        
        assert len(results) == 20
        assert all(r is not None for r in results)
        assert elapsed < 500  # Concurrent should still be fast


class TestMemoryUsage:
    """Test memory usage characteristics."""
    
    def test_large_config_handling(self, temp_db):
        """Test handling of large configs."""
        store, db_path = temp_db
        
        # Create config with many tables/columns
        large_config = {
            "id": "large_config",
            "name": "Large Config",
            "version": "1.0.0",
            "tables": {
                f"Table_{i}": {
                    "columns": {
                        f"col_{j}": {"width": "100px"}
                        for j in range(50)
                    }
                }
                for i in range(20)
            }
        }
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="test/large/1",
            config=large_config,
            change_summary="Large config test"
        )
        
        start = time.time()
        record = store.create(request, "user:test")
        elapsed = (time.time() - start) * 1000
        
        assert record is not None
        assert elapsed < 500  # Should handle large configs reasonably
