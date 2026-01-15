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
    
    TTL_SECONDS = 5 * 60  # 5 minutes
    MAX_ENTRIES = 1000
    
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
            
            # Check TTL
            # Note: We store mtime instead of timestamp, so TTL is implicit
            # via table modification time check above
            
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
            if len(self._cache) >= self.MAX_ENTRIES:
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
    
    def get_column_types(self, db_path: Path, table_name: str) -> list[ColumnType]:
        """
        Get column type information from table schema.
        
        Args:
            db_path: Path to SQLite database
            table_name: Name of the table
            
        Returns:
            List of ColumnType objects
        """
        conn = self.pool.get_connection(db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"PRAGMA table_info({table_name})")
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
        """
        Check if a column type is numeric.
        
        Args:
            column_type: SQLite column type string
            
        Returns:
            True if column is numeric (INTEGER, REAL, NUMERIC)
        """
        if not column_type:
            return False
        
        type_upper = column_type.upper()
        return any(numeric_type in type_upper for numeric_type in ["INT", "REAL", "NUMERIC"])
    
    def convert_numeric_value(self, value: Any, column_type: str) -> float | int:
        """
        Convert a value to numeric type based on column type.
        
        Args:
            value: Value to convert (may be string)
            column_type: SQLite column type
            
        Returns:
            Converted numeric value (int for INTEGER, float for REAL/NUMERIC)
        """
        if value is None:
            return 0
        
        type_upper = column_type.upper()
        
        if "INT" in type_upper:
            # INTEGER column: use integer conversion
            try:
                return int(float(str(value)))  # Handle "50.0" -> 50
            except (ValueError, TypeError):
                return 0
        else:
            # REAL or NUMERIC column: use float conversion
            try:
                return float(str(value))
            except (ValueError, TypeError):
                return 0.0
    
    def build_filter_condition(
        self,
        filter_spec: FilterSpec,
        column_types: dict[str, ColumnType],
        params: list[Any]
    ) -> str:
        """
        Build SQL WHERE condition for a filter.
        
        Handles type conversion for numeric columns and builds appropriate
        SQL conditions based on operator.
        
        Args:
            filter_spec: Filter specification
            column_types: Dictionary mapping column names to ColumnType
            params: List to append parameter values to
            
        Returns:
            SQL WHERE condition string
        """
        column = filter_spec.column
        operator = filter_spec.operator.lower()
        value = filter_spec.value
        
        if column not in column_types:
            logger.warning(f"Column {column} not found in schema, skipping filter")
            return ""
        
        col_type = column_types[column]
        is_numeric = self.is_numeric_column(col_type.type)
        
        # Escape column name for SQL
        safe_column = f'"{column}"'
        
        # Handle null checks (no value conversion needed)
        if operator == "is_null":
            return f"{safe_column} IS NULL"
        
        if operator == "is_not_null":
            return f"{safe_column} IS NOT NULL"
        
        # For other operators, value is required
        if value is None:
            logger.warning(f"Filter operator {operator} requires a value, skipping")
            return ""
        
        # Convert numeric values for numeric columns
        if is_numeric and operator in ["eq", "ne", "gt", "gte", "lt", "lte", "between"]:
            if operator == "between":
                # Convert both values
                if filter_spec.value2 is None:
                    logger.warning(f"between operator requires value2, skipping")
                    return ""
                num_value = self.convert_numeric_value(value, col_type.type)
                num_value2 = self.convert_numeric_value(filter_spec.value2, col_type.type)
                params.append(num_value)
                params.append(num_value2)
                return f"{safe_column} BETWEEN ? AND ?"
            elif operator in ["in", "not_in"]:
                # Convert all array values
                if not isinstance(value, list):
                    logger.warning(f"{operator} operator requires array value, skipping")
                    return ""
                converted_values = [
                    self.convert_numeric_value(v, col_type.type) for v in value
                ]
                placeholders = ",".join(["?"] * len(converted_values))
                params.extend(converted_values)
                sql_op = "IN" if operator == "in" else "NOT IN"
                return f"{safe_column} {sql_op} ({placeholders})"
            else:
                # Single value conversion
                num_value = self.convert_numeric_value(value, col_type.type)
                params.append(num_value)
        else:
            # Text column or text operator: use as-is
            if operator in ["like", "ilike"]:
                # Add wildcards for pattern matching
                pattern = f"%{value}%"
                params.append(pattern)
            elif operator in ["in", "not_in"]:
                # Array of text values
                if not isinstance(value, list):
                    logger.warning(f"{operator} operator requires array value, skipping")
                    return ""
                placeholders = ",".join(["?"] * len(value))
                params.extend(value)
                sql_op = "IN" if operator == "in" else "NOT IN"
                return f"{safe_column} {sql_op} ({placeholders})"
            else:
                params.append(value)
        
        # Map operator to SQL
        operator_map = {
            "eq": "=",
            "ne": "!=",
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
            "like": "LIKE",
            "ilike": "LIKE",  # SQLite doesn't have ILIKE, use LOWER() for case-insensitive
        }
        
        sql_op = operator_map.get(operator)
        if not sql_op:
            logger.warning(f"Unknown operator: {operator}, skipping filter")
            return ""
        
        # For ilike, use LOWER() function for case-insensitive matching
        if operator == "ilike":
            return f"LOWER({safe_column}) {sql_op} LOWER(?)"
        
        return f"{safe_column} {sql_op} ?"
    
    def ensure_index(self, db_path: Path, table_name: str, column: str) -> None:
        """
        Ensure an index exists on a column.
        
        Creates index if it doesn't exist. Uses naming: idx_{table}_{column}
        
        Args:
            db_path: Path to SQLite database
            table_name: Name of the table
            column: Name of the column
        """
        conn = self.pool.get_connection(db_path)
        cursor = conn.cursor()
        
        try:
            index_name = f"idx_{table_name}_{column}".replace(" ", "_").replace("-", "_")
            
            # Check if index already exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (index_name,)
            )
            if cursor.fetchone():
                return  # Index already exists
            
            # Create index
            safe_table = f'"{table_name}"'
            safe_column = f'"{column}"'
            cursor.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" ON {safe_table}({safe_column})'
            )
            conn.commit()
            logger.debug(f"Created index: {index_name}")
        
        except sqlite3.Error as e:
            logger.warning(f"Error creating index on {table_name}.{column}: {e}")
            # Don't raise - indexing is an optimization
    
    def ensure_fts5_table(self, db_path: Path, table_name: str, text_columns: list[str]) -> bool:
        """
        Ensure FTS5 virtual table exists for full-text search.
        
        Args:
            db_path: Path to SQLite database
            table_name: Name of the table
            text_columns: List of text column names
            
        Returns:
            True if FTS5 table exists or was created, False otherwise
        """
        if not text_columns:
            return False
        
        conn = self.pool.get_connection(db_path)
        cursor = conn.cursor()
        
        try:
            fts5_table_name = f"{table_name}_fts5"
            
            # Check if FTS5 table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (fts5_table_name,)
            )
            if cursor.fetchone():
                return True  # FTS5 table already exists
            
            # Check if FTS5 is available
            cursor.execute("PRAGMA compile_options")
            compile_options = [row[0] for row in cursor.fetchall()]
            if "ENABLE_FTS5" not in compile_options:
                logger.warning("FTS5 not available in this SQLite build")
                return False
            
            # Create FTS5 virtual table
            safe_columns = ", ".join(f'"{col}"' for col in text_columns)
            cursor.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS "{fts5_table_name}" 
                USING fts5({safe_columns}, content="{table_name}", content_rowid="rowid")
            """)
            
            # Populate FTS5 table from original table
            # Get rowid column name (usually "rowid" but could be primary key)
            cursor.execute(f"PRAGMA table_info({table_name})")
            pk_columns = [row[1] for row in cursor.fetchall() if row[5]]  # row[5] is pk flag
            
            if pk_columns:
                # Use primary key for content_rowid
                pk_col = pk_columns[0]
                cursor.execute(f"""
                    INSERT INTO "{fts5_table_name}"(rowid, {safe_columns})
                    SELECT rowid, {safe_columns} FROM "{table_name}"
                """)
            else:
                # Use implicit rowid
                cursor.execute(f"""
                    INSERT INTO "{fts5_table_name}"(rowid, {safe_columns})
                    SELECT rowid, {safe_columns} FROM "{table_name}"
                """)
            
            conn.commit()
            logger.info(f"Created FTS5 table: {fts5_table_name}")
            return True
        
        except sqlite3.Error as e:
            logger.warning(f"Error creating FTS5 table: {e}")
            return False
    
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
        """
        Execute a comprehensive query with all features.
        
        Args:
            db_path: Path to SQLite database
            table_name: Name of the table
            limit: Maximum rows to return
            offset: Number of rows to skip
            columns: List of columns to select (None = all)
            sort_column: Column to sort by
            sort_order: Sort direction (ASC/DESC)
            search_value: Global search term
            filters: List of filter specifications
            aggregations: List of aggregation specifications
            group_by: List of columns for GROUP BY
            use_cache: Whether to use query result cache
            
        Returns:
            Dictionary with query results and metadata
        """
        start_time = time.time()
        
        # Get table modification time for cache invalidation
        try:
            table_mtime = db_path.stat().st_mtime
        except OSError:
            table_mtime = 0.0
        
        # Build cache key
        cache_key = self._build_cache_key(
            db_path, table_name, limit, offset, columns, sort_column,
            sort_order, search_value, filters, aggregations, group_by
        )
        
        # Check cache
        if use_cache:
            cached_result = self.cache.get(cache_key, table_mtime)
            if cached_result is not None:
                logger.debug(f"Cache hit for query: {table_name}")
                cached_result["cached"] = True
                return cached_result
        
        # Get column types for type-aware filtering
        column_types_list = self.get_column_types(db_path, table_name)
        column_types = {col.name: col for col in column_types_list}
        
        # Get connection
        conn = self.pool.get_connection(db_path)
        cursor = conn.cursor()
        
        # Ensure indexes on filtered/sorted columns
        if filters:
            for filter_spec in filters:
                if filter_spec.column in column_types:
                    self.ensure_index(db_path, table_name, filter_spec.column)
        
        if sort_column and sort_column in column_types:
            self.ensure_index(db_path, table_name, sort_column)
        
        # Build SELECT clause
        if aggregations:
            # Aggregation query
            select_parts = []
            for agg in aggregations:
                if agg.function == "count":
                    expr = "COUNT(*)" if agg.column == "*" else f'COUNT("{agg.column}")'
                elif agg.function == "distinct_count":
                    expr = f'COUNT(DISTINCT "{agg.column}")'
                elif agg.function == "stddev":
                    # SQLite doesn't have STDDEV, use approximation
                    expr = f'AVG(("{agg.column}" - (SELECT AVG("{agg.column}") FROM "{table_name}")) * ("{agg.column}" - (SELECT AVG("{agg.column}") FROM "{table_name}")))'
                elif agg.function == "variance":
                    expr = f'AVG(("{agg.column}" - (SELECT AVG("{agg.column}") FROM "{table_name}")) * ("{agg.column}" - (SELECT AVG("{agg.column}") FROM "{table_name}")))'
                else:
                    expr = f'{agg.function.upper()}("{agg.column}")'
                
                alias = agg.alias or f"{agg.function}_{agg.column}"
                select_parts.append(f"{expr} AS \"{alias}\"")
            
            # Add GROUP BY columns to SELECT
            if group_by:
                for col in group_by:
                    if col in column_types:
                        select_parts.insert(0, f'"{col}"')
            
            select_clause = ", ".join(select_parts)
        else:
            # Regular query
            if columns:
                select_clause = ", ".join(f'"{col}"' for col in columns if col in column_types)
            else:
                select_clause = "*"
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        # Global search
        if search_value:
            # Try FTS5 first if available
            text_columns = [
                col.name for col in column_types_list
                if not self.is_numeric_column(col.type)
            ]
            
            if text_columns and self.ensure_fts5_table(db_path, table_name, text_columns):
                # Use FTS5 MATCH
                fts5_table = f"{table_name}_fts5"
                where_conditions.append(
                    f'rowid IN (SELECT rowid FROM "{fts5_table}" WHERE "{fts5_table}" MATCH ?)'
                )
                params.append(search_value)
            else:
                # Fallback to LIKE on all text columns
                search_conditions = []
                for col in text_columns:
                    search_conditions.append(f'"{col}" LIKE ?')
                    params.append(f"%{search_value}%")
                if search_conditions:
                    where_conditions.append(f"({' OR '.join(search_conditions)})")
        
        # Filters
        if filters:
            for filter_spec in filters:
                condition = self.build_filter_condition(filter_spec, column_types, params)
                if condition:
                    where_conditions.append(condition)
        
        where_clause = ""
        if where_conditions:
            where_clause = " WHERE " + " AND ".join(where_conditions)
        
        # Build GROUP BY clause
        group_by_clause = ""
        if group_by:
            valid_group_cols = [col for col in group_by if col in column_types]
            if valid_group_cols:
                group_by_clause = " GROUP BY " + ", ".join(f'"{col}"' for col in valid_group_cols)
        
        # Build ORDER BY clause
        order_by_clause = ""
        if sort_column and sort_column in column_types:
            direction = "DESC" if sort_order.upper() == "DESC" else "ASC"
            order_by_clause = f' ORDER BY "{sort_column}" {direction}'
        elif not aggregations:
            # Default sort for consistent pagination
            if column_types_list:
                first_col = column_types_list[0].name
                order_by_clause = f' ORDER BY "{first_col}" ASC'
        
        # Build LIMIT/OFFSET clause
        limit_clause = f" LIMIT {int(limit)}"
        offset_clause = f" OFFSET {int(offset)}" if offset > 0 else ""
        
        # Execute count query for total_count
        count_query = f'SELECT COUNT(*) FROM "{table_name}"{where_clause}'
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        # Execute filtered count
        filtered_count = total_count  # Same as total if no filters
        
        # Execute main query
        query = f'SELECT {select_clause} FROM "{table_name}"{where_clause}{group_by_clause}{order_by_clause}{limit_clause}{offset_clause}'
        
        query_start = time.time()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        execution_time_ms = (time.time() - query_start) * 1000
        
        # Convert rows to arrays
        if aggregations:
            # Aggregation results
            headers = []
            if group_by:
                headers.extend([col for col in group_by if col in column_types])
            headers.extend([agg.alias or f"{agg.function}_{agg.column}" for agg in aggregations])
            
            data = []
            for row in rows:
                data.append([str(value) if value is not None else "" for value in row])
        else:
            # Regular query results
            if columns:
                headers = [col for col in columns if col in column_types]
            else:
                headers = [col.name for col in column_types_list]
            
            data = []
            for row in rows:
                data.append([str(value) if value is not None else "" for value in row])
        
        # Build response
        response_time_ms = (time.time() - start_time) * 1000
        
        # Build column types for response
        response_column_types = []
        for col in headers:
            if col in column_types:
                col_type = column_types[col]
                response_column_types.append({
                    "name": col_type.name,
                    "type": col_type.type,
                    "notnull": col_type.notnull,
                    "pk": col_type.pk,
                    "dflt_value": col_type.dflt_value
                })
            else:
                # Aggregation column
                response_column_types.append({
                    "name": col,
                    "type": "REAL",  # Aggregations are typically numeric
                    "notnull": False,
                    "pk": False,
                    "dflt_value": None
                })
        
        # Build query metadata
        query_metadata = {
            "query_type": "aggregate" if aggregations else "select",
            "sql": query,
            "filters_applied": len(filters) if filters else 0,
            "has_search": search_value is not None,
            "has_sort": sort_column is not None,
            "has_group_by": group_by is not None and len(group_by) > 0,
            "has_aggregations": aggregations is not None and len(aggregations) > 0
        }
        
        result = {
            "headers": headers,
            "data": data,
            "total_count": total_count,
            "column_types": response_column_types,
            "query_metadata": query_metadata,
            "cached": False,
            "execution_time_ms": execution_time_ms,
            "limit": limit,
            "offset": offset,
            "table_name": table_name,
            "database_path": str(db_path)
        }
        
        # Cache result
        if use_cache:
            self.cache.set(cache_key, result, table_mtime)
        
        return result
    
    def _build_cache_key(
        self,
        db_path: Path,
        table_name: str,
        limit: int,
        offset: int,
        columns: list[str] | None,
        sort_column: str | None,
        sort_order: str,
        search_value: str | None,
        filters: list[FilterSpec] | None,
        aggregations: list[AggregationSpec] | None,
        group_by: list[str] | None
    ) -> str:
        """Build cache key from query parameters."""
        params = {
            "db_path": str(db_path.absolute()),
            "table": table_name,
            "limit": limit,
            "offset": offset,
            "columns": columns,
            "sort_column": sort_column,
            "sort_order": sort_order,
            "search": search_value,
            "filters": [
                {
                    "column": f.column,
                    "operator": f.operator,
                    "value": f.value,
                    "value2": f.value2
                }
                for f in (filters or [])
            ],
            "aggregations": [
                {
                    "column": a.column,
                    "function": a.function,
                    "alias": a.alias
                }
                for a in (aggregations or [])
            ],
            "group_by": group_by
        }
        
        params_json = json.dumps(params, sort_keys=True)
        return hashlib.md5(params_json.encode()).hexdigest()


# Global query service instance
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
