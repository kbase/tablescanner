#!/usr/bin/env python3
"""
Production readiness test for TableScanner + Viewer integration.
Tests both UPAs: 76990/7/2 and 76990/test2
Verifies all data flows work correctly.
"""
import os
import sys
import time
import requests
import json
from pathlib import Path

# Test configuration
UPAS = ["76990/7/2", "76990/test2"]
TOKEN = os.environ.get("KBASE_TOKEN", "")
ENV = os.environ.get("KB_ENV", "appdev")
TABLE_SCANNER_URL = os.environ.get("TABLE_SCANNER_URL", "http://127.0.0.1:8000")
TIMEOUT = 30

ENDPOINTS = {
    "appdev": {
        "workspace": "https://appdev.kbase.us/services/ws",
        "handle": "https://appdev.kbase.us/services/handle_service",
        "shock": "https://appdev.kbase.us/services/shock-api",
    },
    "prod": {
        "workspace": "https://kbase.us/services/ws",
        "handle": "https://kbase.us/services/handle_service",
        "shock": "https://kbase.us/services/shock-api",
    },
}


def test_table_scanner_health():
    """Test TableScanner service is running."""
    print("\n[Test 1] TableScanner Health Check...")
    try:
        r = requests.get(f"{TABLE_SCANNER_URL}/health", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"  ✓ Service: {data.get('service', 'unknown')}")
            print(f"  ✓ Status: {data.get('status', 'unknown')}")
            return True
        else:
            print(f"  ✗ HTTP {r.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        print(f"  → Is TableScanner running at {TABLE_SCANNER_URL}?")
        return False


def test_workspace_access(upa):
    """Test direct workspace access (POST only)."""
    print(f"\n[Test 2] Workspace Access for {upa}...")
    if not TOKEN:
        print("  ⚠ Skipped (no KBASE_TOKEN)")
        return None
    url = ENDPOINTS[ENV]["workspace"]
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "method": "Workspace.get_objects2",
        "params": [{"objects": [{"ref": upa}]}],
        "version": "1.1",
        "id": "test-ws"
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=(10, 25))
        if r.status_code == 200:
            data = r.json()
            if "error" in data:
                print(f"  ✗ API Error: {data['error'].get('message', 'Unknown')}")
                return None
            result = data.get("result", [{}])[0]
            pangenome_data = result.get("data", [{}])[0].get("pangenome_data", [])
            print(f"  ✓ Found {len(pangenome_data)} databases")
            return pangenome_data
        else:
            print(f"  ✗ HTTP {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return None


def test_table_scanner_databases(upa):
    """Test TableScanner /databases endpoint."""
    print(f"\n[Test 3] TableScanner /databases for {upa}...")
    url = f"{TABLE_SCANNER_URL}/databases"
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    params = {"upa": upa, "kb_env": ENV}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            dbs = data.get("databases", [])
            print(f"  ✓ Found {len(dbs)} databases")
            for db in dbs[:3]:  # Show first 3
                print(f"    - {db.get('db_name', 'unknown')}: {db.get('db_display_name', 'N/A')}")
            return dbs
        else:
            print(f"  ✗ HTTP {r.status_code}: {r.text[:300]}")
            return None
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return None


def test_table_scanner_tables(upa, db_name):
    """Test TableScanner /db/{db}/tables endpoint."""
    print(f"\n[Test 4] TableScanner /db/{db_name}/tables for {upa}...")
    url = f"{TABLE_SCANNER_URL}/db/{db_name}/tables"
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    params = {"upa": upa, "kb_env": ENV}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            tables = data.get("tables", [])
            print(f"  ✓ Found {len(tables)} tables")
            for table in tables[:5]:  # Show first 5
                name = table.get("name", "unknown")
                rows = table.get("row_count", 0)
                print(f"    - {name}: {rows:,} rows")
            return tables
        else:
            print(f"  ✗ HTTP {r.status_code}: {r.text[:300]}")
            return None
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return None


def test_table_scanner_data(upa, db_name, table_name):
    """Test TableScanner /db/{db}/tables/{table}/data endpoint."""
    print(f"\n[Test 5] TableScanner /db/{db_name}/tables/{table_name}/data for {upa}...")
    url = f"{TABLE_SCANNER_URL}/db/{db_name}/tables/{table_name}/data"
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    params = {"upa": upa, "kb_env": ENV, "limit": 10, "offset": 0}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            rows = data.get("data", [])
            total = data.get("total", 0)
            print(f"  ✓ Retrieved {len(rows)} rows (total: {total:,})")
            if rows and isinstance(rows[0], dict):
                cols = list(rows[0].keys())[:5]
                print(f"    Columns: {', '.join(cols)}...")
            elif rows:
                print(f"    Data format: {type(rows[0]).__name__}")
            return data
        else:
            print(f"  ✗ HTTP {r.status_code}: {r.text[:300]}")
            return None
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return None


def main():
    print("=" * 70)
    print("TableScanner + Viewer Production Readiness Test")
    print("=" * 70)
    print(f"TableScanner URL: {TABLE_SCANNER_URL}")
    print(f"KBase Env: {ENV}")
    print(f"Token: {'***' + TOKEN[-8:] if TOKEN else 'NOT SET (set KBASE_TOKEN)'}")
    print(f"UPAs to test: {', '.join(UPAS)}")
    
    # Test 1: Health check
    if not test_table_scanner_health():
        print("\n❌ TableScanner is not running. Start it with:")
        print("   cd tablescanner && uvicorn app.main:app --reload --port 8000")
        sys.exit(1)
    
    results = {}
    
    for upa in UPAS:
        print(f"\n{'=' * 70}")
        print(f"Testing UPA: {upa}")
        print('=' * 70)
        
        # Test 2: Workspace access
        pangenome_data = test_workspace_access(upa)
        
        # Test 3: TableScanner databases endpoint
        dbs = test_table_scanner_databases(upa)
        if not dbs:
            print(f"  ⚠ Skipping remaining tests for {upa}")
            results[upa] = {"status": "failed", "reason": "databases endpoint failed"}
            continue
        
        # Test 4 & 5: For each database, test tables and data
        db_results = {}
        for db in dbs[:2]:  # Test first 2 databases
            db_name = db.get("db_name")
            if not db_name:
                continue
            
            tables = test_table_scanner_tables(upa, db_name)
            if not tables:
                db_results[db_name] = {"status": "failed", "reason": "tables endpoint failed"}
                continue
            
            # Test data endpoint for first table
            if tables:
                table_name = tables[0].get("name")
                if table_name:
                    data = test_table_scanner_data(upa, db_name, table_name)
                    db_results[db_name] = {
                        "status": "success" if data else "partial",
                        "tables": len(tables),
                        "data_retrieved": data is not None
                    }
        
        results[upa] = {
            "status": "success" if db_results else "failed",
            "databases": len(dbs),
            "db_results": db_results
        }
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    for upa, result in results.items():
        status_icon = "✓" if result["status"] == "success" else "✗"
        print(f"{status_icon} {upa}: {result['status']}")
        if result.get("databases"):
            print(f"   Databases: {result['databases']}")
    
    # Check if all passed
    all_passed = all(r["status"] == "success" for r in results.values())
    if all_passed:
        print("\n✅ All tests passed! System is production-ready.")
        sys.exit(0)
    else:
        print("\n⚠ Some tests failed. Review output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
