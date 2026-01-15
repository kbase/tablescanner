# Config System Documentation

## Overview

Unified configuration system supporting both **AI-generated configs** and **developer-edited configs** with versioning for new KBase data tables.

**Key Features**:
- Developer-editable JSON files (like `berdl_tables.json`)
- AI-powered config generation for new data
- Versioning and lifecycle management (Draft → Proposed → Published)
- Preview before syncing

---

## Core Concepts

### 1. Developer Configs (JSON Files)

**Location**: `app/configs/*.json`

**Purpose**: Developers edit these JSON files to customize how data is viewed.

**Files**:
- `berdl_tables.json` - For BERDL/Pangenome data
- `genome_data_tables.json` - For Genome Data Tables

**Workflow**:
```bash
# 1. Edit JSON file
vim app/configs/berdl_tables.json

# 2. Preview changes
curl "http://127.0.0.1:8000/config/developer/berdl_tables.json/preview"

# 3. Sync to system
python scripts/sync_developer_configs.py --filename berdl_tables.json
```

### 2. AI-Generated Configs

**Purpose**: Automatically generate configs for new data tables queried through KBase.

**Workflow**:
```bash
# Generate config for new data
curl -X POST "http://127.0.0.1:8000/object/76990/7/2/config/generate"
```

### 3. Versioning

All configs are versioned in the database:
- **Draft** → Work in progress, can be modified
- **Proposed** → Ready for review, read-only
- **Published** → Production-ready, available to consumers
- Full history and audit trail

---

## API Endpoints

### Developer Configs

- `GET /config/developer/list` - List all developer configs
- `GET /config/developer/{filename}` - Get config file
- `PUT /config/developer/{filename}` - Update config
- `POST /config/developer/{filename}/sync` - Sync to system
- `GET /config/developer/{filename}/preview` - Preview config

### Config Resolution

- `GET /config/resolve/{source_ref}` - Get best config for data source

### AI Generation

- `POST /object/{ws_ref}/config/generate` - Generate config via AI

### Config Management

- `POST /config` - Create new draft config
- `GET /config/{config_id}` - Get config by ID
- `PATCH /config/{config_id}` - Update draft config
- `POST /config/{config_id}/publish` - Publish config

---

## Resolution Priority

When resolving a config, the system tries in this order:

1. User override (if authenticated)
2. Published config (fingerprint match)
3. Published config (source_ref match)
4. Published builtin (from developer configs)
5. Fallback registry (static JSON)
6. AI generation
7. Default config

---

## Adding New Configs

### For New Data Types

1. **Create JSON file**:
   ```bash
   cat > app/configs/my_data_type.json << 'EOF'
   {
     "id": "my_data_type",
     "name": "My Data Type",
     "version": "1.0.0",
     "tables": {
       "MyTable": {
         "columns": {
           "id": {"width": "150px"}
         }
       }
     }
   }
   EOF
   ```

2. **Add object type mapping** in `app/configs/fallback_registry.py`:
   ```python
   FALLBACK_CONFIG_PATTERNS = {
       # ... existing ...
       r"MyApp\.MyType.*": "my_data_type.json",
   }
   ```

3. **Sync**:
   ```bash
   python scripts/sync_developer_configs.py --filename my_data_type.json
   ```

---

## Service Organization

```
app/services/
├── config/              # Config management
│   ├── config_store.py      # Database storage
│   ├── config_resolver.py   # Resolution logic
│   ├── developer_config.py  # Developer JSON files
│   └── config_generator.py  # AI generation
├── ai/                  # AI services
│   └── ai_provider.py
└── data/                # Data analysis
    ├── schema_analyzer.py
    ├── fingerprint.py
    └── type_inference.py
```

---

## Quick Reference

### Developer: Edit Config

```bash
vim app/configs/berdl_tables.json
python scripts/sync_developer_configs.py --filename berdl_tables.json
```

### AI: Generate Config

```bash
curl -X POST "http://127.0.0.1:8000/object/76990/7/2/config/generate"
```

### Resolve Config

```bash
curl "http://127.0.0.1:8000/config/resolve/76990/7/2"
```

---

## See Also

- [API Examples](API_EXAMPLES.md) - Usage examples
- [DataTables Viewer Integration](personal/datatable_upgrade/upgrade.md) - Integration guide
