# Usage Guide

This guide covers production usage of the TableScanner service.

## API Endpoint
The service is deployed at:
```
https://appdev.kbase.us/services/berdl_table_scanner
```

## Authentication
All requests require a valid KBase authentication token passed in the `Authorization` header.

```bash
Authorization: <YOUR_TOKEN>
```

---

## 1. Using the Hierarchical REST API (Browser-friendly)

This style uses hierarchical paths and standard GET requests. It is ideal for web applications or simple data navigation.

### List Available Tables
Get a list of all tables found in a KBase object.

**Endpoint:** `GET /object/{upa}/tables`

**Example:**
```bash
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables"
```

### Query Table Data
Retrieve paginated data from a specific table.

**Endpoint:** `GET /object/{upa}/tables/{table_name}/data`

**Parameters:**
- `limit`: (int) Maximum rows (default 100)
- `offset`: (int) Skip rows (default 0)
- `search`: (string) Global search term
- `sort_column`: (string) Column to sort by
- `sort_order`: (string) "ASC" or "DESC"

**Example:**
```bash
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/data?limit=5"
```

---

## 2. Using the Flat POST API (Script-friendly)

The Flat POST API is recommended for Python scripts and programmatic access. It allows sending complex query parameters in a single JSON body.

**Endpoint:** `POST /table-data`

### Implementation Example (Python)

```python
import requests
import json

url = "https://appdev.kbase.us/services/berdl_table_scanner/table-data"
headers = {"Authorization": "YOUR_KBASE_TOKEN"}

payload = {
    "berdl_table_id": "76990/7/2",
    "table_name": "Metadata_Conditions",
    "limit": 50,
    "offset": 0,
    "search_value": "glucose",
    "col_filter": {
        "organism": "E. coli"
    },
    "sort_column": "yield",
    "sort_order": "DESC"
}

response = requests.post(url, json=payload, headers=headers)
data = response.json()

print(f"Retrieved {len(data['data'])} rows.")
```

---

## Pro Tips

### Multi-Source Search
The metadata endpoints support comma-separated IDs to aggregate pangenomes across multiple objects.

```bash
GET /pangenomes?berdl_table_id=76990/7/2,76990/8/1
```

### Performance
The first request for a large dataset may take a few seconds as the service downloads and indexes the database. Subsequent requests will be near-instant.

---

## Web Viewer
Access the interactive viewer at:
`https://appdev.kbase.us/services/berdl_table_scanner/static/viewer.html` # TODO: implement this
