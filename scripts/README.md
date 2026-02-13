# Scripts Directory

This directory contains utility scripts for development, testing, and deployment.

## test_deployment.sh

**Comprehensive deployment test script** that validates all TableScanner functionality in a Docker-like environment.

### Features

- **Server Management**: Automatically starts/stops the server or uses an existing instance
- **Comprehensive Testing**: Tests all major features including:
  - Health checks
  - Table listing and data retrieval
  - POST endpoints
  - Filtering, sorting, and pagination
  - Large table handling
  - Statistics endpoints
  - Multi-database support
  - Authentication formats (Bearer, plain token, cookie)
  - Error handling
  - Complex queries

- **Object-Specific Testing**: Specifically tests object `76990/Test2` with all functionalities
- **Real HTTP Requests**: Uses `curl` to make actual HTTP requests, simulating real-world usage
- **Docker-Ready**: Tests are designed to work in Docker deployment scenarios

### Usage

```bash
# Run all deployment tests
./scripts/test_deployment.sh

# With custom configuration
TEST_BASE_URL=http://localhost:8000 \
KB_ENV=appdev \
./scripts/test_deployment.sh
```

### Configuration

The script reads configuration from:
- `.env` file for `KB_SERVICE_AUTH_TOKEN`
- Environment variables:
  - `TEST_BASE_URL`: Base URL for the service (default: `http://localhost:8000`)
  - `KB_ENV`: KBase environment (default: `appdev`)
  - `TEST_PORT`: Port for the test server (default: `8000`)

### Test Object

The script tests object `76990/Test2` which contains:
- 11 tables including `genome`, `genome_features`, `pan_genome_features`
- Multiple databases (GCF_000368685.1, GCF_004211955.1)
- Large tables (165,496+ rows)

### Output

The script provides:
- Color-coded test results (✓ for pass, ✗ for fail)
- Detailed test summaries
- Performance metrics (response times)
- Final deployment readiness status

### Exit Codes

- `0`: All tests passed - deployment ready
- `1`: One or more tests failed - deployment not ready
