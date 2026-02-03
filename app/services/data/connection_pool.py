"""
Database Connection Pool Manager.

Manages a pool of SQLite database connections with:
- Thread-safe Queue-based pooling (one queue per database file)
- Automatic lifecycle management (30-minute inactivity timeout)
- Connection reuse for performance
- SQLite performance optimizations (WAL mode, cache size, etc.)
- Context manager interface for safe connection handling
"""

from __future__ import annotations

import sqlite3
import logging
import threading
import time
import queue
from pathlib import Path
from typing import Any, Generator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Manages a pool of SQLite database connections using thread-safe Queues.
    
    Features:
    - Dedicated Queue for each database file to enforce thread safety.
    - Context manager `connection()` ensures connections are always returned.
    - Automatic cleanup of idle pools.
    """
    
    # Connection timeout: 10 minutes of inactivity (reduced for local DBs)
    POOL_TIMEOUT_SECONDS = 10 * 60
    
    # Clean up interval
    CLEANUP_INTERVAL_SECONDS = 2 * 60
    
    # Maximum connections per database file
    MAX_CONNECTIONS = 8 
    
    def __init__(self) -> None:
        """Initialize the connection pool."""
        # Key: str(db_path), Value: (queue.Queue, last_access_time)
        self._pools: dict[str, tuple[queue.Queue, float]] = {}
        self._lock = threading.RLock()
        self._last_cleanup = time.time()
        
        logger.info("Initialized SQLite connection pool (Queue-based)")
    
    @contextmanager
    def connection(self, db_path: Path, timeout: float = 10.0) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager to aquire a database connection.
        
        Blocks until a connection is available or timeout occurs.
        Automatically returns the connection to the pool when done.
        
        Args:
            db_path: Path to the SQLite database
            timeout: Max time to wait for a connection in seconds
            
        Yields:
            sqlite3.Connection: Active database connection
            
        Raises:
            queue.Empty: If no connection available within timeout
            sqlite3.Error: If connection cannot be created
        """
        db_key = str(db_path.absolute())
        
        # 1. Get or create the pool queue for this DB
        pool_queue = self._get_or_create_pool(db_key)
        
        conn = None
        try:
            # 2. Try to get a connection from the queue
            try:
                conn = pool_queue.get(block=True, timeout=timeout)
                
                # Check if file changed since this connection was created
                # (Simple check: if we wanted to be robust against file replacements,
                # we'd check stats, but for now we assume connections in queue are valid
                # or will fail fast)
                try:
                    # Lightweight liveliness check
                    conn.execute("SELECT 1")
                except sqlite3.Error:
                    # Connection bad, close and make new one
                    try:
                        conn.close()
                    except (sqlite3.Error, OSError) as e:
                        # Best-effort close; log at debug and continue with a fresh connection.
                        logger.debug("Failed to close bad SQLite connection for %s: %s", db_key, e)
                    conn = self._create_new_connection(db_key)

            except queue.Empty:
                # Pool is empty - try to create a new connection if under limit
                with self._lock:
                    # Check current pool size and total connections
                    current_queue_size = pool_queue.qsize()
                    # Estimate total connections: queue size + active connections
                    # Since we can't track active connections perfectly, we'll be conservative
                    if current_queue_size == 0 and len(self._pools.get(db_key, [(queue.Queue(), 0)])[0]._queue) < self.MAX_CONNECTIONS:
                        # Create new connection on-demand
                        try:
                            conn = self._create_new_connection(db_key)
                        except (sqlite3.Error, OSError, ValueError) as e:
                            logger.error("Failed to create new connection for %s: %s", db_key, e)
                            raise TimeoutError(f"Timeout waiting for database connection: {db_path}") from e
                    else:
                        # Wait for available connection
                        try:
                            conn = pool_queue.get(block=True, timeout=timeout)
                        except queue.Empty:
                            raise TimeoutError(f"Timeout waiting for database connection: {db_path}")

            yield conn

        finally:
            # 3. Return connection to pool
            if conn:
                # Rollback uncommitted transaction to reset state
                try:
                    conn.rollback()
                except (sqlite3.Error, OSError, ValueError) as e:
                    # If rollback fails, the connection may be in a bad state; it will
                    # still be returned to the pool but future health checks will replace it.
                    logger.debug("Failed to rollback SQLite connection for %s: %s", db_key, e)
                
                # Put back in queue
                # Note: We must update the last access time for the POOL, not the connection
                self._update_pool_access(db_key)
                pool_queue.put(conn)

            # 4. Trigger cleanup periodically
            self._maybe_cleanup()

    def _get_or_create_pool(self, db_key: str) -> queue.Queue:
        """Get existing pool or create a new one with connections."""
        with self._lock:
            if db_key in self._pools:
                q, _ = self._pools[db_key]
                self._pools[db_key] = (q, time.time()) # Update access
                return q
            
            # Create new pool
            q = queue.Queue(maxsize=self.MAX_CONNECTIONS)
            
            # Pre-fill connections (Block-safe inside lock? Creation is IO)
            # Better to create them. 
            # Note: opening 5 sqlite connections is fast.
            try:
                for _ in range(self.MAX_CONNECTIONS):
                    conn = self._create_new_connection(db_key)
                    q.put(conn)
            except (sqlite3.Error, OSError, ValueError) as e:
                logger.error("Error filling connection pool for %s: %s", db_key, e)
                # Close any created ones?
                while not q.empty():
                    try:
                        q.get_nowait().close()
                    except (sqlite3.Error, OSError) as e:
                        logger.debug("Failed to close SQLite connection during pool recovery: %s", e)
                raise
            
            self._pools[db_key] = (q, time.time())
            return q

    def _create_new_connection(self, db_path_str: str) -> sqlite3.Connection:
        """Create and configure a single SQLite connection."""
        conn = sqlite3.connect(db_path_str, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Performance optimizations
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000") # 64MB
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA mmap_size=268435456") # 256MB
        except (sqlite3.Error, OSError) as e:
            logger.warning("Failed to apply optimizations: %s", e)
            
        return conn

    def _update_pool_access(self, db_key: str):
        """Update last access timestamp for a pool."""
        with self._lock:
            if db_key in self._pools:
                q, _ = self._pools[db_key]
                self._pools[db_key] = (q, time.time())

    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed."""
        now = time.time()
        # Non-blocking check
        if now - self._last_cleanup < self.CLEANUP_INTERVAL_SECONDS:
            return
            
        with self._lock:
            # Double check inside lock
            if now - self._last_cleanup < self.CLEANUP_INTERVAL_SECONDS:
                return
            self._last_cleanup = now
            self.cleanup_expired()

    def cleanup_expired(self) -> None:
        """Close pools that haven't been accessed recently."""
        now = time.time()
        expired_keys = []
        
        with self._lock:
            for db_key, (q, last_access) in self._pools.items():
                if now - last_access > self.POOL_TIMEOUT_SECONDS:
                    expired_keys.append(db_key)
            
            for key in expired_keys:
                q, _ = self._pools.pop(key)
                self._close_pool_queue(q)
                logger.info("Cleaned up expired pool for: %s", key)

    def _close_pool_queue(self, q: queue.Queue):
        """Close all connections in a queue."""
        while not q.empty():
            try:
                conn = q.get_nowait()
                conn.close()
            except (sqlite3.Error, OSError) as e:
                # Best-effort close; swallow errors but record at debug.
                logger.debug("Failed to close SQLite connection during pool cleanup: %s", e)

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        with self._lock:
            stats = []
            for db_key, (q, last_access) in self._pools.items():
                stats.append({
                    "db_path": db_key,
                    "available_connections": q.qsize(),
                    "last_access_ago": time.time() - last_access
                })
            return {
                "total_pools": len(self._pools),
                "pools": stats
            }

    # Helper for legacy or non-context usage (Deprecated)
    def get_connection(self, db_path: Path) -> sqlite3.Connection:
        """
        DEPRECATED: Use `with pool.connection(path) as conn:` instead.
        This method will raise an error to enforce refactoring.
        """
        raise NotImplementedError("get_connection() is deprecated. Use 'with pool.connection(db_path) as conn:'")

# Global instances
_global_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

def get_connection_pool() -> ConnectionPool:
    global _global_pool
    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                _global_pool = ConnectionPool()
    return _global_pool

