import requests
import json
import os

# Set your KBase authentication token
TOKEN = os.environ.get("KBASE_TOKEN")
if not TOKEN:
    raise RuntimeError("KBASE_TOKEN environment variable is not set.")
HEADERS = {"Authorization": TOKEN}
BASE_URL = "http://127.0.0.1:8000"

# ----------------------------------------------------------
# STYLE 1: HIERARCHICAL REST (GET)
# Ideal for simple navigation and web viewers
# ----------------------------------------------------------

print("\n--- REST: List Tables ---")
# Literal path: /object/{upa}/tables
res = requests.get(f"{BASE_URL}/object/76990/7/2/tables", headers=HEADERS)
res.raise_for_status()
print(json.dumps(res.json()["tables"][:3], indent=2))



print("\n--- REST: Get Top 3 Genes ---")
# Literal path: /object/{upa}/tables/{table_name}/data
res = requests.get(f"{BASE_URL}/object/76990/7/2/tables/Genes/data", params={"limit": 3}, headers=HEADERS)
res.raise_for_status()
print(json.dumps(res.json()["data"], indent=2))



print("\n--- REST: Filtered Search (kinase) ---")
# Literal path with query parameters
params = {"limit": 3, "search": "kinase"}
res = requests.get(f"{BASE_URL}/object/76990/7/2/tables/Genes/data", params=params, headers=HEADERS)
res.raise_for_status()
print(json.dumps(res.json()["data"], indent=2))


# ----------------------------------------------------------
# STYLE 2: FLAT POST
# Ideal for complex queries and production scripts
# ----------------------------------------------------------

print("\n--- POST: Basic Fetch (3 rows) ---")
# Single endpoint for all data: /table-data
payload = {
    "berdl_table_id": "76990/7/2",
    "table_name": "Conditions",
    "limit": 3
}
res = requests.post(f"{BASE_URL}/table-data", json=payload, headers=HEADERS)
res.raise_for_status()
print(json.dumps(res.json()["data"], indent=2))



print("\n--- POST: Column-Specific Filter (Carbon_source=pyruvate) ---")
# Precise AND-logic filtering via col_filter
payload = {
    "berdl_table_id": "76990/7/2",
    "table_name": "Conditions",
    "limit": 3,
    "col_filter": {"Carbon_source": "pyruvate"}
}
res = requests.post(f"{BASE_URL}/table-data", json=payload, headers=HEADERS)
res.raise_for_status()
print(json.dumps(res.json()["data"], indent=2))



print("\n--- POST: Sorted Multi-column Query ---")
# Support for complex ordering
payload = {
    "berdl_table_id": "76990/7/2",
    "table_name": "Genes",
    "limit": 3,
    "order_by": [
        {"column": "Length", "direction": "DESC"},
        {"column": "ID", "direction": "ASC"}
    ]
}
res = requests.post(f"{BASE_URL}/table-data", json=payload, headers=HEADERS)
res.raise_for_status()
print(json.dumps(res.json()["data"], indent=2))
