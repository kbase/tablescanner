"""
Low-level SQLite utilities.
"""
from __future__ import annotations
import sqlite3
import logging
import time
from pathlib import Path

# Configure module logger
logger = logging.getLogger(__name__)


def _validate_table_name(cursor, table_name: str) -> None:
    """
    Validate that table_name corresponds to an existing table in the database.
    """
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if not cursor.fetchone():
        raise ValueError(f"Invalid table name: {table_name}")


def list_tables(db_path: Path) -> list[str]:
    """
    List all user tables in a SQLite database.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)

        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables

    except sqlite3.Error as e:
        logger.error("Error listing tables from %s: %s", db_path, e)
        raise


def _quote_identifier(name: str) -> str:
    """Quote an identifier (table or column name) for SQLite."""
    return '"' + name.replace('"', '""') + '"'


def get_table_columns(db_path: Path, table_name: str) -> list[str]:
    """
    Get column names for a specific table.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Validate table existence and get validated table name
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Invalid table name: {table_name}")
        
        validated_table_name = result[0]
        # PRAGMA table_info accepts string literals or identifiers, but let's be consistent
        quoted_table_name = _quote_identifier(validated_table_name)
        cursor.execute("PRAGMA table_info(" + quoted_table_name + ")")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        return columns

    except sqlite3.Error as e:
        logger.error("Error getting columns for %s: %s", table_name, e)
        raise


def get_table_row_count(db_path: Path, table_name: str) -> int:
    """
    Get the total row count for a table.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Validate table existence and get validated table name
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Invalid table name: {table_name}")
        
        validated_table_name = result[0]
        quoted_table_name = _quote_identifier(validated_table_name)
        cursor.execute("SELECT COUNT(*) FROM " + quoted_table_name)
        count = cursor.fetchone()[0]
        conn.close()

        return count

    except sqlite3.Error as e:
        logger.error("Error counting rows in %s: %s", table_name, e)
        raise


def validate_table_exists(db_path: Path, table_name: str) -> bool:
    """
    Check if a table exists in the database.
    """
    try:
        tables = list_tables(db_path)
        return table_name in tables
    except (sqlite3.Error, OSError, ValueError) as e:
        # Any database-related error means we can't validate the table
        logger.debug("Failed to validate table %s: %s", table_name, e)
        return False


def get_table_statistics(db_path: Path, table_name: str) -> dict:
    """
    Calculate statistics for all columns in a table.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        # Use row factory to access columns by name if needed, though we use indices here
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Validate table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            raise ValueError(f"Invalid table name: {table_name}")

        validated_table = table_name

        # Get total row count
        quoted_table_name = _quote_identifier(validated_table)
        cursor.execute("SELECT COUNT(*) FROM " + quoted_table_name)
        row_count = cursor.fetchone()[0]

        # Get columns and types
        cursor.execute("PRAGMA table_info(" + quoted_table_name + ")")
        columns_info = cursor.fetchall()
        
        stats_columns = []

        for col in columns_info:
            col_name = col['name']
            col_type = col['type']
            
            # Use proper identifier quoting
            quoted_col_name = _quote_identifier(col_name)
            
            # Base stats query
            # We use SUM(CASE WHEN ... IS NULL) instead of COUNT(col) logic sometimes to be explicit
            # but COUNT(col) counts non-nulls. So Nulls = Total - COUNT(col).
            cursor.execute("""
                SELECT 
                    COUNT(""" + quoted_col_name + """) as non_null_count,
                    COUNT(DISTINCT """ + quoted_col_name + """) as distinct_count
                FROM """ + quoted_table_name)
            basic_stats = cursor.fetchone()
            non_null_count = basic_stats['non_null_count']
            null_count = row_count - non_null_count
            distinct_count = basic_stats['distinct_count']

            col_stats = {
                "column": col_name,
                "type": col_type,
                "non_null_count": non_null_count,
                "null_count": null_count,
                "distinct_count": distinct_count,
                "sample_values": []
            }

            # Extended stats for numeric types
            # Heuristic: simplistic check for INT, REAL, FLO, DOUB, NUM
            is_numeric = any(t in col_type.upper() for t in ['INT', 'REAL', 'FLO', 'DOUB', 'NUM', 'DEC'])
            
            if is_numeric and non_null_count > 0:
                try:
                    cursor.execute("""
                        SELECT 
                            MIN(""" + quoted_col_name + """), 
                            MAX(""" + quoted_col_name + """), 
                            AVG(""" + quoted_col_name + """)
                        FROM """ + quoted_table_name + """
                        WHERE """ + quoted_col_name + """ IS NOT NULL
                    """)
                    num_stats = cursor.fetchone()
                    if num_stats[0] is not None:
                        col_stats["min"] = num_stats[0]
                        col_stats["max"] = num_stats[1]
                        col_stats["mean"] = num_stats[2]
                except (sqlite3.Error, ValueError, TypeError) as e:
                    # Ignore errors in numeric aggregate (e.g. if column declared int but has strings)
                    logger.debug("Numeric stats failed for column %s: %s", col_name, e)
            elif non_null_count > 0:
                # For non-numeric, just get Min/Max
                try:
                    cursor.execute("""
                        SELECT MIN(""" + quoted_col_name + """), MAX(""" + quoted_col_name + """)
                        FROM """ + quoted_table_name + """
                        WHERE """ + quoted_col_name + """ IS NOT NULL
                    """)
                    str_stats = cursor.fetchone()
                    if str_stats[0] is not None:
                        col_stats["min"] = str_stats[0]
                        col_stats["max"] = str_stats[1]
                except (sqlite3.Error, ValueError, TypeError) as e:
                    # Ignore errors in string aggregate
                    logger.debug("String stats failed for column %s: %s", col_name, e)

            # Get sample values (first 5 non-null distinct preferred, or just first 5)
            try:
                cursor.execute("""
                    SELECT DISTINCT """ + quoted_col_name + """
                    FROM """ + quoted_table_name + """
                    WHERE """ + quoted_col_name + """ IS NOT NULL
                    LIMIT 5
                """)
                samples = [row[0] for row in cursor.fetchall()]
                col_stats["sample_values"] = samples
            except (sqlite3.Error, ValueError, TypeError) as e:
                # Failed to get sample values
                logger.debug("Sample values failed for column %s: %s", col_name, e)
                col_stats["sample_values"] = []

            stats_columns.append(col_stats)

        conn.close()
        
        return {
            "table": table_name,
            "row_count": row_count,
            "columns": stats_columns,
            "last_updated": int(time.time() * 1000)
        }

    except sqlite3.Error as e:
        logger.error("Error calculating stats for %s: %s", table_name, e)
        raise
