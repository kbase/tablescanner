# API Examples

## Overview

Real-world examples for using the Config System API. All examples use `curl` but can be adapted to any HTTP client.

**Base URL**: `http://127.0.0.1:8000` (adjust for your environment)

---

## Authentication

All examples assume you have a KBase auth token. Set it as an environment variable:

```bash
export KB_TOKEN="your-kbase-token-here"
```

Or use in curl:
```bash
curl -H "Authorization: Bearer $KB_TOKEN" ...
```

---

## 1. Config Resolution

### Basic Resolution

Resolve config for a KBase object:

```bash
curl "http://127.0.0.1:8000/config/resolve/76990/7/2" \
  -H "Authorization: Bearer $KB_TOKEN"
```

**Response**:
```json
{
  "config": {
    "id": "berdl_tables",
    "name": "BERDL Tables",
    "version": "1.0.0",
    "tables": { ... }
  },
  "source": "published",
  "config_id": "abc123-def456",
  "fingerprint": "v1_auto_xyz789",
  "version": 1,
  "object_type": "KBaseGeneDataLakes.BERDLTables-1.0",
  "resolution_time_ms": 45.2
}
```

### Resolution with Fingerprint

Get exact match by database fingerprint:

```bash
curl "http://127.0.0.1:8000/config/resolve/76990/7/2?fingerprint=v1_auto_xyz789" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### Resolution with User Override

Get user-specific config:

```bash
curl "http://127.0.0.1:8000/config/resolve/76990/7/2?user_id=user:alice" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### Trigger AI Generation

Generate config if not found:

```bash
curl "http://127.0.0.1:8000/config/resolve/76990/7/2?trigger_generation=true" \
  -H "Authorization: Bearer $KB_TOKEN"
```

---

## 2. Creating Configs

### Create Draft Config

```bash
curl -X POST "http://127.0.0.1:8000/config" \
  -H "Authorization: Bearer $KB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "object",
    "source_ref": "76990/7/2",
    "config": {
      "id": "my_custom_config",
      "name": "My Custom Configuration",
      "version": "1.0.0",
      "tables": {
        "Genes": {
          "columns": {
            "gene_id": {
              "width": "150px",
              "sortable": true,
              "filterable": true
            },
            "gene_name": {
              "width": "200px",
              "transform": {
                "type": "link",
                "options": {
                  "urlTemplate": "https://ncbi.nlm.nih.gov/gene/{value}"
                }
              }
            }
          }
        }
      }
    },
    "change_summary": "Initial creation with custom column widths"
  }'
```

### Create Derived Config (Inheritance)

Create a config that extends another:

```bash
curl -X POST "http://127.0.0.1:8000/config" \
  -H "Authorization: Bearer $KB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "custom",
    "source_ref": "custom:my_variant",
    "extends_id": "abc123-def456",
    "config": {},
    "change_summary": "Derived from base config with customizations"
  }'
```

Then update with overlays:

```bash
curl -X PATCH "http://127.0.0.1:8000/config/{config_id}" \
  -H "Authorization: Bearer $KB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": {
      "tables": {
        "Genes": {
          "columns": {
            "gene_id": {
              "width": "200px",
              "pin": "left"
            }
          }
        }
      }
    },
    "change_summary": "Added left pin to gene_id column"
  }'
```

---

## 3. Lifecycle Management

### Propose Config for Review

```bash
curl -X POST "http://127.0.0.1:8000/config/{config_id}/propose" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### Publish Config

```bash
curl -X POST "http://127.0.0.1:8000/config/{config_id}/publish" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### Deprecate Config

```bash
curl -X POST "http://127.0.0.1:8000/config/{config_id}/deprecate" \
  -H "Authorization: Bearer $KB_TOKEN"
```

---

## 4. User Overrides

### Set User Override

```bash
curl -X POST "http://127.0.0.1:8000/config/user/override" \
  -H "Authorization: Bearer $KB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_ref": "76990/7/2",
    "override_config": {
      "tables": {
        "Genes": {
          "columns": {
            "gene_id": {
              "width": "250px",
              "pin": "left"
            },
            "gene_name": {
              "displayName": "Gene Symbol"
            }
          }
        }
      }
    },
    "priority": 50
  }'
```

### Get User Override

```bash
curl "http://127.0.0.1:8000/config/user/override/76990/7/2" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### Remove User Override

```bash
curl -X DELETE "http://127.0.0.1:8000/config/user/override/76990/7/2" \
  -H "Authorization: Bearer $KB_TOKEN"
```

---

## 5. Config Comparison

### Diff Two Configs

```bash
curl -X POST "http://127.0.0.1:8000/config/diff" \
  -H "Content-Type: application/json" \
  -d '{
    "config_id1": "abc123-def456",
    "config_id2": "xyz789-uvw012"
  }'
```

**Response**:
```json
{
  "added": {
    "tables": {
      "NewTable": { ... }
    }
  },
  "removed": {
    "tables": {
      "OldTable": { ... }
    }
  },
  "modified": {
    "tables": {
      "Genes": {
        "columns": {
          "gene_id": {
            "old": {"width": "150px"},
            "new": {"width": "200px"}
          }
        }
      }
    }
  },
  "unchanged": {
    "id": "berdl_tables",
    "name": "BERDL Tables"
  },
  "summary": "1 added, 1 removed, 1 modified",
  "has_changes": true
}
```

---

## 6. Config Testing

### Test Configuration

```bash
curl -X POST "http://127.0.0.1:8000/config/test" \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "abc123-def456",
    "test_types": ["schema", "data", "performance", "integration"],
    "db_path": "/path/to/test.db"
  }'
```

**Response**:
```json
{
  "config_id": "abc123-def456",
  "results": [
    {
      "test_type": "schema",
      "status": "passed",
      "details": {
        "db_tables": 5,
        "config_tables": 5,
        "matched_tables": 5
      },
      "execution_time_ms": 12.5,
      "errors": [],
      "warnings": []
    },
    {
      "test_type": "data",
      "status": "warning",
      "details": {
        "tested_tables": 3,
        "total_tables": 5
      },
      "execution_time_ms": 45.2,
      "errors": [],
      "warnings": ["Table Metadata_Conditions is empty"]
    }
  ],
  "overall_status": "warning",
  "total_time_ms": 57.7
}
```

---

## 7. Listing Configs

### List All Published Configs

```bash
curl "http://127.0.0.1:8000/config/list?state=published" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### List Builtin Configs

```bash
curl "http://127.0.0.1:8000/config/list?source_type=builtin&state=published" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### List Configs by Object Type

```bash
curl "http://127.0.0.1:8000/config/list?object_type=KBaseGeneDataLakes.BERDLTables-1.0" \
  -H "Authorization: Bearer $KB_TOKEN"
```

### Paginated Listing

```bash
curl "http://127.0.0.1:8000/config/list?page=2&per_page=10" \
  -H "Authorization: Bearer $KB_TOKEN"
```

---

## 8. AI Integration

### Submit AI Proposal

```bash
curl -X POST "http://127.0.0.1:8000/config/ai/propose" \
  -H "Authorization: Bearer $KB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Add UniRef links to genome_features table",
    "target_source_ref": "76990/7/2",
    "target_tables": ["genome_features"],
    "proposed_changes": {
      "tables": {
        "genome_features": {
          "columns": {
            "uniref_90": {
              "transform": {
                "type": "link",
                "options": {
                  "urlTemplate": "https://www.uniprot.org/uniref/{value}"
                }
              }
            }
          }
        }
      }
    },
    "reasoning": "UniRef IDs should be clickable links to UniProt",
    "confidence": 0.95,
    "requires_human_review": true
  }'
```

### Validate Config

```bash
curl -X POST "http://127.0.0.1:8000/config/ai/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "id": "test_config",
      "name": "Test",
      "version": "1.0.0",
      "tables": {
        "Genes": {
          "columns": {
            "gene_id": {"width": "150px"}
          }
        }
      }
    },
    "strict": false
  }'
```

---

## 9. Complete Workflow Example

### End-to-End Config Creation and Publishing

```bash
# 1. Create draft config
CONFIG_ID=$(curl -X POST "http://127.0.0.1:8000/config" \
  -H "Authorization: Bearer $KB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "object",
    "source_ref": "76990/7/2",
    "config": { ... },
    "change_summary": "Initial draft"
  }' | jq -r '.id')

# 2. Test the config
curl -X POST "http://127.0.0.1:8000/config/test" \
  -H "Content-Type: application/json" \
  -d "{
    \"config_id\": \"$CONFIG_ID\",
    \"test_types\": [\"schema\", \"data\", \"integration\"]
  }"

# 3. Propose for review
curl -X POST "http://127.0.0.1:8000/config/$CONFIG_ID/propose" \
  -H "Authorization: Bearer $KB_TOKEN"

# 4. Publish (after review)
curl -X POST "http://127.0.0.1:8000/config/$CONFIG_ID/publish" \
  -H "Authorization: Bearer $KB_TOKEN"

# 5. Verify it's available via resolve
curl "http://127.0.0.1:8000/config/resolve/76990/7/2" \
  -H "Authorization: Bearer $KB_TOKEN"
```

---

## 10. Python Client Example

```python
import requests

BASE_URL = "http://127.0.0.1:8000"
TOKEN = "your-kbase-token"

headers = {"Authorization": f"Bearer {TOKEN}"}

# Resolve config
response = requests.get(
    f"{BASE_URL}/config/resolve/76990/7/2",
    headers=headers,
    params={"fingerprint": "v1_auto_xyz789"}
)
config = response.json()

# Create config
create_response = requests.post(
    f"{BASE_URL}/config",
    headers=headers,
    json={
        "source_type": "object",
        "source_ref": "76990/7/2",
        "config": {
            "id": "my_config",
            "name": "My Config",
            "version": "1.0.0",
            "tables": {}
        },
        "change_summary": "Created via Python"
    }
)
config_id = create_response.json()["id"]

# Publish
requests.post(
    f"{BASE_URL}/config/{config_id}/publish",
    headers=headers
)
```

---

## 11. JavaScript/TypeScript Example

```typescript
const BASE_URL = 'http://127.0.0.1:8000';
const TOKEN = 'your-kbase-token';

async function resolveConfig(sourceRef: string) {
  const response = await fetch(
    `${BASE_URL}/config/resolve/${sourceRef}`,
    {
      headers: {
        'Authorization': `Bearer ${TOKEN}`
      }
    }
  );
  return await response.json();
}

async function createConfig(config: any) {
  const response = await fetch(`${BASE_URL}/config`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      source_type: 'object',
      source_ref: '76990/7/2',
      config,
      change_summary: 'Created via TypeScript'
    })
  });
  return await response.json();
}

// Usage
const config = await resolveConfig('76990/7/2');
console.log('Config source:', config.source);
```

---

## Error Handling

All endpoints return standard HTTP status codes:

- `200 OK` - Success
- `400 Bad Request` - Invalid request
- `401 Unauthorized` - Missing or invalid token
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

Error responses include a `detail` field:

```json
{
  "detail": "Config not found: abc123"
}
```

---

## Rate Limiting

For production deployments, consider rate limiting:
- Config resolution: 100 requests/minute
- Config creation: 10 requests/minute
- Config testing: 5 requests/minute

---

## Best Practices

1. **Always use fingerprints** for exact matching when available
2. **Test before publishing** to catch issues early
3. **Use inheritance** for related configs to reduce duplication
4. **Set user overrides** for personalization, not base configs
5. **Monitor resolution times** - should be < 500ms
6. **Cache resolved configs** on the client side
7. **Handle fallbacks** gracefully when API is unavailable

---

**See Also**:
- [Config Control Plane Documentation](CONFIG_CONTROL_PLANE.md)
- [Migration Guide](MIGRATION_GUIDE.md)
- [Admin Guide](ADMIN_GUIDE.md)
