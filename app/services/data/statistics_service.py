"""
Column Statistics Service.

Pre-computes and caches column statistics including:
- null_count, distinct_count, min, max, mean, median, stddev
- Sample values for data exploration
"""

from __future__ import annotations

import sqlite3
import logging
import time
import threading
import math
from pathlib import Path
from typing import Any
from collections import OrderedDict
from dataclasses import dataclass

from app.services.data.connection_pool import get_connection_pool
from app.services.data.query_service import QueryService

logger = logging.getLogger(__name__)


@dataclass
class ColumnStatistics:
    """Statistics for a single column."""
    
    column: str
    type: str
    null_count: int = 0
    distinct_count: int = 0
    min: Any = None
    max: Any = None
    mean: float | None = None
    median: float | None = None
    stddev: float | None = None
    sample_values: list[Any] = None
    
    def __post_init__(self):
        """Initialize sample_values if None."""
        if self.sample_values is None:
            self.sample_values = []


class StatisticsCache:
    """
    Cache for pre-computed column statistics.
    
    Invalidates when table modification time changes.
    """
    
    def __init__(self) -> None:
        """Initialize the statistics cache."""
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._lock = threading.Lock()
    
    def get(self, cache_key: str, table_mtime: float) -> dict[str, Any] | None:
        """
        Get cached statistics.
        
        Args:
            cache_key: Cache key (db_path:table_name)
            table_mtime: Table file modification time
            
        Returns:
            Cached statistics if valid, None otherwise
        """
        with self._lock:
            if cache_key not in self._cache:
                return None
            
            stats, cached_mtime = self._cache[cache_key]
            
            # Check if table has been modified
            if cached_mtime != table_mtime:
                del self._cache[cache_key]
                return None
            
            return stats
    
    def set(self, cache_key: str, stats: dict[str, Any], table_mtime: float) -> None:
        """
        Store statistics in cache.
        
        Args:
            cache_key: Cache key (db_path:table_name)
            stats: Statistics dictionary
            table_mtime: Table file modification time
        """
        with self._lock:
            self._cache[cache_key] = (stats, table_mtime)
    
    def clear(self) -> None:
        """Clear all cached statistics."""
        with self._lock:
            self._cache.clear()


# Global statistics cache instance
_stats_cache: StatisticsCache | None = None
_stats_cache_lock = threading.Lock()


def get_statistics_cache() -> StatisticsCache:
    """Get the global statistics cache instance."""
    global _stats_cache
    
    if _stats_cache is None:
        with _stats_cache_lock:
            if _stats_cache is None:
                _stats_cache = StatisticsCache()
    
    return _stats_cache


class StatisticsService:
    """
    Service for computing and caching column statistics.
    """
    
    def __init__(self) -> None:
        """Initialize the statistics service."""
        self.pool = get_connection_pool()
        self.query_service = QueryService()
        self.cache = get_statistics_cache()
    
    def get_table_statistics(
        self,
        db_path: Path,
        table_name: str,
        use_cache: bool = True
    ) -> dict[str, Any]:
        """
        Get comprehensive statistics for all columns in a table.
        
        Args:
            db_path: Path to SQLite database
            table_name: Name of the table
            use_cache: Whether to use cached statistics
            
        Returns:
            Dictionary with table and column statistics
        """
        # Get table modification time for cache invalidation
        try:
            table_mtime = db_path.stat().st_mtime
        except OSError:
            table_mtime = 0.0
        
        cache_key = f"{db_path.absolute()}:{table_name}"
        
        # Check cache
        if use_cache:
            cached_stats = self.cache.get(cache_key, table_mtime)
            if cached_stats is not None:
                logger.debug(f"Cache hit for statistics: {table_name}")
                return cached_stats
        
        # Get connection
        conn = self.pool.get_connection(db_path)
        cursor = conn.cursor()
        
        # Get row count
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        row_count = cursor.fetchone()[0]
        
        # Get column types
        column_types = self.query_service.get_column_types(db_path, table_name)
        
        # Compute statistics for each column
        column_stats_list = []
        
        for col_type in column_types:
            stats = self._compute_column_statistics(
                cursor, table_name, col_type, row_count
            )
            column_stats_list.append(stats)
        
        # Build response
        result = {
            "table": table_name,
            "row_count": row_count,
            "columns": [
                {
                    "column": stats.column,
                    "type": stats.type,
                    "null_count": stats.null_count,
                    "distinct_count": stats.distinct_count,
                    "min": stats.min,
                    "max": stats.max,
                    "mean": stats.mean,
                    "median": stats.median,
                    "stddev": stats.stddev,
                    "sample_values": stats.sample_values
                }
                for stats in column_stats_list
            ],
            "last_updated": int(time.time() * 1000)  # Milliseconds since epoch
        }
        
        # Cache result
        if use_cache:
            self.cache.set(cache_key, result, table_mtime)
        
        return result
    
    def _compute_column_statistics(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
        col_type: Any,  # ColumnType from query_service
        row_count: int
    ) -> ColumnStatistics:
        """
        Compute statistics for a single column.
        
        Args:
            cursor: Database cursor
            table_name: Name of the table
            col_type: ColumnType object
            row_count: Total row count
            
        Returns:
            ColumnStatistics object
        """
        column = col_type.name
        sql_type = col_type.type
        is_numeric = self.query_service.is_numeric_column(sql_type)
        
        safe_column = f'"{column}"'
        
        stats = ColumnStatistics(column=column, type=sql_type)
        
        try:
            # Null count
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}" WHERE {safe_column} IS NULL')
            stats.null_count = cursor.fetchone()[0]
            
            # Distinct count
            cursor.execute(f'SELECT COUNT(DISTINCT {safe_column}) FROM "{table_name}"')
            stats.distinct_count = cursor.fetchone()[0]
            
            if is_numeric:
                # Numeric statistics
                try:
                    # Min, max, mean
                    cursor.execute(f'''
                        SELECT 
                            MIN({safe_column}),
                            MAX({safe_column}),
                            AVG({safe_column})
                        FROM "{table_name}"
                        WHERE {safe_column} IS NOT NULL
                    ''')
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        stats.min = float(row[0]) if "REAL" in sql_type.upper() else int(row[0])
                        stats.max = float(row[1]) if "REAL" in sql_type.upper() else int(row[1])
                        stats.mean = float(row[2]) if row[2] is not None else None
                    
                    # Median (approximate using ORDER BY and LIMIT)
                    if row_count > 0:
                        cursor.execute(f'''
                            SELECT {safe_column}
                            FROM "{table_name}"
                            WHERE {safe_column} IS NOT NULL
                            ORDER BY {safe_column}
                            LIMIT 1 OFFSET ?
                        ''', (row_count // 2,))
                        median_row = cursor.fetchone()
                        if median_row and median_row[0] is not None:
                            stats.median = float(median_row[0]) if "REAL" in sql_type.upper() else int(median_row[0])
                    
                    # Standard deviation (approximate)
                    if stats.mean is not None:
                        cursor.execute(f'''
                            SELECT AVG(({safe_column} - ?) * ({safe_column} - ?))
                            FROM "{table_name}"
                            WHERE {safe_column} IS NOT NULL
                        ''', (stats.mean, stats.mean))
                        variance_row = cursor.fetchone()
                        if variance_row and variance_row[0] is not None:
                            variance = float(variance_row[0])
                            stats.stddev = math.sqrt(variance) if variance >= 0 else None
                
                except sqlite3.Error as e:
                    logger.warning(f"Error computing numeric statistics for {column}: {e}")
            
            # Sample values (always compute)
            try:
                cursor.execute(f'''
                    SELECT DISTINCT {safe_column}
                    FROM "{table_name}"
                    WHERE {safe_column} IS NOT NULL
                    LIMIT 5
                ''')
                sample_rows = cursor.fetchall()
                stats.sample_values = [row[0] for row in sample_rows if row[0] is not None]
            
            except sqlite3.Error as e:
                logger.warning(f"Error getting sample values for {column}: {e}")
        
        except sqlite3.Error as e:
            logger.warning(f"Error computing statistics for {column}: {e}")
        
        return stats


# Global statistics service instance
_stats_service: StatisticsService | None = None
_stats_service_lock = threading.Lock()


def get_statistics_service() -> StatisticsService:
    """Get the global statistics service instance."""
    global _stats_service
    
    if _stats_service is None:
        with _stats_service_lock:
            if _stats_service is None:
                _stats_service = StatisticsService()
    
    return _stats_service
