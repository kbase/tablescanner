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
    tables: list[TableInfo] = Field(
        default_factory=list,
        description="List of available tables",
        examples=[[
            {"name": "Genes", "row_count": 3356, "column_count": 18},
            {"name": "Metadata_Conditions", "row_count": 42, "column_count": 12}
        ]]
    )
    source: str | None = Field(None, description="Data source", examples=["Cache"])


class PangenomeInfo(BaseModel):
    """Information about a pangenome found in the SQLite file."""
    pangenome_taxonomy: str | None = Field(None, description="Taxonomy of the pangenome", examples=["Escherichia coli"])
    genome_count: int = Field(..., description="Number of genomes in the pangenome", examples=[42])
    source_berdl_id: str = Field(..., description="Source BERDL Table ID", examples=["76990/7/2"])
    user_genomes: list[str] = Field(
        default_factory=list,
        description="List of user-provided genome references",
        examples=[["76990/1/1", "76990/2/1"]]
    )
    berdl_genomes: list[str] = Field(
        default_factory=list,
        description="List of BERDL/Datalake genome identifiers",
        examples=[["GLM4:EC_G1", "GLM4:EC_G2"]]
    )
    handle_ref: str | None = Field(
        None,
        description="Blobstore handle reference for SQLite database",
        examples=["KBH_248028"]
    )


class PangenomesResponse(BaseModel):
    """Response for listing pangenomes from a BERDLTables object."""
    berdl_table_id: str | None = Field(None, description="BERDLTable object reference", examples=["76990/7/2"])
    pangenomes: list[PangenomeInfo] = Field(
        default_factory=list,
        description="List of available pangenomes",
        examples=[[
            {
                "pangenome_taxonomy": "Escherichia coli",
                "genome_count": 42,
                "source_berdl_id": "76990/7/2",
                "handle_ref": "KBH_248028"
            }
        ]]
    )
    pangenome_count: int = Field(
        1,
        description="Total number of pangenomes",
        examples=[1]
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