import unittest
from fastapi.testclient import TestClient
from app.main import app

class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/health")
        # 500/503 is NOT acceptable. Integration tests must ensure the application can start.
        # The ConnectionPool does not require external connectivity to initialize.
        self.assertEqual(response.status_code, 200)

    def test_api_docs_accessible(self):
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)

    def test_openapi_schema_structure(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("paths", data)
        # Verify Key Endpoints exist
        self.assertIn("/object/{ws_ref}/tables", data["paths"])
        self.assertIn("/table-data", data["paths"])
        
        # Verify Deprecated Endpoints are GONE
        self.assertNotIn("/handle/{handle_ref}/tables", data["paths"])
        self.assertNotIn("/pangenomes", data["paths"])
        self.assertNotIn("/tables", data["paths"])
        self.assertNotIn("/config/providers", data["paths"])
        self.assertNotIn("/config/resolve", data["paths"])

if __name__ == "__main__":
    unittest.main()
