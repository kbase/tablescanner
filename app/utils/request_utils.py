"""
Request processing utilities for TableScanner routes.
"""

from __future__ import annotations

import time
import logging
from typing import Any
from pathlib import Path

from fastapi import HTTPException
from app.services.data.query_service import get_query_service, FilterSpec
from app.utils.async_utils import run_sync_in_thread
from app.exceptions import TableNotFoundError

logger = logging.getLogger(__name__)

class TableRequestProcessor:
    """
    Handles common logic for table data requests:
    - Parameter extraction
    - Database access (via helper/callback)
    - Query execution via QueryService
    - Response formatting
    """
    
    @staticmethod
    async def process_data_request(
        db_path: Path,
        table_name: str,
        limit: int,
        offset: int,
        sort_column: str | None = None,
        sort_order: str = "ASC",
        search_value: str | None = None,
        columns: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        handle_ref_or_id: str | None = None
    ) -> dict[str, Any]:
        """
        Process a generic table data request.
        """
        start_time = time.time()
        
        # Prepare filters
        service_filters = []
        if filters:
            for col, val in filters.items():
                service_filters.append(FilterSpec(column=col, operator="like", value=val))
        
        # Determine sort direction
        direction = "ASC"
        if sort_order and sort_order.lower() == "desc":
            direction = "DESC"
            
        def _execute():
            query_service = get_query_service()
            try:
                return query_service.execute_query(
                    db_path=db_path,
                    table_name=table_name,
                    limit=limit,
                    offset=offset,
                    columns=columns,
                    sort_column=sort_column,
                    sort_order=direction,
                    search_value=search_value,
                    filters=service_filters,
                    use_cache=True
                )
            except TableNotFoundError as e:
                # Re-raise to be handled by caller or global handler
                raise ValueError(str(e))
                
        try:
            result = await run_sync_in_thread(_execute)
        except ValueError as e:
            # Map TableNotFoundError/ValueError to 404 for this context
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
            
        response_time_ms = (time.time() - start_time) * 1000
        
        # Format response
        return {
            "berdl_table_id": handle_ref_or_id, # Context dependent
            "handle_ref": handle_ref_or_id,     # Context dependent
            "table_name": table_name,
            "headers": result["headers"],
            "data": result["data"],
            "row_count": len(result["data"]),
            "total_count": result["total_count"],
            "filtered_count": result["total_count"], # Matches logic in routes.py
            "response_time_ms": response_time_ms,
            "db_query_ms": result["execution_time_ms"],
            "conversion_ms": 0.0, # Deprecated metric
            "sqlite_file": str(db_path)
        }
