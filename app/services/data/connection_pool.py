"""
Database Connection Pool Manager.

Manages a pool of SQLite database connections with:
- Automatic lifecycle management (30-minute inactivity timeout)
- Connection reuse for performance
- SQLite performance optimizations (WAL mode, cache size, etc.)
- Prepared statement caching
- Automatic cleanup of expired connections
"""

from __future__ import annotations

import sqlite3
import logging
import threading
import time
from pathlib import Path
from typing import Any
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Information about a cached database connection."""
    
    connection: sqlite3.Connection
    db_path: Path
    last_access: float = field(default_factory=time.time)
    access_count: int = 0
    file_mtime: float = 0.0
    prepared_statements: dict[str, sqlite3.Cursor] = field(default_factory=dict)
    
    def touch(self) -> None:
        """Update last access time and increment access count."""
        self.last_access = time.time()
        self.access_count += 1


class ConnectionPool:
    """
    Manages a pool of SQLite database connections.
    
    Features:
    - Opens databases on first access
    - Caches connections in memory
    - Tracks last access time and access count
    - Automatically closes databases after 30 minutes of inactivity
    - Cleans up expired connections every 5 minutes
    - Reloads database if file modification time changes
    - Applies SQLite performance optimizations
    - Caches prepared statements for reuse
    """
    
    # Connection timeout: 30 minutes of inactivity
    CONNECTION_TIMEOUT_SECONDS = 30 * 60
    
    # Cleanup interval: run cleanup every 5 minutes
    CLEANUP_INTERVAL_SECONDS = 5 * 60
    
    def __init__(self) -> None:
        """Initialize the connection pool."""
        self._connections: dict[str, ConnectionInfo] = OrderedDict()
        self._lock = threading.RLock()
        self._last_cleanup = time.time()
        
        logger.info("Initialized SQLite connection pool")
    
    def get_connection(self, db_path: Path) -> sqlite3.Connection:
        """
        Get a connection to a SQLite database.
        
        Opens the database if not already cached, or returns existing connection.
        Automatically applies performance optimizations and checks for file changes.
        
        Args:
            db_path: Path to the SQLite database file
            
        Returns:
            SQLite connection object
            
        Raises:
            sqlite3.Error: If database cannot be opened
        """
        db_key = str(db_path.absolute())
        
        with self._lock:
            # Check if connection exists and is still valid
            if db_key in self._connections:
                conn_info = self._connections[db_key]
                
                # Check if file has been modified
                try:
                    current_mtime = db_path.stat().st_mtime
                    if current_mtime != conn_info.file_mtime:
                        logger.info(f"Database file modified, reloading: {db_path}")
                        self._close_connection(db_key, conn_info)
                        # Will create new connection below
                    else:
                        # Connection is valid, update access time
                        conn_info.touch()
                        # Move to end (LRU)
                        self._connections.move_to_end(db_key)
                        return conn_info.connection
                except OSError:
                    # File no longer exists, remove connection
                    logger.warning(f"Database file no longer exists: {db_path}")
                    self._close_connection(db_key, conn_info)
                    del self._connections[db_key]
            
            # Create new connection
            logger.debug(f"Opening new database connection: {db_path}")
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            
            # Apply performance optimizations
            self._optimize_connection(conn)
            
            # Store connection info
            try:
                file_mtime = db_path.stat().st_mtime
            except OSError:
                file_mtime = 0.0
            
            conn_info = ConnectionInfo(
                connection=conn,
                db_path=db_path,
                file_mtime=file_mtime
            )
            conn_info.touch()
            
            self._connections[db_key] = conn_info
            
            # Run cleanup if needed
            self._maybe_cleanup()
            
            return conn
    
    def _optimize_connection(self, conn: sqlite3.Connection) -> None:
        """
        Apply SQLite performance optimizations.
        
        Sets pragmas for better performance:
        - journal_mode=WAL: Write-Ahead Logging for better concurrency
        - synchronous=NORMAL: Balance between safety and performance
        - cache_size=-64000: 64MB cache (negative = KB)
        - temp_store=MEMORY: Store temporary tables in memory
        - mmap_size=268435456: 256MB memory-mapped I/O
        """
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA mmap_size=268435456")
            logger.debug("Applied SQLite performance optimizations")
        except sqlite3.Error as e:
            logger.warning(f"Failed to apply some SQLite optimizations: {e}")
    
    def _close_connection(self, db_key: str, conn_info: ConnectionInfo) -> None:
        """Close a connection and clean up resources."""
        try:
            # Close prepared statements
            for stmt in conn_info.prepared_statements.values():
                try:
                    stmt.close()
                except Exception:
                    pass
            
            # Close connection
            conn_info.connection.close()
            logger.debug(f"Closed database connection: {conn_info.db_path}")
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
    
    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed."""
        now = time.time()
        if now - self._last_cleanup < self.CLEANUP_INTERVAL_SECONDS:
            return
        
        self._last_cleanup = now
        self.cleanup_expired()
    
    def cleanup_expired(self) -> None:
        """
        Close and remove connections that have been inactive for too long.
        
        Connections are closed if they haven't been accessed in the last
        30 minutes (CONNECTION_TIMEOUT_SECONDS).
        """
        now = time.time()
        expired_keys = []
        
        with self._lock:
            for db_key, conn_info in list(self._connections.items()):
                age = now - conn_info.last_access
                if age > self.CONNECTION_TIMEOUT_SECONDS:
                    expired_keys.append((db_key, conn_info))
            
            for db_key, conn_info in expired_keys:
                logger.info(
                    f"Closing expired connection (inactive {age:.0f}s): {conn_info.db_path}"
                )
                self._close_connection(db_key, conn_info)
                del self._connections[db_key]
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired connections")
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            for db_key, conn_info in list(self._connections.items()):
                self._close_connection(db_key, conn_info)
            self._connections.clear()
        
        logger.info("Closed all database connections")
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about the connection pool.
        
        Returns:
            Dictionary with pool statistics
        """
        with self._lock:
            now = time.time()
            connections = []
            
            for db_key, conn_info in self._connections.items():
                age = now - conn_info.last_access
                connections.append({
                    "db_path": str(conn_info.db_path),
                    "last_access_seconds_ago": age,
                    "access_count": conn_info.access_count,
                    "prepared_statements": len(conn_info.prepared_statements)
                })
            
            return {
                "total_connections": len(self._connections),
                "connections": connections
            }


# Global connection pool instance
_global_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_connection_pool() -> ConnectionPool:
    """
    Get the global connection pool instance.
    
    Returns:
        Global ConnectionPool instance
    """
    global _global_pool
    
    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                _global_pool = ConnectionPool()
    
    return _global_pool
