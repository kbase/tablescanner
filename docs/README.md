# TableScanner

**TableScanner** is a high-performance, read-only API service for querying SQLite databases stored in [KBase](https://kbase.us). It powers the DataTables Viewer and other applications requiring fast access to tabular data.

## Documentation

-   **[API Reference](API.md)**: Endpoints, authentication, and usage examples.
-   **[Architecture](ARCHITECTURE.md)**: System design and technical overview.
-   **[Contributing Guide](CONTRIBUTING.md)**: Setup, testing, and development standards.

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

The `./scripts/dev.sh` script is the recommended way to run locally as it handles environment loading and PYTHONPATH setup automatically.
