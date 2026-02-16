# TableScanner API Reference

The **TableScanner** service provides read-only access to SQLite databases stored in KBase (via Workspace objects). It supports listing tables, inspecting schemas, querying data with filtering, sorting, and pagination, and multi-database objects.

## Base URL

| Environment | URL |
|-------------|-----|
| **AppDev** | `https://appdev.kbase.us/services/berdl_table_scanner` |
| **Production** | `https://kbase.us/services/berdl_table_scanner` |
| **Local Development** | `http://localhost:8000` |

## Authentication

**Each user must provide their own KBase authentication token.** The service does not use a shared/service-level token for production access.

- **Header (recommended)**: `Authorization: <token>` or `Authorization: Bearer <token>`
- **Cookie**: `kbase_session=<token>` (useful for browser-based clients like DataTables Viewer)

> **Note for Developers**: The `KB_SERVICE_AUTH_TOKEN` environment variable is available as a legacy fallback for local testing only. It should NOT be relied upon in production.

---

## Performance
- **Gzip Support**: Responses >1KB are automatically compressed if the `Accept-Encoding: gzip` header is present.
- **Fast JSON**: All responses use optimized JSON serialization (ORJSON).

---

## 1. Service Status

### `GET /`
Basic service check.
- **Response**: `{"service": "TableScanner", "version": "1.0.0", "status": "running"}`

### `GET /health`
Detailed health check including connection pool stats.

**Example:**
```bash
curl "https://appdev.kbase.us/services/berdl_table_scanner/health"
```

---

## 2. Object Access (Single Database)

Access databases via KBase Workspace Object Reference (UPA, e.g., `76990/7/2`).

### `GET /object/{ws_ref}/tables`
List tables for a BERDLTables object.

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables"
```

**Response**: Table list with schema overviews, row counts, and column counts.

### `GET /object/{ws_ref}/tables/{table_name}/data`
Query table data.

**Query Params:**
- `limit` (default: 100, max: 500000)
- `offset` (default: 0)
- `sort_column`, `sort_order` (`ASC`/`DESC`)
- `search` (Global text search)

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/data?limit=100&search=kinase"
```

### `GET /object/{ws_ref}/tables/{table_name}/stats`
Get detailed statistics for all columns in a table.

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/stats"
```

**Response**: Column statistics including null counts, distinct counts, min/max/mean, and sample values.

---

## 3. Multi-Database Access (v2.1)

For objects containing multiple databases.

**Note**: All multi-database endpoints use query parameters for the UPA to avoid path parsing issues with slashes in workspace references.

### `GET /databases?upa={ws_ref}`
List all databases within an object.

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/databases?upa=76990/7/2"
```

**Response:**
```json
{
  "berdl_table_id": "76990/7/2",
  "databases": [
    {"db_name": "GCF_000368685.1", "db_display_name": "E. coli", "tables": [...]},
    {"db_name": "GCF_004211955.1", "db_display_name": "E. coli O157:H7", "tables": [...]}
  ],
  "has_multiple_databases": true
}
```

### `GET /db/{db_name}/tables?upa={ws_ref}`
List tables in a specific database.

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/db/GCF_000368685.1/tables?upa=76990/Test2"
```

### `GET /db/{db_name}/tables/{table_name}/data?upa={ws_ref}`
Query data from a specific database.

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/db/GCF_000368685.1/tables/Genes/data?upa=76990/Test2&limit=100"
```

---

## 4. Advanced Query (POST)

### `POST /table-data`
Complex query endpoint supporting advanced filtering and aggregations.

**Request Body:**
```json
{
  "berdl_table_id": "76990/7/2",
  "table_name": "Genes",
  "limit": 100,
  "offset": 0,
  "filters": [
    {"column": "contigs", "operator": "gt", "value": 50},
    {"column": "gene_name", "operator": "like", "value": "kinase"}
  ],
  "sort_column": "gene_length",
  "sort_order": "DESC"
}
```

**Supported Filter Operators:**
| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal | `{"column": "status", "operator": "eq", "value": "active"}` |
| `ne` | Not equal | `{"column": "status", "operator": "ne", "value": "deleted"}` |
| `gt` | Greater than | `{"column": "length", "operator": "gt", "value": 1000}` |
| `gte` | Greater than or equal | `{"column": "score", "operator": "gte", "value": 0.95}` |
| `lt` | Less than | `{"column": "length", "operator": "lt", "value": 100}` |
| `lte` | Less than or equal | `{"column": "score", "operator": "lte", "value": 0.5}` |
| `like` | Contains (case-sensitive) | `{"column": "name", "operator": "like", "value": "kinase"}` |
| `ilike` | Contains (case-insensitive) | `{"column": "name", "operator": "ilike", "value": "KINASE"}` |
| `in` | Value in list | `{"column": "type", "operator": "in", "value": ["CDS", "gene"]}` |
| `not_in` | Value not in list | `{"column": "type", "operator": "not_in", "value": ["pseudo"]}` |
| `between` | Range (inclusive) | `{"column": "length", "operator": "between", "value": [100, 500]}` |
| `is_null` | Is NULL | `{"column": "description", "operator": "is_null"}` |
| `is_not_null` | Is not NULL | `{"column": "product", "operator": "is_not_null"}` |

```bash
curl -X POST -H "Authorization: Bearer $KB_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"berdl_table_id": "76990/7/2", "table_name": "Genes", "limit": 100}' \
     "https://appdev.kbase.us/services/berdl_table_scanner/table-data"
```

---

## 5. Local Database Upload

### `POST /upload`
Upload a temporary SQLite database file to the server. Useful for testing or serving local files.

**Request**: Multipart form data with key `file`

**Response:**
```json
{
  "handle": "local:sha256hash",
  "filename": "my_db.db",
  "size_bytes": 10240,
  "message": "Database uploaded successfully"
}
```

**Features:**
- **Deduplication**: Same file uploaded twice returns the same handle (SHA-256 based)
- **Max Size**: 500MB (configurable)
- **Expiration**: Uploaded files expire after 1 hour
- **Quota**: 10GB total upload storage (auto-cleanup when exceeded)

### Usage Workflow

1. **Upload File**:
   ```bash
   curl -X POST "https://appdev.kbase.us/services/berdl_table_scanner/upload" \
        -F "file=@/path/to/test.db"
   ```

2. **Use Handle**: The returned `handle` (e.g., `local:abc123def456...`) can be used as the `berdl_table_id` or `ws_ref` in any other endpoint.
   - List tables: `GET /object/local:abc123.../tables`
   - Query data: `POST /table-data` with `"berdl_table_id": "local:abc123..."`

---

## Response Format

All data query endpoints return a consistent response structure:

```json
{
  "headers": ["gene_id", "gene_name", "product"],
  "data": [["ACIAD_RS00005", "dnaA", "replication initiator"], ...],
  "row_count": 100,
  "total_count": 3356,
  "filtered_count": 3356,
  "table_name": "Genes",
  "response_time_ms": 125.5,
  "db_query_ms": 42.0,
  "cached": false,
  "limit": 100,
  "offset": 0
}
```

---

## 6. System Logs

### `GET /system/logs`

Retrieve recent in-memory logs from the TableScanner service. This is primarily used by frontend tools (like the DataTables Viewer) for debugging and monitoring.

**Query Parameters:**
- `limit` (optional, default: 100, max: 1000) – number of log entries to return
- `level` (optional) – minimum log level (`debug`, `info`, `warn`, `error`, `critical`)

**Example:**

```bash
curl "https://appdev.kbase.us/services/berdl_table_scanner/system/logs?limit=50&level=error"
```

**Response (simplified):**

```json
[
  {
    "timestamp": "2026-02-13T10:26:17.512994",
    "level": "error",
    "message": "Error accessing object database 99999/999/999: ...",
    "source": "backend",
    "logger": "app.utils.workspace"
  }
]
```

---

## Error Responses

| Status | Description |
|--------|-------------|
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Missing or invalid token |
| 404 | Not Found - Object or table not found |
| 413 | Payload Too Large - File exceeds 500MB |
| 422 | Unprocessable Entity - Invalid filter syntax |
| 500 | Internal Server Error |
| 507 | Insufficient Storage - Upload quota exceeded |
