# Usage Guide

This guide covers production usage of the TableScanner service.

## API Endpoint
The service is deployed at:
```
https://appdev.kbase.us/services/berdl_table_scanner
```

## Python API Usage

You can interact with the service programmatically using Python's `requests` library.

### 1. Listing Pangenomes
```python
import requests

service_url = "https://appdev.kbase.us/services/berdl_table_scanner"
token = "YOUR_KBASE_TOKEN"
berdl_id = "76990/ADP1Test"

headers = {"Authorization": token}
params = {"berdl_table_id": berdl_id}

response = requests.get(f"{service_url}/pangenomes", headers=headers, params=params)
data = response.json()

print(f"Found {data['pangenome_count']} pangenomes")
for pg in data['pangenomes']:
    print(f"- {pg['pangenome_id']} (Source: {pg['source_berdl_id']})")
```

### 2. Querying Table Data

Query table data with filtering and column selection. 

```python
headers = {"Authorization": token}

# Get data from "Conditions" table
berdl_id = "76990/ADP1Test"
table_name = "Conditions"

payload = {
    "berdl_table_id": berdl_id,
    "table_name": table_name,
    "columns": "Database_ID, Name",
    "col_filter": {
        "Name": "test"
    },
    "order_by": [
        {"column": "Name", "direction": "ASC"}
    ],
    "limit": 5,
    "offset": 0
}

response = requests.post(f"{service_url}/table-data", json=payload, headers=headers)
data = response.json()

print(f"Loaded {data['row_count']} rows from {table_name}")
print(f"Headers: {data['headers']}")
```

## Multi-Source Querying

The `/pangenomes` endpoint supports multiple comma-separated BERDL IDs.

```python
multi_params = {
    "berdl_table_id": "76990/ADP1Test, 12345/AnotherTable"
}

response = requests.get(f"{service_url}/pangenomes", headers=headers, params=multi_params)
# Returns pangenomes from BOTH objects in a single list
```

## Viewer Usage

The web viewer is available at:
`https://appdev.kbase.us/services/berdl_table_scanner/static/viewer.html`

1. Enter **Auth Token**.
2. Enter **BERDL Table ID(s)** (comma-separated).
3. Click **Search**.
4. Use the interface to filter, sort, and export data.
