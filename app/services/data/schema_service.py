"""
Schema Information Service.

Provides table and column schema information including:
- Column names, types, constraints (NOT NULL, PRIMARY KEY)
- Default values
- Indexes
"""

from __future__ import annotations

import sqlite3
import logging
import threading
from pathlib import Path
from typing import Any

from app.services.data.connection_pool import get_connection_pool
from app.services.data.query_service import QueryService
from app.utils.sqlite import list_tables

logger = logging.getLogger(__name__)


class SchemaService:
    """
    Service for retrieving database schema information.
    """
    
    def __init__(self) -> None:
        """Initialize the schema service."""
        self.pool = get_connection_pool()
        self.query_service = QueryService()
    
    def get_table_schema(
        self,
        db_path: Path,
        table_name: str
    ) -> dict[str, Any]:
        """
        Get schema information for a single table.
        
        Args:
            db_path: Path to SQLite database
            table_name: Name of the table
            
        Returns:
            Dictionary with table schema information
        """
        # Get column schema using query service (which handles its own connection)
        column_types = self.query_service.get_column_types(db_path, table_name)
        
        columns = []
        for col_type in column_types:
            columns.append({
                "name": col_type.name,
                "type": col_type.type,
                "notnull": col_type.notnull,
                "pk": col_type.pk,
                "dflt_value": col_type.dflt_value
            })
        
        # Get indexes using direct connection
        indexes = []
        try:
            with self.pool.connection(db_path) as conn:
                cursor = conn.cursor()
                indexes = self._get_table_indexes(cursor, table_name)
        except sqlite3.Error as e:
            logger.warning(f"Error getting indexes for {table_name}: {e}")
            # We continue with empty indexes rather than failing the whole schema request
        
        return {
            "table": table_name,
            "columns": columns,
            "indexes": indexes
        }
    
    def get_all_tables_schema(
        self,
        db_path: Path
    ) -> dict[str, Any]:
        """
        Get schema information for all tables in the database.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            Dictionary mapping table names to schema information
        """

        table_names = list_tables(db_path)
        schemas = {}
        
        for table_name in table_names:
            try:
                schemas[table_name] = self.get_table_schema(db_path, table_name)
            except Exception as e:
                logger.warning(f"Error getting schema for {table_name}: {e}")
        
        return schemas
    
    def _get_table_indexes(
        self,
        cursor: sqlite3.Cursor,
        table_name: str
    ) -> list[dict[str, str]]:
        """
        Get all indexes for a table.
        
        Args:
            cursor: Database cursor
            table_name: Name of the table
            
        Returns:
            List of index information dictionaries
        """
        indexes = []
        
        try:
            # Get indexes for this table
            cursor.execute("""
                SELECT name, sql
                FROM sqlite_master
                WHERE type='index'
                AND tbl_name=?
                AND name NOT LIKE 'sqlite_%'
            """, (table_name,))
            
            for row in cursor.fetchall():
                indexes.append({
                    "name": row[0],
                    "sql": row[1] or ""
                })
        
        except sqlite3.Error as e:
            logger.warning(f"Error getting indexes for {table_name}: {e}")
        
        return indexes


# Global schema service instance
_schema_service: SchemaService | None = None
_schema_service_lock = threading.Lock()


def get_schema_service() -> SchemaService:
    """Get the global schema service instance."""
    global _schema_service
    
    if _schema_service is None:
        with _schema_service_lock:
            if _schema_service is None:
                _schema_service = SchemaService()
    
    return _schema_service
