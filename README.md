# TableScanner

FastAPI application for table scanning operations with MinIO storage integration.

## Features

- FastAPI web framework
- Search endpoint accepting ID parameters
- Docker and Docker Compose support
- Dependency management with uv
- MinIO client integration
- KBUtilLib utilities

## Prerequisites

- Docker
- Docker Compose

## Quick Start

### Using Docker Compose

1. Build and start the application:
```bash
docker compose up --build
```

2. The API will be available at `http://localhost:8000`

3. Access the interactive API documentation at `http://localhost:8000/docs`

### API Endpoints

#### Root Endpoint
- **URL**: `GET /`
- **Description**: Returns service information
- **Response**:
```json
{
  "service": "TableScanner",
  "version": "1.0.0",
  "status": "running"
}
```

#### Search Endpoint
- **URL**: `GET /search`
- **Parameters**: 
  - `id` (required): The ID to search for
- **Description**: Searches for a table by ID
- **Example**: `GET /search?id=12345`
- **Response**:
```json
{
  "query_id": "12345",
  "status": "success",
  "message": "Search completed for ID: 12345"
}
```

## Development

### Project Structure
```
.
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application factory
│   └── routes.py        # API route definitions
├── Dockerfile           # Docker build configuration
├── docker-compose.yml   # Docker Compose configuration
├── pyproject.toml       # Python project metadata
├── requirements.txt     # Python dependencies
└── README.md
```

### Dependencies

The application requires:
- `fastapi` - Web framework
- `uvicorn[standard]` - ASGI server
- `minio` - MinIO client for object storage
- `KBUtilLib` - KBase utility library

### Local Development

To run locally without Docker:

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docker

### Build the Image
```bash
docker build -t tablescanner .
```

### Run the Container
```bash
docker run -p 8000:8000 tablescanner
```

## Health Check

The application includes a health check that verifies the service is running:
- Endpoint: `GET /`
- Interval: 30 seconds
- Timeout: 10 seconds
- Start period: 40 seconds

## License

See [LICENSE](LICENSE) file for details.
