"""
Tests for Config Control Plane functionality.

Tests cover:
- ConfigStore CRUD operations
- Lifecycle transitions
- Config resolution cascade
- AI proposal handling
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime

from app.services.config_store import ConfigStore, get_config_store
from app.services.config_resolver import ConfigResolver, get_config_resolver
from app.models import (
    ConfigCreateRequest,
    ConfigUpdateRequest,
    ConfigState,
    ConfigSourceType,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    store = ConfigStore(db_path=db_path)
    yield store, db_path
    
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def sample_config():
    """Sample config for testing."""
    return {
        "id": "test_config",
        "name": "Test Configuration",
        "version": "1.0.0",
        "description": "Test config for unit tests",
        "tables": {
            "Genes": {
                "columns": {
                    "gene_id": {
                        "width": "150px",
                        "sortable": True
                    }
                }
            }
        }
    }


class TestConfigStore:
    """Test ConfigStore CRUD operations."""
    
    def test_create_config(self, temp_db, sample_config):
        """Test creating a new draft config."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
            change_summary="Initial creation"
        )
        
        record = store.create(request, "user:test")
        
        assert record.state == ConfigState.DRAFT
        assert record.source_ref == "76990/7/2"
        assert record.config == sample_config
        assert record.version == 1
    
    def test_get_config(self, temp_db, sample_config):
        """Test retrieving a config by ID."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        created = store.create(request, "user:test")
        retrieved = store.get(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.config == sample_config
    
    def test_update_draft_config(self, temp_db, sample_config):
        """Test updating a draft config."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        
        update_request = ConfigUpdateRequest(
            change_summary="Added new column",
            overlays={
                "tables": {
                    "Genes": {
                        "columns": {
                            "gene_name": {"width": "200px"}
                        }
                    }
                }
            }
        )
        
        updated = store.update(record.id, update_request, "user:test")
        
        assert "gene_name" in updated.config["tables"]["Genes"]["columns"]
        assert updated.config["tables"]["Genes"]["columns"]["gene_id"]["width"] == "150px"
    
    def test_cannot_update_published_config(self, temp_db, sample_config):
        """Test that published configs cannot be updated."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        store.propose(record.id, "user:test")
        store.publish(record.id, "user:test")
        
        update_request = ConfigUpdateRequest(
            change_summary="Trying to update published",
            config={"id": "modified"}
        )
        
        with pytest.raises(ValueError, match="Cannot update config in state"):
            store.update(record.id, update_request, "user:test")
    
    def test_delete_draft_config(self, temp_db, sample_config):
        """Test deleting a draft config."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        deleted = store.delete(record.id, "user:test")
        
        assert deleted is True
        assert store.get(record.id) is None
    
    def test_cannot_delete_published_config(self, temp_db, sample_config):
        """Test that published configs cannot be deleted."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        store.propose(record.id, "user:test")
        store.publish(record.id, "user:test")
        
        with pytest.raises(ValueError, match="Cannot delete config in state"):
            store.delete(record.id, "user:test")


class TestLifecycleTransitions:
    """Test config lifecycle state transitions."""
    
    def test_draft_to_proposed(self, temp_db, sample_config):
        """Test transitioning draft to proposed."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        proposed = store.propose(record.id, "user:reviewer")
        
        assert proposed.state == ConfigState.PROPOSED
    
    def test_proposed_to_published(self, temp_db, sample_config):
        """Test transitioning proposed to published."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        store.propose(record.id, "user:reviewer")
        published = store.publish(record.id, "user:publisher")
        
        assert published.state == ConfigState.PUBLISHED
        assert published.published_at is not None
        assert published.published_by == "user:publisher"
    
    def test_published_to_deprecated(self, temp_db, sample_config):
        """Test deprecating a published config."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        store.propose(record.id, "user:reviewer")
        store.publish(record.id, "user:publisher")
        deprecated = store.deprecate(record.id, "user:admin")
        
        assert deprecated.state == ConfigState.DEPRECATED
    
    def test_invalid_transition(self, temp_db, sample_config):
        """Test that invalid transitions raise errors."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        
        # Try to publish without proposing first
        with pytest.raises(ValueError, match="must be in proposed state"):
            store.publish(record.id, "user:test")


class TestConfigResolution:
    """Test config resolution cascade."""
    
    def test_resolve_by_fingerprint(self, temp_db, sample_config):
        """Test resolution with fingerprint match."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
            fingerprint="abc123def456",
        )
        
        record = store.create(request, "user:test")
        store.propose(record.id, "user:test")
        store.publish(record.id, "user:test")
        
        resolver = ConfigResolver()
        resolver.store = store  # Use test store
        
        resolved = store.resolve("76990/7/2", fingerprint="abc123def456")
        
        assert resolved is not None
        assert resolved.id == record.id
        assert resolved.fingerprint == "abc123def456"
    
    def test_resolve_by_source_ref(self, temp_db, sample_config):
        """Test resolution by source reference."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        record = store.create(request, "user:test")
        store.propose(record.id, "user:test")
        store.publish(record.id, "user:test")
        
        resolved = store.resolve("76990/7/2")
        
        assert resolved is not None
        assert resolved.id == record.id
    
    def test_resolve_builtin_by_object_type(self, temp_db, sample_config):
        """Test resolution of builtin config by object type."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.BUILTIN,
            source_ref="builtin:berdl_tables",
            config=sample_config,
            object_type="KBaseGeneDataLakes.BERDLTables-1.0",
        )
        
        record = store.create(request, "user:test")
        store.propose(record.id, "user:test")
        store.publish(record.id, "user:test")
        
        resolved = store.resolve(
            "unknown_ref",
            object_type="KBaseGeneDataLakes.BERDLTables-1.0"
        )
        
        assert resolved is not None
        assert resolved.source_type == ConfigSourceType.BUILTIN
    
    def test_resolution_fallback_to_default(self, temp_db):
        """Test resolution falls back to default when nothing found."""
        resolver = ConfigResolver()
        resolver.store = ConfigStore(db_path=temp_db[1])
        
        response = resolver.resolve("unknown/ref/123")
        
        assert response.source == "default"
        assert response.config is not None
        assert "id" in response.config


class TestConfigListing:
    """Test config listing and filtering."""
    
    def test_list_all_configs(self, temp_db, sample_config):
        """Test listing all configs."""
        store, db_path = temp_db
        
        # Create multiple configs
        for i in range(3):
            request = ConfigCreateRequest(
                source_type=ConfigSourceType.OBJECT,
                source_ref=f"76990/{i}/1",
                config={**sample_config, "id": f"config_{i}"},
            )
            store.create(request, "user:test")
        
        configs, total = store.list_configs()
        
        assert total == 3
        assert len(configs) == 3
    
    def test_list_by_state(self, temp_db, sample_config):
        """Test filtering configs by state."""
        store, db_path = temp_db
        
        request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        
        draft = store.create(request, "user:test")
        store.propose(draft.id, "user:test")
        published = store.publish(draft.id, "user:test")
        
        drafts, draft_total = store.list_configs(state=ConfigState.DRAFT)
        published_configs, pub_total = store.list_configs(state=ConfigState.PUBLISHED)
        
        assert draft_total == 0  # No drafts after publishing
        assert pub_total == 1
        assert published_configs[0].id == published.id
    
    def test_list_by_source_type(self, temp_db, sample_config):
        """Test filtering configs by source type."""
        store, db_path = temp_db
        
        # Create object and builtin configs
        obj_request = ConfigCreateRequest(
            source_type=ConfigSourceType.OBJECT,
            source_ref="76990/7/2",
            config=sample_config,
        )
        store.create(obj_request, "user:test")
        
        builtin_request = ConfigCreateRequest(
            source_type=ConfigSourceType.BUILTIN,
            source_ref="builtin:test",
            config=sample_config,
        )
        store.create(builtin_request, "user:test")
        
        builtins, total = store.list_configs(source_type=ConfigSourceType.BUILTIN)
        
        assert total == 1
        assert builtins[0].source_type == ConfigSourceType.BUILTIN
    
    def test_pagination(self, temp_db, sample_config):
        """Test pagination in config listing."""
        store, db_path = temp_db
        
        # Create 5 configs
        for i in range(5):
            request = ConfigCreateRequest(
                source_type=ConfigSourceType.OBJECT,
                source_ref=f"76990/{i}/1",
                config={**sample_config, "id": f"config_{i}"},
            )
            store.create(request, "user:test")
        
        # Get first page
        page1, total = store.list_configs(page=1, per_page=2)
        assert len(page1) == 2
        assert total == 5
        
        # Get second page
        page2, total = store.list_configs(page=2, per_page=2)
        assert len(page2) == 2
        assert total == 5
        
        # Verify different configs
        assert page1[0].id != page2[0].id
