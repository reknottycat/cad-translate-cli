# API Routes Quick Reference

Base URL: `http://localhost:8000`

## Health & Docs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | App info + docs links |
| GET | `/api/health` | Health check (db, celery) |
| GET | `/api/docs` | Swagger UI |
| GET | `/api/redoc` | ReDoc |

## Translation (Modern)

Router: `backend/app/routers/translation.py`

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/translation/text` | Single text translation |
| POST | `/api/translation/batch` | Batch text translation |
| POST | `/api/translation/excel` | Excel file translation |
| GET | `/api/translation/config` | Get runtime translation config |
| POST | `/api/translation/config` | Update runtime translation config |
| GET | `/api/translation/providers` | List built-in LLM provider presets |

## CAD Pipeline

Router: `backend/app/api/routes/cad.py`

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/cad/extract` | Extract text from DWG/DXF → Excel |
| POST | `/api/cad/apply` | Apply translations from Excel → DXF |
| POST | `/api/cad/pipeline` | Full pipeline: upload → extract → translate → apply |
| GET | `/api/cad/download/{task_id}` | Download output file |
| GET | `/api/cad/tasks` | List backend CAD tasks |
| GET | `/api/cad/tasks/{task_id}` | Get task status/detail |
| POST | `/api/cad/tasks/{task_id}/resume` | Resume failed/cancelled task |
| POST | `/api/cad/tasks/{task_id}/cancel` | Cancel running task |
| DELETE | `/api/cad/tasks/{task_id}` | Delete task |

## Projects & Files

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/api/projects` | List / create projects |
| GET/PUT/DELETE | `/api/projects/{id}` | Project CRUD |
| POST | `/api/files/upload` | File upload |
| GET | `/api/files/{file_id}` | File download |

## Admin (guarded when `ENABLE_ADMIN_GUARD=true`)

| Method | Path | Guard |
|--------|------|-------|
| Various | Admin routes | `X-Admin-Token` or `Authorization: Bearer` |

## Config Service

Router: `backend/app/services/runtime_config_service.py` (no direct HTTP routes, used internally)

Key methods:
- `load()` — read from `~/.config/cli-anything-cad/config.json`
- `save(config)` — write back with API key masking
- `mask_api_key(key)` — `sk-ab...cd` format
- `resolve_provider_api_key(provider)` — check env → config → settings fallback
