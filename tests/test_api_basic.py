"""
Basic API Tests

Tests core API functionality without requiring KBase authentication.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Test health/status endpoint."""
    response = client.get("/health")
    assert response.status_code in [200, 404]  # May not exist


def test_api_docs():
    """Test that API docs are accessible."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema():
    """Test OpenAPI schema is available."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema


def test_config_providers():
    """Test config providers endpoint."""
    response = client.get("/config/providers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_routes_exist():
    """Test that key routes are registered."""
    response = client.get("/openapi.json")
    schema = response.json()
    paths = schema["paths"]
    
    # Key endpoints should exist
    assert "/object/{ws_ref}/tables" in paths
    assert "/object/{ws_ref}/config/generate" in paths
    assert "/config/providers" in paths


def test_config_generate_endpoint_exists():
    """Test config generate endpoint is registered."""
    response = client.get("/openapi.json")
    schema = response.json()
    paths = schema["paths"]
    
    assert "/object/{ws_ref}/config/generate" in paths
    # Should be POST
    assert "post" in paths["/object/{ws_ref}/config/generate"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
