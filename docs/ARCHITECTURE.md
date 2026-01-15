# TableScanner Architecture

## Overview

TableScanner is a microservice that provides filtered and paginated access to tabular data stored in KBase. It generates DataTables Viewer configurations using AI for new data types and sends them to DataTables Viewer for storage and management.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TableScanner Service                       │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  API Layer (FastAPI)                                 │    │
│  │  - Data access endpoints                              │    │
│  │  - Config generation endpoints                        │    │
│  └──────────────────┬──────────────────────────────────┘    │
│                      │                                        │
│  ┌───────────────────▼──────────────────────────────────┐    │
│  │  Services Layer                                       │    │
│  │  - Config Generator (AI-powered)                      │    │
│  │  - Config Registry (tracks existing configs)         │    │
│  │  - Viewer Client (sends to DataTables Viewer)       │    │
│  │  - Schema Analyzer                                    │    │
│  │  - AI Provider                                        │    │
│  └──────────────────┬───────────────────────────────────┘    │
│                      │                                        │
│  ┌───────────────────▼──────────────────────────────────┐    │
│  │  Data Layer                                           │    │
│  │  - KBase Workspace API                                │    │
│  │  - KBase Blobstore                                    │    │
│  │  - Local SQLite cache                                 │    │
│  └───────────────────────────────────────────────────────┘    │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            │ HTTP API
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              DataTables Viewer                               │
│                                                               │
│  - Receives generated configs                                │
│  - Stores configs in database                                 │
│  - Allows developer editing                                  │
│  - Resolves configs for rendering                            │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. API Layer (`app/routes.py`)

**Data Access Endpoints:**
- `GET /object/{ws_ref}/tables` - List tables in a KBase object
- `GET /object/{ws_ref}/tables/{table}/data` - Query table data
- `GET /object/{ws_ref}/tables/{table}/schema` - Get table schema
- `POST /table-data` - Programmatic table query

**Config Generation Endpoints:**
- `POST /object/{ws_ref}/config/generate` - Generate config with AI
- `GET /config/providers` - List available AI providers
- `GET /config/generated/{fingerprint}` - Get cached generated config
- `GET /config/cached` - List all cached configs

### 2. Config Generation Service (`app/services/config/config_generator.py`)

**Purpose**: Generates DataTables Viewer-compatible JSON configurations using AI.

**Process**:
1. Analyzes database schema
2. Infers column types and patterns
3. Uses AI to generate appropriate transforms and display options
4. Returns complete config JSON

**Key Features**:
- AI-powered column inference
- Automatic category assignment
- Transform suggestions (links, badges, etc.)
- Caching by database fingerprint

### 3. Config Registry (`app/services/config_registry.py`)

**Purpose**: Tracks which object types already have configs in DataTables Viewer.

**Functionality**:
- `has_config(object_type)` - Check if config exists
- `mark_has_config(object_type)` - Mark config as existing
- `mark_no_config(object_type)` - Mark config as missing
- `list_registered_types()` - List all registered types

**Storage**: SQLite database at `{CACHE_DIR}/config_registry.db`

### 4. Viewer Client (`app/services/viewer_client.py`)

**Purpose**: Sends generated configs to DataTables Viewer API.

**Methods**:
- `send_config(object_type, source_ref, config)` - Send config to viewer
- `check_config_exists(object_type)` - Check if config exists in viewer

**Configuration**: `VIEWER_API_URL` in settings (default: `http://localhost:3000/api`)

### 5. Schema Analyzer (`app/services/data/schema_analyzer.py`)

**Purpose**: Analyzes SQLite database schemas to extract table and column information.

**Output**: Table profiles with column metadata, types, and statistics.

### 6. AI Provider (`app/services/ai/ai_provider.py`)

**Purpose**: Abstraction layer for multiple AI backends.

**Supported Providers**:
- OpenAI (GPT-4o-mini, GPT-4)
- Argo Gateway (ANL internal)
- Ollama (local LLMs)
- Claude Code CLI
- Rules-only (fallback)

**Configuration**: Via environment variables (see `app/config.py`)

## Data Flow

### Config Generation Flow

```
1. Client Request
   POST /object/{ws_ref}/config/generate
   │
   ▼
2. Check Registry
   Does config exist for object_type?
   │
   ├─ Yes → Return "exists" status
   │
   └─ No → Continue
      │
      ▼
3. Download Database
   Fetch SQLite DB from KBase Blobstore
   │
   ▼
4. Analyze Schema
   Extract tables, columns, types
   │
   ▼
5. Generate Config (AI)
   - Infer column types
   - Suggest transforms
   - Assign categories
   - Generate complete config JSON
   │
   ▼
6. Send to DataTables Viewer
   POST /api/configs
   {
     "object_type": "...",
     "source_ref": "...",
     "config": { ... }
   }
   │
   ▼
7. Update Registry
   Mark object_type as having config
   │
   ▼
8. Return Response
   {
     "status": "generated_and_sent",
     "config": { ... },
     ...
   }
```

### Data Access Flow

```
1. Client Request
   GET /object/{ws_ref}/tables/{table}/data
   │
   ▼
2. Check Cache
   Is database cached locally?
   │
   ├─ Yes → Use cached DB
   │
   └─ No → Download from Blobstore
      │
      ▼
3. Create Indices
   Index all columns for fast queries
   │
   ▼
4. Execute Query
   SQL query with filters, pagination
   │
   ▼
5. Return Results
   JSON response with data and metadata
```

## Configuration

### Environment Variables

**KBase Authentication:**
- `KB_SERVICE_AUTH_TOKEN` - KBase authentication token

**Cache Settings:**
- `CACHE_DIR` - Directory for cached files (default: `/tmp/tablescanner_cache`)
- `CACHE_MAX_AGE_HOURS` - Cache expiration (default: 24)

**KBase Service URLs:**
- `WORKSPACE_URL` - Workspace service URL
- `BLOBSTORE_URL` - Blobstore service URL
- `KBASE_ENDPOINT` - Base KBase services URL

**AI Provider:**
- `AI_PROVIDER` - Preferred provider (auto, openai, argo, ollama, etc.)
- `OPENAI_API_KEY` - OpenAI API key
- `ARGO_USER` - Argo gateway username
- `OLLAMA_HOST` - Ollama server URL

**DataTables Viewer:**
- `VIEWER_API_URL` - Viewer API base URL (default: `http://localhost:3000/api`)

## DataTables Viewer Integration

### Required API Endpoints

DataTables Viewer must implement these endpoints:

#### 1. POST `/api/configs`

Receive and store AI-generated configs.

**Request:**
```json
{
  "object_type": "KBaseGeneDataLakes.BERDLTables-1.0",
  "source_ref": "76990/7/2",
  "config": {
    "id": "berdl_tables",
    "name": "BERDL Tables",
    "version": "1.0.0",
    "tables": { ... }
  },
  "source": "ai_generated"
}
```

**Response:**
```json
{
  "status": "stored",
  "config_id": "abc123",
  "object_type": "KBaseGeneDataLakes.BERDLTables-1.0"
}
```

#### 2. GET `/api/configs/check?object_type={object_type}`

Check if config exists.

**Response:**
```json
{
  "exists": true,
  "object_type": "KBaseGeneDataLakes.BERDLTables-1.0"
}
```

#### 3. GET `/api/configs?object_type={object_type}`

Get config for object type.

**Response:**
```json
{
  "config": { ... },
  "object_type": "KBaseGeneDataLakes.BERDLTables-1.0",
  "source": "ai_generated",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Config Storage

**Database Schema:**
```sql
CREATE TABLE configs (
    id TEXT PRIMARY KEY,
    object_type TEXT NOT NULL UNIQUE,
    source_ref TEXT,
    config_json TEXT NOT NULL,
    source TEXT DEFAULT 'ai_generated',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_configs_object_type ON configs(object_type);
```

### Config Resolution

When rendering tables, DataTables Viewer should resolve configs in this order:

1. **User override** (if authenticated)
2. **Config for object_type** (from database)
3. **Default config** (minimal fallback)

### Developer Editing

DataTables Viewer should provide:
- UI to view/edit configs
- API to update configs: `PUT /api/configs/{config_id}`
- Version history (optional but recommended)

## File Structure

```
app/
├── routes.py                    # API endpoints
├── models.py                    # Pydantic models
├── config.py                    # Settings
├── services/
│   ├── config/
│   │   ├── config_generator.py # AI config generation
│   │   └── __init__.py
│   ├── config_registry.py       # Track existing configs
│   ├── viewer_client.py         # Send to DataTables Viewer
│   ├── ai/
│   │   ├── ai_provider.py       # AI abstraction
│   │   └── prompts.py           # AI prompts
│   └── data/
│       ├── schema_analyzer.py   # Schema analysis
│       ├── fingerprint.py       # Database fingerprinting
│       └── type_inference.py    # Type inference
├── utils/
│   ├── workspace.py             # KBase Workspace client
│   ├── sqlite.py                # SQLite utilities
│   └── cache.py                 # Caching utilities
└── db/
    └── schema.sql               # Database schema (for registry)
```

## Key Design Decisions

### 1. Config Storage Separation

**Decision**: Configs are stored in DataTables Viewer, not TableScanner.

**Rationale**:
- Configs are viewer-specific
- Developers edit configs in viewer
- Viewer manages config lifecycle
- TableScanner only generates configs

### 2. Registry Pattern

**Decision**: Simple registry tracks which configs exist.

**Rationale**:
- Avoids regenerating existing configs
- Lightweight tracking mechanism
- No need for full config storage here

### 3. AI-First Generation

**Decision**: AI generates configs for new data types automatically.

**Rationale**:
- Handles new data types without manual config creation
- Learns from schema patterns
- Reduces developer burden

### 4. Caching Strategy

**Decision**: Cache databases locally, cache generated configs by fingerprint.

**Rationale**:
- Reduces KBase API calls
- Fast repeated access
- Fingerprint-based caching ensures consistency

## Error Handling

### Config Generation Failures

- **AI Provider Unavailable**: Falls back to rules-based generation
- **Database Download Fails**: Returns 500 error
- **Viewer API Unavailable**: Returns config but marks send as failed
- **Invalid Schema**: Returns 400 error with details

### Data Access Failures

- **Object Not Found**: Returns 404
- **Table Not Found**: Returns 404
- **Query Error**: Returns 500 with error details
- **Cache Corruption**: Automatically re-downloads

## Performance Considerations

### Caching

- Databases cached locally (24 hour TTL)
- Generated configs cached by fingerprint
- Registry cached in memory

### Database Indexing

- All columns indexed automatically on first access
- Indices persist across requests
- Fast filtering and sorting

### AI Generation

- Configs cached by database fingerprint
- Avoids regeneration for same schema
- AI calls only when needed

## Security

### Authentication

- KBase token required for data access
- Token passed via `Authorization` header
- Token validated by KBase services

### API Security

- No authentication required for public endpoints
- Config generation requires KBase token
- Viewer API should implement authentication

## Testing

### Unit Tests

- Service layer tests
- Config generator tests
- Registry tests

### Integration Tests

- End-to-end config generation
- Viewer client tests
- API endpoint tests

### Manual Testing

```bash
# Generate config
curl -X POST "http://127.0.0.1:8000/object/76990/7/2/config/generate" \
  -H "Authorization: Bearer $KB_TOKEN"

# List tables
curl "http://127.0.0.1:8000/object/76990/7/2/tables" \
  -H "Authorization: Bearer $KB_TOKEN"

# Get table data
curl "http://127.0.0.1:8000/object/76990/7/2/tables/Genes/data?limit=10" \
  -H "Authorization: Bearer $KB_TOKEN"
```

## Deployment

### Docker

```bash
docker compose up --build -d
```

### Development

```bash
bash scripts/dev.sh
```

### Environment Setup

1. Copy `.env.example` to `.env`
2. Set `KB_SERVICE_AUTH_TOKEN`
3. Configure AI provider (optional)
4. Set `VIEWER_API_URL` if viewer is on different host

## Monitoring

### Health Checks

- `/health` endpoint (if implemented)
- Database cache status
- AI provider availability

### Logging

- All operations logged
- Config generation tracked
- Viewer API calls logged
- Errors logged with stack traces

## Future Enhancements

### Potential Improvements

1. **Batch Config Generation**: Generate configs for multiple objects
2. **Config Templates**: Reusable config templates
3. **Config Validation**: Validate configs before sending
4. **Metrics**: Track generation success rates
5. **Webhooks**: Notify on config generation

### DataTables Viewer Enhancements

1. **Config Versioning**: Track config changes over time
2. **Config Sharing**: Share configs between users
3. **Config Marketplace**: Community-contributed configs
4. **Config Testing**: Test configs against real data
5. **Config Diff**: Compare config versions

## Summary

TableScanner is a focused service that:
- Provides data access to KBase tabular data
- Generates DataTables Viewer configs using AI
- Sends configs to DataTables Viewer for storage
- Tracks which configs exist to avoid regeneration

DataTables Viewer should:
- Receive and store configs via API
- Allow developers to edit configs
- Resolve configs when rendering tables
- Provide UI for config management

This separation of concerns keeps TableScanner simple and focused, while giving DataTables Viewer full control over config management and presentation.
