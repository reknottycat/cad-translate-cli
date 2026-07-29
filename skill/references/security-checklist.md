# Release Security Checklist

Run this checklist before every `scale_release` commit.

## Automated Checks

Run `scripts/security-audit.ps1` (or copy the checks below).

## Manual Verification

### 1. Database Files
- [ ] No `*.db` files anywhere in `scale_release/`
- Common leak: `scale_release/backend/cad_translation.db`
- Fix: `Remove-Item scale_release/backend/*.db -Force`

### 2. Node Modules
- [ ] No `node_modules/` directory in `scale_release/`
- Fix: `Remove-Item -Recurse -Force scale_release/node_modules`

### 3. Runtime User Config
- [ ] No `runtime_config.local.json` in `scale_release/`
- This file contains user API keys, target language, model preferences
- Fix: `Remove-Item scale_release/backend/config/runtime_config.local.json -Force`
- Keep `runtime_config.example.json` — it is safe (no real keys)

### 4. Environment Files
- [ ] No `.env` files (except `.env.example`)
- `.env.example` is safe — it contains only placeholders
- Fix: `Remove-Item scale_release/backend/.env -Force` (keep `.env.example`)

### 5. API Key Leaks
- [ ] No hardcoded keys in `scale_release/backend/app/config.py`
- Check pattern: `= "sk-..."` or `= "ak-..."` or long alphanumeric strings
- Safe: `Field(default="")` placeholders

### 6. Test Files
- [ ] No `test_*.py` files in `scale_release/`
- Build script excludes these, but verify manually

### 7. Source Code Leaks
- [ ] No `frontend/src/` in `scale_release/`
- [ ] No `__pycache__/` directories
- [ ] No `.pytest_cache/` directories

### 8. Electron Artifacts (if previously mixed)
- [ ] No `main.js`, `preload.js`, `package.json` in `scale_release/` root
- These are from old `electron_release` experiments

## Final Directory Structure Verification

`scale_release/` should contain **only**:

```
backend/
  app/
  config/
    runtime_config.example.json
  config_guide.md
  config_validator.py
  ... (other runtime files)
docs/modern/
frontend/dist/
tools/
README.md
requirements.txt
start_delivery.bat
```

## Post-Cleanup Verification Command

```powershell
cd scale_release
Get-ChildItem -Recurse -Filter "*.db"
Get-ChildItem -Recurse -Filter "runtime_config.local.json"
Get-ChildItem -Recurse -Filter ".env" | Where-Object { $_.Name -ne ".env.example" }
if (Test-Path "node_modules") { Write-Error "node_modules found!" }
```
