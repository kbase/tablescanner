# TableScanner Development Guide

## Development Setup

### Prerequisites

- Python 3.10+
- KBase authentication token
- Access to KBase services (workspace, blobstore)

### Environment Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```

5. Configure `.env`:
   ```env
   KB_SERVICE_AUTH_TOKEN=your_token_here
   CACHE_DIR=/tmp/tablescanner_cache
   DEBUG=false
   ```

### Running the Service

**Development mode:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Production mode:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Using Docker:**
```bash
docker-compose up --build
```

## Project Structure

```
TableScanner/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── routes.py            # API endpoints
│   ├── models.py            # Pydantic models
│   ├── config.py            # Configuration settings
│   ├── services/
│   │   └── data/
│   │       ├── connection_pool.py    # Connection pooling
│   │       ├── query_service.py      # Query execution
│   │       ├── schema_service.py     # Schema information
│   │       ├── statistics_service.py # Column statistics
│   │       ├── schema_analyzer.py    # Schema analysis
│   │       └── fingerprint.py       # Database fingerprinting
│   ├── utils/
│   │   ├── sqlite.py        # SQLite utilities
│   │   ├── workspace.py     # KBase workspace client
│   │   └── cache.py         # Cache utilities
│   └── db/
│       └── schema.sql       # Database schema (if needed)
├── docs/
│   ├── API_REFERENCE.md     # API documentation
│   ├── SERVICES.md          # Service documentation
│   └── DEVELOPMENT.md       # This file
├── tests/
│   └── test_*.py           # Test files
├── static/
│   └── viewer.html         # Static viewer (if applicable)
├── archive/                # Archived code (AI/config generation)
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Code Style

### Python Style

- Follow PEP 8
- Use type hints for all function signatures
- Use docstrings for all classes and functions
- Maximum line length: 100 characters

### Documentation

- All public functions and classes must have docstrings
- Use Google-style docstrings
- Include parameter descriptions and return types
- No emojis in documentation

### Error Handling

- Use specific exception types
- Log errors with context
- Return appropriate HTTP status codes
- Provide helpful error messages

### Testing

- Write tests for all new features
- Aim for >80% code coverage
- Use descriptive test names
- Test both success and error cases

## Adding New Features

### Adding a New Endpoint

1. Define request/response models in `app/models.py`
2. Add endpoint function in `app/routes.py`
3. Implement business logic in appropriate service
4. Add tests in `tests/`
5. Update API documentation in `docs/API_REFERENCE.md`

### Adding a New Service

1. Create service file in `app/services/data/`
2. Implement service class with proper error handling
3. Add thread-safe singleton pattern if needed
4. Export from `app/services/__init__.py` if public API
5. Add tests
6. Document in `docs/SERVICES.md`

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_query_service.py

# Run specific test
pytest tests/test_query_service.py::test_numeric_filtering
```

### Writing Tests

Example test structure:

```python
import pytest
from pathlib import Path
from app.services.data.query_service import get_query_service, FilterSpec

def test_numeric_filtering():
    """Test that numeric filters convert string values to numbers."""
    service = get_query_service()
    
    filters = [
        FilterSpec(column="contigs", operator="gt", value="50")
    ]
    
    result = service.execute_query(
        db_path=Path("test.db"),
        table_name="test_table",
        filters=filters
    )
    
    assert result["total_count"] >= 0
    assert "query_metadata" in result
```

### Test Database Setup

Create test databases for integration tests:

```python
import sqlite3
from pathlib import Path

def create_test_db(path: Path):
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE test_table (
            id INTEGER PRIMARY KEY,
            name TEXT,
            value INTEGER
        )
    """)
    cursor.execute("INSERT INTO test_table VALUES (1, 'test', 100)")
    conn.commit()
    conn.close()
```

## Debugging

### Logging

The service uses Python's logging module. Configure log level in `.env`:

```env
DEBUG=true  # Enable debug logging
```

### Common Issues

**Connection Pool Exhaustion:**
- Check connection pool stats via `/health`
- Verify connections are being closed properly
- Increase pool size if needed

**Query Performance:**
- Check if indexes are being created
- Verify query cache is working
- Review execution times in response metadata

**Type Conversion Errors:**
- Verify column types are detected correctly
- Check filter value formats
- Review query service logs

## Performance Optimization

### Database Connections

- Use connection pooling (automatic)
- Reuse connections across requests
- Monitor connection pool stats

### Query Caching

- Cache keys include all query parameters
- Cache invalidated on table modification
- Monitor cache hit rates

### Indexing

- Indexes created automatically on first use
- Monitor index creation in logs
- Verify indexes improve query performance

## Deployment

### Docker Deployment

1. Build image:
   ```bash
   docker build -t tablescanner:latest .
   ```

2. Run container:
   ```bash
   docker run -p 8000:8000 \
     -e KB_SERVICE_AUTH_TOKEN=your_token \
     -v /tmp/cache:/tmp/tablescanner_cache \
     tablescanner:latest
   ```

### Production Considerations

- Set `DEBUG=false` in production
- Use proper logging configuration
- Monitor connection pool stats
- Set appropriate cache TTLs
- Configure rate limiting if needed
- Use reverse proxy (nginx) for SSL termination

## Contributing

1. Create a feature branch
2. Make changes following code style guidelines
3. Write tests for new features
4. Update documentation
5. Submit pull request

## Troubleshooting

### Service Won't Start

- Check `.env` file exists and is configured
- Verify KBase token is valid
- Check port 8000 is available
- Review logs for errors

### Queries Failing

- Verify database file exists and is accessible
- Check table name is correct
- Review query syntax in logs
- Check column names match schema

### Performance Issues

- Check connection pool stats
- Verify query cache is working
- Review index creation
- Monitor database file I/O
