#!/bin/bash
# Basic integration test - starts server and tests endpoints

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BASE_URL="http://localhost:8000"
TEST_UPA="76990/Test2"
KB_ENV="appdev"
PORT=8000
SERVER_PID=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

ENV_FILE="$PROJECT_ROOT/.env"
TOKEN=$(grep KB_SERVICE_AUTH_TOKEN "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" | tr -d ' ')

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        echo -e "\n${YELLOW}Stopping server...${NC}"
        kill "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

start_server() {
    echo -e "${BLUE}Starting server...${NC}"
    
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}Port $PORT in use, using existing server${NC}"
        return
    fi
    
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT > /tmp/tablescanner_test.log 2>&1 &
    SERVER_PID=$!
    
    for i in {1..30}; do
        if curl -s "$BASE_URL/health" >/dev/null 2>&1; then
            echo -e "${GREEN}Server ready!${NC}"
            return 0
        fi
        sleep 1
    done
    
    echo -e "${RED}Server failed to start${NC}"
    exit 1
}

test_get() {
    local path=$1
    local desc=$2
    shift 2
    
    echo -n "  $desc... "
    local status=$(curl -s -o /tmp/response.json -w "%{http_code}" \
        -H "Authorization: $TOKEN" \
        "$BASE_URL$path" "$@" 2>/dev/null)
    
    if [ "$status" = "200" ]; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗ (status: $status)${NC}"
        return 1
    fi
}

test_post() {
    local path=$1
    local desc=$2
    local json=$3
    shift 3
    
    echo -n "  $desc... "
    local status=$(curl -s -o /tmp/response.json -w "%{http_code}" \
        -H "Authorization: $TOKEN" \
        -H "Content-Type: application/json" \
        -X POST \
        -d "$json" \
        "$BASE_URL$path" "$@" 2>/dev/null)
    
    if [ "$status" = "200" ]; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗ (status: $status)${NC}"
        return 1
    fi
}

main() {
    echo "=========================================="
    echo "  TableScanner Integration Test"
    echo "=========================================="
    echo ""
    
    start_server
    
    local failed=0
    
    echo -e "\n${BLUE}1. Health Check${NC}"
    test_get "/health" "Health endpoint" || ((failed++))
    
    echo -e "\n${BLUE}2. List Tables${NC}"
    test_get "/object/$TEST_UPA/tables" "List tables" -G -d "kb_env=$KB_ENV" || ((failed++))
    
    if [ -f /tmp/response.json ]; then
        local table_name=$(python3 -c "import json; t=json.load(open('/tmp/response.json')); print(t['tables'][0]['name'] if t.get('tables') else '')" 2>/dev/null)
        
        if [ -n "$table_name" ]; then
            echo -e "\n${BLUE}3. Get Table Data${NC}"
            test_get "/object/$TEST_UPA/tables/$table_name/data" "Get data" -G -d "limit=10" -d "kb_env=$KB_ENV" || ((failed++))
            
            echo -e "\n${BLUE}4. POST /table-data${NC}"
            local json="{\"berdl_table_id\":\"$TEST_UPA\",\"table_name\":\"$table_name\",\"limit\":10}"
            test_post "/table-data" "POST endpoint" "$json" || ((failed++))
            
            echo -e "\n${BLUE}5. Statistics${NC}"
            test_get "/object/$TEST_UPA/tables/$table_name/stats" "Statistics" -G -d "kb_env=$KB_ENV" || ((failed++))
        fi
    fi
    
    echo -e "\n${BLUE}6. Multi-Database${NC}"
    test_get "/databases" "List databases" -G -d "upa=$TEST_UPA" -d "kb_env=$KB_ENV" || ((failed++))
    
    echo -e "\n${BLUE}7. Authentication Formats${NC}"
    local status=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV" 2>/dev/null)
    if [ "$status" = "200" ]; then
        echo -e "  ${GREEN}✓ Bearer token${NC}"
    else
        echo -e "  ${RED}✗ Bearer token${NC}"
        ((failed++))
    fi
    
    status=$(curl -s -o /dev/null -w "%{http_code}" -H "Cookie: kbase_session=$TOKEN" "$BASE_URL/object/$TEST_UPA/tables?kb_env=$KB_ENV" 2>/dev/null)
    if [ "$status" = "200" ]; then
        echo -e "  ${GREEN}✓ Cookie auth${NC}"
    else
        echo -e "  ${RED}✗ Cookie auth${NC}"
        ((failed++))
    fi
    
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
