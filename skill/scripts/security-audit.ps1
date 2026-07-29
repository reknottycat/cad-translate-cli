# Security Audit for scale_release/
# Run from project root: . .agents/skills/cad-translation-dev/scripts/security-audit.ps1

param(
    [string]$ReleaseDir = "scale_release"
)

$ErrorActionPreference = "Stop"
$hasErrors = $false

function Write-Result($Label, $Pass, $Detail) {
    $icon = if ($Pass) { "PASS" } else { "FAIL" }
    $color = if ($Pass) { "Green" } else { "Red" }
    Write-Host "[$icon] $Label" -ForegroundColor $color
    if ($Detail) {
        Write-Host "      $Detail" -ForegroundColor Gray
    }
}

if (-not (Test-Path $ReleaseDir)) {
    Write-Error "Release directory not found: $ReleaseDir"
    exit 1
}

Write-Host ""
Write-Host "=== CAD Translation System Release Security Audit ==="
Write-Host "Target: $ReleaseDir"
Write-Host ""

# 1. Database files
$dbFiles = Get-ChildItem -Path $ReleaseDir -Recurse -Filter "*.db" -ErrorAction SilentlyContinue
Write-Result -Label "No .db files" -Pass ($dbFiles.Count -eq 0) -Detail ($dbFiles | ForEach-Object { $_.FullName })
if ($dbFiles.Count -gt 0) { $hasErrors = $true }

# 2. node_modules
$hasNode = Test-Path (Join-Path $ReleaseDir "node_modules")
Write-Result -Label "No node_modules" -Pass (-not $hasNode)
if ($hasNode) { $hasErrors = $true }

# 3. runtime_config.local.json
$rcLocal = Get-ChildItem -Path $ReleaseDir -Recurse -Filter "runtime_config.local.json" -ErrorAction SilentlyContinue
Write-Result -Label "No runtime_config.local.json" -Pass ($rcLocal.Count -eq 0) -Detail ($rcLocal | ForEach-Object { $_.FullName })
if ($rcLocal.Count -gt 0) { $hasErrors = $true }

# 4. .env files (excluding .env.example)
$envFiles = Get-ChildItem -Path $ReleaseDir -Recurse -Filter ".env" -ErrorAction SilentlyContinue
Write-Result -Label "No .env files" -Pass ($envFiles.Count -eq 0) -Detail ($envFiles | ForEach-Object { $_.FullName })
if ($envFiles.Count -gt 0) { $hasErrors = $true }

# 5. Hardcoded API keys in Python files
$keyPatterns = @(
    '=\s*"sk-[a-zA-Z0-9]{20,}"',
    '=\s*"ak-[a-zA-Z0-9]{20,}"',
    'api_key\s*[:=]\s*"[a-zA-Z0-9]{32,}"'
)
$pyFiles = Get-ChildItem -Path $ReleaseDir -Recurse -Filter "*.py" -ErrorAction SilentlyContinue
$leaks = @()
foreach ($file in $pyFiles) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    foreach ($pattern in $keyPatterns) {
        if ($content -match $pattern) {
            $leaks += "$($file.FullName): matched pattern"
            break
        }
    }
}
Write-Result -Label "No hardcoded API keys in .py" -Pass ($leaks.Count -eq 0) -Detail $leaks
if ($leaks.Count -gt 0) { $hasErrors = $true }

# 6. Test files
$testFiles = Get-ChildItem -Path $ReleaseDir -Recurse -Filter "test_*.py" -ErrorAction SilentlyContinue
Write-Result -Label "No test_*.py files" -Pass ($testFiles.Count -eq 0) -Detail ($testFiles | ForEach-Object { $_.FullName })
if ($testFiles.Count -gt 0) { $hasErrors = $true }

# 7. __pycache__
$pycaches = Get-ChildItem -Path $ReleaseDir -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue
Write-Result -Label "No __pycache__ dirs" -Pass ($pycaches.Count -eq 0) -Detail ($pycaches | ForEach-Object { $_.FullName })
if ($pycaches.Count -gt 0) { $hasErrors = $true }

# 8. frontend/src
$hasFrontendSrc = Test-Path (Join-Path $ReleaseDir "frontend\src")
Write-Result -Label "No frontend/src" -Pass (-not $hasFrontendSrc)
if ($hasFrontendSrc) { $hasErrors = $true }

# 9. Electron artifacts
$electronFiles = @("main.js", "preload.js", "package.json", "package-lock.json")
$foundElectron = @()
foreach ($f in $electronFiles) {
    if (Test-Path (Join-Path $ReleaseDir $f)) {
        $foundElectron += $f
    }
}
Write-Result -Label "No Electron artifacts in root" -Pass ($foundElectron.Count -eq 0) -Detail $foundElectron
if ($foundElectron.Count -gt 0) { $hasErrors = $true }

# 10. Top-level directory check
$expectedTop = @("backend", "docs", "frontend", "tools", "README.md", "requirements.txt", "start_delivery.bat")
$actualTop = Get-ChildItem -Path $ReleaseDir -Directory | Select-Object -ExpandProperty Name
$actualTop += Get-ChildItem -Path $ReleaseDir -File | Select-Object -ExpandProperty Name
$unexpected = $actualTop | Where-Object { $_ -notin $expectedTop }
Write-Result -Label "Top-level only expected items" -Pass ($unexpected.Count -eq 0) -Detail $unexpected
if ($unexpected.Count -gt 0) { $hasErrors = $true }

Write-Host ""
if ($hasErrors) {
    Write-Host "AUDIT FAILED — fix issues above before releasing." -ForegroundColor Red
    exit 1
} else {
    Write-Host "AUDIT PASSED — release is clean." -ForegroundColor Green
    exit 0
}
