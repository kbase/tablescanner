# TableScanner

TableScanner is a microservice for providing filtered and paginated access to tabular data stored in KBase. 
## Functionality

The service provides two methods for data access:
1. **Hierarchical REST**: Path-based endpoints for navigating objects and tables using GET requests (includes object type detection).
2. **Flat POST**: A single endpoint (`/table-data`) for programmatic queries.


## Architecture

TableScanner operates as a bridge between KBase storage and client applications:
1. **Data Fetching**: Retrieves SQLite databases from the KBase Blobstore.
2. **Local Caching**: Stores databases locally to avoid repeated downloads.
3. **Indexing**: Creates indices on-the-fly for all table columns to optimize query performance.
4. **API Layer**: A FastAPI application that handles requests and executes SQL queries against the local cache.

Technical details on race conditions, UI design, and concurrency are available in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Web Explorer

Access the interactive **Research Data Explorer** at:
`http://localhost:8000/static/viewer.html`

Features:
- **Sidebar-First Navigation**: IDE-like experience for pangenome and table selection.
- **Scientific Modern UI**: Light-themed, high-density interface with premium typography.
- **Interactive Tools**: Global search, column visibility controls, and density toggles.
- **Performance**: Instant filtering and sticky headers for a research-grade experience.

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
List tables and identify object type:
`GET /object/{upa}/tables`

**Example Response**:
```json
{
    "berdl_table_id": "76990/7/2",
    "object_type": "KBaseFBA.GenomeDataLakeTables-2.0",
    "tables": [
        {"name": "Genes", "row_count": 3356, "column_count": 18},
        {"name": "Metadata_Conditions", "row_count": 42, "column_count": 12}
    ],
    "source": "Cache"
}
```

Query table data:
`GET /object/{upa}/tables/{table_name}/data?limit=5`

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
- `app/utils/`: Utilities for caching, SQLite, and KBase Workspace integration.
- `static/`: Production-grade Web Explorer (`viewer.html`).
- `docs/`: Technical documentation and usage guides.
- `scripts/`: Client examples and utility scripts.

## License
MIT License.
