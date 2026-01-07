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

**Response**:
```json
{
    "berdl_table_id": "76990/7/2",
    "object_type": "KBaseFBA.GenomeDataLakeTables-2.0",
    "tables": [
        {"name": "Genes", "row_count": 3356, "column_count": 18},
        {"name": "Metadata_Conditions", "row_count": 42, "column_count": 12}
    ],
    "source": "Cache"
}
```
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
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/data?limit=1"

**Response**:
```json
{
    "headers": ["gene_id", "contig_id", "start", "..."],
    "data": [["gene_1", "contig_A", "100", "..."]],
    "row_count": 1,
    "total_count": 3356,
    "filtered_count": 3356,
    "object_type": "KBaseFBA.GenomeDataLakeTables-2.0",
    "response_time_ms": 12.4
}
```
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

**Example Response**:
```json
{
    "headers": ["organism", "yield", "..."],
    "data": [["E. coli", "0.42", "..."]],
    "row_count": 1,
    "total_count": 500,
    "filtered_count": 50,
    "object_type": "KBaseFBA.GenomeDataLakeTables-2.0",
    "response_time_ms": 15.6
}
```

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

## Web Viewer: Research Data Explorer

The TableScanner interactive viewer is a premium, single-page application built for high-performance research.

### Key Operations
1. **Connect**: Enter a KBase UPA (e.g. `76990/7/2`) and your Auth Token to load available tables.
2. **Explore**: Use the IDE-like sidebar to navigate between pangenomes and tables.
3. **Analyze**: 
   - **Global Search**: Instantly filters all columns with high-contrast highlighting.
   - **Density Control**: Toggle between `Compact`, `Default`, and `Comfortable` views.
   - **Column Management**: Custom visibility toggles for wide datasets.
4. **Export**: One-click **Export to CSV** for local analysis.

### Visual Architecture
- **Scientific Modern Theme**: A professional light mode designed for long sessions.
- **Dynamic Feedback**: Real-time status bar updates with cache performance metrics.
- **Sticky Layout**: Fixed headers and primary columns ensure context is never lost during scrolling.
