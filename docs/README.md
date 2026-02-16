# TableScanner

**TableScanner** is a high-performance, read-only API service for querying SQLite databases stored in [KBase](https://kbase.us). It powers the DataTables Viewer and other applications requiring fast access to tabular data.

## Production URL

**`https://appdev.kbase.us/services/berdl_table_scanner`**

## Documentation

- **[API Reference](API.md)**: Endpoints, authentication, and usage examples
- **[Architecture](ARCHITECTURE.md)**: System design and technical overview
- **[Contributing Guide](CONTRIBUTING.md)**: Setup, testing, and development standards

## Quick Start

### Run with Docker
```bash
docker-compose up --build
```
The API will be available at `http://localhost:8000`.

### Run Locally
```bash
# 1. Setup environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your KBase Token

# 2. Run using helper script
./scripts/dev.sh
```

## Quick API Examples

```bash
# Health check
curl "https://appdev.kbase.us/services/berdl_table_scanner/health"

# List tables (requires auth)
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables"

# Query data
curl -H "Authorization: $KB_TOKEN" \
     "https://appdev.kbase.us/services/berdl_table_scanner/object/76990/7/2/tables/Genes/data?limit=100"

# Upload local database
curl -X POST "https://appdev.kbase.us/services/berdl_table_scanner/upload" \
     -F "file=@my_data.db"
```

## Key Features

- **Multi-Database Support (v2.1)**: Access objects containing multiple pangenomes
- **Upload Deduplication**: SHA-256 based deduplication saves storage
- **500MB Uploads**: Large file support with streaming
- **FTS5 Search**: Fast full-text search across all columns
- **Type-Aware Filtering**: Automatic numeric/text detection
