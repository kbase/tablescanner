"""
Integration Tests for Config Control Plane.

End-to-end tests that verify the full workflow from config creation
to resolution and consumption.
"""

import pytest
import tempfile
import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.config_store import ConfigStore
from app.services.config_resolver import get_config_resolver
from app.models import ConfigCreateRequest, ConfigSourceType, ConfigState


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    yield db_path
    
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def client(temp_db):
    """Create test client with temporary database."""
    # Override config store DB path
    import app.services.config_store
    original_init = ConfigStore.__init__
    
    def mock_init(self, db_path=None):
        original_init(self, db_path=temp_db)
    
    ConfigStore.__init__ = mock_init
    
    app = create_app()
    client = TestClient(app)
    
    yield client
    
    # Restore
    ConfigStore.__init__ = original_init


@pytest.fixture
def sample_config():
    """Sample config for testing."""
    return {
        "id": "test_integration",
        "name": "Integration Test Config",
        "version": "1.0.0",
        "description": "Config for integration testing",
        "tables": {
            "Genes": {
                "columns": {
                    "gene_id": {
                        "width": "150px",
                        "sortable": True,
                        "filterable": True
                    },
                    "gene_name": {
                        "width": "200px",
                        "displayName": "Gene Name"
                    }
                }
            }
        }
    }


class TestConfigWorkflow:
    """Test complete config lifecycle workflow."""
    
    def test_create_propose_publish_workflow(self, client, sample_config):
        """Test full lifecycle: create → propose → publish."""
        # 1. Create draft
        response = client.post(
            "/config",
            json={
                "source_type": "object",
                "source_ref": "test/1/1",
                "config": sample_config,
                "change_summary": "Integration test"
            }
        )
        assert response.status_code == 200
        config_id = response.json()["id"]
        assert response.json()["state"] == "draft"
        
        # 2. Propose
        response = client.post(f"/config/{config_id}/propose")
        assert response.status_code == 200
        assert response.json()["status"] == "proposed"
        
        # Get config to verify state
        response = client.get(f"/config/{config_id}")
        assert response.json()["state"] == "proposed"
        
        # 3. Publish
        response = client.post(f"/config/{config_id}/publish")
        assert response.status_code == 200
        assert response.json()["status"] == "published"
        
        # Verify published
        response = client.get(f"/config/{config_id}")
        assert response.json()["state"] == "published"
        assert response.json()["published_at"] is not None
    
    def test_resolution_after_publish(self, client, sample_config):
        """Test that published config is available via resolve."""
        # Create and publish
        create_resp = client.post(
            "/config",
            json={
                "source_type": "object",
                "source_ref": "test/2/1",
                "config": sample_config,
                "object_type": "Test.ObjectType-1.0",
                "change_summary": "For resolution test"
            }
        )
        config_id = create_resp.json()["id"]
        
        client.post(f"/config/{config_id}/propose")
        client.post(f"/config/{config_id}/publish")
        
        # Resolve
        response = client.get("/config/resolve/test/2/1")
        assert response.status_code == 200
        data = response.json()
        
        assert data["source"] == "published"
        assert data["config_id"] == config_id
        assert data["config"]["id"] == "test_integration"
    
    def test_user_override_workflow(self, client, sample_config):
        """Test user override creation and resolution."""
        # Create base config
        create_resp = client.post(
            "/config",
            json={
                "source_type": "object",
                "source_ref": "test/3/1",
                "config": sample_config,
                "change_summary": "Base config"
            }
        )
        config_id = create_resp.json()["id"]
        client.post(f"/config/{config_id}/propose")
        client.post(f"/config/{config_id}/publish")
        
        # Set user override
        override_resp = client.post(
            "/config/user/override",
            json={
                "source_ref": "test/3/1",
                "override_config": {
                    "tables": {
                        "Genes": {
                            "columns": {
                                "gene_id": {
                                    "width": "300px",  # Override
                                    "pin": "left"  # New field
                                }
                            }
                        }
                    }
                },
                "priority": 50
            },
            headers={"Authorization": "Bearer test_token"}
        )
        assert override_resp.status_code == 200
        
        # Resolve with user ID
        resolve_resp = client.get(
            "/config/resolve/test/3/1?user_id=user:test"
        )
        assert resolve_resp.status_code == 200
        data = resolve_resp.json()
        
        # Should use override
        assert data["source"] == "user_override"
        assert data["config"]["tables"]["Genes"]["columns"]["gene_id"]["width"] == "300px"
    
    def test_config_inheritance_workflow(self, client, sample_config):
        """Test config inheritance and overlays."""
        # Create parent config
        parent_resp = client.post(
            "/config",
            json={
                "source_type": "builtin",
                "source_ref": "builtin:parent",
                "config": sample_config,
                "change_summary": "Parent config"
            }
        )
        parent_id = parent_resp.json()["id"]
        client.post(f"/config/{parent_id}/propose")
        client.post(f"/config/{parent_id}/publish")
        
        # Create child config with inheritance
        child_resp = client.post(
            "/config",
            json={
                "source_type": "custom",
                "source_ref": "custom:child",
                "extends_id": parent_id,
                "config": {},
                "change_summary": "Child config"
            }
        )
        child_id = child_resp.json()["id"]
        
        # Add overlays
        client.patch(
            f"/config/{child_id}",
            json={
                "overlays": {
                    "tables": {
                        "Genes": {
                            "columns": {
                                "gene_id": {
                                    "width": "250px"  # Override parent
                                }
                            }
                        }
                    }
                },
                "change_summary": "Added overlays"
            }
        )
        
        # Publish child
        client.post(f"/config/{child_id}/propose")
        client.post(f"/config/{child_id}/publish")
        
        # Resolve child - should have parent + overlays
        resolve_resp = client.get("/config/resolve/custom:child")
        assert resolve_resp.status_code == 200
        data = resolve_resp.json()
        
        # Should have parent's structure
        assert "Genes" in data["config"]["tables"]
        # Should have overlay applied
        assert data["config"]["tables"]["Genes"]["columns"]["gene_id"]["width"] == "250px"


class TestConfigTesting:
    """Test config testing functionality."""
    
    def test_config_testing_endpoint(self, client, sample_config):
        """Test config testing endpoint."""
        # Create and publish config
        create_resp = client.post(
            "/config",
            json={
                "source_type": "object",
                "source_ref": "test/4/1",
                "config": sample_config,
                "change_summary": "For testing"
            }
        )
        config_id = create_resp.json()["id"]
        client.post(f"/config/{config_id}/propose")
        client.post(f"/config/{config_id}/publish")
        
        # Test config
        test_resp = client.post(
            "/config/test",
            json={
                "config_id": config_id,
                "test_types": ["schema", "performance", "integration"]
            }
        )
        assert test_resp.status_code == 200
        data = test_resp.json()
        
        assert data["config_id"] == config_id
        assert len(data["results"]) == 3
        assert "overall_status" in data


class TestConfigDiff:
    """Test config diff functionality."""
    
    def test_config_diff_endpoint(self, client, sample_config):
        """Test config diff endpoint."""
        # Create two configs
        config1_resp = client.post(
            "/config",
            json={
                "source_type": "object",
                "source_ref": "test/5/1",
                "config": sample_config,
                "change_summary": "Config 1"
            }
        )
        config1_id = config1_resp.json()["id"]
        
        # Modify config for second
        modified_config = sample_config.copy()
        modified_config["tables"]["Genes"]["columns"]["gene_id"]["width"] = "300px"
        
        config2_resp = client.post(
            "/config",
            json={
                "source_type": "object",
                "source_ref": "test/5/2",
                "config": modified_config,
                "change_summary": "Config 2"
            }
        )
        config2_id = config2_resp.json()["id"]
        
        # Diff
        diff_resp = client.post(
            "/config/diff",
            json={
                "config_id1": config1_id,
                "config_id2": config2_id
            }
        )
        assert diff_resp.status_code == 200
        data = diff_resp.json()
        
        assert "modified" in data
        assert "summary" in data
        assert data["has_changes"] is True


class TestErrorHandling:
    """Test error handling in workflows."""
    
    def test_cannot_update_published_config(self, client, sample_config):
        """Test that published configs cannot be updated."""
        # Create and publish
        create_resp = client.post(
            "/config",
            json={
                "source_type": "object",
                "source_ref": "test/6/1",
                "config": sample_config,
                "change_summary": "Test"
            }
        )
        config_id = create_resp.json()["id"]
        client.post(f"/config/{config_id}/propose")
        client.post(f"/config/{config_id}/publish")
        
        # Try to update
        update_resp = client.patch(
            f"/config/{config_id}",
            json={
                "config": {"id": "modified"},
                "change_summary": "Trying to update"
            }
        )
        assert update_resp.status_code == 400
    
    def test_resolution_fallback(self, client):
        """Test resolution falls back when no config found."""
        # Resolve non-existent config
        response = client.get("/config/resolve/nonexistent/ref/123")
        assert response.status_code == 200
        data = response.json()
        
        # Should return default
        assert data["source"] in ["default", "builtin"]
        assert "config" in data


class TestPerformance:
    """Test performance characteristics."""
    
    def test_resolution_performance(self, client, sample_config):
        """Test that resolution is fast."""
        import time
        
        # Create and publish
        create_resp = client.post(
            "/config",
            json={
                "source_type": "object",
                "source_ref": "test/7/1",
                "config": sample_config,
                "change_summary": "Performance test"
            }
        )
        config_id = create_resp.json()["id"]
        client.post(f"/config/{config_id}/propose")
        client.post(f"/config/{config_id}/publish")
        
        # Time resolution
        start = time.time()
        response = client.get("/config/resolve/test/7/1")
        elapsed = (time.time() - start) * 1000  # ms
        
        assert response.status_code == 200
        assert elapsed < 500  # Should be < 500ms
        assert response.json()["resolution_time_ms"] < 500
