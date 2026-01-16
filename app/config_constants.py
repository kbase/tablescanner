"""
Configuration constants for TableScanner.
"""

# Default values
DEFAULT_LIMIT = 100
MAX_LIMIT = 500000
DEFAULT_OFFSET = 0
DEFAULT_SORT_ORDER = "ASC"

# Cache settings
CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_MAX_ENTRIES = 1000
INDEX_CACHE_TTL = 3600  # 1 hour

# Timeout settings
KBASE_API_TIMEOUT_SECONDS = 30

# API Version
API_VERSION = "2.0"
