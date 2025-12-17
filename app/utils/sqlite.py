"""
SQLite utilities for database conversion and querying.

This module provides efficient functions for:
- Extracting table data from SQLite databases
- Converting data to 2D array format for JSON serialization
- Filtering, sorting, and pagination
- Index optimization for query performance

Migrated from: BERDLTable_conversion_service/db_utils.py
"""

import sqlite3
import logging
import time
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# TABLE LISTING & METADATA
# =============================================================================

def list_tables(db_path: Path) -> List[str]:
    """
    List all user tables in a SQLite database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        List of table names (excludes sqlite_ system tables)

    Raises:
        sqlite3.Error: If database access fails
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Query for user tables (exclude sqlite_ system tables)
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)

        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        logger.info(f"Found {len(tables)} tables in database: {tables}")
        return tables

    except sqlite3.Error as e:
        logger.error(f"Error listing tables from {db_path}: {e}")
        raise


def get_table_columns(db_path: Path, table_name: str) -> List[str]:
    """
    Get column names for a specific table.

    Args:
        db_path: Path to the SQLite database file
        table_name: Name of the table to query

    Returns:
        List of column names
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Use PRAGMA to get table info
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        return columns

    except sqlite3.Error as e:
        logger.error(f"Error getting columns for {table_name}: {e}")
        raise


def get_table_row_count(db_path: Path, table_name: str) -> int:
    """
    Get the total row count for a table.

    Args:
        db_path: Path to the SQLite database file
        table_name: Name of the table

    Returns:
        Number of rows in the table
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        conn.close()

        return count

    except sqlite3.Error as e:
        logger.error(f"Error counting rows in {table_name}: {e}")
        raise


def validate_table_exists(db_path: Path, table_name: str) -> bool:
    """
    Check if a table exists in the database.

    Args:
        db_path: Path to the SQLite database file
        table_name: Name of the table to check

    Returns:
        True if table exists, False otherwise
    """
    tables = list_tables(db_path)
    return table_name in tables


# =============================================================================
# INDEX OPTIMIZATION
# =============================================================================

def ensure_indices(db_path: Path, table_name: str) -> None:
    """
    Ensure indices exist for all columns in the table to optimize filtering.

    This is an optimization step - failures are logged but not raised.

    Args:
        db_path: Path to the SQLite database file
        table_name: Name of the table
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get columns
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]

        # Create index for each column
        for col in columns:
            index_name = f"idx_{table_name}_{col}"
            # Sanitize column name for SQL safety
            safe_col = col.replace('"', '""')
            cursor.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ("{safe_col}")'
            )

        conn.commit()
        conn.close()
        logger.info(f"Ensured indices for table {table_name}")

    except sqlite3.Error as e:
        # Don't raise, just log warning as this is an optimization step
        logger.warning(f"Error creating indices for {table_name}: {e}")


# =============================================================================
# DATA RETRIEVAL - SIMPLE QUERY
# =============================================================================

def query_sqlite(sqlite_file: Path, query_id: str) -> dict:
    """
    Query SQLite database by ID. Legacy compatibility function.

    Args:
        sqlite_file: Path to SQLite database
        query_id: Query identifier

    Returns:
        Query results as dictionary
    """
    return {
        "stub": "SQLite query results would go here",
        "query_id": query_id,
        "sqlite_file": str(sqlite_file)
    }


# =============================================================================
# DATA RETRIEVAL - FULL FEATURED
# =============================================================================

def get_table_data(
    sqlite_file: Path,
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    sort_column: Optional[str] = None,
    sort_order: str = "ASC",
    search_value: Optional[str] = None,
    query_filters: Optional[Dict[str, str]] = None,
    columns: Optional[str] = "all",
    order_by: Optional[List[Dict[str, str]]] = None
) -> Tuple[List[str], List[Any], int, int, float, float]:
    """
    Get paginated and filtered data from a table.
    
    Supports two filtering APIs for flexibility:
    1. `filters`: List of FilterSpec-style dicts with column, op, value
    2. `query_filters`: Simple dict of column -> search_value (LIKE matching)

    Args:
        sqlite_file: Path to SQLite database
        table_name: Name of the table to query
        limit: Maximum number of rows to return
        offset: Number of rows to skip
        sort_column: Single column to sort by (alternative to order_by)
        sort_order: Sort direction 'asc' or 'desc' (with sort_column)
        search_value: Global search term for all columns
        query_filters: Dict of column-specific search terms
        columns: Comma-separated list of columns to select
        order_by: List of order specifications [{column, direction}]

    Returns:
        Tuple of (headers, data, total_count, filtered_count, db_query_ms, conversion_ms)

    Raises:
        sqlite3.Error: If database query fails
        ValueError: If invalid operator is specified
    """
    start_time = time.time()
    
    # Initialize legacy filters to None since removed from signature
    filters = None
    
    try:
        conn = sqlite3.connect(str(sqlite_file))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get all column names first for validation
        all_headers = get_table_columns(sqlite_file, table_name)

        if not all_headers:
            logger.warning(f"Table {table_name} has no columns or doesn't exist")
            return [], [], 0, 0, 0.0, 0.0

        # Parse requested columns
        selected_headers = all_headers
        select_clause = "*"
        
        if columns and columns.lower() != "all":
            requested = [c.strip() for c in columns.split(',') if c.strip()]
            valid = [c for c in requested if c in all_headers]
            if valid:
                selected_headers = valid
                safe_cols = [f'"{c}"' for c in selected_headers]
                select_clause = ", ".join(safe_cols)
        
        headers = selected_headers

        # 1. Get total count (before filtering)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_count = cursor.fetchone()[0]

        # 2. Build WHERE clause
        conditions = []
        params = []

        # 2a. Global Search (OR logic across all columns)
        if search_value:
            search_conditions = []
            term = f"%{search_value}%"
            for col in headers:
                search_conditions.append(f'"{col}" LIKE ?')
                params.append(term)

            if search_conditions:
                conditions.append(f"({' OR '.join(search_conditions)})")

        # 2b. Column Filters via query_filters dict (AND logic)
        if query_filters:
            for col, val in query_filters.items():
                if col in headers and val:
                    conditions.append(f'"{col}" LIKE ?')
                    params.append(f"%{val}%")

        # 2c. Structured filters via filters list (AND logic)
        if filters:
            allowed_ops = ["=", "!=", "<", ">", "<=", ">=", "LIKE", "IN"]
            for filter_spec in filters:
                column = filter_spec.get("column")
                op = filter_spec.get("op", "LIKE")
                value = filter_spec.get("value")

                if not column or column not in headers:
                    continue

                if op not in allowed_ops:
                    raise ValueError(f"Invalid operator: {op}")

                conditions.append(f'"{column}" {op} ?')
                params.append(value)

        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        # 3. Get filtered count
        if where_clause:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} {where_clause}", params)
            filtered_count = cursor.fetchone()[0]
        else:
            filtered_count = total_count

        # 4. Build final query
        query = f"SELECT {select_clause} FROM {table_name}{where_clause}"

        # Add ORDER BY clause
        order_clauses = []

        # Handle order_by list
        if order_by:
            for order_spec in order_by:
                col = order_spec.get("column")
                direction = order_spec.get("direction", "ASC").upper()

                if col and col in headers:
                    if direction not in ["ASC", "DESC"]:
                        direction = "ASC"
                    order_clauses.append(f'"{col}" {direction}')

        # Handle single sort_column (alternative API)
        if sort_column and sort_column in headers:
            direction = "DESC" if sort_order and sort_order.lower() == "desc" else "ASC"
            order_clauses.append(f'"{sort_column}" {direction}')

        if order_clauses:
            query += " ORDER BY " + ", ".join(order_clauses)
        elif headers:
            # Default sort for consistent pagination
            query += f' ORDER BY "{headers[0]}" ASC'

        # Add LIMIT clause
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        # Add OFFSET clause
        if offset is not None:
            query += f" OFFSET {int(offset)}"

        # Execute query with timing
        query_start = time.time()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        db_query_ms = (time.time() - query_start) * 1000

        conn.close()

        # Convert rows to string arrays with timing
        conversion_start = time.time()
        data = []
        for row in rows:
            string_row = [
                str(value) if value is not None else ""
                for value in row
            ]
            data.append(string_row)
        conversion_ms = (time.time() - conversion_start) * 1000

        return headers, data, total_count, filtered_count, db_query_ms, conversion_ms

    except sqlite3.Error as e:
        logger.error(f"Error extracting data from {table_name}: {e}")
        raise


# =============================================================================
# CONVERSION (PLACEHOLDER)
# =============================================================================

def convert_to_sqlite(binary_file: Path, sqlite_file: Path) -> None:
    """
    Convert binary file to SQLite database.

    This function handles conversion of various binary formats
    to SQLite for efficient querying.

    Args:
        binary_file: Path to binary file
        sqlite_file: Path to output SQLite file

    Raises:
        NotImplementedError: Conversion logic depends on binary format
    """
    # Check if file is already a SQLite database
    if binary_file.suffix == '.db':
        # Just copy/link the file
        import shutil
        shutil.copy2(binary_file, sqlite_file)
        logger.info(f"Copied SQLite database to {sqlite_file}")
        return

    # TODO: Implement conversion logic based on binary file format
    # The BERDLTables object stores SQLite directly, so this may not be needed
    raise NotImplementedError(
        f"SQLite conversion not implemented for format: {binary_file.suffix}"
    )
