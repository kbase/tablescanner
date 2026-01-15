# TableScanner API Testing Guide

## Quick Test

Test basic endpoints:

```bash
# Health check
curl http://127.0.0.1:8000/health

# Root endpoint
curl http://127.0.0.1:8000/

# Cache status
curl http://127.0.0.1:8000/cache
```

## Comprehensive Testing

### Using the Test Scripts

**Simple test (no auth required):**
```bash
python3 scripts/test_simple.py
```

**Full API test (requires auth token):**
```bash
export KB_SERVICE_AUTH_TOKEN=your_token
python3 scripts/test_api.py
```

**Diagnostic test:**
```bash
python3 scripts/diagnose_api.py
```

## Manual Testing

### 1. Health Check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00Z",
  "mode": "cached_sqlite",
  "data_dir": "/tmp/tablescanner_cache",
  "cache": {
    "databases_cached": 0,
    "databases": []
  }
}
```

### 2. List Tables

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "http://127.0.0.1:8000/object/76990/7/2/tables"
```

### 3. Query Table Data

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "http://127.0.0.1:8000/object/76990/7/2/tables/Genes/data?limit=10"
```

### 4. Enhanced Query with Filters

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
     "http://127.0.0.1:8000/table-data"
```

### 5. Get Schema

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "http://127.0.0.1:8000/schema/local/76990_7_2/tables/Genes"
```

### 6. Get Statistics

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "http://127.0.0.1:8000/object/local/76990_7_2/tables/Genes/stats"
```

### 7. Aggregation Query

```bash
curl -X POST -H "Authorization: Bearer $KB_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "group_by": ["category"],
       "aggregations": [
         {"column": "value", "function": "sum", "alias": "total"}
       ]
     }' \
     "http://127.0.0.1:8000/api/aggregate/local/76990_7_2/tables/Data"
```

## Testing Type-Aware Filtering

Test that numeric filters convert string values to numbers:

```bash
curl -X POST -H "Authorization: Bearer $KB_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "berdl_table_id": "local/76990_7_2",
       "table_name": "Genes",
       "limit": 10,
       "filters": [
         {"column": "contigs", "operator": "gt", "value": "50"}
       ]
     }' \
     "http://127.0.0.1:8000/table-data"
```

Verify in response that:
- `query_metadata.filters_applied` is 1
- SQL query shows numeric comparison: `contigs > ?` (not `contigs > "50"`)

## Testing Query Caching

1. Make a query and note `execution_time_ms`
2. Make the same query again
3. Verify `cached: true` in response
4. Verify second query is faster

## Testing Connection Pooling

1. Make multiple queries to the same database
2. Check `/health` endpoint
3. Verify `access_count` increases for the database connection
4. Wait 30+ minutes, verify connection is closed

## Common Issues

### Server Not Responding

1. Check if server is running:
   ```bash
   ps aux | grep uvicorn
   ```

2. Check server logs for errors

3. Verify port 8000 is not blocked:
   ```bash
   netstat -tuln | grep 8000
   ```

### Timeout Errors

1. Check KBase service availability
2. Verify auth token is valid
3. Check network connectivity
4. Review server logs for blocking operations

### 404 Errors

1. Verify object/table exists in KBase
2. Check database is cached locally
3. Verify table name is correct (case-sensitive)

### 500 Errors

1. Check server logs for detailed error
2. Verify database file is not corrupted
3. Check disk space for cache directory
4. Verify SQLite database is valid

## Performance Testing

### Query Performance

```bash
time curl -H "Authorization: Bearer $KB_TOKEN" \
     "http://127.0.0.1:8000/object/76990/7/2/tables/Genes/data?limit=1000"
```

### Cache Hit Rate

Monitor cache hit rate by checking `cached` field in responses:
- First query: `cached: false`
- Subsequent queries: `cached: true`

### Connection Pool Stats

```bash
curl http://127.0.0.1:8000/health | jq '.cache'
```

## Integration Testing

Test with DataTables Viewer frontend:

1. Start TableScanner service
2. Configure frontend to point to `http://127.0.0.1:8000`
3. Test table loading
4. Test filtering
5. Test sorting
6. Test pagination
7. Verify all features work correctly

## Automated Testing

Run pytest suite:

```bash
pytest tests/ -v
```

Run with coverage:

```bash
pytest tests/ --cov=app --cov-report=html
```
