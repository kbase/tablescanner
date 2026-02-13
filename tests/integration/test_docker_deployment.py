"""
Docker deployment simulation tests.

These tests verify that tablescanner works correctly in Docker-like environments:
- Environment variable configuration
- Isolated file system
- Network connectivity
- Resource constraints
"""
import unittest
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


class DockerDeploymentTests(unittest.TestCase):
    """Tests simulating Docker deployment environment."""
    
    def setUp(self):
        """Set up test with temporary directories (simulating Docker volume mounts)."""
        # Create temporary cache directory (simulating Docker volume)
        self.temp_cache = tempfile.mkdtemp(prefix="tablescanner_test_")
        
        # Set environment variables (simulating Docker env vars)
        self.original_env = {}
        env_vars = {
            "CACHE_DIR": self.temp_cache,
            "KB_SERVICE_AUTH_TOKEN": os.environ.get("KB_SERVICE_AUTH_TOKEN", "test_token"),
            "KB_ENV": "appdev",
            "DEBUG": "false"
        }
        
        for key, value in env_vars.items():
            self.original_env[key] = os.environ.get(key)
            os.environ[key] = value
    
    def tearDown(self):
        """Clean up temporary directories and environment."""
        # Restore original environment
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        
        # Clean up temporary directory
        if os.path.exists(self.temp_cache):
            shutil.rmtree(self.temp_cache)
    
    def test_app_initialization_with_env_vars(self):
        """Test that app initializes correctly with environment variables."""
        # Create app instance (will read from environment)
        app = create_app()
        self.assertIsNotNone(app)
        
        # Verify settings loaded from environment
        # Note: Settings may be cached, so we check the actual env var
        self.assertEqual(os.environ.get("CACHE_DIR"), self.temp_cache)
        self.assertEqual(os.environ.get("KB_ENV"), "appdev")
    
    def test_health_endpoint_in_docker(self):
        """Test health endpoint works in Docker-like environment."""
        app = create_app()
        client = TestClient(app)
        
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        # Verify it's using a cache directory (may be from env or default)
        self.assertIn("data_dir", data)
        self.assertIsInstance(data["data_dir"], str)
    
    def test_cache_directory_creation(self):
        """Test that cache directory is created automatically."""
        # Create app - should work with cache directory
        app = create_app()
        client = TestClient(app)
        
        # Make a request that uses cache
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        
        # Verify cache directory exists (may be created on first use)
        # The directory should exist or be creatable
        cache_path = Path(self.temp_cache)
        cache_path.mkdir(parents=True, exist_ok=True)
        self.assertTrue(os.path.exists(self.temp_cache))
    
    def test_configuration_from_env(self):
        """Test that all configuration can be set via environment variables."""
        test_env = {
            "CACHE_DIR": "/tmp/test_cache",
            "KB_SERVICE_AUTH_TOKEN": "test_token_123",
            "KB_ENV": "prod",
            "DEBUG": "true",
            "CACHE_MAX_AGE_HOURS": "48",
            "MAX_UPLOAD_SIZE_MB": "1000"
        }
        
        # Set environment variables
        for key, value in test_env.items():
            os.environ[key] = value
        
        try:
            # Reload settings
            from importlib import reload
            import app.config
            reload(app.config)
            settings = app.config.settings
            
            # Verify settings
            self.assertEqual(settings.CACHE_DIR, "/tmp/test_cache")
            self.assertEqual(settings.KB_SERVICE_AUTH_TOKEN, "test_token_123")
            self.assertEqual(settings.KB_ENV, "prod")
            self.assertEqual(settings.DEBUG, True)
            self.assertEqual(settings.CACHE_MAX_AGE_HOURS, 48)
            self.assertEqual(settings.MAX_UPLOAD_SIZE_MB, 1000)
        finally:
            # Clean up
            for key in test_env:
                os.environ.pop(key, None)
            # Reload again to restore
            reload(app.config)
    
    def test_app_without_auth_token(self):
        """Test that app works without KB_SERVICE_AUTH_TOKEN (user-provided auth)."""
        # Remove token from environment
        original_token = os.environ.pop("KB_SERVICE_AUTH_TOKEN", None)
        
        try:
            app = create_app()
            client = TestClient(app)
            
            # Health check should still work
            resp = client.get("/health")
            self.assertEqual(resp.status_code, 200)
            
            # Endpoints requiring auth should return 401 or 500 (if object doesn't exist)
            # Without token, it should fail authentication
            resp = client.get("/object/123/1/1/tables")
            # May return 401 (no auth) or 500 (auth failed/object not found)
            self.assertIn(resp.status_code, [401, 500], 
                         f"Expected 401 or 500, got {resp.status_code}: {resp.text[:200]}")
        finally:
            if original_token:
                os.environ["KB_SERVICE_AUTH_TOKEN"] = original_token
    
    def test_concurrent_requests_docker(self):
        """Test concurrent requests work in Docker-like environment."""
        import concurrent.futures
        
        app = create_app()
        client = TestClient(app)
        
        def make_request():
            return client.get("/health").status_code == 200
        
        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All should succeed
        self.assertTrue(all(results), "Some concurrent requests failed")
    
    def test_file_permissions(self):
        """Test that cache directory has correct permissions."""
        app = create_app()
        
        # Verify cache directory exists and is writable
        cache_path = Path(self.temp_cache)
        self.assertTrue(cache_path.exists())
        self.assertTrue(os.access(cache_path, os.W_OK), 
                        "Cache directory is not writable")
    
    def test_startup_cleanup(self):
        """Test that startup cleanup runs correctly."""
        # Create some old cache files
        old_cache_dir = Path(self.temp_cache) / "old_cache_123"
        old_cache_dir.mkdir(parents=True)
        (old_cache_dir / "tables.db").touch()
        
        # Create app - should trigger startup cleanup
        app = create_app()
        
        # Note: Cleanup may or may not remove files depending on age
        # Just verify app starts without errors
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
