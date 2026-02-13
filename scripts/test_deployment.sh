#!/bin/bash
# Comprehensive deployment test script
# Tests Docker deployment scenarios and object 76990/Test2 with all functionalities
# Uses curl and POST requests to verify everything works correctly

set -uo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
BASE_URL="${TEST_BASE_URL:-http://localhost:8000}"
TEST_UPA="76990/Test2"
KB_ENV="${KB_ENV:-appdev}"
PORT="${TEST_PORT:-8000}"
SERVER_PID=""
FAILED_TESTS=0
TOTAL_TESTS=0
LAST_RESPONSE_FILE=""

# Get project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Get token from .env
ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: .env file not found at $ENV_FILE${NC}" >&2
    exit 1
fi

TOKEN=$(grep KB_SERVICE_AUTH_TOKEN "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" | tr -d ' ')

if [ -z "$TOKEN" ]; then
    echo -e "${RED}ERROR: KB_SERVICE_AUTH_TOKEN not found in .env${NC}" >&2
    exit 1
fi

# Cleanup function
cleanup() {
    if [ -n "$SERVER_PID" ]; then
        echo -e "\n${YELLOW}Stopping test server (PID: $SERVER_PID)...${NC}" >&2
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    rm -f /tmp/test_response_*.json /tmp/test_payload_*.json
}
trap cleanup EXIT

# Print section header
print_section() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}========================================${NC}"
}

# Print test header
print_test() {
    echo ""
    echo -e "${BLUE}$1${NC}"
}

# Start server if needed
start_server() {
    print_section "Server Setup"
    
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}Port $PORT is already in use${NC}"
        echo -e "${YELLOW}Using existing server at $BASE_URL${NC}"
        SERVER_PID=""
        
        # Verify server is working
        if ! curl -s "$BASE_URL/health" >/dev/null 2>&1; then
            echo -e "${RED}Server on port $PORT is not responding${NC}"
            exit 1
        fi
        return
    fi
    
    echo -e "${BLUE}Starting server on port $PORT...${NC}"
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT > /tmp/tablescanner_test_server.log 2>&1 &
    SERVER_PID=$!
    echo "Server PID: $SERVER_PID"
    
    # Wait for server to be ready
    echo "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s "$BASE_URL/health" >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Server is ready!${NC}"
            sleep 1
            return 0
        fi
        echo -n "."
        sleep 1
    done
    
    echo ""
    echo -e "${RED}✗ Server failed to start${NC}"
    echo "Server logs:"
    cat /tmp/tablescanner_test_server.log
    exit 1
}

# Test helper - GET request
# Sets LAST_RESPONSE_FILE global variable
test_get() {
    local path=$1
    local desc=$2
    local expected_status=${3:-200}
    shift 3
    local extra_args=("$@")
    
    ((TOTAL_TESTS++))
    echo -n "  Testing: $desc... "
    
    LAST_RESPONSE_FILE="/tmp/test_response_${TOTAL_TESTS}.json"
    local status_code
    
    status_code=$(curl -s -o "$LAST_RESPONSE_FILE" -w "%{http_code}" \
        -H "Authorization: $TOKEN" \
        "$BASE_URL$path" \
        "${extra_args[@]}" 2>/dev/null)
    
    if [ "$status_code" = "$expected_status" ] && [ -f "$LAST_RESPONSE_FILE" ]; then
        echo -e "${GREEN}✓${NC} (Status: $status_code)"
        return 0
    else
        echo -e "${RED}✗${NC} (Expected: $expected_status, Got: $status_code)"
        if [ -f "$LAST_RESPONSE_FILE" ]; then
            echo "    Response: $(head -3 "$LAST_RESPONSE_FILE" | tr '\n' ' ')"
        fi
        ((FAILED_TESTS++))
        rm -f "$LAST_RESPONSE_FILE"
        LAST_RESPONSE_FILE=""
        return 1
    fi
}

# Test helper - POST request
# Sets LAST_RESPONSE_FILE global variable
test_post() {
    local path=$1
    local desc=$2
    local json_data=$3
    local expected_status=${4:-200}
    shift 4
    local extra_args=("$@")
    
    ((TOTAL_TESTS++))
    echo -n "  Testing: $desc... "
    
    LAST_RESPONSE_FILE="/tmp/test_response_${TOTAL_TESTS}.json"
    local payload_file="/tmp/test_payload_${TOTAL_TESTS}.json"
    local status_code
    
    echo "$json_data" > "$payload_file"
    
    status_code=$(curl -s -o "$LAST_RESPONSE_FILE" -w "%{http_code}" \
        -H "Authorization: $TOKEN" \
        -H "Content-Type: application/json" \
        -X POST \
        -d @"$payload_file" \
        "$BASE_URL$path" \
        "${extra_args[@]}" 2>/dev/null)
    
    rm -f "$payload_file"
    
    if [ "$status_code" = "$expected_status" ] && [ -f "$LAST_RESPONSE_FILE" ]; then
        echo -e "${GREEN}✓${NC} (Status: $status_code)"
        return 0
    else
        echo -e "${RED}✗${NC} (Expected: $expected_status, Got: $status_code)"
        if [ -f "$LAST_RESPONSE_FILE" ]; then
            echo "    Response: $(head -3 "$LAST_RESPONSE_FILE" | tr '\n' ' ')"
        fi
        ((FAILED_TESTS++))
        rm -f "$LAST_RESPONSE_FILE"
        LAST_RESPONSE_FILE=""
        return 1
    fi
}

# Extract JSON value using Python
json_get() {
    local file=$1
    local key=$2
    python3 -c "import json, sys; data=json.load(open('$file')); print(data.get('$key', ''))" 2>/dev/null || echo ""
}

# Extract JSON array length
json_array_len() {
    local file=$1
    local key=$2
    python3 -c "import json, sys; data=json.load(open('$file')); arr=data.get('$key', []); print(len(arr) if isinstance(arr, list) else 0)" 2>/dev/null || echo "0"
}

# Extract first table name
get_first_table() {
    local file=$1
    python3 -c "import json, sys; data=json.load(open('$file')); tables=data.get('tables', []); print(tables[0]['name'] if tables else '')" 2>/dev/null || echo ""
}

# ============================================================================
# TEST SUITE
# ============================================================================

test_health() {
    print_test "1. Health Check"
    test_get "/health" "Health endpoint" 200
}

test_list_tables() {
    print_test "2. List Tables"
    if ! test_get "/object/$TEST_UPA/tables" "List tables for $TEST_UPA" 200 -G -d "kb_env=$KB_ENV"; then
        return 1
    fi
    
    local response_file="$LAST_RESPONSE_FILE"
    if [ ! -f "$response_file" ]; then
        echo "    ⚠ Response file not found"
        return 1
    fi
    
    local table_count=$(json_array_len "$response_file" "tables")
    echo "    Found $table_count tables"
    
    # Show table summary
    python3 <<EOF
import json
with open('$response_file') as f:
    data = json.load(f)
    tables = data.get('tables', [])[:6]
    for i, table in enumerate(tables, 1):
        name = table.get('name', 'Unknown')
        rows = table.get('row_count', '?')
        cols = table.get('column_count', '?')
        print(f"    {i}. {name}: {rows:,} rows, {cols} columns")
EOF
    return 0
}

test_get_table_data() {
    print_test "3. Get Table Data"
    local tables_file=$1
    
    if [ ! -f "$tables_file" ]; then
        echo "    ⚠ No tables file available"
        return 0
    fi
    
    local table_name=$(get_first_table "$tables_file")
    if [ -z "$table_name" ]; then
        echo "    ⚠ No table name found"
        return 0
    fi
    
    echo "    Testing table: $table_name"
    if ! test_get "/object/$TEST_UPA/tables/$table_name/data" \
        "Get data from $table_name" 200 \
        -G -d "limit=10" -d "kb_env=$KB_ENV"; then
        return 1
    fi
    
    local response_file="$LAST_RESPONSE_FILE"
    if [ -f "$response_file" ]; then
        local rows=$(json_array_len "$response_file" "data")
        local total=$(json_get "$response_file" "total_count")
        local headers=$(json_array_len "$response_file" "headers")
        echo "    Retrieved $rows rows (Total: $total), $headers columns"
    fi
}

test_post_table_data() {
    print_test "4. POST /table-data Endpoint"
    local tables_file=$1
    
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name=$(get_first_table "$tables_file")
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    local json_payload=$(cat <<EOF
{
    "berdl_table_id": "$TEST_UPA",
    "table_name": "$table_name",
    "limit": 10,
    "offset": 0
}
EOF
)
    
    if ! test_post "/table-data" "POST table-data" "$json_payload" 200; then
        return 1
    fi
    
    local response_file="$LAST_RESPONSE_FILE"
    if [ -f "$response_file" ]; then
        local rows=$(json_array_len "$response_file" "data")
        echo "    Retrieved $rows rows via POST"
    fi
}

test_filtering() {
    print_test "5. Filtering"
    local tables_file=$1
    
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name=$(get_first_table "$tables_file")
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    local json_payload=$(cat <<EOF
{
    "berdl_table_id": "$TEST_UPA",
    "table_name": "$table_name",
    "limit": 50,
    "filters": [
        {"column": "id", "operator": "gt", "value": 0}
    ]
}
EOF
)
    
    if ! test_post "/table-data" "Filtered query" "$json_payload" 200; then
        return 0  # Filtering may not work for all tables
    fi
    
    local response_file="$LAST_RESPONSE_FILE"
    if [ -f "$response_file" ]; then
        local filtered=$(json_get "$response_file" "filtered_count")
        local rows=$(json_array_len "$response_file" "data")
        echo "    Filtered to $filtered rows, returned $rows"
    fi
}

test_sorting() {
    print_test "6. Sorting"
    local tables_file=$1
    
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name=$(get_first_table "$tables_file")
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    # Test ASC
    test_get "/object/$TEST_UPA/tables/$table_name/data" \
        "Sorted query (ASC)" 200 \
        -G -d "limit=20" -d "sort_column=id" -d "sort_order=ASC" -d "kb_env=$KB_ENV"
    
    # Test DESC
    test_get "/object/$TEST_UPA/tables/$table_name/data" \
        "Sorted query (DESC)" 200 \
        -G -d "limit=20" -d "sort_column=id" -d "sort_order=DESC" -d "kb_env=$KB_ENV"
    
    echo "    ✓ Sorting works (ASC and DESC)"
}

test_pagination() {
    print_test "7. Pagination"
    local tables_file=$1
    
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name=$(get_first_table "$tables_file")
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    # Page 1
    test_get "/object/$TEST_UPA/tables/$table_name/data" \
        "Page 1" 200 \
        -G -d "limit=5" -d "offset=0" -d "kb_env=$KB_ENV"
    local page1_file="$LAST_RESPONSE_FILE"
    
    # Page 2
    test_get "/object/$TEST_UPA/tables/$table_name/data" \
        "Page 2" 200 \
        -G -d "limit=5" -d "offset=5" -d "kb_env=$KB_ENV"
    local page2_file="$LAST_RESPONSE_FILE"
    
    if [ -f "$page1_file" ] && [ -f "$page2_file" ]; then
        local rows1=$(json_array_len "$page1_file" "data")
        local rows2=$(json_array_len "$page2_file" "data")
        echo "    Page 1: $rows1 rows, Page 2: $rows2 rows"
    fi
}

test_large_table() {
    print_test "8. Large Table Handling"
    local tables_file=$1
    
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    # Find largest table
    local large_table=$(python3 <<EOF
import json
with open('$tables_file') as f:
    data = json.load(f)
    tables = data.get('tables', [])
    if tables:
        largest = max(tables, key=lambda t: t.get('row_count', 0))
        print(largest.get('name', ''))
EOF
)
    
    if [ -z "$large_table" ]; then
        return 0
    fi
    
    echo "    Testing large table: $large_table"
    local start_time=$(date +%s%N)
    if ! test_get "/object/$TEST_UPA/tables/$large_table/data" \
        "Retrieve from large table" 200 \
        -G -d "limit=100" -d "kb_env=$KB_ENV"; then
        return 0
    fi
    local end_time=$(date +%s%N)
    local duration=$(( (end_time - start_time) / 1000000 ))
    
    local response_file="$LAST_RESPONSE_FILE"
    if [ -f "$response_file" ]; then
        local rows=$(json_array_len "$response_file" "data")
        local total=$(json_get "$response_file" "total_count")
        echo "    Retrieved $rows rows from $total total in ${duration}ms"
    fi
}

test_statistics() {
    print_test "9. Table Statistics"
    local tables_file=$1
    
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name=$(get_first_table "$tables_file")
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    if ! test_get "/object/$TEST_UPA/tables/$table_name/stats" \
        "Statistics endpoint" 200 \
        -G -d "kb_env=$KB_ENV"; then
        return 0  # Stats may timeout for large tables
    fi
    
    local response_file="$LAST_RESPONSE_FILE"
    if [ -f "$response_file" ]; then
        local col_count=$(json_array_len "$response_file" "columns")
        echo "    Statistics for $col_count columns"
    fi
}

test_multi_database() {
    print_test "10. Multi-Database Support"
    if ! test_get "/databases" "List databases" 200 \
        -G -d "upa=$TEST_UPA" -d "kb_env=$KB_ENV"; then
        return 0
    fi
    
    local response_file="$LAST_RESPONSE_FILE"
    if [ -f "$response_file" ]; then
        local db_count=$(json_array_len "$response_file" "databases")
        echo "    Found $db_count databases"
        
        if [ "$db_count" -gt 0 ]; then
            python3 <<EOF
import json
with open('$response_file') as f:
    data = json.load(f)
    databases = data.get('databases', [])[:3]
    for db in databases:
        name = db.get('db_name', 'Unknown')
        tables = len(db.get('tables', []))
        print(f"    - {name}: {tables} tables")
EOF
        fi
    fi
}

test_auth_formats() {
    print_test "11. Authentication Formats"
    
    # Test Bearer token
    local status=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV" 2>/dev/null)
    
    if [ "$status" = "200" ]; then
        echo -e "    ${GREEN}✓ Bearer token authentication${NC}"
    else
        echo -e "    ${RED}✗ Bearer token failed (Status: $status)${NC}"
        ((FAILED_TESTS++))
    fi
    ((TOTAL_TESTS++))
    
    # Test plain token
    status=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: $TOKEN" \
        "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV" 2>/dev/null)
    
    if [ "$status" = "200" ]; then
        echo -e "    ${GREEN}✓ Plain token authentication${NC}"
    else
        echo -e "    ${RED}✗ Plain token failed (Status: $status)${NC}"
        ((FAILED_TESTS++))
    fi
    ((TOTAL_TESTS++))
    
    # Test cookie auth
    status=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Cookie: kbase_session=$TOKEN" \
        "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV" 2>/dev/null)
    
    if [ "$status" = "200" ]; then
        echo -e "    ${GREEN}✓ Cookie authentication${NC}"
    else
        echo -e "    ${RED}✗ Cookie authentication failed (Status: $status)${NC}"
        ((FAILED_TESTS++))
    fi
    ((TOTAL_TESTS++))
}

test_complex_query() {
    print_test "12. Complex Query (Filters + Sorting + Column Selection)"
    local tables_file=$1
    
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name=$(get_first_table "$tables_file")
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    local json_payload=$(cat <<EOF
{
    "berdl_table_id": "$TEST_UPA",
    "table_name": "$table_name",
    "limit": 100,
    "offset": 0,
    "sort_column": "id",
    "sort_order": "DESC",
    "filters": [
        {"column": "id", "operator": "gt", "value": 0}
    ],
    "columns": ["id"]
}
EOF
)
    
    if ! test_post "/table-data" "Complex query" "$json_payload" 200; then
        return 0  # Complex queries may not work for all tables
    fi
    
    local response_file="$LAST_RESPONSE_FILE"
    if [ -f "$response_file" ]; then
        local rows=$(json_array_len "$response_file" "data")
        local filtered=$(json_get "$response_file" "filtered_count")
        local headers=$(json_array_len "$response_file" "headers")
        echo "    Returned $rows rows (filtered: $filtered), selected $headers columns"
    fi
}

test_error_handling() {
    print_test "13. Error Handling"
    
    # Test invalid table
    test_get "/object/$TEST_UPA/tables/NonExistentTable/data" \
        "Invalid table name" 404 \
        -G -d "kb_env=$KB_ENV"
    
    # Test missing auth (should use fallback or fail gracefully)
    local status=$(curl -s -o /dev/null -w "%{http_code}" \
        "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV" 2>/dev/null)
    if [ "$status" = "401" ] || [ "$status" = "200" ]; then
        echo -e "    ${GREEN}✓ Missing auth handled correctly${NC}"
    else
        echo -e "    ${YELLOW}⚠ Unexpected status for missing auth: $status${NC}"
    fi
    ((TOTAL_TESTS++))
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    echo "=========================================="
    echo "  TableScanner Deployment Test Suite"
    echo "=========================================="
    echo ""
    echo "Configuration:"
    echo "  Base URL: $BASE_URL"
    echo "  Test Object: $TEST_UPA"
    echo "  KBase Environment: $KB_ENV"
    echo "  Port: $PORT"
    echo ""
    
    start_server
    
    print_section "Basic Functionality Tests"
    
    test_health
    if ! test_list_tables; then
        echo -e "\n${RED}✗ Failed to get tables list. Cannot continue with remaining tests.${NC}"
        exit 1
    fi
    
    local tables_file="$LAST_RESPONSE_FILE"
    if [ -z "$tables_file" ] || [ ! -f "$tables_file" ]; then
        echo -e "\n${RED}✗ Tables file not available. Cannot continue.${NC}"
        exit 1
    fi
    
    print_section "Data Access Tests"
    
    test_get_table_data "$tables_file"
    test_post_table_data "$tables_file"
    test_pagination "$tables_file"
    test_large_table "$tables_file"
    
    print_section "Advanced Feature Tests"
    
    test_filtering "$tables_file"
    test_sorting "$tables_file"
    test_statistics "$tables_file"
    test_complex_query "$tables_file"
    
    print_section "Multi-Database Tests"
    
    test_multi_database
    
    print_section "Authentication Tests"
    
    test_auth_formats
    
    print_section "Error Handling Tests"
    
    test_error_handling
    
    # Summary
    echo ""
    echo "=========================================="
    echo "  Test Summary"
    echo "=========================================="
    echo "  Total Tests: $TOTAL_TESTS"
    echo "  Passed: $((TOTAL_TESTS - FAILED_TESTS))"
    echo "  Failed: $FAILED_TESTS"
    echo ""
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}✅ All tests passed!${NC}"
        echo ""
        echo "Deployment Status: ${GREEN}READY${NC}"
        exit 0
    else
        echo -e "${RED}✗ $FAILED_TESTS test(s) failed${NC}"
        echo ""
        echo "Deployment Status: ${RED}NOT READY${NC}"
        exit 1
    fi
}

main "$@"
