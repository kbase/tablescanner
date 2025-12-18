from __future__ import annotations
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


# =============================================================================
# RESPONSE MODELS
# =============================================================================




class TableInfo(BaseModel):
    """Information about a database table."""
    name: str = Field(..., description="Table name")
    row_count: int | None = Field(None, description="Number of rows")
    column_count: int | None = Field(None, description="Number of columns")


class TableListResponse(BaseModel):
    """Response for listing tables in a database."""
    tables: list[TableInfo] = Field(
        default_factory=list,
        description="List of available tables"
    )


class PangenomeInfo(BaseModel):
    """Information about a pangenome found in the SQLite file."""
    pangenome_taxonomy: str | None = Field(None, description="Taxonomy of the pangenome")
    genome_count: int = Field(..., description="Number of genomes in the pangenome")
    source_berdl_id: str = Field(..., description="Source BERDL Table ID")
    user_genomes: list[str] = Field(
        default_factory=list,
        description="List of user-provided genome references"
    )
    berdl_genomes: list[str] = Field(
        default_factory=list,
        description="List of BERDL/Datalake genome identifiers"
    )
    handle_ref: str | None = Field(
        None,
        description="Blobstore handle reference for SQLite database"
    )


class PangenomesResponse(BaseModel):
    """Response for listing pangenomes from a BERDLTables object."""
    pangenomes: list[PangenomeInfo] = Field(
        default_factory=list,
        description="List of available pangenomes"
    )
    pangenome_count: int = Field(
        0,
        description="Total number of pangenomes"
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