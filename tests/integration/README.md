# Integration Test Scripts

Shell scripts that start the server and test all endpoints with proper HTTP requests.

> **Note**: For comprehensive deployment testing, see the consolidated script: [`scripts/test_deployment.sh`](../../scripts/test_deployment.sh)
> 
> This script consolidates all functionality tests, Docker deployment scenarios, and object-specific testing (including `76990/Test2`) into a single comprehensive test suite.

## Available Test Scripts

### `test_full.sh`
**Complete integration test suite**
- Starts the server automatically
- Tests all major endpoints
- Tests authentication formats
- Cleans up automatically

**Usage:**
```bash
./tests/integration/test_full.sh
```

**Tests:**
1. Health check
2. List tables
3. Get table data
4. POST /table-data endpoint
5. Statistics endpoint
6. Multi-database support
7. Authentication formats (Bearer, Cookie)

### `test_object_76990_Test2.sh`
**Comprehensive test for specific object: 76990/Test2**
- Tests all functionality with real KBase object
- Tests large table handling (165k+ rows)
- Tests filtering, sorting, pagination
- Tests multi-database access

**Usage:**
```bash
./tests/integration/test_object_76990_Test2.sh
```

### `test_server.sh`
**General server integration tests**
- Tests basic server functionality
- Tests all endpoint types
- Tests error handling

**Usage:**
```bash
./tests/integration/test_server.sh
```

## Features

All test scripts:
- ✅ **Start the server automatically** - No manual server startup needed
- ✅ **Use proper HTTP requests** - Real curl commands with proper headers
- ✅ **Test authentication** - Bearer token, plain token, and cookie auth
- ✅ **Clean up automatically** - Stop server and remove temp files on exit
- ✅ **Proper exit codes** - Return 0 on success, 1 on failure
- ✅ **Color output** - Easy to read test results
- ✅ **Error handling** - Proper error messages and cleanup

## Requirements

- `bash` (version 4+)
- `curl`
- `python3`
- `uvicorn` (installed in project)
- `.env` file with `KB_SERVICE_AUTH_TOKEN` set

## Example Output

```
==========================================
  TableScanner Integration Test
==========================================

Starting server...
Server PID: 12345
Server ready!

1. Health Check
  Health endpoint... ✓

2. List Tables
  List tables... ✓
    Found 6 tables

3. Get Table Data
  Get data... ✓

4. POST /table-data
  POST endpoint... ✓

5. Statistics
  Statistics... ✓

6. Multi-Database
  List databases... ✓

7. Authentication Formats
  ✓ Bearer token
  ✓ Cookie auth

==========================================
✅ All tests passed!
```

## Running All Tests

```bash
# Run all integration tests
for test in tests/integration/test_*.sh; do
    echo "Running $test..."
    bash "$test"
    echo ""
done
```

## Troubleshooting

**Server won't start:**
- Check if port 8000 is already in use: `lsof -i :8000`
- Check server logs: `/tmp/tablescanner_server.log`

**Tests fail:**
- Verify `.env` file exists and has `KB_SERVICE_AUTH_TOKEN`
- Check that server is accessible: `curl http://localhost:8000/health`
- Check server logs for errors

**Permission errors:**
- Make scripts executable: `chmod +x tests/integration/*.sh`

## Adding New Tests

To add a new test:

1. Create a new `.sh` file in `tests/integration/`
2. Include the standard header (colors, config, cleanup)
3. Use the `test_curl` helper function for HTTP requests
4. Follow the pattern of existing tests
5. Make sure to clean up temp files

Example:
```bash
#!/bin/bash
set -euo pipefail

# ... standard setup ...

test_my_feature() {
    echo -e "\n${BLUE}Testing My Feature${NC}"
    test_curl GET "/my/endpoint" "My test" 200 || ((failed++))
}
```
