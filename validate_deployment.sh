#!/bin/bash
# Comprehensive Deployment Validation Script
# Tests TableScanner backend and DataTables Viewer frontend integration

set -uo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"
TEST_UPA="${TEST_UPA:-76990/7/2}"
TEST_UPA_MULTI="${TEST_UPA_MULTI:-76990/Test2}"
FAILED=0
PASSED=0

# Get token from .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: .env file not found${NC}" >&2
    exit 1
fi

TOKEN=$(grep KB_SERVICE_AUTH_TOKEN "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" | tr -d ' ' || echo "")

if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}WARNING: KB_SERVICE_AUTH_TOKEN not found in .env${NC}" >&2
    echo -e "${YELLOW}Some tests may fail without authentication${NC}" >&2
fi

print_test() {
    local name="$1"
    local result="$2"
    if [ "$result" = "PASS" ]; then
        echo -e "  ${GREEN}✓${NC} $name"
        ((PASSED++))
    else
        echo -e "  ${RED}✗${NC} $name"
        ((FAILED++))
    fi
}

test_endpoint() {
    local method="$1"
    local endpoint="$2"
    local name="$3"
    local expected_status="${4:-200}"
    local use_cookie="${5:-false}"
    local post_data="${6:-}"
    
    local status_code
    local headers=""
    
    if [ "$use_cookie" = "true" ] && [ -n "$TOKEN" ]; then
        headers="-H 'Cookie: kbase_session=$TOKEN'"
    elif [ -n "$TOKEN" ]; then
        headers="-H 'Authorization: Bearer $TOKEN'"
    fi
    
    if [ "$method" = "POST" ]; then
        if [ -n "$post_data" ]; then
            status_code=$(eval "curl -s -w '%{http_code}' -o /tmp/test_response.json $headers -X POST -H 'Content-Type: application/json' -d '$post_data' '$BACKEND_URL$endpoint'" | tail -1)
        else
            status_code=$(eval "curl -s -w '%{http_code}' -o /tmp/test_response.json $headers -X POST '$BACKEND_URL$endpoint'" | tail -1)
        fi
    else
        status_code=$(eval "curl -s -w '%{http_code}' -o /tmp/test_response.json $headers '$BACKEND_URL$endpoint'" | tail -1)
    fi
    
    if [ "$status_code" = "$expected_status" ]; then
        print_test "$name" "PASS"
        return 0
    else
        print_test "$name (got $status_code, expected $expected_status)" "FAIL"
        return 1
    fi
}

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Deployment Validation Test Suite${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${BLUE}Backend URL:${NC} $BACKEND_URL"
echo -e "${BLUE}Frontend URL:${NC} $FRONTEND_URL"
echo -e "${BLUE}Test UPA:${NC} $TEST_UPA"
echo ""

# 1. Backend Health Check
echo -e "${BLUE}1. Backend Health Check${NC}"
test_endpoint "GET" "/health" "Health endpoint" "200" "false"
test_endpoint "GET" "/" "Root endpoint" "200" "false"

# 2. Authentication Tests
echo -e "\n${BLUE}2. Authentication Tests${NC}"
test_endpoint "GET" "/object/$TEST_UPA/tables?kb_env=appdev" "Bearer token auth" "200" "false"
test_endpoint "GET" "/object/$TEST_UPA/tables?kb_env=appdev" "Cookie auth" "200" "true"

# 3. Object Access Endpoints
echo -e "\n${BLUE}3. Object Access Endpoints${NC}"
test_endpoint "GET" "/object/$TEST_UPA/tables?kb_env=appdev" "List tables" "200" "false"
test_endpoint "GET" "/object/$TEST_UPA/tables/Genes/data?limit=5&kb_env=appdev" "Get table data" "200" "false"

# 4. Multi-Database Support
echo -e "\n${BLUE}4. Multi-Database Support${NC}"
test_endpoint "GET" "/databases?upa=$TEST_UPA_MULTI&kb_env=appdev" "List databases" "200" "false"
test_endpoint "GET" "/db/GCF_000368685.1/tables?upa=$TEST_UPA_MULTI&kb_env=appdev" "List tables in database" "200" "false"

# 5. POST Endpoint
echo -e "\n${BLUE}5. POST /table-data Endpoint${NC}"
PAYLOAD="{\"berdl_table_id\":\"$TEST_UPA\",\"table_name\":\"Genes\",\"limit\":3,\"offset\":0}"
test_endpoint "POST" "/table-data" "POST table-data" "200" "false" "$PAYLOAD"

# 6. System Logs
echo -e "\n${BLUE}6. System Logs Endpoint${NC}"
test_endpoint "GET" "/system/logs?limit=10" "Get system logs" "200" "false"

# 7. Frontend Accessibility
echo -e "\n${BLUE}7. Frontend Accessibility${NC}"
if curl -s "$FRONTEND_URL" > /dev/null 2>&1; then
    print_test "Frontend serves HTML" "PASS"
else
    print_test "Frontend serves HTML" "FAIL"
fi

FRONTEND_DIST="/home/vibhav/Downloads/Work/ANL/Research/DataTables_Viewer/dist"
if [ -d "$FRONTEND_DIST" ]; then
    print_test "Frontend dist/ directory exists" "PASS"
else
    print_test "Frontend dist/ directory exists" "FAIL"
fi

if [ -f "$FRONTEND_DIST/config/index.json" ]; then
    CONFIG_URL=$(python3 -c "import json; print(json.load(open('$FRONTEND_DIST/config/index.json'))['apis']['tablescanner']['url'])" 2>/dev/null || echo "")
    if [ -n "$CONFIG_URL" ]; then
        print_test "Frontend config accessible (URL: $CONFIG_URL)" "PASS"
    else
        print_test "Frontend config accessible" "FAIL"
    fi
else
    print_test "Frontend config accessible" "FAIL"
fi

# 8. CORS Headers
echo -e "\n${BLUE}8. CORS Configuration${NC}"
CORS_HEADER=$(curl -s -I -H "Origin: $FRONTEND_URL" "$BACKEND_URL/health" | grep -i "access-control" || echo "")
if [ -n "$CORS_HEADER" ]; then
    print_test "CORS headers present" "PASS"
else
    print_test "CORS headers present" "FAIL"
fi

# Summary
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Test Summary${NC}"
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}Passed:${NC} $PASSED"
echo -e "${RED}Failed:${NC} $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed! Deployment is ready.${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Please review the errors above.${NC}"
    exit 1
fi
