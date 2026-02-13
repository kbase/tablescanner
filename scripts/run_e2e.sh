#!/usr/bin/env bash
# Comprehensive E2E test — saves each response to /tmp then inspects
set -uo pipefail

BASE="http://127.0.0.1:8003"
TOKEN="QLD6TZTNRFW4UH2B5YWTM4SG2NFMHZVV"
COOKIE="kbase_session=${TOKEN}"
PASS=0; FAIL=0

p() { ((PASS++)); printf "  \e[32m✓\e[0m %s\n" "$1"; }
f() { ((FAIL++)); printf "  \e[31m✗\e[0m %s — %s\n" "$1" "$2"; }

check_json_field() {
    local file=$1 field=$2 expected=$3 label=$4
    val=$(python3 -c "import json; d=json.load(open('$file')); print(d.get('$field',''))" 2>/dev/null)
    if [[ "$val" == "$expected" ]]; then p "$label ($val)"; else f "$label" "got=$val want=$expected"; fi
}

echo ""
echo "========================================================="
echo "  BACKEND E2E TEST SUITE — Deployment Simulation"
echo "  Container: tablescanner:latest on port 8003"
echo "  Auth: Cookie-based (kbase_session), no KB_SERVICE_AUTH_TOKEN"
echo "========================================================="

## ───────── 1. CONNECTIVITY ─────────
echo -e "\n─── 1. CONNECTIVITY ───"
curl -m 10 -s "$BASE/" -o /tmp/t_root.json -w "%{http_code}" > /tmp/t_root_code.txt 2>&1
CODE=$(cat /tmp/t_root_code.txt)
[[ "$CODE" == "200" ]] && p "Root endpoint (200)" || f "Root endpoint" "$CODE"

curl -m 10 -s "$BASE/health" -o /tmp/t_health.json -w "%{http_code}" > /tmp/t_health_code.txt 2>&1
check_json_field /tmp/t_health.json status ok "Health check"

## ───────── 2. AUTHENTICATION ─────────
echo -e "\n─── 2. AUTHENTICATION (no service token in container) ───"
# 2.1 No auth → 401
CODE=$(curl -m 10 -s -o /dev/null -w "%{http_code}" "$BASE/object/76990/7/2/tables?kb_env=appdev")
[[ "$CODE" == "401" ]] && p "Unauthenticated → 401" || f "Unauthenticated" "$CODE"

# 2.2 Raw token header
CODE=$(curl -m 30 -s -o /dev/null -w "%{http_code}" -H "Authorization: ${TOKEN}" "$BASE/object/76990/7/2/tables?kb_env=appdev")
[[ "$CODE" == "200" ]] && p "Raw token header → 200" || f "Raw token header" "$CODE"

# 2.3 Bearer token header  
CODE=$(curl -m 30 -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${TOKEN}" "$BASE/object/76990/7/2/tables?kb_env=appdev")
[[ "$CODE" == "200" ]] && p "Bearer token header → 200" || f "Bearer token header" "$CODE"

# 2.4 Cookie auth (deployment method)
CODE=$(curl -m 30 -s -o /dev/null -w "%{http_code}" --cookie "$COOKIE" "$BASE/object/76990/7/2/tables?kb_env=appdev")
[[ "$CODE" == "200" ]] && p "Cookie auth → 200 (deployment method)" || f "Cookie auth" "$CODE"

## ───────── 3. SINGLE-DB (76990/7/2) ─────────
echo -e "\n─── 3. SINGLE-DB OBJECT (76990/7/2) ───"
# 3.1 List tables 
curl -m 60 -s --cookie "$COOKIE" "$BASE/object/76990/7/2/tables?kb_env=appdev" -o /tmp/t_list.json 2>&1
TABLE_COUNT=$(python3 -c "import json; d=json.load(open('/tmp/t_list.json')); print(len(d.get('tables',[])))" 2>/dev/null || echo 0)
TOTAL_ROWS=$(python3 -c "import json; d=json.load(open('/tmp/t_list.json')); print(d.get('total_rows',0))" 2>/dev/null || echo 0)
OBJ_TYPE=$(python3 -c "import json; d=json.load(open('/tmp/t_list.json')); print(d.get('object_type',''))" 2>/dev/null || echo "")
SCHEMA_COUNT=$(python3 -c "import json; d=json.load(open('/tmp/t_list.json')); print(len(d.get('schemas',{})))" 2>/dev/null || echo 0)
[[ "$TABLE_COUNT" -gt 0 ]] && p "Listed $TABLE_COUNT tables (rows=$TOTAL_ROWS, type=$OBJ_TYPE, schemas=$SCHEMA_COUNT)" || f "List tables" "got $TABLE_COUNT"

# Print table details
python3 -c "
import json
d=json.load(open('/tmp/t_list.json'))
for t in d.get('tables',[]):
    print(f'    • {t[\"name\"]}: {t.get(\"row_count\",\"?\")} rows, {t.get(\"column_count\",\"?\")} cols')
" 2>/dev/null

# 3.2 Data: Genes limit=5
curl -m 30 -s --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Genes/data?limit=5&offset=0&kb_env=appdev" -o /tmp/t_genes.json 2>&1
ROWS=$(python3 -c "import json; d=json.load(open('/tmp/t_genes.json')); print(len(d.get('data',[])))" 2>/dev/null || echo 0)
TOTAL=$(python3 -c "import json; d=json.load(open('/tmp/t_genes.json')); print(d.get('total_count',0))" 2>/dev/null || echo 0)
[[ "$ROWS" == "5" ]] && p "Genes data: got 5 rows (total=$TOTAL)" || f "Genes data" "rows=$ROWS"

# 3.3 Data: Genes with search
curl -m 30 -s --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Genes/data?limit=20&search=kinase&kb_env=appdev" -o /tmp/t_search.json 2>&1
S_ROWS=$(python3 -c "import json; print(len(json.load(open('/tmp/t_search.json')).get('data',[])))" 2>/dev/null || echo "ERR")
[[ "$S_ROWS" != "ERR" ]] && p "Search 'kinase': $S_ROWS rows" || f "Search query" "$S_ROWS"

# 3.4 Data: Genes with sort DESC
curl -m 30 -s --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Genes/data?limit=3&sort_column=Database_ID&sort_order=DESC&kb_env=appdev" -o /tmp/t_sort.json 2>&1
SORT_OK=$(python3 -c "import json; d=json.load(open('/tmp/t_sort.json')); print('ok' if len(d.get('data',[])) > 0 else 'fail')" 2>/dev/null || echo "fail")
[[ "$SORT_OK" == "ok" ]] && p "Sort DESC on Database_ID works" || f "Sort" "no data"

# 3.5 Pagination  
curl -m 30 -s --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Genes/data?limit=2&offset=0&kb_env=appdev" -o /tmp/t_p1.json 2>&1
curl -m 30 -s --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Genes/data?limit=2&offset=2&kb_env=appdev" -o /tmp/t_p2.json 2>&1
PAG_OK=$(python3 -c "
import json
p1 = json.load(open('/tmp/t_p1.json')).get('data',[])
p2 = json.load(open('/tmp/t_p2.json')).get('data',[])
print('ok' if p1 and p2 and p1 != p2 else 'fail')
" 2>/dev/null || echo "fail")
[[ "$PAG_OK" == "ok" ]] && p "Pagination: page1 ≠ page2" || f "Pagination" "pages match or empty"

# 3.6 Statistics
curl -m 30 -s --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Genes/stats?kb_env=appdev" -o /tmp/t_stats.json 2>&1
STAT_COLS=$(python3 -c "import json; print(len(json.load(open('/tmp/t_stats.json')).get('columns',[])))" 2>/dev/null || echo 0)
[[ "$STAT_COLS" -gt 0 ]] && p "Statistics: $STAT_COLS column stats" || f "Statistics" "$STAT_COLS cols"

# 3.7 Strains table
CODE=$(curl -m 30 -s -o /dev/null -w "%{http_code}" --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Strains/data?limit=3&kb_env=appdev")
[[ "$CODE" == "200" ]] && p "Strains table accessible (200)" || f "Strains" "$CODE"

# 3.8 Samples table
CODE=$(curl -m 30 -s -o /dev/null -w "%{http_code}" --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Samples/data?limit=3&kb_env=appdev")
[[ "$CODE" == "200" ]] && p "Samples table accessible (200)" || f "Samples" "$CODE"

# 3.9 Empty table (robotic_mt_samples)
curl -m 30 -s --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/robotic_mt_samples/data?limit=10&kb_env=appdev" -o /tmp/t_empty.json 2>&1
EMPTY_ROWS=$(python3 -c "import json; print(len(json.load(open('/tmp/t_empty.json')).get('data',[])))" 2>/dev/null || echo "ERR")
[[ "$EMPTY_ROWS" == "0" ]] && p "Empty table: 0 rows" || f "Empty table" "rows=$EMPTY_ROWS"

# 3.10 Non-existent table  
CODE=$(curl -m 10 -s -o /dev/null -w "%{http_code}" --cookie "$COOKIE" "$BASE/object/76990/7/2/tables/Fake/data?kb_env=appdev")
[[ "$CODE" == "404" || "$CODE" == "500" ]] && p "Non-existent table rejected ($CODE)" || f "Non-existent table" "$CODE"

## ───────── 4. MULTI-DB (76990/Test2) ─────────
echo -e "\n─── 4. MULTI-DB OBJECT (76990/Test2) ───"
echo "    (This may take a few minutes if not cached...)"

curl -m 300 -s --cookie "$COOKIE" "$BASE/databases?upa=76990/Test2&kb_env=appdev" -o /tmp/t_dbs.json 2>&1
DB_COUNT=$(python3 -c "import json; d=json.load(open('/tmp/t_dbs.json')); print(len(d.get('databases',[])))" 2>/dev/null || echo 0)
HAS_MULTI=$(python3 -c "import json; print(json.load(open('/tmp/t_dbs.json')).get('has_multiple_databases',''))" 2>/dev/null || echo "")
API_VER=$(python3 -c "import json; print(json.load(open('/tmp/t_dbs.json')).get('api_version',''))" 2>/dev/null || echo "")

[[ "$DB_COUNT" -gt 0 ]] && p "Listed $DB_COUNT databases (multi=$HAS_MULTI, api=$API_VER)" || f "List databases" "count=$DB_COUNT"

# Print database details
python3 -c "
import json
d=json.load(open('/tmp/t_dbs.json'))
for db in d.get('databases',[]):
    name = db.get('db_name','?')
    tables = len(db.get('tables',[]))
    rows = db.get('row_count',0)
    print(f'    • {name}: {tables} tables, {rows} rows')
" 2>/dev/null

# 4.2 Get first DB name and test
FIRST_DB=$(python3 -c "import json; dbs=json.load(open('/tmp/t_dbs.json')).get('databases',[]); print(dbs[0]['db_name'] if dbs else '')" 2>/dev/null || echo "")
if [[ -n "$FIRST_DB" ]]; then
    p "First database: $FIRST_DB"
    
    # 4.3 List tables in specific DB
    curl -m 60 -s --cookie "$COOKIE" "$BASE/db/${FIRST_DB}/tables?upa=76990/Test2&kb_env=appdev" -o /tmp/t_db_tables.json 2>&1
    DB_TABLE_COUNT=$(python3 -c "import json; print(len(json.load(open('/tmp/t_db_tables.json')).get('tables',[])))" 2>/dev/null || echo 0)
    [[ "$DB_TABLE_COUNT" -gt 0 ]] && p "Tables in $FIRST_DB: $DB_TABLE_COUNT" || f "Tables in $FIRST_DB" "$DB_TABLE_COUNT"
    
    # Table names
    FIRST_TABLE=$(python3 -c "import json; ts=json.load(open('/tmp/t_db_tables.json')).get('tables',[]); print(ts[0]['name'] if ts else '')" 2>/dev/null || echo "")
    if [[ -n "$FIRST_TABLE" ]]; then
        p "First table: $FIRST_TABLE"
        
        # 4.4 Query data from specific DB
        curl -m 30 -s --cookie "$COOKIE" "$BASE/db/${FIRST_DB}/tables/${FIRST_TABLE}/data?upa=76990/Test2&limit=5&kb_env=appdev" -o /tmp/t_db_data.json 2>&1
        DB_ROWS=$(python3 -c "import json; print(len(json.load(open('/tmp/t_db_data.json')).get('data',[])))" 2>/dev/null || echo 0)
        [[ "$DB_ROWS" -gt 0 ]] && p "Data from $FIRST_DB/$FIRST_TABLE: $DB_ROWS rows" || f "Data from $FIRST_DB/$FIRST_TABLE" "rows=$DB_ROWS"
    fi
else
    f "Could not determine first database" ""
fi

## ───────── 5. POST /table-data ─────────
echo -e "\n─── 5. POST /table-data (Frontend-style requests) ───"

# 5.1 POST for Genes
curl -m 30 -s --cookie "$COOKIE" -H "Content-Type: application/json" \
  -X POST "$BASE/table-data" \
  -d '{"berdl_table_id":"76990/7/2","table_name":"Genes","limit":10,"offset":0,"kb_env":"appdev"}' \
  -o /tmp/t_post1.json 2>&1
P1_ROWS=$(python3 -c "import json; print(len(json.load(open('/tmp/t_post1.json')).get('data',[])))" 2>/dev/null || echo 0)
[[ "$P1_ROWS" -gt 0 ]] && p "POST Genes: $P1_ROWS rows" || f "POST Genes" "rows=$P1_ROWS"

# 5.2 POST with sort
curl -m 30 -s --cookie "$COOKIE" -H "Content-Type: application/json" \
  -X POST "$BASE/table-data" \
  -d '{"berdl_table_id":"76990/7/2","table_name":"Strains","limit":5,"offset":0,"sort_column":"Name","sort_order":"ASC","kb_env":"appdev"}' \
  -o /tmp/t_post2.json 2>&1
P2_ROWS=$(python3 -c "import json; print(len(json.load(open('/tmp/t_post2.json')).get('data',[])))" 2>/dev/null || echo 0)
[[ "$P2_ROWS" == "5" ]] && p "POST Strains sorted: 5 rows" || f "POST Strains" "rows=$P2_ROWS"

# 5.3 POST with search
curl -m 30 -s --cookie "$COOKIE" -H "Content-Type: application/json" \
  -X POST "$BASE/table-data" \
  -d '{"berdl_table_id":"76990/7/2","table_name":"Genes","limit":50,"search_value":"DNA","kb_env":"appdev"}' \
  -o /tmp/t_post3.json 2>&1
P3_ROWS=$(python3 -c "import json; print(len(json.load(open('/tmp/t_post3.json')).get('data',[])))" 2>/dev/null || echo 0)
[[ "$P3_ROWS" -gt 0 ]] && p "POST search 'DNA': $P3_ROWS rows" || f "POST search" "rows=$P3_ROWS"

## ───────── 6. DATA INTEGRITY ─────────
echo -e "\n─── 6. DATA INTEGRITY ───"

# 6.1 Response format
python3 -c "
import json
d = json.load(open('/tmp/t_list.json'))
required = ['berdl_table_id','object_type','tables','schemas','total_rows','api_version']
missing = [f for f in required if f not in d]
if not missing: print('FIELDS_OK')
else: print(f'MISSING:{missing}')
" 2>/dev/null | while read r; do 
[[ "$r" == "FIELDS_OK" ]] && p "List tables: all required fields present" || f "Fields" "$r"
done

# 6.2 Data shape
python3 -c "
import json
d = json.load(open('/tmp/t_genes.json'))
data = d.get('data', [])
if data:
    row = data[0]
    if isinstance(row, dict):
        print('DICT')
    elif isinstance(row, list):
        print('LIST')
    else:
        print(f'UNKNOWN:{type(row)}')
else:
    print('EMPTY')
" 2>/dev/null | while read r; do
[[ "$r" == "DICT" || "$r" == "LIST" ]] && p "Data format: $r rows" || f "Data format" "$r"
done

# 6.3 Content-Type
CT=$(curl -m 10 -s -o /dev/null -w "%{content_type}" --cookie "$COOKIE" "$BASE/object/76990/7/2/tables?kb_env=appdev")
echo "$CT" | grep -q "application/json" && p "Content-Type: application/json" || f "Content-Type" "$CT"

## ───────── SUMMARY ─────────
echo -e "\n========================================================="
printf "  Total: %d | \e[32mPassed: %d\e[0m | \e[31mFailed: %d\e[0m\n" $((PASS+FAIL)) $PASS $FAIL
echo "========================================================="

[[ $FAIL -eq 0 ]] && echo -e "\e[32m  ✓ ALL TESTS PASSED — Backend is deployment-ready\e[0m" || echo -e "\e[31m  ✗ Some tests failed\e[0m"
exit $FAIL
