#!/bin/bash
# Complete integration test script
# Starts server, runs all tests, cleans up

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Config
BASE_URL="http://localhost:8000"
TEST_UPA="76990/Test2"
KB_ENV="appdev"
PORT=8000
SERVER_PID=""

# Get project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Get token
ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: .env file not found${NC}"
    exit 1
fi

TOKEN=$(grep KB_SERVICE_AUTH_TOKEN "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" | tr -d ' ')

if [ -z "$TOKEN" ]; then
    echo -e "${RED}ERROR: KB_SERVICE_AUTH_TOKEN not found${NC}"
    exit 1
fi

# Cleanup
cleanup() {
    if [ -n "$SERVER_PID" ]; then
        echo -e "\n${YELLOW}Stopping server (PID: $SERVER_PID)...${NC}"
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    rm -f /tmp/test_response_*.json
}
trap cleanup EXIT

# Start server
start_server() {
    echo -e "${BLUE}Starting server...${NC}"
    
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}Port $PORT in use, using existing server${NC}"
        SERVER_PID=""
        return
    fi
    
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT > /tmp/tablescanner_server.log 2>&1 &
    SERVER_PID=$!
    echo "Server PID: $SERVER_PID"
    
    # Wait for server
    for i in {1..30}; do
        if curl -s "$BASE_URL/health" >/dev/null 2>&1; then
            echo -e "${GREEN}Server ready!${NC}"
            sleep 1
            return 0
        fi
        sleep 1
    done
    
    echo -e "${RED}Server failed to start${NC}"
    cat /tmp/tablescanner_server.log
    exit 1
}

# Test endpoint
test_curl() {
    local method=$1
    local path=$2
    local desc=$3
    local expected=${4:-200}
    shift 4
    
    echo -n "  $desc... " >&2
    
    local status
    local response="/tmp/test_$$_$(date +%s).json"
    
    if [ "$method" = "GET" ]; then
        status=$(curl -s -o "$response" -w "%{http_code}" \
            -H "Authorization: $TOKEN" \
            "$BASE_URL$path" "$@" 2>/dev/null)
    elif [ "$method" = "POST" ]; then
        status=$(curl -s -o "$response" -w "%{http_code}" \
            -H "Authorization: $TOKEN" \
            -H "Content-Type: application/json" \
            -X POST \
            -d @- \
            "$BASE_URL$path" "$@" 2>/dev/null)
    fi
    
    if [ "$status" = "$expected" ]; then
        echo -e "${GREEN}✓${NC}" >&2
        echo "$response"  # Output file path to stdout
        return 0
    else
        echo -e "${RED}✗ (got $status)${NC}" >&2
        [ -f "$response" ] && head -5 "$response" | sed 's/^/    /' >&2
        rm -f "$response"
        return 1
    fi
}

# Tests
main() {
    echo "=========================================="
    echo "  TableScanner Integration Test"
    echo "=========================================="
    echo ""
    
    start_server
    
    local failed=0
    local tables_file=""
    
    # Test 1: Health
    echo -e "\n${BLUE}1. Health Check${NC}"
    test_curl GET "/health" "Health endpoint" 200 || ((failed++))
    
    # Test 2: List tables
    echo -e "\n${BLUE}2. List Tables${NC}"
    if tables_file=$(test_curl GET "/object/$TEST_UPA/tables" "List tables" 200 -G -d "kb_env=$KB_ENV"); then
        if [ -f "$tables_file" ]; then
            local count=$(python3 -c "import json; print(len(json.load(open('$tables_file')).get('tables', [])))" 2>/dev/null || echo "0")
            echo "    Found $count tables"
        fi
    else
        ((failed++))
    fi
    
    # Test 3: Get table data
    if [ -n "$tables_file" ] && [ -f "$tables_file" ]; then
        echo -e "\n${BLUE}3. Get Table Data${NC}"
        local table_name=$(python3 -c "import json; t=json.load(open('$tables_file')); print(t['tables'][0]['name'] if t.get('tables') else '')" 2>/dev/null)
        if [ -n "$table_name" ]; then
            test_curl GET "/object/$TEST_UPA/tables/$table_name/data" "Get data" 200 -G -d "limit=10" -d "kb_env=$KB_ENV" || ((failed++))
        fi
    fi
    
    # Test 4: POST endpoint
    if [ -n "$tables_file" ] && [ -f "$tables_file" ]; then
        echo -e "\n${BLUE}4. POST /table-data${NC}"
        local table_name=$(python3 -c "import json; t=json.load(open('$tables_file')); print(t['tables'][0]['name'] if t.get('tables') else '')" 2>/dev/null)
        if [ -n "$table_name" ]; then
            echo "{\"berdl_table_id\":\"$TEST_UPA\",\"table_name\":\"$table_name\",\"limit\":10}" | \
                test_curl POST "/table-data" "POST endpoint" 200 || ((failed++))
        fi
    fi
    
    # Test 5: Statistics
    if [ -n "$tables_file" ] && [ -f "$tables_file" ]; then
        echo -e "\n${BLUE}5. Statistics${NC}"
        local table_name=$(python3 -c "import json; t=json.load(open('$tables_file')); print(t['tables'][0]['name'] if t.get('tables') else '')" 2>/dev/null)
        if [ -n "$table_name" ]; then
            test_curl GET "/object/$TEST_UPA/tables/$table_name/stats" "Statistics" 200 -G -d "kb_env=$KB_ENV" || ((failed++))
        fi
    fi
    
    # Test 6: Multi-database
    echo -e "\n${BLUE}6. Multi-Database${NC}"
    test_curl GET "/databases" "List databases" 200 -G -d "upa=$TEST_UPA" -d "kb_env=$KB_ENV" || ((failed++))
    
    # Test 7: Auth formats
    echo -e "\n${BLUE}7. Authentication Formats${NC}"
    local status=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV" 2>/dev/null)
    if [ "$status" = "200" ]; then
        echo -e "  ${GREEN}✓ Bearer token${NC}"
    else
        echo -e "  ${RED}✗ Bearer token (got $status)${NC}"
        ((failed++))
    fi
    
    status=$(curl -s -o /dev/null -w "%{http_code}" -H "Cookie: kbase_session=$TOKEN" "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV" 2>/dev/null)
    if [ "$status" = "200" ]; then
        echo -e "  ${GREEN}✓ Cookie auth${NC}"
    else
        echo -e "  ${RED}✗ Cookie auth (got $status)${NC}"
        ((failed++))
    fi
    
    # Summary
    echo ""
    echo "=========================================="
    if [ $failed -eq 0 ]; then
        echo -e "${GREEN}✅ All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}✗ $failed test(s) failed${NC}"
        exit 1
    fi
}

main "$@"
