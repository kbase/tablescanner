# TableScanner API Reference

Complete API documentation for the TableScanner service.

## Base URL

The service is typically deployed at:
- Development: `http://localhost:8000`
- Production: `https://kbase.us/services/berdl_table_scanner`

## Authentication

All endpoints require a KBase authentication token passed in the `Authorization` header:

```
Authorization: Bearer <token>
```

Or as a simple token:

```
Authorization: <token>
```

## Endpoints

### Health Check

#### GET /health

Returns service health status and connection pool information.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00Z",
  "mode": "cached_sqlite",
  "data_dir": "/tmp/tablescanner_cache",
  "config_dir": "/tmp/tablescanner_cache/configs",
  "cache": {
    "databases_cached": 2,
    "connections": [
      {
        "db_path": "/tmp/tablescanner_cache/76990_7_2/tables.db",
        "last_access_seconds_ago": 120.5,
        "access_count": 15,
        "prepared_statements": 3
      }
    ]
  }
}
```

### List Tables

#### GET /object/{ws_ref}/tables

List all tables in a KBase object database.

**Parameters:**
- `ws_ref` (path): KBase workspace object reference (e.g., "76990/7/2")
- `kb_env` (query, optional): KBase environment (default: "appdev")
- `Authorization` (header, required): KBase authentication token

**Response:**
```json
{
  "berdl_table_id": "local/76990_7_2",
  "object_type": "KBaseGeneDataLakes.BERDLTables-1.0",
  "tables": [
    {
      "name": "Genes",
      "displayName": "Genes",
      "row_count": 3356,
      "column_count": 18
    }
  ],
  "source": "Local",
  "has_config": false,
  "config_source": null,
  "schemas": {
    "Genes": {
      "gene_id": "TEXT",
      "contigs": "INTEGER"
    }
  },
  "database_size_bytes": 1048576,
  "total_rows": 3356,
  "api_version": "2.0"
}
```

### Get Table Schema

#### GET /schema/{db_name}/tables/{table_name}

Get detailed schema information for a table.

**Parameters:**
- `db_name` (path): Database identifier (format: "local/{berdl_table_id}" or "handle/{handle_ref}")
- `table_name` (path): Name of the table
- `kb_env` (query, optional): KBase environment
- `Authorization` (header, required): KBase authentication token

**Response:**
```json
{
  "table": "Genes",
  "columns": [
    {
      "name": "gene_id",
      "type": "TEXT",
      "notnull": true,
      "pk": false,
      "dflt_value": null
    },
    {
      "name": "contigs",
      "type": "INTEGER",
      "notnull": false,
      "pk": false,
      "dflt_value": null
    }
  ],
  "indexes": [
    {
      "name": "idx_Genes_gene_id",
      "sql": "CREATE INDEX idx_Genes_gene_id ON \"Genes\"(\"gene_id\")"
    }
  ]
}
```

#### GET /schema/{db_name}/tables

Get schema information for all tables in a database.

**Response:**
```json
{
  "Genes": {
    "table": "Genes",
    "columns": [...],
    "indexes": [...]
  },
  "Metadata_Conditions": {
    "table": "Metadata_Conditions",
    "columns": [...],
    "indexes": [...]
  }
}
```

### Get Table Data

#### GET /object/{ws_ref}/tables/{table_name}/data

Query table data with filtering, sorting, and pagination.

**Parameters:**
- `ws_ref` (path): KBase workspace object reference
- `table_name` (path): Name of the table
- `limit` (query, optional): Maximum rows to return (default: 100, max: 500000)
- `offset` (query, optional): Number of rows to skip (default: 0)
- `sort_column` (query, optional): Column to sort by
- `sort_order` (query, optional): Sort direction - "ASC" or "DESC" (default: "ASC")
- `search` (query, optional): Global search term
- `kb_env` (query, optional): KBase environment
- `Authorization` (header, required): KBase authentication token

**Response:**
```json
{
  "headers": ["gene_id", "gene_name", "contigs"],
  "data": [
    ["ACIAD_RS00005", "dnaA", "1"],
    ["ACIAD_RS00010", "dnaN", "1"]
  ],
  "row_count": 2,
  "total_count": 3356,
  "filtered_count": 3356,
  "response_time_ms": 125.5,
  "db_query_ms": 42.0,
  "table_name": "Genes",
  "sqlite_file": "/tmp/tablescanner_cache/76990_7_2/tables.db",
  "object_type": "KBaseGeneDataLakes.BERDLTables-1.0"
}
```

#### POST /table-data

Enhanced table data query with full DataTables Viewer API support.

**Request Body:**
```json
{
  "berdl_table_id": "local/76990_7_2",
  "table_name": "Genes",
  "limit": 100,
  "offset": 0,
  "columns": ["gene_id", "gene_name", "contigs"],
  "sort_column": "gene_id",
  "sort_order": "ASC",
  "search_value": "dna",
  "filters": [
    {
      "column": "contigs",
      "operator": "gt",
      "value": "50"
    },
    {
      "column": "gene_name",
      "operator": "like",
      "value": "kinase"
    }
  ],
  "aggregations": null,
  "group_by": null
}
```

**Response:**
```json
{
  "headers": ["gene_id", "gene_name", "contigs"],
  "data": [
    ["ACIAD_RS00005", "dnaA", "1"],
    ["ACIAD_RS00010", "dnaN", "1"]
  ],
  "total_count": 3356,
  "column_types": [
    {
      "name": "gene_id",
      "type": "TEXT",
      "notnull": true,
      "pk": false,
      "dflt_value": null
    },
    {
      "name": "contigs",
      "type": "INTEGER",
      "notnull": false,
      "pk": false,
      "dflt_value": null
    }
  ],
  "query_metadata": {
    "query_type": "select",
    "sql": "SELECT \"gene_id\", \"gene_name\", \"contigs\" FROM \"Genes\" WHERE \"contigs\" > ? AND \"gene_name\" LIKE ? ORDER BY \"gene_id\" ASC LIMIT 100 OFFSET 0",
    "filters_applied": 2,
    "has_search": false,
    "has_sort": true,
    "has_group_by": false,
    "has_aggregations": false
  },
  "cached": false,
  "execution_time_ms": 15.2,
  "limit": 100,
  "offset": 0,
  "table_name": "Genes",
  "database_path": "/tmp/tablescanner_cache/76990_7_2/tables.db"
}
```

### Filter Operators

The following filter operators are supported:

- `eq` - Equals
- `ne` - Not equals
- `gt` - Greater than
- `gte` - Greater than or equal
- `lt` - Less than
- `lte` - Less than or equal
- `like` - Pattern match (case-sensitive)
- `ilike` - Pattern match (case-insensitive)
- `in` - Value in list
- `not_in` - Value not in list
- `between` - Range (requires `value` and `value2`)
- `is_null` - Null check (no value needed)
- `is_not_null` - Not null check (no value needed)

**Type-Aware Filtering:**

For numeric columns (INTEGER, REAL, NUMERIC), string filter values are automatically converted to numbers before SQL binding. For example:

```json
{
  "column": "contigs",
  "operator": "gt",
  "value": "50"  // Automatically converted to integer 50
}
```

This ensures proper numeric comparison: `contigs > 50` instead of `contigs > "50"`.

### Aggregations

#### POST /api/aggregate/{db_name}/tables/{table_name}

Execute aggregation query with GROUP BY.

**Parameters:**
- `db_name` (path): Database identifier
- `table_name` (path): Name of the table
- `kb_env` (query, optional): KBase environment
- `Authorization` (header, required): KBase authentication token

**Request Body:**
```json
{
  "group_by": ["category"],
  "aggregations": [
    {
      "column": "value",
      "function": "sum",
      "alias": "total"
    },
    {
      "column": "value",
      "function": "avg",
      "alias": "average"
    }
  ],
  "filters": [
    {
      "column": "value",
      "operator": "gt",
      "value": 100
    }
  ],
  "limit": 100,
  "offset": 0
}
```

**Supported Aggregation Functions:**
- `count` - Count rows
- `sum` - Sum of values
- `avg` - Average of values
- `min` - Minimum value
- `max` - Maximum value
- `stddev` - Standard deviation (approximate)
- `variance` - Variance (approximate)
- `distinct_count` - Count distinct values

**Response:**
```json
{
  "headers": ["category", "total", "average"],
  "data": [
    ["A", "1000", "100.5"],
    ["B", "2000", "200.3"]
  ],
  "total_count": 2,
  "column_types": [
    {"name": "category", "type": "TEXT", "notnull": false, "pk": false, "dflt_value": null},
    {"name": "total", "type": "REAL", "notnull": false, "pk": false, "dflt_value": null},
    {"name": "average", "type": "REAL", "notnull": false, "pk": false, "dflt_value": null}
  ],
  "query_metadata": {
    "query_type": "aggregate",
    "sql": "SELECT \"category\", SUM(\"value\") AS \"total\", AVG(\"value\") AS \"average\" FROM \"Data\" WHERE \"value\" > ? GROUP BY \"category\" LIMIT 100 OFFSET 0",
    "filters_applied": 1,
    "has_search": false,
    "has_sort": false,
    "has_group_by": true,
    "has_aggregations": true
  },
  "cached": false,
  "execution_time_ms": 25.3,
  "limit": 100,
  "offset": 0,
  "table_name": "Data",
  "database_path": "/tmp/tablescanner_cache/76990_7_2/tables.db"
}
```

### Column Statistics

#### GET /object/{db_name}/tables/{table_name}/stats

Get pre-computed column statistics.

**Parameters:**
- `db_name` (path): Database identifier
- `table_name` (path): Name of the table
- `kb_env` (query, optional): KBase environment
- `Authorization` (header, required): KBase authentication token

**Response:**
```json
{
  "table": "Genes",
  "row_count": 3356,
  "columns": [
    {
      "column": "contigs",
      "type": "INTEGER",
      "null_count": 0,
      "distinct_count": 5,
      "min": 1,
      "max": 100,
      "mean": 50.5,
      "median": 50,
      "stddev": 28.87,
      "sample_values": [1, 2, 3, 4, 5]
    }
  ],
  "last_updated": 1705320000000
}
```

### Cache Management

#### GET /cache

List all cached database items.

**Response:**
```json
{
  "cache_dir": "/tmp/tablescanner_cache",
  "items": [
    {
      "id": "76990_7_2",
      "berdl_table_id": "76990/7/2",
      "databases": 1,
      "total_size_bytes": 1048576,
      "pangenomes": []
    }
  ],
  "total": 1
}
```

#### POST /clear-cache

Clear cached databases.

**Parameters:**
- `berdl_table_id` (query, optional): Specific database to clear (clears all if not provided)

**Response:**
```json
{
  "status": "success",
  "message": "Cleared cache for 76990/7/2"
}
```

## Error Responses

All endpoints return consistent error responses:

```json
{
  "error": "Error type",
  "message": "Detailed error message",
  "db_name": "database_name"  // If applicable
}
```

**HTTP Status Codes:**
- `200` - Success
- `400` - Bad request (invalid parameters)
- `401` - Unauthorized (missing or invalid token)
- `404` - Not found (database/table not found)
- `500` - Server error

## Performance

- Query execution: < 100ms for typical queries
- Cache hit rate: > 80% for repeated queries
- Database connection: Reused for 30 minutes
- Query cache: 5-minute TTL, max 1000 entries
- Automatic indexing: One-time cost, cached thereafter

## Examples

### Basic Query

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "http://localhost:8000/object/76990/7/2/tables/Genes/data?limit=10"
```

### Filtered Query

```bash
curl -X POST -H "Authorization: Bearer $KB_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "berdl_table_id": "local/76990_7_2",
       "table_name": "Genes",
       "limit": 100,
       "filters": [
         {"column": "contigs", "operator": "gt", "value": "50"}
       ]
     }' \
     "http://localhost:8000/table-data"
```

### Aggregation Query

```bash
curl -X POST -H "Authorization: Bearer $KB_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "group_by": ["category"],
       "aggregations": [
         {"column": "value", "function": "sum", "alias": "total"}
       ]
     }' \
     "http://localhost:8000/api/aggregate/local/76990_7_2/tables/Data"
```
