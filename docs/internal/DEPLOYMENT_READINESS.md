# Deployment Readiness Assessment

**Date:** 2026-02-20  
**Version:** 2.2.0  
**Target:** Production Deployment (AppDev + Production)  

| Environment | URL |
|-------------|-----|
| **AppDev** | `https://appdev.kbase.us/services/berdl_table_scanner` |
| **Production** | `https://berdl.kbase.us/apis/dev_tablescanner` |

---

## Executive Summary

✅ **READY FOR DEPLOYMENT** — This release fixes a critical environment routing bug and adds multi-environment support.

### What Changed in v2.2.0

1. ✅ **Critical Fix: `kb_env` defaults** — All 15 hardcoded `"appdev"` defaults in routes, models, and utility functions have been replaced with `settings.KB_ENV`. The backend now correctly reads the `KB_ENV` environment variable set by the deployment.
2. ✅ **Production Support** — The `KBaseClient` endpoint map includes `prod`, `appdev`, and `ci` environments with correct URLs for workspace, shock, and handle services.
3. ✅ **All Tests Passing** — Unit tests verified with both `KB_ENV=prod` and `KB_ENV=appdev`.

### Bug That Was Fixed

Previously, every route defined `kb_env` with a hardcoded default:
```python
# BROKEN (v2.1):
kb_env: str = Query("appdev", ...)

# FIXED (v2.2):
kb_env: str = Query(settings.KB_ENV, ...)
```

Because the frontend never sent `kb_env` as a query parameter, the backend always defaulted to `"appdev"` regardless of the `KB_ENV` environment variable. This caused production deployments to call AppDev workspace URLs, resulting in auth failures and missing data.

---

## Pre-Deployment Checklist

### ✅ Code Requirements

- [x] **`kb_env` defaults fixed** in `routes.py` (7 endpoints), `workspace.py` (7 functions), `models.py` (1 model)
- [x] **Multi-Database Endpoints** (v2.1)
  - `GET /databases?upa={ws_ref}`
  - `GET /db/{db_name}/tables?upa={ws_ref}`
  - `GET /db/{db_name}/tables/{table}/data?upa={ws_ref}`
- [x] **Docker Configuration** — Dockerfile, docker-compose.yml, health check at `/health`
- [x] **Documentation Updated** — URLs corrected for production
- [x] **Testing** — Unit tests pass with `KB_ENV=prod` and `KB_ENV=appdev`

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| **`KB_ENV`** | **YES** | `appdev` | **CRITICAL.** Must be `prod` for production. Controls which KBase service URLs are used. |
| `CACHE_DIR` | No | `/tmp/tablescanner_cache` | Cache directory. Mount a persistent volume in production. |
| `CACHE_MAX_AGE_HOURS` | No | `24` | How long cached databases are valid. |
| `DEBUG` | No | `false` | Enable verbose logging. |
| `CORS_ORIGINS` | No | `["*"]` | Restrict in production (see examples below). |
| `KB_SERVICE_ROOT_PATH` | No | (empty) | Path prefix for proxy deployment. |
| `DOWNLOAD_TIMEOUT_SECONDS` | No | `30.0` | Timeout for downloading from KBase. |
| `KBASE_API_TIMEOUT_SECONDS` | No | `10.0` | Timeout for KBase API calls. |
| `MAX_UPLOAD_STORAGE_GB` | No | `10` | Total upload storage quota. |

### How `KB_ENV` Maps to Service URLs

| `KB_ENV` | Workspace URL | Shock URL | Handle URL |
|----------|---------------|-----------|------------|
| `appdev` | `https://appdev.kbase.us/services/ws` | `https://appdev.kbase.us/services/shock-api` | `https://appdev.kbase.us/services/handle_service` |
| `prod` | `https://kbase.us/services/ws` | `https://kbase.us/services/shock-api` | `https://kbase.us/services/handle_service` |
| `ci` | `https://ci.kbase.us/services/ws` | `https://ci.kbase.us/services/shock-api` | `https://ci.kbase.us/services/handle_service` |

---

## Deployment: Production (berdl.kbase.us)

### 1. Environment Configuration

```bash
KB_ENV=prod
CACHE_DIR=/data/tablescanner_cache
CACHE_MAX_AGE_HOURS=24
DEBUG=false
CORS_ORIGINS=["https://kbase.us","https://narrative.kbase.us","https://berdl.kbase.us"]
KB_SERVICE_ROOT_PATH=/apis/dev_tablescanner
```

### 2. Deploy Container

```bash
docker run -d \
  --name tablescanner \
  -p 8000:8000 \
  -e KB_ENV=prod \
  -e CORS_ORIGINS='["https://kbase.us","https://narrative.kbase.us","https://berdl.kbase.us"]' \
  -e KB_SERVICE_ROOT_PATH=/apis/dev_tablescanner \
  -v /data/tablescanner_cache:/tmp/tablescanner_cache \
  tablescanner:v2.2
```

### 3. Verify Deployment

```bash
# Health check
curl https://berdl.kbase.us/apis/dev_tablescanner/health

# Test database listing (requires prod token)
curl -H "Authorization: $KB_TOKEN" \
     "https://berdl.kbase.us/apis/dev_tablescanner/databases?upa=76990/7/2"

# Verify KB_ENV is set correctly in logs
curl "https://berdl.kbase.us/apis/dev_tablescanner/system/logs?limit=10"
```

---

## Deployment: AppDev (appdev.kbase.us)

### 1. Environment Configuration

```bash
KB_ENV=appdev
CACHE_DIR=/data/tablescanner_cache
CACHE_MAX_AGE_HOURS=24
DEBUG=false
CORS_ORIGINS=["https://appdev.kbase.us"]
KB_SERVICE_ROOT_PATH=/services/berdl_table_scanner
```

### 2. Deploy Container

```bash
docker run -d \
  --name tablescanner \
  -p 8000:8000 \
  -e KB_ENV=appdev \
  -e CORS_ORIGINS='["https://appdev.kbase.us"]' \
  -e KB_SERVICE_ROOT_PATH=/services/berdl_table_scanner \
  -v /data/tablescanner_cache:/tmp/tablescanner_cache \
  tablescanner:v2.2
```

---

## ⚠️ Nginx Configuration

Required for file uploads to work:

```nginx
# For berdl.kbase.us (production)
location /apis/dev_tablescanner/ {
    client_max_body_size 500M;
    proxy_request_buffering off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 60s;
    proxy_pass http://tablescanner-backend:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# For appdev.kbase.us
location /services/berdl_table_scanner/ {
    client_max_body_size 500M;
    proxy_request_buffering off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 60s;
    proxy_pass http://tablescanner-backend:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## API Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.2 | 2026-02-20 | **Critical fix**: `kb_env` defaults now read from `settings.KB_ENV` instead of hardcoded `"appdev"`. Production deployment support. |
| 2.1 | 2026-02-02 | Multi-database support, upload deduplication |
| 2.0 | 2026-01-28 | Streaming uploads, storage quotas |
| 1.0 | 2025-01-20 | Initial release |

---

## Rollback Plan

If issues occur:

```bash
docker stop tablescanner
docker run -d --name tablescanner -p 8000:8000 tablescanner:v2.1
```

No data migration needed (read-only service).

---

## Sign-Off

- [x] `kb_env` bug fixed (15 occurrences)
- [x] Unit tests passing (KB_ENV=prod and KB_ENV=appdev)
- [x] End-to-end test passing (local backend + local viewer + AppDev workspace)
- [x] Documentation updated (URLs, env vars, deployment steps)
- [x] `.env.example` updated with production examples
- [ ] Production deployment by Boris
- [ ] Production verification complete
