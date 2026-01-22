# TableScanner API

The **TableScanner** service provides read-only access to SQLite databases stored in KBase (via Workspace objects). It supports listing tables, inspecting schemas, and querying data with filtering, sorting, and pagination.

## Base URL
- **Development**: `http://localhost:8000`
- **Production**: `https://kbase.us/services/berdl_table_scanner` (or similar)

## Authentication

**Each user must provide their own KBase authentication token.** The service does not use a shared/service-level token for production access.

- **Header (recommended)**: `Authorization: <token>` or `Authorization: Bearer <token>`
- **Cookie**: `kbase_session=<token>` (useful for browser-based clients like DataTables Viewer)

> **Note for Developers**: The `KB_SERVICE_AUTH_TOKEN` environment variable is available as a legacy fallback for local testing only. It should NOT be relied upon in production.

---
## Performance
- **Gzip Support**: Responses >1KB are automatically compressed if the `Accept-Encoding: gzip` header is present.
- **Fast JSON**: All responses use optimized JSON serialization.
---

## 1. Service Status

### `GET /`
Basic service check.
- **Response**: `{"service": "TableScanner", "version": "1.0.0", "status": "running"}`

### `GET /health`
Detailed health check including connection pool stats.

---

## 2. Object Access
Access databases via KBase Workspace Object Reference (UPA, e.g., `76990/7/2`).

### Example curl (with auth)

```bash
# List tables for an object (replace WS_REF with a real UPA like 76990/7/2)
curl -X GET \
  "http://localhost:8000/object/WS_REF/tables?kb_env=appdev" \
  -H "accept: application/json" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### `GET /object/{ws_ref}/tables`
List tables for a BERDLTables object.
- **Response**: Table list with schema overviews.

### `GET /object/{ws_ref}/tables/{table_name}/data`
Query table data.
- **Query Params**:
  - `limit` (default: 100)
  - `offset` (default: 0)
  - `sort_column`, `sort_order` (`ASC`/`DESC`)
  - `search` (Global text search)
- **Response**: Headers, data rows, total count.

```bash
# Query table data (replace TABLE_NAME with a real table like Genes)
curl -X GET \
  "http://localhost:8000/object/WS_REF/tables/TABLE_NAME/data?limit=10&kb_env=appdev" \
  -H "accept: application/json" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### `GET /object/{ws_ref}/tables/{table_name}/stats`
Get detailed statistics for all columns in a table.
- **Response**: Column statistics including null counts, distinct counts, min/max/mean, and samples.


---

## 3. Data Access

### `POST /table-data`
Complex query endpoint supporting advanced filtering.
- **Body**:
  ```json
  {
    "berdl_table_id": "...",
    "table_name": "Genes",
    "limit": 100,
    "filters": [
       {"column": "contigs", "operator": "gt", "value": 50},
       {"column": "gene_name", "operator": "like", "value": "kinase"}
    ]
  }
  ```
- **Supported Operators**: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `like`, `ilike`, `in`, `not_in`, `between`, `is_null`, `is_not_null`.

---

## 4. Local Database Upload

### `POST /upload`
Upload a temporary SQLite database file to the server. Useful for testing or serving local files.

- **Request**: Multipart form data with key `file`
- **Response**:
  ```json
  {
    "handle": "local:uuid-string",
    "filename": "my_db.db",
    "size_bytes": 10240,
    "message": "Database uploaded successfully"
  }
  ```

### Usage Workflow
1. **Upload File**:
   ```bash
   curl -X POST "http://localhost:8000/upload" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@/path/to/test.db"
   ```
2. **Use Handle**: The returned `handle` (e.g., `local:abc-123`) can be used as the `berdl_table_id` or `ws_ref` in any other endpoint.
   - List tables: `GET /object/local:abc-123/tables`
   - Query data: `POST /table-data` with `"berdl_table_id": "local:abc-123"`

