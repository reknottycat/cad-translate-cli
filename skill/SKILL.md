---
name: cad-translation-dev
description: CAD Translation System development, build, and release assistant. Use when working on the CAD Translation System project for: (1) Building or releasing the scale_release runtime bundle, (2) Modifying backend (FastAPI) or frontend (React) code, (3) Performing security audits on the release bundle, (4) Configuring LLM providers or translation parameters, (5) Debugging translation pipeline issues, (6) Adding new CAD converter backends or insertion modes, (7) Any development, testing, or maintenance task within this project.
---

# CAD Translation System — Development Skill

## Project at a Glance

A CAD drawing translation system with three runtime surfaces:
- **Web**: React 18 + Vite frontend, FastAPI backend
- **CLI**: `cli-anything-cad` installable package in `agent-harness/`
- **Desktop GUI** (legacy): `trans_CAD_gui_V1.0/`

**Trusted source**: Only `backend/` and `frontend/` are live source. `scale_release/` is a build artifact — never edit directly.

## Critical Paths

| Task | Entry Point |
|------|-------------|
| Start backend | `backend/run_server.py` or `uvicorn app.main:app --reload` |
| Start frontend | `cd frontend && npm run dev` |
| Start Celery | `backend/run_celery.py` |
| Build release | `scripts/build_scale.ps1` |
| Build frontend dist | `cd frontend && npm run build` |
| API docs | `http://localhost:8000/api/docs` |
| Runtime config | `~/.config/cli-anything-cad/config.json` |

## Development Workflow

### 1. Backend Change

1. Edit files under `backend/app/`
2. Restart `run_server.py` (or rely on `--reload`)
3. Test via Swagger UI at `/api/docs`
4. Run tests: `python -m pytest tests/backend/ -v`

### 2. Frontend Change

1. Edit files under `frontend/src/`
2. Vite dev server hot-reloads automatically
3. Type-check: `cd frontend && npx tsc --noEmit`
4. Build for release: `cd frontend && npm run build`

### 3. Build Release Bundle

```powershell
# Full rebuild (includes frontend build)
powershell -ExecutionPolicy Bypass -File scripts/build_scale.ps1

# Skip frontend build if already built
powershell -ExecutionPolicy Bypass -File scripts/build_scale.ps1 -SkipFrontendBuild
```

Produces `scale_release/` + `scale_release.zip`.

### 4. Security Audit Release

Run the audit script and manually verify results:

```powershell
. .agents/skills/cad-translation-dev/scripts/security-audit.ps1
```

Or run checks manually — see [references/security-checklist.md](references/security-checklist.md).

**Must verify**:
- No `.db` files in `scale_release/`
- No `node_modules` in `scale_release/`
- No `runtime_config.local.json` (user config) in `scale_release/`
- No `.env` files (except `.env.example`)
- No hardcoded API keys in any `scale_release/` file

### 5. Update Release After Backend/Frontend Changes

1. Build frontend: `cd frontend && npm run build`
2. Delete old `scale_release/` and `scale_release.zip`
3. Run `scripts/build_scale.ps1`
4. Run security audit
5. Remove any leaked files the script missed
6. Commit `scale_release/` and `scale_release.zip`

## Code Standards

- **Module limit**: 800 lines max per file (project rule in `.trae/rules/project_rules.md`)
- **Python**: PEP 8 + type annotations (`from __future__ import annotations`)
- **Frontend**: PascalCase components, camelCase variables/functions
- **After config changes**: Update `AGENTS.md` if relevant

## Key Configuration

| Config | Location | Purpose |
|--------|----------|---------|
| Static env | `backend/.env` | DB, Redis, JWT, converter paths |
| Runtime config | `~/.config/cli-anything-cad/config.json` | LLM provider, model, API keys |
| Provider presets | `backend/app/config.py` | Built-in 10+ vendor presets |

## Reference Documents

- **Project layout**: [references/project-layout.md](references/project-layout.md) — directory/module navigation
- **Security checklist**: [references/security-checklist.md](references/security-checklist.md) — release audit items
- **API routes**: [references/api-routes.md](references/api-routes.md) — backend endpoint quick reference
