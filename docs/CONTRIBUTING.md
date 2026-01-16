# Contributing to TableScanner

## Development Setup

### Prerequisites
- Python 3.10+
- KBase authentication token
- Access to KBase services (Workspace, Blobstore)

### Quick Start
1.  **Clone & Venv**:
    ```bash
    git clone <repo>
    cd tablescanner
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

2.  **Configuration**:
    Copy `.env.example` to `.env` and set `KB_SERVICE_AUTH_TOKEN`.

3.  **Run Locally**:
    You can use the provided helper script:
    ```bash
    ./scripts/dev.sh
    ```
    This script handles:
    - Activating the virtual environment (`.venv`)
    - Loading environment variables from `.env`
    - Setting `PYTHONPATH`
    - Starting the server via `fastapi dev`

    Alternatively, run manually:
    ```bash
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```

4.  **Run with Docker**:
    ```bash
    docker-compose up --build
    ```

---

## Project Structure
-   `app/`: Core application code.
    -   `main.py`: Entry point.
    -   `routes.py`: API endpoints.
    -   `services/`: Business logic (Data queries, schema).
    -   `utils/`: Helpers (SQLite, KBase Client).
    -   `models.py`: Pydantic data models.
-   `tests/`: Test suite.
-   `docs/`: Documentation.

---

## Testing

### Running Tests
We use `unittest` (compatible with `pytest`).

```bash
# Run all tests
python -m unittest discover tests

# Or using pytest (recommended)
pytest tests/ -v
```

### Writing Tests
-   Place unit tests in `tests/unit/`.
-   Place integration tests in `tests/integration/`.
-   Use `app/services/data/query_service.py` tests as a reference for mocking SQLite.

---

## Code Style
-   Follow PEP 8.
-   Use type hints.
-   Ensure purely synchronous I/O (like `sqlite3`) is wrapped in `run_sync_in_thread`.
