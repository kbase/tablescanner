import os
import pytest
import sqlite3
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

@pytest.fixture
def dummy_sqlite_db():
    """Create a temporary SQLite database with some data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        conn = sqlite3.connect(tmp.name)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE TestTable (id INTEGER PRIMARY KEY, name TEXT)")
        cursor.execute("INSERT INTO TestTable (name) VALUES ('Alpha')")
        cursor.execute("INSERT INTO TestTable (name) VALUES ('Beta')")
        conn.commit()
        conn.close()
        tmp_path = Path(tmp.name)
        yield tmp_path
        # Cleanup
        if tmp_path.exists():
            tmp_path.unlink()

def test_upload_and_query_flow(dummy_sqlite_db):
    """
    Test the full flow:
    1. Upload DB -> Get handle
    2. List tables -> Success
    3. Query data -> Success
    """
    # 1. Upload
    with open(dummy_sqlite_db, "rb") as f:
        response = client.post(
            "/upload",
            files={"file": ("my_test.db", f, "application/vnd.sqlite3")}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "handle" in data
    assert data["handle"].startswith("local:")
    assert data["message"] == "Database uploaded successfully"
    
    handle = data["handle"]
    
    # 2. List Tables
    # Need to mock the KBase ID check or auth if implied, BUT local handles bypass KBase download.
    # The endpoint /object/{ref}/tables takes the ref.
    # Note: Authorization header might still be checked by get_auth_token.
    # We provide a dummy token to pass the check.
    headers = {"Authorization": "Bearer dummy_token"}
    
    # We must patch get_object_type or it might try to call KBase for 'local:...' which is not a valid UPA.
    # Let's check routes.py: list_tables_by_object calls get_object_type logic.
    # Wait, routes.py:325 handles object_type by calling get_object_type.
    # get_object_type might fail for local handle. I need to make sure get_object_type handles it gracefully or mock it.
    
    # Actually, in routes.py, I should update get_object_type logic OR just let it fail non-critically?
    # routes.py:301 catches Exception and sets object_type = None. That's fine.
    
    response = client.get(f"/object/{handle}/tables", headers=headers)
    assert response.status_code == 200, response.text
    tables_data = response.json()
    
    assert tables_data["object_type"] == "LocalDatabase" or tables_data["object_type"] is None
    names = [t["name"] for t in tables_data["tables"]]
    assert "TestTable" in names
    
    # 3. Query Data
    query_payload = {
        "berdl_table_id": handle,
        "table_name": "TestTable",
        "limit": 10
    }
    response = client.post("/table-data", json=query_payload, headers=headers)
    assert response.status_code == 200
    query_data = response.json()
    assert len(query_data["data"]) == 2
    assert query_data["data"][0][1] == "Alpha"

def test_upload_security_traversal():
    """Test that we can't directory traverse with a crafted handle."""
    headers = {"Authorization": "Bearer dummy_token"}
    
    # Try to access a file outside uploads via path traversal
    # get_object_db_path has a check for ".."
    
    # We'll try to use a handle that looks like traversal
    bad_handle = "local:../../../../etc/passwd" 
    
    response = client.get(f"/object/{bad_handle}/tables", headers=headers)
    # converting slash to %2F might happen in client depending on how it's passed,
    # but the routes.py extracts it.
    # The check in db_helper.py should catch it.
    
    # FastAPI path parameter handling might encode it, but we can try injecting it.
    # Since {ws_ref:path} captures slashes, we can test:
    response = client.get("/object/local:..%2F..%2Fetc%2Fpasswd/tables", headers=headers)
    
    # Should get 400 or 500, but definitely not success.
    # Our db_helper validation raises 400.
    assert response.status_code in (400, 404, 500)

def test_upload_invalid_file_format():
    """Test that uploading a non-SQLite file is rejected."""
    # Create a dummy text file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(b"This is not a SQLite database")
        tmp_path = Path(tmp.name)
    
    try:
        with open(tmp_path, "rb") as f:
            response = client.post(
                "/upload",
                files={"file": ("fake.db", f, "application/vnd.sqlite3")}
            )
        
        # Should be rejected due to header mismatch
        assert response.status_code == 400
        assert "Invalid SQLite file format" in response.json()["detail"]
        
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

def test_upload_and_get_stats(dummy_sqlite_db):
    """Test getting statistics for an uploaded table."""
    # 1. Upload
    with open(dummy_sqlite_db, "rb") as f:
        response = client.post(
            "/upload",
            files={"file": ("stats_test.db", f, "application/vnd.sqlite3")}
        )
    handle = response.json()["handle"]
    
    # 2. Get Stats
    headers = {"Authorization": "Bearer dummy_token"}
    response = client.get(f"/object/{handle}/tables/TestTable/stats", headers=headers)
    
    assert response.status_code == 200
    stats = response.json()
    assert stats["table"] == "TestTable"
    assert stats["row_count"] == 2
    
    # Check column stats
    cols = {c["column"]: c for c in stats["columns"]}
    assert "name" in cols
    assert cols["name"]["distinct_count"] == 2
    assert "Alpha" in cols["name"]["sample_values"]
