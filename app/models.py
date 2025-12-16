"""
Pydantic models for TableScanner API.

Defines strictly typed request/response schemas for clean /docs output.
All models use Field with descriptions and examples for documentation.
"""

from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field


# =============================================================================
# REQUEST MODELS
# =============================================================================

class OrderSpec(BaseModel):
    """Specification for ordering/sorting query results."""
    column: str = Field(..., description="Column name to sort by")
    order: Literal["ASC", "DESC"] = Field(
        "ASC",
        description="Sort direction: ASC (ascending) or DESC (descending)"
    )


class FilterSpec(BaseModel):
    """Specification for column-specific filtering."""
    column: str = Field(..., description="Column name to filter")
    value: str = Field(..., description="Filter value (uses LIKE matching)")
    operator: Literal["LIKE", "=", ">", "<", ">=", "<="] = Field(
        "LIKE",
        description="Filter operator"
    )


class SearchRequest(BaseModel):
    """
    Request model for /search endpoint.
    
    Provides a flexible interface for searching table data with
    optional filtering, sorting, and pagination.
    """
    berdl_table_id: str = Field(
        ...,
        description="BERDLTables object reference (e.g., '76990/ADPITest')",
        examples=["76990/ADPITest"]
    )
    pangenome_id: Optional[str] = Field(
        None,
        description="Pangenome ID within the BERDLTables object. Uses first available if not specified."
    )
    table_name: str = Field(
        ...,
        description="Name of the table to query",
        examples=["Genes", "Organisms"]
    )
    limit: int = Field(
        100,
        ge=1,
        le=500000,
        description="Maximum number of rows to return"
    )
    offset: int = Field(
        0,
        ge=0,
        description="Number of rows to skip (for pagination)"
    )
    search_value: Optional[str] = Field(
        None,
        description="Global search term (searches all columns)"
    )
    order_by: Optional[List[Dict[str, str]]] = Field(
        None,
        description="List of {column, order} dicts for sorting",
        examples=[[{"column": "gene_name", "order": "ASC"}]]
    )
    filters: Optional[List[Dict[str, str]]] = Field(
        None,
        description="List of column filters [{column, value}]"
    )
    kb_env: str = Field(
        "appdev",
        description="KBase environment: appdev, ci, or prod"
    )


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
    pangenome_id: str = Field(
        ...,
        description="Pangenome ID to query",
        examples=["pg_default"]
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
    sort_column: Optional[str] = Field(
        None,
        description="Column to sort by"
    )
    sort_order: Optional[Literal["ASC", "DESC"]] = Field(
        "ASC",
        description="Sort direction"
    )
    search_value: Optional[str] = Field(
        None,
        description="Global search term"
    )
    query_filters: Optional[Dict[str, str]] = Field(
        None,
        description="Column-specific filters {column_name: filter_value}",
        examples=[{"gene_name": "kinase", "organism": "E. coli"}]
    )
    kb_env: str = Field(
        "appdev",
        description="KBase environment"
    )


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class TableColumn(BaseModel):
    """Information about a table column."""
    name: str = Field(..., description="Column name")
    type: Optional[str] = Field(None, description="Column data type")


class TableInfo(BaseModel):
    """Information about a database table."""
    name: str = Field(..., description="Table name")
    row_count: Optional[int] = Field(None, description="Number of rows")
    column_count: Optional[int] = Field(None, description="Number of columns")


class TableListResponse(BaseModel):
    """Response for listing tables in a pangenome database."""
    pangenome_id: str = Field(..., description="Pangenome identifier")
    tables: List[TableInfo] = Field(
        default_factory=list,
        description="List of available tables"
    )


class PangenomeInfo(BaseModel):
    """Information about a pangenome within a BERDLTables object."""
    pangenome_id: Optional[str] = Field(None, description="Unique pangenome identifier")
    pangenome_taxonomy: Optional[str] = Field(None, description="Taxonomic classification")
    user_genomes: List[str] = Field(
        default_factory=list,
        description="List of user-provided genome references"
    )
    berdl_genomes: List[str] = Field(
        default_factory=list,
        description="List of BERDL/Datalake genome identifiers"
    )
    handle_ref: Optional[str] = Field(
        None,
        description="Blobstore handle reference for SQLite database"
    )


class PangenomesResponse(BaseModel):
    """Response for listing pangenomes from a BERDLTables object."""
    pangenomes: List[PangenomeInfo] = Field(
        default_factory=list,
        description="List of available pangenomes"
    )
    pangenome_count: int = Field(
        0,
        description="Total number of pangenomes"
    )
    auto_selected: Optional[str] = Field(
        None,
        description="Auto-selected pangenome ID when only one exists"
    )


class TableDataResponse(BaseModel):
    """
    Response for table data queries.
    
    Includes the data, metadata, and performance metrics.
    """
    headers: List[str] = Field(
        ...,
        description="Column names in order"
    )
    data: List[List[str]] = Field(
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
    pangenome_id: str = Field(
        ...,
        description="Pangenome identifier"
    )
    response_time_ms: float = Field(
        ...,
        description="Total response time in milliseconds"
    )
    db_query_ms: Optional[float] = Field(
        None,
        description="Database query time in milliseconds"
    )
    conversion_ms: Optional[float] = Field(
        None,
        description="Data conversion time in milliseconds"
    )
    source: Optional[str] = Field(
        None,
        description="Data source (Cache or Downloaded)"
    )
    cache_file: Optional[str] = Field(
        None,
        description="Path to cached file"
    )
    sqlite_file: Optional[str] = Field(
        None,
        description="Path to SQLite database"
    )


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