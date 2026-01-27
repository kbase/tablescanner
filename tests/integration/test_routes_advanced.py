import unittest
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

def create_test_db(db_path: Path):
    """Create a comprehensive test database with various types."""
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
            count INTEGER,
            is_active BOOLEAN,
            features TEXT, -- JSON-like
            created_at TEXT
        )
    """)
    
    data = [
        ("G1", "dnaA", 95.5, 10, 1, '{"type": "init"}', "2023-01-01"),
        ("G2", "dnaN", 45.2, 5, 0, '{"type": "pol"}', "2023-01-02"),
        ("G3", "gyrA", 88.0, 20, 1, '{"type": "top"}', "2023-01-03"),
        ("G4", "gyrB", 87.5, 15, 1, '{"type": "top"}', "2023-01-03"),
        ("G5", "recA", 12.5, 2, 0, None, "2023-01-04"),
    ]
    
    cursor.executemany("INSERT INTO Genes VALUES (?,?,?,?,?,?,?)", data)
    
    # Text search table
    cursor.execute("CREATE TABLE TextContents (id INTEGER PRIMARY KEY, title TEXT, body TEXT)")
    cursor.execute("INSERT INTO TextContents VALUES (1, 'Hello World', 'This is a test document')")
    cursor.execute("INSERT INTO TextContents VALUES (2, 'Foo Bar', 'Another document with different content')")
    cursor.execute("INSERT INTO TextContents VALUES (3, 'Baz Qux', 'Hello again, world!')")
    
    conn.commit()
    conn.close()
    return db_path

def setup_cache_with_db(cache_dir: Path, upa: str) -> Path:
    """Setup a cache directory with the test DB for a specific UPA."""
    # From app/utils/cache.py logic: cache_dir / sanitized_upa / tables.db
    safe_upa = upa.replace("/", "_").replace(":", "_").replace(" ", "_")
    target_dir = cache_dir / safe_upa
    target_dir.mkdir(parents=True, exist_ok=True)
    
    db_path = target_dir / "tables.db"
    create_test_db(db_path)
    return db_path

class TestAdvancedFeatures(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.headers["Authorization"] = "Bearer dummy_token"
        # Setup a real database in the configured cache directory
        self.test_upa = "12345/Test/1"
        self.db_path = setup_cache_with_db(Path(settings.CACHE_DIR), self.test_upa)

    def test_advanced_filtering(self):
        """Test strict filtering capabilities."""
        # 1. Greater Than
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "filters": [
                {"column": "score", "operator": "gt", "value": 90}
            ]
        })
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["total_count"], 1)
        self.assertEqual(data["data"][0][0], "G1") # G1 has score 95.5

        # 2. IN operator (list)
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "filters": [
                {"column": "gene_name", "operator": "in", "value": ["dnaA", "gyrA"]}
            ]
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_count"], 2)
        names = sorted([r[1] for r in data["data"]])
        self.assertEqual(names, ["dnaA", "gyrA"])

        # 3. Like (text search on specific column)
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "filters": [
                {"column": "gene_name", "operator": "like", "value": "gyr"}
            ]
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_count"], 2) # gyrA, gyrB

    def test_aggregations(self):
        """Test aggregation capabilities."""
        # 1. Simple Count
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "aggregations": [
                {"column": "*", "function": "count", "alias": "total"}
            ]
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Expecting one row with count
        self.assertEqual(data["headers"], ["total"])
        self.assertEqual(int(data["data"][0][0]), 5)

        # 2. Group By
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "group_by": ["is_active"],
            "aggregations": [
                {"column": "*", "function": "count", "alias": "cnt"},
                {"column": "score", "function": "avg", "alias": "avg_score"}
            ],
            "sort_column": "is_active",
            "sort_order": "ASC"
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # 0 (inactive): G2(45.2), G5(12.5) -> avg ~28.85
        # 1 (active): G1(95.5), G3(88.0), G4(87.5) -> avg ~90.33
        self.assertEqual(len(data["data"]), 2)
        self.assertEqual(data["data"][0][0], "0") # is_active=0
        self.assertEqual(data["data"][1][0], "1") # is_active=1

    def test_sorting_and_pagination(self):
        """Test sorting and pagination."""
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "sort_column": "score",
            "sort_order": "DESC",
            "limit": 2,
            "offset": 1
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["data"]), 2)
        # Scores descending: 95.5 (G1), 88.0 (G3), 87.5 (G4), 45.2 (G2), 12.5 (G5)
        # Offset 1 means we skip G1.
        # Should get G3 and G4.
        self.assertEqual(data["data"][0][0], "G3")
        self.assertEqual(data["data"][1][0], "G4")

    # Not testing global search heavily as it relies on FTS5 which might be optional/missing in some sqlite builds,
    # though QueryService attempts to create it.
    def test_global_search_fallback(self):
        """Test global search matches text columns."""
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "search_value": "dna*" # Use FTS5 prefix syntax
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # dnaA, dnaN should match 'dna*'
        self.assertTrue(len(data["data"]) >= 2, f"Expected >=2 matches for 'dna*', got {len(data['data'])}")

    def test_legacy_compatibility(self):
        """Test that legacy fields still work."""
        response = self.client.post("/table-data", json={
            "berdl_table_id": self.test_upa,
            "table_name": "Genes",
            "columns": "gene_id, gene_name", # String format
            "col_filter": {"gene_name": "dna"} # Legacy filter dict
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["headers"], ["gene_id", "gene_name"])
        # Should match dnaA, dnaN
        self.assertEqual(data["total_count"], 2)

if __name__ == "__main__":
    unittest.main()
