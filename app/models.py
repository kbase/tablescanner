from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


# =============================================================================
# REQUEST MODELS
# =============================================================================


class TableDataRequest(BaseModel):
    """
    Request model for /table-data endpoint.
    
    Mirrors the parameters from the original BERDLTable_conversion_service
    for API compatibility.
    """
    berdl_table_id: str = Field(
        ...,
        description="BERDLTables object reference",
        examples=["76990/ADPITest"]
    )
    columns: str | None = Field(
        "all",
        description="Comma-separated list of columns to select or 'all'",
        examples=["gene_id, gene_name"]
    )
    col_filter: dict[str, str] | None = Field(
        None,
        description="Column-specific filters (alias for query_filters)",
        examples=[{"gene_name": "kinase"}]
    )
    table_name: str = Field(
        ...,
        description="Table name within the SQLite database",
        examples=["Genes"]
    )
    limit: int = Field(
        100,
        ge=1,
        le=500000,
        description="Maximum rows to return"
    )
    offset: int = Field(
        0,
        ge=0,
        description="Offset for pagination"
    )
    sort_column: str | None = Field(
        None,
        description="Column to sort by"
    )
    sort_order: Literal["ASC", "DESC"] | None = Field(
        "ASC",
        description="Sort direction"
    )
    order_by: list[dict[str, str]] | None = Field(
        None,
        description="Multi-column sort specifications [{'column': 'col_name', 'direction': 'asc'}]",
        examples=[[{"column": "gene_name", "direction": "asc"}, {"column": "score", "direction": "desc"}]]
    )
    search_value: str | None = Field(
        None,
        description="Global search term"
    )
    query_filters: dict[str, str] | None = Field(
        None,
        description="Column-specific filters {column_name: filter_value}",
        examples=[{"gene_name": "kinase", "organism": "E. coli"}]
    )
    kb_env: str = Field(
        "appdev",
        description="KBase environment"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "berdl_table_id": "76990/7/2",
                "table_name": "Metadata_Conditions",
                "limit": 50,
                "offset": 0,
                "search_value": "glucose",
                "col_filter": {
                    "organism": "E. coli"
                },
                "sort_column": "yield",
                "sort_order": "DESC"
            }
        }
    }


# =============================================================================
# RESPONSE MODELS
# =============================================================================




class TableInfo(BaseModel):
    """Information about a database table."""
    name: str = Field(..., description="Table name", examples=["Genes"])
    row_count: int | None = Field(None, description="Number of rows", examples=[3356])
    column_count: int | None = Field(None, description="Number of columns", examples=[18])


class TableListResponse(BaseModel):
    """Response for listing tables in a database."""
    berdl_table_id: str | None = Field(None, description="BERDLTable object reference", examples=["76990/7/2"])
    handle_ref: str | None = Field(None, description="Blobstore handle reference", examples=["KBH_248028"])
    object_type: str | None = Field(None, description="KBase object type", examples=["KBaseGeneDataLakes.BERDLTables-1.0"])
    tables: list[TableInfo] = Field(
        default_factory=list,
        description="List of available tables",
        examples=[[
            {"name": "Genes", "row_count": 3356, "column_count": 18},
            {"name": "Metadata_Conditions", "row_count": 42, "column_count": 12}
        ]]
    )
    source: str | None = Field(None, description="Data source", examples=["Cache"])
    
    # Viewer integration fields
    config_fingerprint: str | None = Field(
        None, 
        description="Fingerprint of cached viewer config (if exists)",
        examples=["v1_auto_abc123def456"]
    )
    config_url: str | None = Field(
        None,
        description="URL to retrieve generated viewer config",
        examples=["/config/generated/v1_auto_abc123def456"]
    )
    has_cached_config: bool = Field(
        False,
        description="Whether a viewer config is cached for this database"
    )
    
    # Schema information for immediate viewer use
    schemas: dict | None = Field(
        None,
        description="Column types per table: {table_name: {column: sql_type}}"
    )
    
    # Fallback config availability
    has_builtin_config: bool = Field(
        False,
        description="Whether a built-in fallback config exists for this object type"
    )
    builtin_config_id: str | None = Field(
        None,
        description="ID of the matching built-in config"
    )
    
    # Database metadata
    database_size_bytes: int | None = Field(
        None,
        description="Size of the SQLite database file in bytes"
    )
    total_rows: int = Field(
        0,
        description="Total rows across all tables"
    )
    
    # Versioning for backward compatibility
    api_version: str = Field(
        "2.0",
        description="API version for response format compatibility"
    )





class TableDataResponse(BaseModel):
    """
    Response for table data queries.
    
    Includes the data, metadata, and performance metrics.
    """
    headers: list[str] = Field(
        ...,
        description="Column names in order"
    )
    data: list[list[str]] = Field(
        ...,
        description="Row data as list of lists"
    )
    row_count: int = Field(
        ...,
        description="Number of rows in this response"
    )
    total_count: int = Field(
        ...,
        description="Total rows in table (before filtering)"
    )
    filtered_count: int = Field(
        ...,
        description="Rows matching filter criteria"
    )
    table_name: str = Field(
        ...,
        description="Name of the queried table"
    )
    response_time_ms: float = Field(
        ...,
        description="Total response time in milliseconds"
    )
    db_query_ms: float | None = Field(
        None,
        description="Database query time in milliseconds"
    )
    conversion_ms: float | None = Field(
        None,
        description="Data conversion time in milliseconds"
    )
    source: str | None = Field(
        None,
        description="Data source (Cache or Downloaded)"
    )
    cache_file: str | None = Field(
        None,
        description="Path to cached file"
    )
    sqlite_file: str | None = Field(
        None,
        description="Path to SQLite database"
    )
    object_type: str | None = Field(
        None,
        description="KBase object type",
        examples=["KBaseGeneDataLakes.BERDLTables-1.0"]
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Scenario: Cached Data (Fast)",
                    "description": "Subsequent requests are served from the local SQLite cache.",
                    "value": {
                        "headers": ["gene_id", "gene_name", "product"],
                        "data": [
                            ["ACIAD_RS00005", "dnaA", "replication initiator"],
                            ["ACIAD_RS00010", "dnaN", "DNA pol III beta"]
                        ],
                        "row_count": 2,
                        "total_count": 3356,
                        "filtered_count": 3356,
                        "table_name": "Genes",
                        "response_time_ms": 125.5,
                        "db_query_ms": 42.0,
                        "conversion_ms": 5.2,
                        "source": "Cache",
                        "sqlite_file": "/app/cache/76990_7_2/tables.db"
                    }
                },
                {
                    "summary": "Scenario: First-time Download (Slow)",
                    "description": "The first request downloads the file from KBase and builds the cache.",
                    "value": {
                        "headers": ["gene_id", "gene_name", "product"],
                        "data": [
                            ["ACIAD_RS00005", "dnaA", "replication initiator"],
                            ["ACIAD_RS00010", "dnaN", "DNA pol III beta"]
                        ],
                        "row_count": 2,
                        "total_count": 3356,
                        "filtered_count": 3356,
                        "table_name": "Genes",
                        "response_time_ms": 4250.0,
                        "db_query_ms": 110.0,
                        "conversion_ms": 8.5,
                        "source": "Downloaded",
                        "sqlite_file": "/app/cache/76990_7_2/tables.db"
                    }
                }
            ]
        }
    }


class TableSchemaResponse(BaseModel):
    """Response for table schema (columns) queries."""
    handle_ref: str | None = Field(None, description="Blobstore handle reference")
    berdl_table_id: str | None = Field(None, description="BERDLTable object reference")
    table_name: str = Field(..., description="Name of the table")
    columns: list[str] = Field(..., description="List of column names", examples=[["gene_id", "gene_name", "product"]])
    row_count: int = Field(..., description="Total rows in table", examples=[3356])


class CacheResponse(BaseModel):
    """Response for cache operations."""
    status: Literal["success", "error"] = Field(
        ...,
        description="Operation status"
    )
    message: str = Field(
        ...,
        description="Status message"
    )


class ServiceStatus(BaseModel):
    """Service health check response."""
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    status: Literal["running", "degraded", "error"] = Field(
        ...,
        description="Service status"
    )
    cache_dir: str = Field(..., description="Cache directory path")




# =============================================================================
# DATATABLES VIEWER API MODELS
# =============================================================================


class FilterRequest(BaseModel):
    """Filter specification for DataTables Viewer API."""
    column: str = Field(..., description="Column name to filter")
    operator: str = Field(
        ...,
        description="Filter operator: eq, ne, gt, gte, lt, lte, like, ilike, in, not_in, between, is_null, is_not_null"
    )
    value: Any = Field(None, description="Filter value (or first value for 'between')")
    value2: Any = Field(None, description="Second value for 'between' operator")


class AggregationRequest(BaseModel):
    """Aggregation specification for DataTables Viewer API."""
    column: str = Field(..., description="Column name to aggregate")
    function: str = Field(
        ...,
        description="Aggregation function: count, sum, avg, min, max, stddev, variance, distinct_count"
    )
    alias: str | None = Field(None, description="Alias for aggregated column")


class TableDataQueryRequest(BaseModel):
    """Enhanced table data query request for DataTables Viewer API."""
    berdl_table_id: str = Field(..., description="Database identifier (local/db_name format)")
    table_name: str = Field(..., description="Table name")
    limit: int = Field(100, ge=1, le=500000, description="Maximum rows to return")
    offset: int = Field(0, ge=0, description="Number of rows to skip")
    columns: list[str] | None = Field(None, description="List of columns to select (None = all)")
    sort_column: str | None = Field(None, description="Column to sort by")
    sort_order: Literal["ASC", "DESC"] = Field("ASC", description="Sort direction")
    search_value: str | None = Field(None, description="Global search term")
    col_filter: dict[str, str] | None = Field(None, description="Simple column filters (legacy)")
    filters: list[FilterRequest] | None = Field(None, description="Advanced filter specifications")
    aggregations: list[AggregationRequest] | None = Field(None, description="Aggregation specifications")
    group_by: list[str] | None = Field(None, description="Columns for GROUP BY clause")


class AggregationQueryRequest(BaseModel):
    """Aggregation query request."""
    group_by: list[str] = Field(..., description="Columns for GROUP BY")
    aggregations: list[AggregationRequest] = Field(..., description="Aggregation specifications")
    filters: list[FilterRequest] | None = Field(None, description="Filter specifications")
    limit: int = Field(100, ge=1, le=500000, description="Maximum rows to return")
    offset: int = Field(0, ge=0, description="Number of rows to skip")


class ColumnTypeInfo(BaseModel):
    """Column type information."""
    name: str = Field(..., description="Column name")
    type: str = Field(..., description="SQLite type (INTEGER, REAL, TEXT, etc.)")
    notnull: bool = Field(False, description="Whether column is NOT NULL")
    pk: bool = Field(False, description="Whether column is PRIMARY KEY")
    dflt_value: Any = Field(None, description="Default value")


class QueryMetadata(BaseModel):
    """Query execution metadata."""
    query_type: str = Field(..., description="Type of query: select, aggregate")
    sql: str = Field(..., description="Executed SQL query")
    filters_applied: int = Field(0, description="Number of filters applied")
    has_search: bool = Field(False, description="Whether search was applied")
    has_sort: bool = Field(False, description="Whether sorting was applied")
    has_group_by: bool = Field(False, description="Whether GROUP BY was applied")
    has_aggregations: bool = Field(False, description="Whether aggregations were applied")


class TableDataQueryResponse(BaseModel):
    """Enhanced table data query response for DataTables Viewer API."""
    headers: list[str] = Field(..., description="Column names")
    data: list[list[str]] = Field(..., description="Row data as list of lists")
    total_count: int = Field(..., description="Total rows in table (before filtering)")
    column_types: list[ColumnTypeInfo] = Field(..., description="Column type information")
    query_metadata: QueryMetadata = Field(..., description="Query execution metadata")
    cached: bool = Field(False, description="Whether result was from cache")
    execution_time_ms: float = Field(..., description="Query execution time in milliseconds")
    limit: int = Field(..., description="Limit applied")
    offset: int = Field(..., description="Offset applied")
    table_name: str = Field(..., description="Table name")
    database_path: str = Field(..., description="Path to database file")


class TableSchemaInfo(BaseModel):
    """Table schema information."""
    table: str = Field(..., description="Table name")
    columns: list[ColumnTypeInfo] = Field(..., description="Column information")
    indexes: list[dict[str, str]] = Field(default_factory=list, description="Index information")


class ColumnStatistic(BaseModel):
    """Column statistics."""
    column: str = Field(..., description="Column name")
    type: str = Field(..., description="Column type")
    null_count: int = Field(0, description="Number of NULL values")
    distinct_count: int = Field(0, description="Number of distinct values")
    min: Any = Field(None, description="Minimum value")
    max: Any = Field(None, description="Maximum value")
    mean: float | None = Field(None, description="Mean value")
    median: float | None = Field(None, description="Median value")
    stddev: float | None = Field(None, description="Standard deviation")
    sample_values: list[Any] = Field(default_factory=list, description="Sample values")


class TableStatisticsResponse(BaseModel):
    """Table statistics response."""
    table: str = Field(..., description="Table name")
    row_count: int = Field(..., description="Total row count")
    columns: list[ColumnStatistic] = Field(..., description="Column statistics")
    last_updated: int = Field(..., description="Last update timestamp (milliseconds since epoch)")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field("ok", description="Service status")
    timestamp: str = Field(..., description="ISO8601 timestamp")
    mode: str = Field("cached_sqlite", description="Service mode")
    data_dir: str = Field(..., description="Data directory path")
    config_dir: str = Field(..., description="Config directory path")
    cache: dict[str, Any] = Field(..., description="Cache information")