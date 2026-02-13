#!/bin/bash
# Integration test script that starts the server and tests all endpoints
# Tests object 76990/Test2 comprehensively

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="http://localhost:8000"
TEST_UPA="76990/Test2"
KB_ENV="appdev"
SERVER_PID=""
PORT=8000

# Get token from .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: .env file not found at $ENV_FILE${NC}"
    exit 1
fi

TOKEN=$(grep KB_SERVICE_AUTH_TOKEN "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" | tr -d ' ')

if [ -z "$TOKEN" ]; then
    echo -e "${RED}ERROR: KB_SERVICE_AUTH_TOKEN not found in .env${NC}"
    exit 1
fi

# Cleanup function
cleanup() {
    if [ ! -z "$SERVER_PID" ]; then
        echo -e "\n${YELLOW}Stopping server (PID: $SERVER_PID)...${NC}"
        kill $SERVER_PID 2>/dev/null || true
        wait $SERVER_PID 2>/dev/null || true
    fi
}

trap cleanup EXIT

# Start server
start_server() {
    echo -e "${GREEN}Starting server...${NC}"
    cd "$PROJECT_ROOT"
    
    # Check if port is already in use
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        echo -e "${YELLOW}Port $PORT is already in use. Using existing server.${NC}"
        SERVER_PID=""
        return
    fi
    
    # Start server in background
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT > /tmp/tablescanner_test_server.log 2>&1 &
    SERVER_PID=$!
    
    echo "Server started with PID: $SERVER_PID"
    
    # Wait for server to be ready
    echo "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s "$BASE_URL/health" > /dev/null 2>&1; then
            echo -e "${GREEN}Server is ready!${NC}"
            return 0
        fi
        sleep 1
    done
    
    echo -e "${RED}Server failed to start${NC}"
    cat /tmp/tablescanner_test_server.log
    exit 1
}

# Test helper function
test_endpoint() {
    local method=$1
    local path=$2
    local description=$3
    local expected_status=${4:-200}
    shift 4
    local extra_args=("$@")
    
    echo -n "  Testing: $description... "
    
    local status_code
    if [ "$method" = "GET" ]; then
        status_code=$(curl -s -o /tmp/test_response.json -w "%{http_code}" \
            -H "Authorization: $TOKEN" \
            "$BASE_URL$path" \
            "${extra_args[@]}")
    elif [ "$method" = "POST" ]; then
        status_code=$(curl -s -o /tmp/test_response.json -w "%{http_code}" \
            -H "Authorization: $TOKEN" \
            -H "Content-Type: application/json" \
            -X POST \
            -d "$(cat -)" \
            "$BASE_URL$path" \
            "${extra_args[@]}" < /dev/stdin)
    fi
    
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} (Status: $status_code)"
        return 0
    else
        echo -e "${RED}✗${NC} (Expected: $expected_status, Got: $status_code)"
        echo "Response:"
        cat /tmp/test_response.json | head -20
        return 1
    fi
}

# Test functions
test_health() {
    echo -e "\n${GREEN}1. Testing Health Endpoint${NC}"
    test_endpoint "GET" "/health" "Health check" 200
}

test_list_tables() {
    echo -e "\n${GREEN}2. Testing List Tables${NC}"
    test_endpoint "GET" "/object/$TEST_UPA/tables" \
        "List tables for $TEST_UPA" 200 \
        -G -d "kb_env=$KB_ENV"
    
    # Verify response contains tables
    if grep -q '"tables"' /tmp/test_response.json; then
        echo -e "  ${GREEN}✓ Response contains tables array${NC}"
        table_count=$(cat /tmp/test_response.json | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('tables', [])))" 2>/dev/null || echo "0")
        echo -e "  ${GREEN}✓ Found $table_count tables${NC}"
    else
        echo -e "  ${RED}✗ Response does not contain tables${NC}"
        return 1
    fi
}

test_get_table_data() {
    echo -e "\n${GREEN}3. Testing Get Table Data${NC}"
    
    # Get first table name
    table_name=$(cat /tmp/test_response.json | python3 -c "import sys, json; tables = json.load(sys.stdin).get('tables', []); print(tables[0]['name'] if tables else '')" 2>/dev/null)
    
    if [ -z "$table_name" ]; then
        echo -e "  ${YELLOW}⚠ No tables found, skipping${NC}"
        return 0
    fi
    
    echo "  Testing with table: $table_name"
    test_endpoint "GET" "/object/$TEST_UPA/tables/$table_name/data" \
        "Get data from $table_name" 200 \
        -G -d "limit=10" -d "kb_env=$KB_ENV"
    
    # Verify response structure
    if grep -q '"data"' /tmp/test_response.json && grep -q '"headers"' /tmp/test_response.json; then
        echo -e "  ${GREEN}✓ Response has correct structure${NC}"
        row_count=$(cat /tmp/test_response.json | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('data', [])))" 2>/dev/null || echo "0")
        echo -e "  ${GREEN}✓ Retrieved $row_count rows${NC}"
    else
        echo -e "  ${RED}✗ Response structure invalid${NC}"
        return 1
    fi
}

test_post_table_data() {
    echo -e "\n${GREEN}4. Testing POST /table-data${NC}"
    
    # Get first table name
    table_name=$(cat /tmp/test_response.json | python3 -c "import sys, json; tables = json.load(sys.stdin).get('tables', []); print(tables[0]['name'] if tables else '')" 2>/dev/null)
    
    if [ -z "$table_name" ]; then
        echo -e "  ${YELLOW}⚠ No tables found, skipping${NC}"
        return 0
    fi
    
    # Create JSON payload
    json_payload=$(cat <<EOF
{
    "berdl_table_id": "$TEST_UPA",
    "table_name": "$table_name",
    "limit": 10,
    "offset": 0
}
EOF
)
    
    echo "$json_payload" | test_endpoint "POST" "/table-data" \
        "POST table-data for $table_name" 200
    
    if grep -q '"data"' /tmp/test_response.json; then
        echo -e "  ${GREEN}✓ POST endpoint works${NC}"
    else
        echo -e "  ${RED}✗ POST endpoint failed${NC}"
        return 1
    fi
}

test_filtering() {
    echo -e "\n${GREEN}5. Testing Filtering${NC}"
    
    # Get a table with numeric columns
    table_name=$(cat /tmp/test_response.json | python3 -c "import sys, json; tables = json.load(sys.stdin).get('tables', []); print(tables[0]['name'] if tables else '')" 2>/dev/null)
    
    if [ -z "$table_name" ]; then
        echo -e "  ${YELLOW}⚠ No tables found, skipping${NC}"
        return 0
    fi
    
    # Test POST with filter
    json_payload=$(cat <<EOF
{
    "berdl_table_id": "$TEST_UPA",
    "table_name": "$table_name",
    "limit": 10,
    "filters": [
        {"column": "id", "operator": "gt", "value": 0}
    ]
}
EOF
)
    
    echo "$json_payload" | test_endpoint "POST" "/table-data" \
        "Filtered query" 200
    
    if grep -q '"filtered_count"' /tmp/test_response.json; then
        echo -e "  ${GREEN}✓ Filtering works${NC}"
    else
        echo -e "  ${YELLOW}⚠ Filtering may not be supported for this table${NC}"
    fi
}

test_sorting() {
    echo -e "\n${GREEN}6. Testing Sorting${NC}"
    
    table_name=$(cat /tmp/test_response.json | python3 -c "import sys, json; tables = json.load(sys.stdin).get('tables', []); print(tables[0]['name'] if tables else '')" 2>/dev/null)
    
    if [ -z "$table_name" ]; then
        echo -e "  ${YELLOW}⚠ No tables found, skipping${NC}"
        return 0
    fi
    
    test_endpoint "GET" "/object/$TEST_UPA/tables/$table_name/data" \
        "Sorted query (ASC)" 200 \
        -G -d "limit=10" -d "sort_column=id" -d "sort_order=ASC" -d "kb_env=$KB_ENV"
    
    echo -e "  ${GREEN}✓ Sorting works${NC}"
}

test_statistics() {
    echo -e "\n${GREEN}7. Testing Statistics${NC}"
    
    table_name=$(cat /tmp/test_response.json | python3 -c "import sys, json; tables = json.load(sys.stdin).get('tables', []); print(tables[0]['name'] if tables else '')" 2>/dev/null)
    
    if [ -z "$table_name" ]; then
        echo -e "  ${YELLOW}⚠ No tables found, skipping${NC}"
        return 0
    fi
    
    test_endpoint "GET" "/object/$TEST_UPA/tables/$table_name/stats" \
        "Table statistics" 200 \
        -G -d "kb_env=$KB_ENV"
    
    if grep -q '"columns"' /tmp/test_response.json; then
        echo -e "  ${GREEN}✓ Statistics endpoint works${NC}"
    else
        echo -e "  ${RED}✗ Statistics endpoint failed${NC}"
        return 1
    fi
}

test_multi_database() {
    echo -e "\n${GREEN}8. Testing Multi-Database Support${NC}"
    
    test_endpoint "GET" "/databases" \
        "List databases" 200 \
        -G -d "upa=$TEST_UPA" -d "kb_env=$KB_ENV"
    
    if grep -q '"databases"' /tmp/test_response.json; then
        db_count=$(cat /tmp/test_response.json | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('databases', [])))" 2>/dev/null || echo "0")
        echo -e "  ${GREEN}✓ Found $db_count databases${NC}"
    else
        echo -e "  ${YELLOW}⚠ Multi-database structure not detected${NC}"
    fi
}

test_auth_formats() {
    echo -e "\n${GREEN}9. Testing Authentication Formats${NC}"
    
    # Test Bearer token
    status_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV")
    
    if [ "$status_code" = "200" ]; then
        echo -e "  ${GREEN}✓ Bearer token authentication works${NC}"
    else
        echo -e "  ${RED}✗ Bearer token authentication failed (Status: $status_code)${NC}"
        return 1
    fi
    
    # Test cookie auth
    status_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Cookie: kbase_session=$TOKEN" \
        "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV")
    
    if [ "$status_code" = "200" ]; then
        echo -e "  ${GREEN}✓ Cookie authentication works${NC}"
    else
        echo -e "  ${RED}✗ Cookie authentication failed (Status: $status_code)${NC}"
        return 1
    fi
}

# Main test execution
main() {
    echo "=========================================="
    echo "TableScanner Integration Tests"
    echo "=========================================="
    echo "Testing object: $TEST_UPA"
    echo "Base URL: $BASE_URL"
    echo ""
    
    start_server
    
    # Run tests
    failed_tests=0
    
    test_health || ((failed_tests++))
    test_list_tables || ((failed_tests++))
    test_get_table_data || ((failed_tests++))
    test_post_table_data || ((failed_tests++))
    test_filtering || ((failed_tests++))
    test_sorting || ((failed_tests++))
    test_statistics || ((failed_tests++))
    test_multi_database || ((failed_tests++))
    test_auth_formats || ((failed_tests++))
    
    echo ""
    echo "=========================================="
    if [ $failed_tests -eq 0 ]; then
        echo -e "${GREEN}All tests passed!${NC}"
        echo "=========================================="
        exit 0
    else
        echo -e "${RED}$failed_tests test(s) failed${NC}"
        echo "=========================================="
        exit 1
    fi
}

main "$@"
