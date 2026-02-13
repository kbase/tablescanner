import logging
import collections
from datetime import datetime
from typing import List, Dict, Any

# Maximum number of logs to keep in memory
MAX_LOG_ENTRIES = 1000

class MemoryLogHandler(logging.Handler):
    """
    Custom logging handler that stores log records in memory.
    Useful for exposing logs via API.
    """
    def __init__(self, capacity=MAX_LOG_ENTRIES):
        super().__init__()
        self.log_buffer = collections.deque(maxlen=capacity)
        
    def emit(self, record):
        try:
            log_entry = self.format(record)
            self.log_buffer.append({
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname.lower(),
                "message": log_entry,
                "source": "backend",
                "logger": record.name
            })
        except Exception as e:
            # Log the error to stderr so it's visible during development/debugging
            import sys
            print(f"MemoryLogHandler.emit() failed: {e}", file=sys.stderr)
            self.handleError(record)

    def get_logs(self, limit: int = 100, level: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve logs from buffer with optional filtering.
        """
        logs = list(self.log_buffer)
        
        if level:
            # Normalize level; actual filtering can be implemented here later.
            level = level.lower()
            # TODO: Implement level-based filtering (e.g., min level severity)
            # For now, return all logs and let clients filter
            
        # Return most recent first
        return sorted(logs, key=lambda x: x['timestamp'], reverse=True)[:limit]

# Global instance
memory_handler = MemoryLogHandler()
memory_handler.setFormatter(logging.Formatter("%(message)s"))

def get_memory_handler():
    return memory_handler

def setup_logging():
    """
    Configure root logger to use memory handler.
    """
    root_logger = logging.getLogger()
    # Add memory handler if not already present
    if not any(isinstance(h, MemoryLogHandler) for h in root_logger.handlers):
        root_logger.addHandler(memory_handler)
        # Ensure we capture everything
        root_logger.setLevel(logging.INFO)
