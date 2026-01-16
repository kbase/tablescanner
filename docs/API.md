# TableScanner API

The **TableScanner** service provides read-only access to SQLite databases stored in KBase (via Blobstore handles or Workspace objects). It supports listing tables, inspecting schemas, and querying data with filtering, sorting, and pagination.

## Base URL
- **Development**: `http://localhost:8000`
- **Production**: `https://kbase.us/services/berdl_table_scanner` (or similar)

## Authentication
All endpoints require a KBase authentication token.
- **Header**: `Authorization: <token>` or `Authorization: Bearer <token>`

---

## 1. Service Status

### `GET /`
Basic service check.
- **Response**: `{"service": "TableScanner", "version": "1.0.0", "status": "running"}`

### `GET /health`
Detailed health check including connection pool stats.

---

## 2. Handle Access
Access databases via Blobstore Handle Reference (e.g., `KBH_12345`).

### `GET /handle/{handle_ref}/tables`
List all tables in the database.
- **Query Params**: `kb_env` (default: `appdev`)
- **Response**: List of tables with row/column counts.

### `GET /handle/{handle_ref}/tables/{table_name}/schema`
Get column definitions for a table.
- **Response**: Columns list (name, type, notnull, pk).

### `GET /handle/{handle_ref}/tables/{table_name}/data`
Query table data.
- **Query Params**:
  - `limit` (default: 100)
  - `offset` (default: 0)
  - `sort_column`, `sort_order` (`ASC`/`DESC`)
  - `search` (Global text search)
- **Response**: Headers, data rows, total count.

---

## 3. Object Access
Access databases via KBase Workspace Object Reference (UPA, e.g., `76990/7/2`).

### `GET /object/{ws_ref}/pangenomes`
List pangenomes associated with a BERDLTables object.

### `GET /object/{ws_ref}/tables`
List tables for a BERDLTables object.
- **Response**: Table list with schema overviews.

### `GET /object/{ws_ref}/tables/{table_name}/data`
Query table data (same parameters as Handle Access).

---

## 4. Legacy Endpoints
Maintained for backward compatibility.

### `GET /pangenomes`
List pangenomes by `berdl_table_id`.

### `GET /tables`
List tables by `berdl_table_id`.

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
