import unittest
import sqlite3
import tempfile
import shutil
import logging
from pathlib import Path
from app.services.data.query_service import QueryService, FilterSpec, AggregationSpec
from app.exceptions import TableNotFoundError

# Configure logging
logging.basicConfig(level=logging.ERROR)

class TestQueryService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.service = QueryService()
        
        # Create a test database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER, salary REAL, status TEXT)")
        data = [
            (1, "Alice", 30, 50000.0, "active"),
            (2, "Bob", 25, 45000.5, "inactive"),
            (3, "Charlie", 35, 70000.0, "active"),
            (4, "David", 30, 52000.0, "active"),
            (5, "Eve", 28, 49000.0, "inactive"),
        ]
        cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", data)
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_simple_select(self):
        result = self.service.execute_query(self.db_path, "users", limit=10)
        self.assertEqual(len(result["data"]), 5)
        self.assertEqual(result["total_count"], 5)
        self.assertEqual(result["headers"], ["id", "name", "age", "salary", "status"])

    def test_filter_numeric(self):
        filters = [FilterSpec(column="age", operator="gt", value=28)]
        result = self.service.execute_query(self.db_path, "users", filters=filters)
        # Should be Alice(30), Charlie(35), David(30)
        self.assertEqual(len(result["data"]), 3)
        self.assertEqual(result["total_count"], 3)

    def test_filter_text(self):
        filters = [FilterSpec(column="status", operator="eq", value="active")]
        result = self.service.execute_query(self.db_path, "users", filters=filters)
        self.assertEqual(len(result["data"]), 3)

    def test_sorting(self):
        # Sort by age DESC
        result = self.service.execute_query(self.db_path, "users", sort_column="age", sort_order="DESC")
        data = result["data"]
        # Charlie(35) first
        self.assertEqual(data[0][1], "Charlie")
        # Bob(25) last
        self.assertEqual(data[4][1], "Bob")

    def test_aggregation(self):
        aggs = [
            AggregationSpec(column="salary", function="avg", alias="avg_salary"),
            AggregationSpec(column="status", function="count", alias="count")
        ]
        result = self.service.execute_query(
            self.db_path, "users", 
            aggregations=aggs, 
            group_by=["status"],
            sort_column="status" 
        )
        
        self.assertEqual(len(result["data"]), 2)
        row_active = next(r for r in result["data"] if r[0] == "active")
        
        # Active: Alice(50k), Charlie(70k), David(52k) -> Avg 57333.33
        self.assertAlmostEqual(float(row_active[1]), 57333.33, delta=0.1)
        self.assertEqual(int(row_active[2]), 3)

    def test_sql_injection_sort_ignored(self):
        """Ensure sort column injection attacks are ignored (fallback to default)."""
        bad_col = "age; DROP TABLE users; --"
        result = self.service.execute_query(self.db_path, "users", sort_column=bad_col)
        self.assertEqual(len(result["data"]), 5)
        
        # Verify table still exists
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM users")
        self.assertEqual(cursor.fetchone()[0], 5)
        conn.close()

    def test_sql_injection_filter_safe(self):
        """Ensure filter value injection is handled safely as literal string."""
        filters = [FilterSpec(column="name", operator="eq", value="Alice' OR '1'='1")]
        result = self.service.execute_query(self.db_path, "users", filters=filters)
        self.assertEqual(len(result["data"]), 0) 

    def test_missing_table(self):
        with self.assertRaises(TableNotFoundError):
            self.service.execute_query(self.db_path, "non_existent_table")

if __name__ == "__main__":
    unittest.main()
