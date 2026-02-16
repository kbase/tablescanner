# TableScanner

TableScanner is a production-grade microservice for querying tabular data from KBase SQLite databases. It provides a comprehensive DataTables Viewer-compatible API with advanced query capabilities, type-aware filtering, and performance optimizations.

## Features

- **Data Access**: Query SQLite databases from KBase objects and handles
- **Multi-Database Support**: Access objects containing multiple pangenomes (v2.1)
- **Local Uploads**: Upload local SQLite files (`.db`, `.sqlite`) for temporary access
- **User-Driven Auth**: Secure access where each user provides their own KBase token
- **Type-Aware Filtering**: Automatic numeric conversion for proper filtering results
- **Advanced Operators**: Support for `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `like`, `ilike`, `in`, `not_in`, `between`, `is_null`, `is_not_null`
- **Aggregations**: `GROUP BY` support with `count`, `sum`, `avg`, `min`, `max`, `stddev`, `variance`, `distinct_count`
- **Table Statistics**: Rich column statistics including null counts, distinct counts, min/max/mean, and sample values
- **Full-Text Search**: FTS5 support with automatic virtual table creation
- **Automatic Operations**: Lifecycle management for connection pooling, query caching, and automatic disk cleanup

## Quick Start

### Production (Docker)

```bash
docker compose up --build -d
```
The service will be available at `http://localhost:8000`. API documentation is available at `/docs`.

### Development

```bash
cp .env.example .env
# Edit .env and set local development parameters
./scripts/dev.sh
```

## Base URL

| Environment | URL |
|-------------|-----|
| **AppDev** | `https://appdev.kbase.us/services/berdl_table_scanner` |
| **Production** | `https://kbase.us/services/berdl_table_scanner` |
| **Local** | `http://localhost:8000` |

## Authentication

**Each user must provide their own KBase authentication token.** The service prioritizes user-provided tokens over shared service tokens.

- **Header (Recommended)**: `Authorization: <token>` 
- **Cookie**: `kbase_session=<token>` (Used by DataTables Viewer)
- **Legacy Fallback**: `KB_SERVICE_AUTH_TOKEN` in `.env` is for **local testing only**

## API Usage Examples

### 1. Upload a Local Database
Upload a SQLite file to receive a temporary handle.

```bash
curl -X POST "https://appdev.kbase.us/services/berdl_table_scanner/upload" \
     -F "file=@/path/to/my_data.db"
# Returns: {"handle": "local:sha256hash", ...}
```

### 2. List Tables
Works with KBase UPA or the local handle returned above.

```bash
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables"
```

### 3. Get Table Statistics
Retrieve detailed column metrics and sample values.

```bash
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/stats"
```

### 4. Advanced Query (POST)
Comprehensive filtering and pagination.

```bash
curl -X POST -H "Authorization: $KB_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "berdl_table_id": "76990/7/2",
       "table_name": "Genes",
       "limit": 100,
       "filters": [
         {"column": "gene_length", "operator": "gt", "value": 1000}
       ]
     }' \
     "https://appdev.kbase.us/services/berdl_table_scanner/table-data"
```

### 5. Multi-Database Objects (v2.1)
For objects containing multiple pangenomes/databases:

```bash
# List all databases in an object
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/databases?upa=76990/7/2"

# List tables in a specific database
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/db/pg_ecoli_k12/tables?upa=76990/7/2"

# Query data from a specific database
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/db/pg_ecoli_k12/tables/Genes/data?upa=76990/7/2&limit=100"
```

## Performance & Optimization

- **Gzip Compression**: Compresses large responses (>1KB) to reduce bandwidth usage
- **High-Performance JSON**: Uses `orjson` for fast JSON serialization
- **Parallel Metadata Fetching**: Retrieves table metadata concurrently for fast listing
- **Metadata Caching**: Caches object types locally to minimize KBase API calls
- **Connection Pooling**: Reuses database connections for up to 10 minutes of inactivity
- **Automatic Cleanup**: Expired caches are purged on startup. Uploaded databases automatically expire after **1 hour**
- **Query Caching**: 5-minute TTL, max 1000 entries per instance
- **Atomic Renaming**: Ensures file integrity during downloads and uploads
- **Upload Deduplication**: SHA-256 hashing prevents duplicate file storage

## Documentation

- **[API Reference](docs/API.md)** - Complete API documentation with examples
- **[Architecture Dictionary](docs/ARCHITECTURE.md)** - System design and technical overview
- **[Deployment Readiness](docs/internal/DEPLOYMENT_READINESS.md)** - Checklist for production deployment
- **[Contributing Guide](docs/CONTRIBUTING.md)** - Setup, testing, and contribution guidelines

## Testing

```bash
# Set PYTHONPATH and run all tests
PYTHONPATH=. pytest

# Run integration tests for local upload
PYTHONPATH=. pytest tests/integration/test_local_upload.py
```

## Project Structure

```
TableScanner/
├── app/
│   ├── main.py              # FastAPI application & Lifecycle handlers
│   ├── routes.py            # API endpoints & Auth logic
│   ├── models.py            # Pydantic (V2) models
│   ├── config.py            # Configuration (BaseSettings)
│   ├── services/
│   │   ├── data/            # Query & Connection pooling logic
│   │   └── db_helper.py     # Secure handle resolution
│   └── utils/               # SQLite, KBase Client, and Cache utilities
├── docs/                    # API and Architectural documentation
├── tests/                   # Unit & Integration tests
├── scripts/                 # Development helper scripts
└── static/                  # Static assets for the viewer
```

## License

MIT License
