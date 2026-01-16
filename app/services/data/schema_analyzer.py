"""
Schema Analyzer.

Comprehensive database schema introspection with sample value analysis.
Profiles tables and columns to provide input for type inference and AI analysis.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ColumnProfile:
    """Detailed profile of a database column."""
    
    name: str
    sqlite_type: str  # INTEGER, TEXT, REAL, BLOB, NULL
    sample_values: list[Any] = field(default_factory=list)
    null_count: int = 0
    total_count: int = 0
    unique_count: int = 0
    avg_length: float = 0.0  # For TEXT columns
    min_value: Any = None  # For numeric columns
    max_value: Any = None
    detected_patterns: list[str] = field(default_factory=list)
    
    @property
    def null_ratio(self) -> float:
        """Percentage of NULL values."""
        return self.null_count / self.total_count if self.total_count > 0 else 0.0
    
    @property
    def unique_ratio(self) -> float:
        """Cardinality indicator (unique / total)."""
        return self.unique_count / self.total_count if self.total_count > 0 else 0.0
    
    @property
    def is_likely_id(self) -> bool:
        """Check if column is likely an identifier."""
        # High cardinality + low nulls + ID-like name pattern
        return (
            self.unique_ratio > 0.9 and 
            self.null_ratio < 0.01 and
            any(p in self.name.lower() for p in ["id", "key", "ref"])
        )


@dataclass
class TableProfile:
    """Complete profile of a database table."""
    
    name: str
    row_count: int = 0
    columns: list[ColumnProfile] = field(default_factory=list)
    primary_key: str | None = None
    foreign_keys: list[str] = field(default_factory=list)
    
    @property
    def column_count(self) -> int:
        return len(self.columns)
    
    def get_column(self, name: str) -> ColumnProfile | None:
        """Get a column profile by name."""
        for col in self.columns:
            if col.name == name:
                return col
        return None


class SchemaAnalyzer:
    """
    Database schema introspection and profiling.
    
    Analyzes SQLite databases to extract:
    - Table metadata (row counts, column counts)
    - Column details (types, nullability, cardinality)
    - Sample values for type inference
    - Statistical summaries
    """
    
    def __init__(self, sample_size: int = 10) -> None:
        """
        Initialize the schema analyzer.
        
        Args:
            sample_size: Number of sample values to collect per column
        """
        self.sample_size = sample_size
    
    def analyze_database(self, db_path: Path) -> list[TableProfile]:
        """
        Analyze all tables in a SQLite database.
        
        Args:
            db_path: Path to the SQLite database file
            
        Returns:
            List of TableProfile objects for each table
        """
        profiles: list[TableProfile] = []
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Get list of user tables
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            for table_name in tables:
                try:
                    profile = self._analyze_table(cursor, table_name)
                    profiles.append(profile)
                except Exception as e:
                    logger.warning(f"Error analyzing table {table_name}: {e}")
            
            conn.close()
            
        except sqlite3.Error as e:
            logger.error(f"Error opening database {db_path}: {e}")
            raise
        
        logger.info(f"Analyzed {len(profiles)} tables from {db_path}")
        return profiles
    
    def analyze_table(self, db_path: Path, table_name: str) -> TableProfile:
        """
        Analyze a single table in a SQLite database.
        
        Args:
            db_path: Path to the SQLite database file
            table_name: Name of the table to analyze
            
        Returns:
            TableProfile for the specified table
        """
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            profile = self._analyze_table(cursor, table_name)
            
            conn.close()
            return profile
            
        except sqlite3.Error as e:
            logger.error(f"Error analyzing table {table_name}: {e}")
            raise
    
    def get_sample_values(
        self,
        db_path: Path,
        table_name: str,
        column_name: str,
        n: int | None = None
    ) -> list[Any]:
        """
        Get sample values from a specific column.
        
        Args:
            db_path: Path to the SQLite database file
            table_name: Name of the table
            column_name: Name of the column
            n: Number of samples (defaults to self.sample_size)
            
        Returns:
            List of sample values (distinct, non-null when possible)
        """
        if n is None:
            n = self.sample_size
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Validate table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            if not cursor.fetchone():
                raise ValueError(f"Table not found: {table_name}")
            
            # Get distinct non-null samples first
            safe_col = column_name.replace('"', '""')
            cursor.execute(f'''
                SELECT DISTINCT "{safe_col}" 
                FROM "{table_name}" 
                WHERE "{safe_col}" IS NOT NULL 
                LIMIT ?
            ''', (n,))
            
            samples = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            return samples
            
        except sqlite3.Error as e:
            logger.error(f"Error getting samples from {table_name}.{column_name}: {e}")
            raise
    
    # ─── Private Methods ────────────────────────────────────────────────────
    
    def _analyze_table(self, cursor: sqlite3.Cursor, table_name: str) -> TableProfile:
        """Analyze a single table using an open cursor."""
        
        profile = TableProfile(name=table_name)
        
        # Get row count
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        profile.row_count = cursor.fetchone()[0]
        
        # Get column info
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        columns_info = cursor.fetchall()
        
        # Get primary key
        for col_info in columns_info:
            if col_info[5] == 1:  # pk column in PRAGMA result
                profile.primary_key = col_info[1]
                break
        
        # Analyze each column
        for col_info in columns_info:
            col_name = col_info[1]
            col_type = col_info[2] or "TEXT"
            
            col_profile = self._analyze_column(
                cursor, table_name, col_name, col_type, profile.row_count
            )
            profile.columns.append(col_profile)
        
        return profile
    
    def _analyze_column(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
        col_name: str,
        col_type: str,
        row_count: int
    ) -> ColumnProfile:
        """Analyze a single column."""
        
        safe_col = col_name.replace('"', '""')
        safe_table = table_name.replace('"', '""')
        
        profile = ColumnProfile(
            name=col_name,
            sqlite_type=col_type.upper(),
            total_count=row_count,
        )
        
        if row_count == 0:
            return profile
        
        # Get null count
        cursor.execute(f'''
            SELECT COUNT(*) FROM "{safe_table}" WHERE "{safe_col}" IS NULL
        ''')
        profile.null_count = cursor.fetchone()[0]
        
        # Get unique count (limit to avoid performance issues on large tables)
        try:
            cursor.execute(f'''
                SELECT COUNT(DISTINCT "{safe_col}") FROM "{safe_table}"
            ''')
            profile.unique_count = cursor.fetchone()[0]
        except sqlite3.Error:
            profile.unique_count = 0
        
        # Get sample values (distinct, non-null)
        cursor.execute(f'''
            SELECT DISTINCT "{safe_col}" 
            FROM "{safe_table}" 
            WHERE "{safe_col}" IS NOT NULL 
            LIMIT {self.sample_size}
        ''')
        profile.sample_values = [row[0] for row in cursor.fetchall()]
        
        # Get statistics for numeric columns
        if col_type.upper() in ("INTEGER", "REAL", "NUMERIC"):
            try:
                cursor.execute(f'''
                    SELECT MIN("{safe_col}"), MAX("{safe_col}"), AVG(LENGTH(CAST("{safe_col}" AS TEXT)))
                    FROM "{safe_table}" 
                    WHERE "{safe_col}" IS NOT NULL
                ''')
                result = cursor.fetchone()
                if result:
                    profile.min_value = result[0]
                    profile.max_value = result[1]
                    profile.avg_length = result[2] or 0.0
            except sqlite3.Error:
                pass
        
        # Get average length for text columns
        elif col_type.upper() in ("TEXT", "VARCHAR", "CHAR", ""):
            try:
                cursor.execute(f'''
                    SELECT AVG(LENGTH("{safe_col}"))
                    FROM "{safe_table}" 
                    WHERE "{safe_col}" IS NOT NULL
                ''')
                result = cursor.fetchone()
                if result and result[0]:
                    profile.avg_length = float(result[0])
            except sqlite3.Error:
                pass
        
        # Detect patterns in sample values
        profile.detected_patterns = self._detect_patterns(profile.sample_values)
        
        return profile
    
    def _detect_patterns(self, values: list[Any]) -> list[str]:
        """Detect common patterns in sample values."""
        patterns: list[str] = []
        
        if not values:
            return patterns
        
        str_values = [str(v) for v in values if v is not None]
        if not str_values:
            return patterns
        
        # Check for URL pattern
        if all(v.startswith(("http://", "https://")) for v in str_values):
            patterns.append("url")
        
        # Check for email pattern
        if all("@" in v and "." in v for v in str_values):
            patterns.append("email")
        
        # Check for GO term pattern
        if all(v.startswith("GO:") for v in str_values):
            patterns.append("go_term")
        
        
        # Check for ISO date pattern
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}")
        if all(date_pattern.match(v) for v in str_values):
            patterns.append("iso_date")
        
        # Check for UUID pattern
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE
        )
        if all(uuid_pattern.match(v) for v in str_values):
            patterns.append("uuid")
        
        # Check for sequence pattern (DNA/RNA/Protein)
        seq_pattern = re.compile(r"^[ATCGUN]+$", re.IGNORECASE)
        protein_pattern = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$", re.IGNORECASE)
        if all(len(v) > 20 for v in str_values):
            if all(seq_pattern.match(v) for v in str_values):
                patterns.append("nucleotide_sequence")
            elif all(protein_pattern.match(v) for v in str_values):
                patterns.append("protein_sequence")
        
        return patterns
