#!/bin/bash
# Comprehensive test script for object 76990/Test2
# Starts server and tests all functionality

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="http://localhost:8000"
TEST_UPA="76990/Test2"
KB_ENV="appdev"
SERVER_PID=""
PORT=8000

# Get paths
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
        echo -e "${GREEN}Server stopped${NC}"
    fi
}

trap cleanup EXIT

# Start server
start_server() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Starting TableScanner Server${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    cd "$PROJECT_ROOT"
    
    # Check if port is already in use
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        echo -e "${YELLOW}Port $PORT is already in use. Using existing server.${NC}"
        SERVER_PID=""
        return
    fi
    
    # Start server in background
    echo "Starting server on port $PORT..."
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT > /tmp/tablescanner_test_76990_Test2.log 2>&1 &
    SERVER_PID=$!
    
    echo "Server started with PID: $SERVER_PID"
    
    # Wait for server to be ready
    echo "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s "$BASE_URL/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Server is ready!${NC}"
            sleep 1  # Give it a moment to fully initialize
            return 0
        fi
        echo -n "."
        sleep 1
    done
    
    echo ""
    echo -e "${RED}✗ Server failed to start${NC}"
    echo "Server logs:"
    cat /tmp/tablescanner_test_76990_Test2.log
    exit 1
}

# Test helper
test_endpoint() {
    local method=$1
    local path=$2
    local description=$3
    local expected_status=${4:-200}
    shift 4
    local extra_args=("$@")
    
    echo -n "  Testing: $description... "
    
    local status_code
    local response_file="/tmp/test_response_$$.json"
    
    if [ "$method" = "GET" ]; then
        status_code=$(curl -s -o "$response_file" -w "%{http_code}" \
            -H "Authorization: $TOKEN" \
            "$BASE_URL$path" \
            "${extra_args[@]}")
    elif [ "$method" = "POST" ]; then
        status_code=$(curl -s -o "$response_file" -w "%{http_code}" \
            -H "Authorization: $TOKEN" \
            -H "Content-Type: application/json" \
            -X POST \
            -d "$(cat -)" \
            "$BASE_URL$path" \
            "${extra_args[@]}" < /dev/stdin)
    fi
    
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} (Status: $status_code)"
        if [ -f "$response_file" ]; then
            echo "$response_file"
        fi
        return 0
    else
        echo -e "${RED}✗${NC} (Expected: $expected_status, Got: $status_code)"
        if [ -f "$response_file" ]; then
            echo "  Response:"
            cat "$response_file" | head -10 | sed 's/^/    /'
        fi
        rm -f "$response_file"
        return 1
    fi
}

# Test 1: Health Check
test_health() {
    echo -e "\n${BLUE}1. Health Check${NC}"
    test_endpoint "GET" "/health" "Server health" 200
}

# Test 2: List Tables
test_list_tables() {
    echo -e "\n${BLUE}2. List Tables${NC}"
    local response_file
    if ! response_file=$(test_endpoint "GET" "/object/$TEST_UPA/tables" \
        "List all tables" 200 \
        -G -d "kb_env=$KB_ENV"); then
        return 1
    fi
    
    if [ -z "$response_file" ] || [ ! -f "$response_file" ]; then
        return 1
    fi
    
    # Extract table information
    local table_count
    table_count=$(python3 <<EOF
import json, sys
try:
    with open('$response_file') as f:
        data = json.load(f)
        tables = data.get('tables', [])
        print(len(tables))
        for i, table in enumerate(tables[:6], 1):
            name = table.get('name', 'Unknown')
            rows = table.get('row_count', '?')
            cols = table.get('column_count', '?')
            print(f"    {i}. {name}: {rows} rows, {cols} columns")
except Exception as e:
    print("0")
EOF
)
    
    if [ "$table_count" -gt 0 ]; then
        echo "$table_count" | tail -n +2 | sed 's/^/  /'
        echo -e "  ${GREEN}✓ Found $table_count tables${NC}"
        echo "$response_file"
        return 0
    else
        echo -e "  ${RED}✗ No tables found${NC}"
        rm -f "$response_file"
        return 1
    fi
}

# Test 3: Get Table Data
test_get_table_data() {
    echo -e "\n${BLUE}3. Get Table Data${NC}"
    
    local tables_file="$1"
    if [ ! -f "$tables_file" ]; then
        echo -e "  ${YELLOW}⚠ No tables file, skipping${NC}"
        return 0
    fi
    
    # Get first table name
    local table_name
    table_name=$(python3 <<EOF
import json
with open('$tables_file') as f:
    data = json.load(f)
    tables = data.get('tables', [])
    if tables:
        print(tables[0].get('name', ''))
EOF
)
    
    if [ -z "$table_name" ]; then
        echo -e "  ${YELLOW}⚠ No table name found, skipping${NC}"
        return 0
    fi
    
    echo "  Testing table: $table_name"
    local response_file
    response_file=$(test_endpoint "GET" "/object/$TEST_UPA/tables/$table_name/data" \
        "Get data from $table_name" 200 \
        -G -d "limit=10" -d "kb_env=$KB_ENV")
    
    if [ -z "$response_file" ] || [ ! -f "$response_file" ]; then
        return 1
    fi
    
    # Verify data structure
    local data_info
    data_info=$(python3 <<EOF
import json
try:
    with open('$response_file') as f:
        data = json.load(f)
        rows = len(data.get('data', []))
        total = data.get('total_count', 0)
        headers = len(data.get('headers', []))
        print(f"{rows}|{total}|{headers}")
except:
    print("0|0|0")
EOF
)
    
    local rows=$(echo "$data_info" | cut -d'|' -f1)
    local total=$(echo "$data_info" | cut -d'|' -f2)
    local headers=$(echo "$data_info" | cut -d'|' -f3)
    
    if [ "$rows" -gt 0 ]; then
        echo -e "  ${GREEN}✓ Retrieved $rows rows (Total: $total)${NC}"
        echo -e "  ${GREEN}✓ Columns: $headers${NC}"
        echo "$response_file"
        return 0
    else
        echo -e "  ${RED}✗ No data returned${NC}"
        rm -f "$response_file"
        return 1
    fi
}

# Test 4: Large Table Handling
test_large_table() {
    echo -e "\n${BLUE}4. Large Table Handling${NC}"
    
    local tables_file="$1"
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    # Find largest table
    local large_table
    large_table=$(python3 <<EOF
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
        echo -e "  ${YELLOW}⚠ No large table found${NC}"
        return 0
    fi
    
    echo "  Testing large table: $large_table"
    local start_time=$(date +%s%N)
    local response_file
    response_file=$(test_endpoint "GET" "/object/$TEST_UPA/tables/$large_table/data" \
        "Retrieve 100 rows from large table" 200 \
        -G -d "limit=100" -d "kb_env=$KB_ENV")
    local end_time=$(date +%s%N)
    local duration=$(( (end_time - start_time) / 1000000 ))
    
    if [ -f "$response_file" ]; then
        local row_count
        row_count=$(python3 <<EOF
import json
with open('$response_file') as f:
    data = json.load(f)
    print(len(data.get('data', [])))
EOF
)
        echo -e "  ${GREEN}✓ Retrieved $row_count rows in ${duration}ms${NC}"
        rm -f "$response_file"
    fi
}

# Test 5: Filtering
test_filtering() {
    echo -e "\n${BLUE}5. Filtering${NC}"
    
    local tables_file="$1"
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name
    table_name=$(python3 <<EOF
import json
with open('$tables_file') as f:
    data = json.load(f)
    tables = data.get('tables', [])
    if tables:
        print(tables[0].get('name', ''))
EOF
)
    
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    local json_payload
    json_payload=$(cat <<EOF
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
    
    echo "$json_payload" | test_endpoint "POST" "/table-data" \
        "Filtered query" 200 > /dev/null
}

# Test 6: Sorting
test_sorting() {
    echo -e "\n${BLUE}6. Sorting${NC}"
    
    local tables_file="$1"
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name
    table_name=$(python3 <<EOF
import json
with open('$tables_file') as f:
    data = json.load(f)
    tables = data.get('tables', [])
    if tables:
        print(tables[0].get('name', ''))
EOF
)
    
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    test_endpoint "GET" "/object/$TEST_UPA/tables/$table_name/data" \
        "Sorted query (DESC)" 200 \
        -G -d "limit=20" -d "sort_column=id" -d "sort_order=DESC" -d "kb_env=$KB_ENV" > /dev/null
}

# Test 7: Statistics
test_statistics() {
    echo -e "\n${BLUE}7. Statistics${NC}"
    
    local tables_file="$1"
    if [ ! -f "$tables_file" ]; then
        return 0
    fi
    
    local table_name
    table_name=$(python3 <<EOF
import json
with open('$tables_file') as f:
    data = json.load(f)
    tables = data.get('tables', [])
    if tables:
        print(tables[0].get('name', ''))
EOF
)
    
    if [ -z "$table_name" ]; then
        return 0
    fi
    
    local response_file
    response_file=$(test_endpoint "GET" "/object/$TEST_UPA/tables/$table_name/stats" \
        "Table statistics" 200 \
        -G -d "kb_env=$KB_ENV")
    
    if [ -f "$response_file" ]; then
        local col_count
        col_count=$(python3 <<EOF
import json
with open('$response_file') as f:
    data = json.load(f)
    cols = data.get('columns', [])
    print(len(cols))
EOF
)
        echo -e "  ${GREEN}✓ Statistics for $col_count columns${NC}"
        rm -f "$response_file"
    fi
}

# Test 8: Multi-Database
test_multi_database() {
    echo -e "\n${BLUE}8. Multi-Database Support${NC}"
    
    local response_file
    response_file=$(test_endpoint "GET" "/databases" \
        "List databases" 200 \
        -G -d "upa=$TEST_UPA" -d "kb_env=$KB_ENV")
    
    if [ -f "$response_file" ]; then
        local db_info
        db_info=$(python3 <<EOF
import json
with open('$response_file') as f:
    data = json.load(f)
    databases = data.get('databases', [])
    print(len(databases))
    for db in databases[:3]:
        name = db.get('db_name', 'Unknown')
        tables = len(db.get('tables', []))
        print(f"    - {name}: {tables} tables")
EOF
)
        local db_count=$(echo "$db_info" | head -1)
        if [ "$db_count" -gt 0 ]; then
            echo "$db_info" | tail -n +2
            echo -e "  ${GREEN}✓ Found $db_count databases${NC}"
        else
            echo -e "  ${YELLOW}⚠ Single database object${NC}"
        fi
        rm -f "$response_file"
    fi
}

# Test 9: Authentication Formats
test_auth_formats() {
    echo -e "\n${BLUE}9. Authentication Formats${NC}"
    
    # Bearer token
    local status_code
    status_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV")
    
    if [ "$status_code" = "200" ]; then
        echo -e "  ${GREEN}✓ Bearer token works${NC}"
    else
        echo -e "  ${RED}✗ Bearer token failed (Status: $status_code)${NC}"
        return 1
    fi
    
    # Cookie auth
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

# Main
main() {
    echo "=========================================="
    echo "  TableScanner Test: 76990/Test2"
    echo "=========================================="
    echo ""
    
    start_server
    
    local failed=0
    local tables_file=""
    
    test_health || ((failed++))
    tables_file=$(test_list_tables) || ((failed++))
    
    if [ -n "$tables_file" ] && [ -f "$tables_file" ]; then
        test_get_table_data "$tables_file" || ((failed++))
        test_large_table "$tables_file" || ((failed++))
        test_filtering "$tables_file" || ((failed++))
        test_sorting "$tables_file" || ((failed++))
        test_statistics "$tables_file" || ((failed++))
    fi
    
    test_multi_database || ((failed++))
    test_auth_formats || ((failed++))
    
    # Cleanup temp files
    rm -f /tmp/test_response_*.json
    
    echo ""
    echo "=========================================="
    if [ $failed -eq 0 ]; then
        echo -e "${GREEN}✅ All tests passed!${NC}"
        echo "=========================================="
        exit 0
    else
        echo -e "${RED}✗ $failed test(s) failed${NC}"
        echo "=========================================="
        exit 1
    fi
}

main "$@"
