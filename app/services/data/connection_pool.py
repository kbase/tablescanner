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
    
    # Connection timeout: 30 minutes of inactivity
    POOL_TIMEOUT_SECONDS = 30 * 60
    
    # Clean up interval
    CLEANUP_INTERVAL_SECONDS = 5 * 60
    
    # Maximum connections per database file
    MAX_CONNECTIONS = 5 
    
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
                    except Exception:
                        # Best-effort close; log at debug and continue with a fresh connection.
                        logger.debug("Failed to close bad SQLite connection for %s", db_key, exc_info=True)
                    conn = self._create_new_connection(db_key)

            except queue.Empty:
                # Pool is empty, if we haven't reached max capacity (logic hard to track with Queue size only),
                # ideally we pre-fill or dynamic fill. 
                # With standard Queue, we put connections IN. 
                # Strategy: Initialize Queue with N "tokens" or create on demand?
                # Alternative: On Queue.get, if empty, we wait.
                # BUT, initially queue is empty.
                # So we need a mechanism to create new connections if < MAX and queue empty.
                # Let's simplify: 
                # The queue holds *idle* connections.
                # We need a semaphore for *total* connections?
                #
                # Let's use a standard sizing approach: 
                # When getting, if queue empty and we can create more, create one.
                # This requires tracking count. Sizing is tricky with just a Queue.
                # 
                # SIMPLIFIED APPROACH for SQLite: 
                # Just use the Queue as a resource pool. Populate it on demand?
                # No, standard pattern: 
                # Queue initialized empty.
                # If queue.empty():
                #   if current connections < max: create new
                #   else: wait on queue
                #
                # This requires tracking active count.
                # Given strict timeline, let's just FILL the queue on first access up to MAX?
                # Or lazily create.
                
                # Let's do lazy creation with a separate semaphore-like logic if needed, 
                # Or just rely on Python's robust GC and just use a pool of created connections.
                
                # Refined Strategy:
                # Queue contains available connections.
                # If we get Empty, we check if we can create better?
                # Actually, simpler: Pre-populate or lazily populate?
                # Lazy: If invalid/closed, we discard.
                #
                # For this fix, let's use a "LifoQueue" or standard Queue.
                # But to manage the *limit*, we need to know how many are out there.
                raise TimeoutError(f"Timeout waiting for database connection: {db_path}")

            yield conn

        finally:
            # 3. Return connection to pool
            if conn:
                # Rollback uncommitted transaction to reset state
                try:
                    conn.rollback()
                except Exception:
                    # If rollback fails, the connection may be in a bad state; it will
                    # still be returned to the pool but future health checks will replace it.
                    logger.debug("Failed to rollback SQLite connection for %s", db_key, exc_info=True)
                
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
            except Exception as e:
                logger.error(f"Error filling connection pool for {db_key}: {e}")
                # Close any created ones?
                while not q.empty():
                    try:
                        q.get_nowait().close()
                    except Exception:
                        logger.debug("Failed to close SQLite connection during pool recovery.", exc_info=True)
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
        except sqlite3.Error as e:
            logger.warning(f"Failed to apply optimizations: {e}")
            
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
                logger.info(f"Cleaned up expired pool for: {key}")

    def _close_pool_queue(self, q: queue.Queue):
        """Close all connections in a queue."""
        while not q.empty():
            try:
                conn = q.get_nowait()
                conn.close()
            except Exception:
                # Best-effort close; swallow errors but record at debug.
                logger.debug("Failed to close SQLite connection during pool cleanup.", exc_info=True)

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

