# Contributing to TableScanner

## Development Setup

### Prerequisites
- Python 3.13+
- `uv` package manager (recommended) or pip
- KBase authentication token
- Access to KBase services (Workspace, Blobstore)

### Quick Start

1. **Clone & Setup**:
   ```bash
   git clone <repo>
   cd tablescanner
   uv sync  # or: pip install -e .
   ```

2. **Configuration**:
   Copy `.env.example` to `.env` and set `KB_SERVICE_AUTH_TOKEN`.

3. **Run Locally**:
   ```bash
   ./scripts/dev.sh
   ```
   This script handles environment loading and PYTHONPATH setup.

   Alternatively:
   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Run with Docker**:
   ```bash
   docker-compose up --build
   ```

---

## Project Structure

```
tablescanner/
├── app/
│   ├── main.py           # FastAPI application & lifecycle
│   ├── routes.py         # API endpoints (including multi-DB v2.1)
│   ├── models.py         # Pydantic data models
│   ├── config.py         # Settings (BaseSettings)
│   ├── services/
│   │   ├── data/         # Query, Schema, Connection Pool
│   │   └── db_helper.py  # Database resolution
│   └── utils/            # SQLite, KBase Client, Cache
├── docs/                 # Documentation
├── tests/               # Unit & Integration tests
└── scripts/             # Development helpers
```

---

## Testing

### Running Tests

```bash
# Run all tests with pytest
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=app

# Run specific test file
uv run pytest tests/integration/test_routes.py -v
```

### In Docker

```bash
docker build -t tablescanner:test .
docker run --rm -v $(pwd)/tests:/app/tests tablescanner:test uv run pytest -v
```

### Writing Tests
- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- See `tests/unit/test_query_service.py` for mocking examples

---

## Code Style

- Follow PEP 8
- Use type hints throughout
- Wrap synchronous I/O (like `sqlite3`) in `run_sync_in_thread`
- Use parameterized SQL queries (never string concatenation)

---

## API Development

### Adding a New Endpoint

1. Define Pydantic models in `app/models.py`
2. Add route handler in `app/routes.py`
3. Tag appropriately (e.g., `tags=["Multi-Database"]`)
4. Add tests in `tests/integration/`
5. Update `docs/API.md`

### Multi-Database Pattern (v2.1)

For endpoints accessing specific databases in multi-DB objects:

```python
@router.get("/db/{db_name}/tables")
# Use query parameter for UPA: ?upa={ws_ref}
async def list_tables_in_database(
    ws_ref: str,
    db_name: str,
    authorization: str | None = Header(None),
):
    # Download all databases
    db_infos = await run_sync_in_thread(
        download_all_pangenome_dbs, ws_ref, token, cache_dir, kb_env
    )
    
    # Find target database
    target_db = next((d for d in db_infos if d["db_name"] == db_name), None)
    if not target_db:
        raise HTTPException(404, f"Database '{db_name}' not found")
    
    # Process using target_db["db_path"]
    ...
```

---

## Deployment

### Production URL
`https://appdev.kbase.us/services/berdl_table_scanner`

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `KB_SERVICE_AUTH_TOKEN` | No | Fallback auth (local testing only) |
| `CACHE_DIR` | No | Cache location (default: `/tmp/tablescanner_cache`) |
| `MAX_UPLOAD_SIZE_MB` | No | Max upload size (default: 500) |
| `MAX_UPLOAD_STORAGE_GB` | No | Upload quota (default: 10) |
| `CORS_ORIGINS` | No | Allowed origins (default: `["*"]`) |

### Nginx Requirements (Production)

```nginx
location /services/berdl_table_scanner/ {
    client_max_body_size 500M;
    proxy_request_buffering off;
    proxy_read_timeout 300s;
    proxy_pass http://backend:8000/;
}
```
