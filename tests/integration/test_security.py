import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.utils.cache import sanitize_id

class TestSecurity(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.cache_dir = Path(settings.CACHE_DIR)
        
    def test_sanitize_id_security(self):
        """Test that ID sanitization prevents traversal."""
        # Standard ID
        self.assertEqual(sanitize_id("123/456"), "123_456")
        
        # Path traversal attempts
        self.assertNotEqual(sanitize_id("../../../etc/passwd"), "../../../etc/passwd")
        # "a/../b" -> "a_.._b" (this is safe as a filename because / is removed)
        self.assertEqual(sanitize_id("a/../b"), "a_.._b")
        
        # What about just ".."
        self.assertNotEqual(sanitize_id(".."), "..")
        # Ensure it was modified to be safe
        self.assertTrue(sanitize_id("..").endswith("_safe"))

    def test_path_traversal_api(self):
        """Test API prevents accessing files outside cache."""
        # Attempt to access a file that definitely exists outside cache but relative
        # This test relies on the fact that the code uses sanitize_id internally
        
        malicious_id = "../../../etc/passwd"
        
        # This should fail because it will look for "......etcpasswd" (or similar) in cache
        # and not find it, returning 404 or empty list, NOT 500 or file content
        response = self.client.get(f"/object/{malicious_id}/tables")
        
        # Accept 404 (Not Found) or 400 (Bad Request) or 422
        # BUT should definitively NOT return 200 with file content
        self.assertNotEqual(response.status_code, 200)
        
    def test_cors_middleware(self):
        """Verify CORS headers are present (default configuration)."""
        response = self.client.get("/", headers={"Origin": "http://example.com"})
        self.assertEqual(response.status_code, 200)
        # Default config allows *
        self.assertEqual(response.headers.get("access-control-allow-origin"), "*")

if __name__ == "__main__":
    unittest.main()
