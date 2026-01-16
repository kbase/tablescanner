# TableScanner

TableScanner is a production-grade microservice for querying tabular data from KBase SQLite databases. It provides a comprehensive DataTables Viewer-compatible API with advanced query capabilities, type-aware filtering, and performance optimizations.

## Features

- **Data Access**: Query SQLite databases from KBase objects and handles
- **Type-Aware Filtering**: Automatic numeric conversion for proper filtering
- **Advanced Operators**: Support for eq, ne, gt, gte, lt, lte, like, ilike, in, not_in, between, is_null, is_not_null
- **Aggregations**: GROUP BY support with count, sum, avg, min, max, stddev, variance, distinct_count
- **Full-Text Search**: FTS5 support with automatic virtual table creation
- **Performance**: Connection pooling, query caching, automatic indexing
- **Statistics**: Pre-computed column statistics (min, max, mean, median, stddev)
- **Schema Information**: Detailed table and column schema with indexes

## Quick Start

### Production

```bash
docker compose up --build -d
```

The service will be available at `http://localhost:8000`. API documentation is at `/docs`.

### Development

```bash
cp .env.example .env
# Edit .env and set KB_SERVICE_AUTH_TOKEN
./scripts/dev.sh
```

The helper script `scripts/dev.sh` automates the environment setup:
1. Activates the virtual environment (`.venv` or `venv`)
2. Loads environment variables from `.env`
3. Sets `PYTHONPATH`
4. Starts the FastAPI development server with hot-reload via `fastapi dev`

## API Usage

### List Tables

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "http://localhost:8000/object/76990/7/2/tables"
```

### Query Table Data

```bash
curl -H "Authorization: Bearer $KB_TOKEN" \
     "http://localhost:8000/object/76990/7/2/tables/Genes/data?limit=10"
```

### Enhanced Query with Filters

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

## Documentation

- **[API Reference](docs/API.md)** - Complete API documentation with examples
- **[Architecture Dictionary](docs/ARCHITECTURE.md)** - System design and technical overview
- **[Contributing Guide](docs/CONTRIBUTING.md)** - Setup, testing, and contribution guidelines

## Architecture

TableScanner operates as a bridge between KBase storage and client applications:

1. **Data Fetching**: Retrieves SQLite databases from KBase Blobstore
2. **Local Caching**: Stores databases locally to avoid repeated downloads
3. **Connection Pooling**: Manages database connections with automatic lifecycle
4. **Query Execution**: Type-aware filtering with automatic numeric conversion
5. **Performance**: Query caching, automatic indexing, SQLite optimizations
6. **API Layer**: FastAPI application with comprehensive endpoints

## Project Structure

```
TableScanner/
├── app/
│   ├── main.py              # FastAPI application
│   ├── routes.py            # API endpoints
│   ├── models.py            # Pydantic models
│   ├── config.py            # Configuration settings
│   ├── services/
│   │   ├── data/
│   │   │   ├── connection_pool.py    # Connection pooling
│   │   │   ├── query_service.py      # Query execution
│   │   │   └── ...
│   │   └── db_helper.py     # Database resolution
│   └── utils/               # Utilities (SQLite, KBase Client)
├── docs/                    # Documentation (API, Architecture, Contributing)
├── tests/                   # Test suite (Unit & Integration)
├── scripts/                 # Helper scripts (dev.sh)
└── static/                  # Static files
```

## Configuration

Create a `.env` file with:

```env
KB_SERVICE_AUTH_TOKEN=your_token_here
CACHE_DIR=/tmp/tablescanner_cache
CACHE_MAX_AGE_HOURS=24
DEBUG=false
```

## Performance

- Query execution: < 100ms for typical queries
- Cache hit rate: > 80% for repeated queries
- Database connection: Reused for 30 minutes
- Query cache: 5-minute TTL, max 1000 entries
- Automatic indexing: One-time cost, cached thereafter

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

## License

MIT License
