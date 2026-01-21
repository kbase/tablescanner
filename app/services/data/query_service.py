"""
Enhanced Query Service for DataTables Viewer API.

Provides comprehensive query execution with:
- Type-aware filtering with proper numeric conversion
- Advanced filter operators (eq, ne, gt, gte, lt, lte, like, ilike, in, not_in, between, is_null, is_not_null)
- Aggregations with GROUP BY
- Full-text search (FTS5)
- Automatic indexing
- Query result caching
- Comprehensive metadata in responses
"""

from __future__ import annotations

import sqlite3
import logging
import time
import hashlib
import json
import threading
from pathlib import Path
from typing import Any
from collections import OrderedDict
from dataclasses import dataclass

from app.services.data.connection_pool import get_connection_pool
from app.config_constants import (
    CACHE_MAX_ENTRIES,
    INDEX_CACHE_TTL,
)
from app.exceptions import (
    TableNotFoundError,
    InvalidFilterError,
)

logger = logging.getLogger(__name__)


@dataclass
class FilterSpec:
    """Filter specification for query building."""
    
    column: str
    operator: str
    value: Any = None
    value2: Any = None  # For 'between' operator


@dataclass
class AggregationSpec:
    """Aggregation specification for query building."""
    
    column: str
    function: str  # count, sum, avg, min, max, stddev, variance, distinct_count
    alias: str | None = None


@dataclass
class ColumnType:
    """Column type information from schema."""
    
    name: str
    type: str  # INTEGER, REAL, TEXT, etc.
    notnull: bool = False
    pk: bool = False
    dflt_value: Any = None


class QueryCache:
    """
    Query result cache with 5-minute TTL and LRU eviction.
    
    Cache key format: {dbPath}:{tableName}:{JSON.stringify(queryParams)}
    Invalidates when table modification time changes.
    """
    
    def __init__(self) -> None:
        """Initialize the query cache."""
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()
    
    def get(self, cache_key: str, table_mtime: float) -> Any | None:
        """
        Get cached query result.
        
        Args:
            cache_key: Cache key for the query
            table_mtime: Table file modification time
            
        Returns:
            Cached result if valid, None otherwise
        """
        with self._lock:
            if cache_key not in self._cache:
                return None
            
            result, cached_mtime = self._cache[cache_key]
            
            # Check if table has been modified
            if cached_mtime != table_mtime:
                del self._cache[cache_key]
                return None
            
            # Move to end (LRU)
            self._cache.move_to_end(cache_key)
            return result
    
    def set(self, cache_key: str, result: Any, table_mtime: float) -> None:
        """
        Store query result in cache.
        
        Args:
            cache_key: Cache key for the query
            result: Query result to cache
            table_mtime: Table file modification time
        """
        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)
            
            self._cache[cache_key] = (result, table_mtime)
            # Move to end (LRU)
            self._cache.move_to_end(cache_key)
    
    def clear(self) -> None:
        """Clear all cached results."""
        with self._lock:
            self._cache.clear()


# Global query cache instance
_query_cache: QueryCache | None = None
_cache_lock = threading.Lock()


def get_query_cache() -> QueryCache:
    """Get the global query cache instance."""
    global _query_cache
    
    if _query_cache is None:
        with _cache_lock:
            if _query_cache is None:
                _query_cache = QueryCache()
    
    return _query_cache


class QueryService:
    """
    Enhanced query service for DataTables Viewer API.
    
    Provides comprehensive query execution with type-aware filtering,
    aggregations, full-text search, and result caching.
    """
    
    def __init__(self) -> None:
        """Initialize the query service."""
        self.pool = get_connection_pool()
        self.cache = get_query_cache()
        # In-memory cache for index existence to avoid frequent sqlite_master queries
        # Key: {db_path}:{table_name}:{column_name}, Value: timestamp
        self._index_cache: dict[str, float] = {}
        self._index_lock = threading.Lock()
    
    def get_column_types(self, db_path: Path, table_name: str) -> list[ColumnType]:
        """
        Get column type information from table schema.
        """
        try:
            with self.pool.connection(db_path) as conn:
                cursor = conn.cursor()
                
                # Validate table existence and get validated table name
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                result = cursor.fetchone()
                if not result:
                    raise TableNotFoundError(table_name)
                
                # Use validated table name from sqlite_master to prevent SQL injection
                validated_table_name = result[0]
                cursor.execute(f"PRAGMA table_info(\"{validated_table_name}\")")
                rows = cursor.fetchall()
                
                column_types = []
                for row in rows:
                    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
                    column_types.append(ColumnType(
                        name=row[1],
                        type=row[2] or "TEXT",  # Default to TEXT if type is NULL
                        notnull=bool(row[3]),
                        pk=bool(row[5]),
                        dflt_value=row[4]
                    ))
                
                return column_types
        
        except sqlite3.Error as e:
            logger.error(f"Error getting column types: {e}")
            raise
    
    def is_numeric_column(self, column_type: str) -> bool:
        """Check if a column type is numeric."""
        if not column_type:
            return False
        type_upper = column_type.upper()
        return any(numeric_type in type_upper for numeric_type in ["INT", "REAL", "NUMERIC"])
    
    def convert_numeric_value(self, value: Any, column_type: str) -> float | int:
        """
        Convert a value to numeric type based on column type.
        
        Raises:
            ValueError: If value cannot be converted to the target numeric type
        """
        if value is None:
            return 0
        
        type_upper = column_type.upper()
        
        # Strict validation: prevent text->0 coercion
        try:
            if "INT" in type_upper:
                return int(float(str(value)))
            else:
                return float(str(value))
        except (ValueError, TypeError):
            # Re-raise with clear message instead of returning 0
            raise ValueError(f"Invalid numeric value '{value}' for column type '{column_type}'")
    
    def ensure_index(self, db_path: Path, table_name: str, column: str) -> None:
        """Ensure an index exists on a column. Optimized with in-memory cache."""
        cache_key = f"{db_path}:{table_name}:{column}"
        
        with self._index_lock:
            # Check cache with TTL
            if cache_key in self._index_cache:
                if time.time() - self._index_cache[cache_key] < INDEX_CACHE_TTL:
                    return

        try:
            with self.pool.connection(db_path) as conn:
                cursor = conn.cursor()
                index_name = f"idx_{table_name}_{column}".replace(" ", "_").replace("-", "_")
                safe_table = f'"{table_name}"'
                safe_column = f'"{column}"'
                
                cursor.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index_name}" ON {safe_table}({safe_column})'
                )
                conn.commit()
            
            with self._index_lock:
                self._index_cache[cache_key] = time.time()
                
        except sqlite3.Error as e:
            logger.warning(f"Error creating index on {table_name}.{column}: {e}")
    
    def ensure_fts5_table(self, db_path: Path, table_name: str, text_columns: list[str]) -> bool:
        """
        Ensure FTS5 virtual table exists for full-text search.
        
        Safety: Skips creation if table is too large (>100k rows) to prevent
        blocking the request thread for too long.
        """
        if not text_columns:
            return False
            
        try:
            with self.pool.connection(db_path) as conn:
                cursor = conn.cursor()
                
                fts5_table_name = f"{table_name}_fts5"
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (fts5_table_name,))
                if cursor.fetchone():
                    return True
                
                # Check capabilities
                cursor.execute("PRAGMA compile_options")
                if "ENABLE_FTS5" not in [row[0] for row in cursor.fetchall()]:
                    return False
    
                # SAFETY CHECK: Row count limit
                # Creating FTS5 index copies all data. For large tables, this is a heavy operation.
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                row_count = cursor.fetchone()[0]
                if row_count > 100000:
                    logger.warning(f"Skipping FTS5 creation for large table '{table_name}' ({row_count} rows)")
                    return False
                    
                safe_columns = ", ".join(f'"{col}"' for col in text_columns)
                cursor.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS "{fts5_table_name}" 
                    USING fts5({safe_columns}, content="{table_name}", content_rowid="rowid")
                """)
                
                # Populate
                # If table has integer PK, use it as rowid implicitly
                cursor.execute(f"""
                    INSERT INTO "{fts5_table_name}"(rowid, {safe_columns})
                    SELECT rowid, {safe_columns} FROM "{table_name}"
                """)
                
                conn.commit()
                return True
        except sqlite3.Error:
            return False

    def _build_select_clause(
        self, 
        columns: list[str] | None, 
        aggregations: list[AggregationSpec] | None,
        group_by: list[str] | None,
        column_types: dict[str, ColumnType]
    ) -> tuple[str, list[str]]:
        """
        Build SELECT clause and return logic for headers.
        
        Returns:
            Tuple of (select_sql, headers_list)
        """
        select_parts = []
        headers = []

        if aggregations:
            # GROUP BY columns in SELECT
            if group_by:
                for col in group_by:
                    if col in column_types:
                        select_parts.append(f'"{col}"')
                        headers.append(col)
            
            # Aggregation columns
            for agg in aggregations:
                if agg.column != "*" and agg.column not in column_types:
                    continue
                
                safe_col = f'"{agg.column}"' if agg.column != "*" else "*"
                
                if agg.function == "count":
                    expr = f"COUNT({safe_col})"
                elif agg.function == "distinct_count":
                    expr = f"COUNT(DISTINCT {safe_col})"
                elif agg.function in ["sum", "avg", "min", "max"]:
                    expr = f"{agg.function.upper()}({safe_col})"
                else: 
                    continue
                
                alias = agg.alias or f"{agg.function}_{agg.column}"
                # Sanitize alias to prevent injection/bad chars
                alias = alias.replace('"', '').replace("'", "")
                safe_alias = alias
                select_parts.append(f'{expr} AS "{safe_alias}"')
                headers.append(safe_alias)
            
            if not select_parts:
                select_parts = ["*"]
        else:
            # Regular columns
            if columns:
                valid_cols = []
                for col in columns:
                    if col in column_types:
                        valid_cols.append(f'"{col}"')
                        headers.append(col)
                if valid_cols:
                    select_parts = valid_cols
                else:
                    select_parts = ["*"]
            else:
                 select_parts = ["*"]
                 headers = list(column_types.keys())

        return ", ".join(select_parts), headers

    def _build_where_clause(
        self,
        db_path: Path,
        table_name: str,
        filters: list[FilterSpec] | None,
        search_value: str | None,
        column_types_list: list[ColumnType],
        column_types_map: dict[str, ColumnType],
        params: list[Any]
    ) -> str:
        """Build WHERE clause including global search and field filters."""
        where_conditions = []
        
        # Global Search
        if search_value:
            text_columns = [
                col.name for col in column_types_list
                if not self.is_numeric_column(col.type)
            ]
            
            # Note: ensures FTS5 table is ready. This might skip if table is large.
            if text_columns and self.ensure_fts5_table(db_path, table_name, text_columns):
                fts5_table = f"{table_name}_fts5"
                where_conditions.append(
                    f'rowid IN (SELECT rowid FROM "{fts5_table}" WHERE "{fts5_table}" MATCH ?)'
                )
                params.append(search_value)
            elif text_columns:
                search_conditions = []
                for col in text_columns:
                    search_conditions.append(f'"{col}" LIKE ?')
                    params.append(f"%{search_value}%")
                if search_conditions:
                    where_conditions.append(f"({' OR '.join(search_conditions)})")

        # Filters
        if filters:
            for filter_spec in filters:
                condition = self._build_single_filter(filter_spec, column_types_map, params)
                if condition:
                    where_conditions.append(condition)

        return f" WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

    def _build_single_filter(
        self,
        filter_spec: FilterSpec,
        column_types: dict[str, ColumnType],
        params: list[Any]
    ) -> str:
        """
        Build SQL condition for a single filter.
        
        Raises:
            InvalidFilterError: If filter parameters are unsafe (e.g. too many IN values)
        """
        column = filter_spec.column
        operator = filter_spec.operator.lower()
        value = filter_spec.value
        
        if column not in column_types:
            logger.warning(f"Column '{column}' not found, skipping filter")
            return ""
        
        col_type = column_types[column]
        is_numeric = self.is_numeric_column(col_type.type)
        safe_column = f'"{column}"'
        
        if operator == "is_null":
            return f"{safe_column} IS NULL"
        if operator == "is_not_null":
            return f"{safe_column} IS NOT NULL"
        
        if value is None:
            return ""
        
        # Check variable limits for array operators
        if operator in ["in", "not_in"] and isinstance(value, list):
            if len(value) > 900:
                raise InvalidFilterError(f"Too many values for IN operator: {len(value)}. Max is 900.")

        # Numeric handling
        if is_numeric and operator in ["eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in"]:
            if operator == "between":
                if filter_spec.value2 is None: return ""
                params.append(self.convert_numeric_value(value, col_type.type))
                params.append(self.convert_numeric_value(filter_spec.value2, col_type.type))
                return f"{safe_column} BETWEEN ? AND ?"
            elif operator in ["in", "not_in"]:
                if not isinstance(value, list): return ""
                vals = [self.convert_numeric_value(v, col_type.type) for v in value]
                placeholders = ",".join(["?"] * len(vals))
                params.extend(vals)
                op = "IN" if operator == "in" else "NOT IN"
                return f"{safe_column} {op} ({placeholders})"
            else:
                params.append(self.convert_numeric_value(value, col_type.type))
        else:
            # Text handling
            if operator in ["like", "ilike"]:
                params.append(f"%{value}%")
            elif operator in ["in", "not_in"]:
                if not isinstance(value, list): return ""
                placeholders = ",".join(["?"] * len(value))
                params.extend(value)
                op = "IN" if operator == "in" else "NOT IN"
                return f"{safe_column} {op} ({placeholders})"
            else:
                params.append(value)
        
        operator_map = {
            "eq": "=", "ne": "!=", "gt": ">", "gte": ">=", 
            "lt": "<", "lte": "<=", "like": "LIKE", "ilike": "LIKE"
        }
        
        sql_op = operator_map.get(operator)
        return f"{safe_column} {sql_op} ?" if sql_op else ""

    def execute_query(
        self,
        db_path: Path,
        table_name: str,
        limit: int = 100,
        offset: int = 0,
        columns: list[str] | None = None,
        sort_column: str | None = None,
        sort_order: str = "ASC",
        search_value: str | None = None,
        filters: list[FilterSpec] | None = None,
        aggregations: list[AggregationSpec] | None = None,
        group_by: list[str] | None = None,
        use_cache: bool = True
    ) -> dict[str, Any]:
        """Execute a comprehensive query with all features."""
        try:
            table_mtime = db_path.stat().st_mtime
        except OSError:
            table_mtime = 0.0
        
        # 1. Cache Check
        cache_key = self._build_cache_key(
            db_path, table_name, limit, offset, columns, sort_column,
            sort_order, search_value, filters, aggregations, group_by
        )
        
        if use_cache:
            cached = self.cache.get(cache_key, table_mtime)
            if cached:
                cached["cached"] = True
                return cached
        
        # 2. Schema & Validation
        # This calls get_column_types internally which uses the pool correctly now
        column_types_list = self.get_column_types(db_path, table_name)
        column_types_map = {col.name: col for col in column_types_list}
        
        # 3. Indices
        if filters:
            for f in filters:
                if f.column in column_types_map:
                    self.ensure_index(db_path, table_name, f.column)
        if sort_column and sort_column in column_types_map:
            self.ensure_index(db_path, table_name, sort_column)
            
        # 4. Query Construction
        select_clause, headers = self._build_select_clause(columns, aggregations, group_by, column_types_map)
        
        where_params: list[Any] = []
        where_clause = self._build_where_clause(
            db_path, table_name, filters, search_value, 
            column_types_list, column_types_map, where_params
        )
        
        group_by_clause = ""
        if group_by:
            valid_groups = [f'"{col}"' for col in group_by if col in column_types_map]
            if valid_groups:
                group_by_clause = " GROUP BY " + ", ".join(valid_groups)
        
        order_by_clause = ""
        if sort_column and sort_column in column_types_map:
            direction = "DESC" if sort_order.upper() == "DESC" else "ASC"
            order_by_clause = f' ORDER BY "{sort_column}" {direction}'
        elif not aggregations and column_types_list:
            order_by_clause = f' ORDER BY "{column_types_list[0].name}" ASC'
            
        limit_clause = f" LIMIT {int(limit)}"
        offset_clause = f" OFFSET {int(offset)}" if offset > 0 else ""
        
        # 5. Execution - Use the connection context manager
        with self.pool.connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Count Query
            count_query = f'SELECT COUNT(*) FROM "{table_name}"{where_clause}'
            cursor.execute(count_query, where_params)
            total_count = cursor.fetchone()[0]
            
            # Data Query
            query = f'SELECT {select_clause} FROM "{table_name}"{where_clause}{group_by_clause}{order_by_clause}{limit_clause}{offset_clause}'
            
            start_time = time.time()
            cursor.execute(query, where_params)
            rows = cursor.fetchall()
            execution_time_ms = (time.time() - start_time) * 1000
        
        # 6. Formatting
        data = [[str(val) if val is not None else "" for val in row] for row in rows]
        
        response_column_types = []
        for col_name in headers:
            if col_name in column_types_map:
                ct = column_types_map[col_name]
                response_column_types.append({
                    "name": ct.name, "type": ct.type, 
                    "notnull": ct.notnull, "pk": ct.pk, "dflt_value": ct.dflt_value
                })
            else:
                response_column_types.append({
                    "name": col_name, "type": "REAL", "notnull": False, 
                    "pk": False, "dflt_value": None
                })

        result = {
            "headers": headers,
            "data": data,
            "total_count": total_count,
            "column_types": response_column_types,
            "query_metadata": {
                "query_type": "aggregate" if aggregations else "select",
                "sql": query,
                "filters_applied": len(filters) if filters else 0,
                "has_search": bool(search_value)
            },
            "cached": False,
            "execution_time_ms": execution_time_ms,
            "limit": limit,
            "offset": offset,
            "table_name": table_name,
            "database_path": str(db_path)
        }
        
        if use_cache:
            self.cache.set(cache_key, result, table_mtime)
            
        return result

    def _build_cache_key(self, db_path, table_name, limit, offset, columns, sort_column,
                         sort_order, search_value, filters, aggregations, group_by) -> str:
        """Build precise cache key."""
        params = {
            "db": str(db_path), "tbl": table_name, "l": limit, "o": offset,
            "cols": columns, "sc": sort_column, "so": sort_order, "q": search_value,
            "f": [(f.column, f.operator, f.value, f.value2) for f in (filters or [])],
            "a": [(a.column, a.function, a.alias) for a in (aggregations or [])],
            "gb": group_by
        }
        return hashlib.md5(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()

_query_service: QueryService | None = None
_service_lock = threading.Lock()

def get_query_service() -> QueryService:
    """Get the global query service instance."""
    global _query_service
    if _query_service is None:
        with _service_lock:
            if _query_service is None:
                _query_service = QueryService()
    return _query_service

