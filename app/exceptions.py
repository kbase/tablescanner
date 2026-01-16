"""
Custom exceptions for TableScanner.
"""

class TableScannerError(Exception):
    """Base exception for TableScanner."""
    pass

class TableNotFoundError(TableScannerError):
    """Raised when a requested table does not exist."""
    def __init__(self, table_name: str, available_tables: list[str] | None = None):
        msg = f"Table '{table_name}' not found"
        if available_tables:
            msg += f". Available: {available_tables}"
        super().__init__(msg)
        self.table_name = table_name

class ColumnNotFoundError(TableScannerError):
    """Raised when a requested column does not exist."""
    def __init__(self, column_name: str, table_name: str):
        super().__init__(f"Column '{column_name}' not found in table '{table_name}'")

class InvalidFilterError(TableScannerError):
    """Raised when a filter configuration is invalid."""
    pass

class DatabaseAccessError(TableScannerError):
    """Raised when database file cannot be accessed or opened."""
    pass
