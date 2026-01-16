"""
Low-level SQLite utilities.
"""
from __future__ import annotations
import sqlite3
import logging
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
        logger.error(f"Error listing tables from {db_path}: {e}")
        raise


def get_table_columns(db_path: Path, table_name: str) -> list[str]:
    """
    Get column names for a specific table.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        _validate_table_name(cursor, table_name)

        cursor.execute(f"PRAGMA table_info(\"{table_name}\")")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        return columns

    except sqlite3.Error as e:
        logger.error(f"Error getting columns for {table_name}: {e}")
        raise


def get_table_row_count(db_path: Path, table_name: str) -> int:
    """
    Get the total row count for a table.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        _validate_table_name(cursor, table_name)

        cursor.execute(f"SELECT COUNT(*) FROM \"{table_name}\"")
        count = cursor.fetchone()[0]
        conn.close()

        return count

    except sqlite3.Error as e:
        logger.error(f"Error counting rows in {table_name}: {e}")
        raise


def validate_table_exists(db_path: Path, table_name: str) -> bool:
    """
    Check if a table exists in the database.
    """
    try:
        tables = list_tables(db_path)
        return table_name in tables
    except Exception:
        return False
