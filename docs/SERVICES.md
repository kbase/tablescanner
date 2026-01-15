# TableScanner Services Documentation

## Overview

TableScanner provides a comprehensive data query service for SQLite databases stored in KBase. The service is built with production-grade features including connection pooling, query caching, type-aware filtering, and performance optimizations.

## Core Services

### Connection Pool Service

**Location:** `app/services/data/connection_pool.py`

Manages a pool of SQLite database connections with automatic lifecycle management.

**Features:**
- Opens databases on first access
- Caches connections in memory
- Tracks last access time and access count
- Automatically closes databases after 30 minutes of inactivity
- Cleans up expired connections every 5 minutes
- Reloads database if file modification time changes
- Applies SQLite performance optimizations (WAL mode, cache size, mmap)

**Performance Optimizations:**
- `journal_mode=WAL` - Write-Ahead Logging for better concurrency
- `synchronous=NORMAL` - Balance between safety and performance
- `cache_size=-64000` - 64MB cache
- `temp_store=MEMORY` - Store temporary tables in memory
- `mmap_size=268435456` - 256MB memory-mapped I/O

**Usage:**
```python
from app.services.data.connection_pool import get_connection_pool

pool = get_connection_pool()
conn = pool.get_connection(db_path)
```

### Query Service

**Location:** `app/services/data/query_service.py`

Provides comprehensive query execution with type-aware filtering, aggregations, and full-text search.

**Features:**
- Type-aware filtering with automatic numeric conversion
- Advanced filter operators (eq, ne, gt, gte, lt, lte, like, ilike, in, not_in, between, is_null, is_not_null)
- Aggregations with GROUP BY support
- Full-text search (FTS5) with automatic table creation
- Automatic indexing on filtered/sorted columns
- Query result caching (5-minute TTL, LRU eviction)

**Type-Aware Filtering:**

The service automatically detects column types and converts filter values appropriately:

- **Numeric columns (INTEGER, REAL, NUMERIC):** String values are converted to numbers before SQL binding
- **Text columns:** Values are used as-is with appropriate operators

**Example:**
```python
from app.services.data.query_service import get_query_service, FilterSpec

service = get_query_service()

# Filter with numeric conversion
filters = [
    FilterSpec(column="contigs", operator="gt", value="50")  # "50" -> 50
]

result = service.execute_query(
    db_path=db_path,
    table_name="Genes",
    limit=100,
    filters=filters
)
```

**Query Caching:**

Results are cached with a 5-minute TTL. Cache keys include:
- Database path
- Table name
- All query parameters (filters, sorting, pagination, etc.)

Cache is invalidated when the table file modification time changes.

### Schema Service

**Location:** `app/services/data/schema_service.py`

Provides table and column schema information.

**Features:**
- Column names, types, constraints (NOT NULL, PRIMARY KEY)
- Default values
- Index information

**Usage:**
```python
from app.services.data.schema_service import get_schema_service

service = get_schema_service()
schema = service.get_table_schema(db_path, "Genes")
```

### Statistics Service

**Location:** `app/services/data/statistics_service.py`

Pre-computes and caches column statistics.

**Features:**
- null_count, distinct_count
- min, max, mean, median, stddev
- Sample values for data exploration
- Caching based on file modification time

**Usage:**
```python
from app.services.data.statistics_service import get_statistics_service

service = get_statistics_service()
stats = service.get_table_statistics(db_path, "Genes")
```

## Data Flow

### Query Execution Flow

1. **Request Received** - API endpoint receives query request
2. **Database Resolution** - Resolve database path from KBase object or handle
3. **Connection Acquisition** - Get connection from pool (or create new)
4. **Cache Check** - Check query result cache
5. **Type Detection** - Get column types from schema
6. **Index Creation** - Ensure indexes exist on filtered/sorted columns
7. **Query Building** - Build SQL with type-aware filtering
8. **Query Execution** - Execute query and fetch results
9. **Result Caching** - Cache results for future requests
10. **Response** - Return results with metadata

### Connection Lifecycle

1. **First Access** - Connection created, optimizations applied
2. **Active Use** - Connection reused for multiple queries
3. **Inactivity** - Connection remains open for 30 minutes
4. **Expiration** - Connection closed after 30 minutes of inactivity
5. **Cleanup** - Expired connections cleaned up every 5 minutes

## Performance Considerations

### Connection Pooling

- Connections are reused across requests
- Reduces database open/close overhead
- Automatic cleanup prevents resource leaks
- File modification tracking ensures data freshness

### Query Caching

- Results cached for 5 minutes
- LRU eviction when cache exceeds 1000 entries
- Automatic invalidation on table modification
- Significant performance improvement for repeated queries

### Automatic Indexing

- Indexes created on first use
- Cached to avoid redundant creation
- Improves filter and sort performance
- One-time cost per column

### SQLite Optimizations

- WAL mode enables better concurrency
- Large cache size reduces disk I/O
- Memory-mapped I/O for faster access
- Temporary tables in memory reduce disk usage

## Error Handling

All services implement comprehensive error handling:

- **Database Errors:** Caught and logged with context
- **Connection Errors:** Automatic retry with new connection
- **Query Errors:** Detailed error messages returned to client
- **Cache Errors:** Graceful degradation (query executes without cache)

## Thread Safety

All services are thread-safe:

- Connection pool uses locks for concurrent access
- Query cache uses locks for thread-safe operations
- Statistics cache uses locks for thread-safe operations
- Global service instances use double-checked locking

## Monitoring

### Connection Pool Stats

Get connection pool statistics via `/health` endpoint:

```json
{
  "cache": {
    "databases_cached": 2,
    "connections": [
      {
        "db_path": "...",
        "last_access_seconds_ago": 120.5,
        "access_count": 15,
        "prepared_statements": 3
      }
    ]
  }
}
```

### Query Performance

Query responses include performance metrics:

- `execution_time_ms` - Database query execution time
- `response_time_ms` - Total response time
- `cached` - Whether result was from cache

## Best Practices

1. **Use Connection Pooling** - Always use `get_connection_pool()` instead of creating connections directly
2. **Leverage Caching** - Repeated queries benefit from result caching
3. **Type-Aware Filtering** - Use appropriate operators for numeric vs text columns
4. **Index Usage** - Filter and sort on indexed columns when possible
5. **Error Handling** - Always handle exceptions from service calls

## Testing

Services can be tested independently:

```python
from app.services.data.query_service import get_query_service

service = get_query_service()
result = service.execute_query(
    db_path=Path("test.db"),
    table_name="test_table",
    limit=10
)
assert result["total_count"] > 0
```
