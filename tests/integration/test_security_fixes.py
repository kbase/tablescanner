
import unittest
import sqlite3
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.services.data.query_service import get_query_service

# Reusing DB setup logic
def create_test_db(db_path: Path):
    """Create a comprehensive test database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
        
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create Genes table
    cursor.execute("""
        CREATE TABLE Genes (
            gene_id TEXT PRIMARY KEY,
            gene_name TEXT,
            score REAL,
            count INTEGER
        )
    """)
    
    data = [
        ("G1", "dnaA", 95.5, 10),
        ("G2", "dnaN", 45.2, 5),
        ("G3", "gyrA", 88.0, 20),
    ]
    cursor.executemany("INSERT INTO Genes VALUES (?,?,?,?)", data)
    
    # Create a dummy large table for FTS5 test (no data needed if we mock count)
    cursor.execute("CREATE TABLE LargeTable (id INTEGER PRIMARY KEY, text TEXT)")
    
    conn.commit()
    conn.close()
    return db_path

def setup_cache_with_db(cache_dir: Path, upa: str) -> Path:
    safe_upa = upa.replace("/", "_").replace(":", "_").replace(" ", "_")
    target_dir = cache_dir / safe_upa
    target_dir.mkdir(parents=True, exist_ok=True)
    
    db_path = target_dir / "tables.db"
    create_test_db(db_path)
    return db_path

class TestSecurityFixes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.test_upa = "99999/Security/1"
        self.db_path = setup_cache_with_db(Path(settings.CACHE_DIR), self.test_upa)

    def tearDown(self):
        # Clean up
        safe_upa = self.test_upa.replace("/", "_")
        target_dir = Path(settings.CACHE_DIR) / safe_upa
        if target_dir.exists():
            shutil.rmtree(target_dir)

    def test_variable_limit_enforcement(self):
        """Test that IN operator with >900 items raises 422."""
        # Create a list of 901 items
        many_items = [f"item_{i}" for i in range(901)]
        
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "filters": [
                {"column": "gene_name", "operator": "in", "value": many_items}
            ]
        })
        
        self.assertEqual(response.status_code, 422)
        self.assertIn("Too many values", response.json()["detail"])

    def test_variable_limit_under_threshold(self):
        """Test that IN operator with <900 items works."""
        items = ["dnaA", "dnaN"]
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "filters": [
                {"column": "gene_name", "operator": "in", "value": items}
            ]
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_count"], 2)

    def test_strict_numeric_validation(self):
        """Test that invalid numeric inputs return 422 instead of 0."""
        # 1. String in numeric filter
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "filters": [
                {"column": "score", "operator": "gt", "value": "high_score"}
            ]
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("Invalid numeric value", response.json()["detail"])

        # 2. String in integer filter
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "filters": [
                {"column": "count", "operator": "gt", "value": "not_an_int"}
            ]
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("Invalid numeric value", response.json()["detail"])

    @patch("app.services.data.connection_pool.ConnectionPool.get_connection")
    def test_fts5_safety_logic_mocked_pool(self, mock_get_conn):
        """Mocked unit test for FTS5 safety limit Logic."""
        qs = get_query_service()
        
        # Setup mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Call sequence in ensure_fts5_table:
        # 1. execute(check_table) -> fetchone() -> None (not exists)
        # 2. execute(compile_options) -> fetchall() -> ["ENABLE_FTS5"]
        # 3. execute(count) -> fetchone() -> [150000] (Too large)
        
        mock_cursor.fetchone.side_effect = [
            None,      # 1. FTS5 table check
            [150000],  # 3. Row count
        ]
        # mock fetchall for compile options
        mock_cursor.fetchall.return_value = [("ENABLE_FTS5",)] 
        
        # Call
        result = qs.ensure_fts5_table(Path("dummy.db"), "LargeTable", ["text"])
        
        # Assert
        self.assertFalse(result, "Should return False for tables > 100k rows")
        # Ensure we didn't try to create it
        # The CREATE VIRTUAL TABLE call should NOT have happened
        # We can check the execute calls
        execute_calls = [args[0] for args, _ in mock_cursor.execute.call_args_list]
        self.assertFalse(any("CREATE VIRTUAL TABLE" in cmd for cmd in execute_calls))

    def test_fts5_creation_small_table(self):
        """Verify FTS5 IS created for small tables."""
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "search_value": "dna"
        })
        self.assertEqual(response.status_code, 200)
        # Check logs or side effects? 
        # We can check if `Genes_fts5` table exists in the DB file.
        
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Genes_fts5'")
        self.assertIsNotNone(cur.fetchone(), "Genes_fts5 should be created for small table")
        conn.close()

if __name__ == "__main__":
    unittest.main()
