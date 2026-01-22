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
from app.exceptions import TableNotFoundError, InvalidFilterError
from app.config_constants import MAX_LIMIT

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
        columns: list[str] | str | None = None,
        filters: dict[str, Any] | list[Any] | None = None,
        aggregations: list[Any] | None = None,
        group_by: list[str] | None = None,
        handle_ref_or_id: str | None = None
    ) -> dict[str, Any]:
        """
        Process a generic table data request.
        """
        # Defensive check for limit
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT
            
        start_time = time.time()
        
        # Prepare filters
        service_filters = []
        if filters:
            if isinstance(filters, dict):
                # Legacy dict filters
                for col, val in filters.items():
                    service_filters.append(FilterSpec(column=col, operator="like", value=val))
            elif isinstance(filters, list):
                # Advanced filters (list of FilterRequest or dicts)
                for f in filters:
                    if hasattr(f, "column"): # Pydantic model
                        service_filters.append(FilterSpec(
                            column=f.column, 
                            operator=f.operator, 
                            value=f.value, 
                            value2=f.value2
                        ))
                    elif isinstance(f, dict): # Dict
                        service_filters.append(FilterSpec(
                            column=f.get("column"), 
                            operator=f.get("operator"), 
                            value=f.get("value"), 
                            value2=f.get("value2")
                        ))

        # Prepare aggregations
        service_aggregations = []
        if aggregations:
            from app.services.data.query_service import AggregationSpec
            for agg in aggregations:
                if hasattr(agg, "column"):
                    service_aggregations.append(AggregationSpec(
                        column=agg.column,
                        function=agg.function,
                        alias=agg.alias
                    ))
                elif isinstance(agg, dict):
                    service_aggregations.append(AggregationSpec(
                        column=agg.get("column"),
                        function=agg.get("function"),
                        alias=agg.get("alias")
                    ))
        
        # Determine sort direction
        direction = "ASC"
        if sort_order and sort_order.lower() == "desc":
            direction = "DESC"
            
        # Handle columns (string vs list) compatibility
        columns_list = None
        if columns:
            if isinstance(columns, str):
                 if columns.lower() != "all":
                     columns_list = [c.strip() for c in columns.split(",") if c.strip()]
            elif isinstance(columns, list):
                columns_list = columns

        def _execute():
            query_service = get_query_service()
            return query_service.execute_query(
                db_path=db_path,
                table_name=table_name,
                limit=limit,
                offset=offset,
                columns=columns_list,
                sort_column=sort_column,
                sort_order=direction,
                search_value=search_value,
                filters=service_filters,
                aggregations=service_aggregations,
                group_by=group_by,
                use_cache=True
            )
                
        try:
            result = await run_sync_in_thread(_execute)
        except (TableNotFoundError, InvalidFilterError):
            # Allow specific exceptions to bubble up to global handlers
            raise
        except ValueError as e:
            # Handle validation errors (e.g. invalid numeric conversion) from QueryService
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
            
        response_time_ms = (time.time() - start_time) * 1000
        
        # Format response
        return {
            "berdl_table_id": handle_ref_or_id, 
            "handle_ref": handle_ref_or_id,
            "table_name": table_name,
            "headers": result["headers"],
            "data": result["data"],
            "row_count": len(result["data"]),
            "total_count": result["total_count"],
            "filtered_count": result["total_count"], # Matches logic in routes.py
            "response_time_ms": response_time_ms,
            "db_query_ms": result["execution_time_ms"],
            "conversion_ms": 0.0, # Deprecated metric
            "sqlite_file": str(db_path),
            
            # System Overhaul / Advanced Metadata
            "column_types": result.get("column_types"),
            "column_schema": result.get("column_types"), # Alias
            "query_metadata": result.get("query_metadata"),
            "cached": result.get("cached", False),
            "execution_time_ms": result.get("execution_time_ms"),
            "limit": limit,
            "offset": offset,
            "database_path": str(db_path)
        }
