# TableScanner

TableScanner is a microservice for providing filtered and paginated access to tabular data stored in KBase. It uses local SQLite caching and indexing to provide fast access to large datasets without loading them entirely into memory.

## Functionality

The service provides two methods for data access:
1. **Hierarchical REST**: Path-based endpoints for navigating objects and tables using GET requests.
2. **Flat POST**: A single endpoint (`/table-data`) that accepts a JSON payload for all query parameters.

## Architecture

TableScanner operates as a bridge between KBase storage and client applications:
1. **Data Fetching**: Retrieves SQLite databases from the KBase Blobstore.
2. **Local Caching**: Stores databases locally to avoid repeated downloads.
3. **Indexing**: Creates indices on-the-fly for all table columns to optimize query performance.
4. **API Layer**: A FastAPI application that handles requests and executes SQL queries against the local cache.

Technical details on race conditions and concurrency handling are available in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Setup

### Production
```bash
docker compose up --build -d
```
The service will be available at `http://localhost:8000`. API documentation is at `/docs`.

### Development
```bash
cp .env.example .env
bash scripts/dev.sh
```

## API Usage

### Path-based REST
List tables:
`GET /object/{upa}/tables`

Query table data:
`GET /object/{upa}/tables/{table_name}/data?limit=100`

### Flat POST
Query table data:
`POST /table-data`

Payload example:
```json
{
    "berdl_table_id": "76990/7/2",
    "table_name": "Genes",
    "limit": 100
}
```

## Project Structure
- `app/`: Application logic and routes.
- `app/utils/`: Utilities for caching, SQLite operations, and Workspace integration.
- `docs/`: Technical documentation.
- `scripts/`: Client examples and utility scripts.

## License
MIT License.
