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
    object_type: str | None = Field(None, description="KBase object type", examples=["KBaseGeneDataLakes.BERDLTables-1.0"])
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
# CONFIG GENERATION MODELS
# =============================================================================


class ColumnInferenceResponse(BaseModel):
    """AI-inferred column characteristics."""
    column: str = Field(..., description="Column name")
    data_type: str = Field(..., description="Inferred data type")
    display_name: str = Field(..., description="Human-readable display name")
    categories: list[str] = Field(default_factory=list, description="Category groupings")
    transform: dict | None = Field(None, description="Rendering transformation")
    width: str = Field("auto", description="Column width")
    pin: Literal["left", "right"] | None = Field(None, description="Pin position")
    sortable: bool = Field(True, description="Enable sorting")
    filterable: bool = Field(True, description="Enable filtering")
    copyable: bool = Field(False, description="Show copy button")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Inference confidence")
    source: Literal["rules", "ai", "hybrid"] = Field("rules", description="Inference source")
    reasoning: str = Field("", description="Explanation of inference")


class ConfigGenerationResponse(BaseModel):
    """Response from config generation endpoint."""
    # Core fields
    status: Literal["generated", "cached", "fallback", "error"] = Field(
        ..., 
        description="Generation status: generated (new), cached (from cache), fallback (builtin), error"
    )
    fingerprint: str = Field(..., description="Database fingerprint for caching")
    config_url: str = Field(..., description="URL to retrieve generated config")
    config: dict = Field(..., description="Full DataTypeConfig JSON")
    
    # Fallback metadata
    fallback_used: bool = Field(
        False,
        description="Whether a fallback config was used instead of AI generation"
    )
    fallback_reason: str | None = Field(
        None,
        description="Reason for fallback: ai_unavailable, generation_failed, object_type_matched"
    )
    config_source: Literal["ai", "rules", "cache", "builtin", "error"] = Field(
        "rules",
        description="Source of the configuration"
    )
    
    # Schema information (viewer can use directly)
    db_schema: dict | None = Field(
        None,
        alias="schema",
        description="Simple schema: {table_name: {column: type}}"
    )
    table_schemas: dict | None = Field(
        None,
        description="Full PRAGMA table_info per table"
    )
    
    # Statistics
    tables_analyzed: int = Field(..., description="Number of tables analyzed")
    columns_inferred: int = Field(..., description="Number of columns inferred")
    total_rows: int = Field(0, description="Total rows across all tables")
    
    # AI provider info
    ai_provider_used: str | None = Field(None, description="AI provider that was used")
    ai_available: bool = Field(True, description="Whether AI was available")
    ai_error: str | None = Field(None, description="Error message if AI failed")
    
    # Performance
    generation_time_ms: float = Field(..., description="Time to generate config in ms")
    cache_hit: bool = Field(..., description="Whether config was from cache")
    
    # Object metadata
    object_type: str | None = Field(None, description="KBase object type")
    object_ref: str | None = Field(None, description="Object reference (ws/obj/ver)")
    
    # Versioning
    api_version: str = Field("2.0", description="API version for compatibility")


class ProviderStatusResponse(BaseModel):
    """Status of an AI provider."""
    name: str = Field(..., description="Provider name")
    available: bool = Field(..., description="Whether provider is available")
    priority: int = Field(..., description="Provider priority (lower = higher)")
    error: str | None = Field(None, description="Error message if unavailable")


# =============================================================================
# CONFIG CONTROL PLANE MODELS
# =============================================================================


class ConfigState(str, Enum):
    """Lifecycle states for configuration records."""
    DRAFT = "draft"
    PROPOSED = "proposed"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ConfigSourceType(str, Enum):
    """Types of configuration sources."""
    OBJECT = "object"
    HANDLE = "handle"
    BUILTIN = "builtin"
    CUSTOM = "custom"


class ConfigCreateRequest(BaseModel):
    """Request to create a new configuration."""
    source_type: ConfigSourceType = Field(..., description="Type of source")
    source_ref: str = Field(..., description="Reference (UPA, handle, or ID)")
    config: dict = Field(..., description="Full DataTypeConfig JSON")
    extends_id: str | None = Field(None, description="Parent config ID to inherit from")
    change_summary: str = Field("Initial creation", description="Description of changes")
    object_type: str | None = Field(None, description="KBase object type")
    fingerprint: str | None = Field(None, description="Database fingerprint")


class ConfigUpdateRequest(BaseModel):
    """Request to update an existing draft configuration."""
    config: dict | None = Field(None, description="Updated config (full replacement)")
    overlays: dict | None = Field(None, description="Delta overlays to merge")
    change_summary: str = Field(..., description="Description of changes")


class ConfigRecord(BaseModel):
    """Full configuration record from database."""
    id: str = Field(..., description="Unique config ID")
    source_type: ConfigSourceType = Field(..., description="Type of source")
    source_ref: str = Field(..., description="Source reference")
    fingerprint: str | None = Field(None, description="Database fingerprint")
    version: int = Field(1, description="Version number")
    state: ConfigState = Field(ConfigState.DRAFT, description="Lifecycle state")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_by: str = Field(..., description="Creator identifier")
    published_at: datetime | None = Field(None, description="Publication timestamp")
    published_by: str | None = Field(None, description="Publisher identifier")
    config: dict = Field(..., description="Full DataTypeConfig JSON")
    extends_id: str | None = Field(None, description="Parent config ID")
    overlays: dict | None = Field(None, description="Delta overlays from parent")
    object_type: str | None = Field(None, description="KBase object type")
    ai_provider: str | None = Field(None, description="AI provider that generated config")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    generation_time_ms: float | None = Field(None, description="Generation time in ms")
    change_summary: str | None = Field(None, description="Latest change summary")
    change_author: str | None = Field(None, description="Latest change author")


class ConfigListResponse(BaseModel):
    """Paginated response for listing configurations."""
    configs: list[ConfigRecord] = Field(default_factory=list)
    total: int = Field(..., description="Total number of matching configs")
    page: int = Field(1, ge=1, description="Current page number")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")


class ConfigResolveResponse(BaseModel):
    """Response from config resolution endpoint."""
    config: dict = Field(..., description="Resolved DataTypeConfig")
    source: Literal["user_override", "published", "generated", "builtin", "default"] = Field(
        ..., description="Resolution source"
    )
    config_id: str | None = Field(None, description="Config record ID if from database")
    fingerprint: str | None = Field(None, description="Database fingerprint")
    version: int | None = Field(None, description="Config version")
    object_type: str | None = Field(None, description="KBase object type")
    resolution_time_ms: float = Field(..., description="Resolution time in ms")


class AIProposalRequest(BaseModel):
    """AI agent proposal for configuration changes."""
    intent: str = Field(..., description="Natural language description of intent")
    target_config_id: str | None = Field(None, description="Existing config ID to modify")
    target_source_ref: str | None = Field(None, description="Source ref for new config")
    target_tables: list[str] = Field(default_factory=list, description="Tables to affect")
    proposed_changes: dict = Field(..., description="Proposed config or overlay")
    reasoning: str = Field("", description="AI reasoning for changes")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="AI confidence")
    requires_human_review: bool = Field(True, description="AI self-assessment")


class AIProposalResponse(BaseModel):
    """Response to AI config proposal."""
    status: Literal["accepted", "needs_revision", "rejected"] = Field(
        ..., description="Proposal status"
    )
    proposal_id: str = Field(..., description="Unique proposal ID for tracking")
    config_id: str | None = Field(None, description="Created/updated config ID")
    validation_errors: list[str] = Field(default_factory=list, description="Validation issues")
    suggestions: list[str] = Field(default_factory=list, description="Improvement suggestions")
    diff_summary: str | None = Field(None, description="Summary of changes")


class ConfigValidationRequest(BaseModel):
    """Request to validate a configuration."""
    config: dict = Field(..., description="Config to validate")
    strict: bool = Field(False, description="Enable strict validation")


class ConfigValidationResponse(BaseModel):
    """Response from config validation."""
    valid: bool = Field(..., description="Whether config is valid")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")


# =============================================================================
# USER OVERRIDES MODELS
# =============================================================================


class UserOverrideRequest(BaseModel):
    """Request to set a user override."""
    source_ref: str = Field(..., description="Source reference")
    override_config: dict = Field(..., description="Partial or full config override")
    priority: int = Field(100, ge=1, le=1000, description="Override priority (lower = higher)")


class UserOverrideResponse(BaseModel):
    """Response for user override operations."""
    user_id: str = Field(..., description="User identifier")
    source_ref: str = Field(..., description="Source reference")
    override_config: dict = Field(..., description="Override configuration")
    priority: int = Field(..., description="Override priority")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# =============================================================================
# CONFIG DIFF MODELS
# =============================================================================


class ConfigDiffRequest(BaseModel):
    """Request to diff two configs."""
    config_id1: str = Field(..., description="First config ID")
    config_id2: str | None = Field(None, description="Second config ID (or use version)")
    version1: int | None = Field(None, description="First version number")
    version2: int | None = Field(None, description="Second version number")


class ConfigDiffResponse(BaseModel):
    """Response from config diff."""
    added: dict = Field(default_factory=dict, description="Added fields")
    removed: dict = Field(default_factory=dict, description="Removed fields")
    modified: dict = Field(default_factory=dict, description="Modified fields")
    unchanged: dict = Field(default_factory=dict, description="Unchanged fields")
    summary: str = Field(..., description="Human-readable summary")
    has_changes: bool = Field(..., description="Whether any changes exist")


# =============================================================================
# CONFIG TESTING MODELS
# =============================================================================


class ConfigTestRequest(BaseModel):
    """Request to test a configuration."""
    config_id: str = Field(..., description="Config to test")
    test_types: list[Literal["schema", "data", "performance", "integration"]] = Field(
        default_factory=lambda: ["schema", "data", "performance"],
        description="Types of tests to run"
    )
    db_path: str | None = Field(None, description="Path to test database (optional)")


class TestResultDetail(BaseModel):
    """Individual test result."""
    test_type: Literal["schema", "data", "performance", "integration"] = Field(..., description="Test type")
    status: Literal["passed", "failed", "warning"] = Field(..., description="Test status")
    details: dict = Field(default_factory=dict, description="Test details")
    execution_time_ms: float = Field(..., description="Execution time")
    errors: list[str] = Field(default_factory=list, description="Errors found")
    warnings: list[str] = Field(default_factory=list, description="Warnings found")


class ConfigTestResponse(BaseModel):
    """Response from config testing."""
    config_id: str = Field(..., description="Tested config ID")
    results: list[TestResultDetail] = Field(..., description="Test results")
    overall_status: Literal["passed", "failed", "warning"] = Field(..., description="Overall status")
    total_time_ms: float = Field(..., description="Total test execution time")


# =============================================================================
# DEVELOPER CONFIG MODELS
# =============================================================================


class DeveloperConfigInfo(BaseModel):
    """Information about a developer-editable config file."""
    filename: str = Field(..., description="Config filename")
    config_id: str = Field(..., description="Config ID")
    name: str = Field(..., description="Config name")
    version: str = Field(..., description="Config version")
    object_types: list[str] = Field(default_factory=list, description="Matching object types")
    sync_status: dict = Field(..., description="Sync status with Control Plane")
    last_modified: str = Field(..., description="File last modified timestamp")
    file_path: str = Field(..., description="Full file path")


class DeveloperConfigUpdateRequest(BaseModel):
    """Request to update a developer config."""
    config: dict = Field(..., description="Updated config JSON")
    sync_to_control_plane: bool = Field(True, description="Sync to Control Plane after update")
    auto_publish: bool = Field(False, description="Auto-publish after sync")


class DeveloperConfigSyncResponse(BaseModel):
    """Response from config sync operation."""
    status: Literal["synced", "unchanged", "error"] = Field(..., description="Sync status")
    config_id: str | None = Field(None, description="Config ID in Control Plane")
    state: str | None = Field(None, description="Config state")
    version: int | None = Field(None, description="Config version")
    message: str = Field(..., description="Status message")


class DeveloperConfigPreviewResponse(BaseModel):
    """Response from config preview."""
    filename: str = Field(..., description="Config filename")
    config: dict = Field(..., description="Config JSON")
    object_types: list[str] = Field(default_factory=list, description="Matching object types")
    sync_status: dict = Field(..., description="Sync status")
    tables: list[str] = Field(default_factory=list, description="Table names")
    table_count: int = Field(..., description="Number of tables")
    resolution: dict | None = Field(None, description="Resolution preview if source_ref provided")