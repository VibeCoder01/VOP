param([string]$Python = "py")
$ErrorActionPreference = "Stop"
$vopRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $vopRoot
$vopManifest = Get-Content -LiteralPath (Join-Path $vopRoot "manifest.json") -Raw | ConvertFrom-Json
foreach ($vopFile in $vopManifest.files.PSObject.Properties) {
    $vopTarget = [System.IO.Path]::GetFullPath((Join-Path $vopRoot $vopFile.Name))
    if (-not $vopTarget.StartsWith($vopRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw "Manifest path escapes the release directory." }
    if ((Get-FileHash -LiteralPath $vopTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne $vopFile.Value) { throw "Release checksum mismatch." }
}
if (Test-Path -LiteralPath ".venv") { throw "Use a fresh directory for installation; .venv already exists." }
if ($Python -eq "py") { & $Python -3.11 -m venv .venv } else { & $Python -m venv .venv }
if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required. Install Python and retry." }
& .\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
$vopWheel = Get-ChildItem -LiteralPath $vopRoot -Filter "vop-*.whl"
if ($vopWheel.Count -ne 1) { throw "Expected exactly one VOP wheel." }
& .\.venv\Scripts\python.exe -m pip install --no-deps $vopWheel.FullName
if ($LASTEXITCODE -ne 0) { throw "VOP installation failed." }
& .\.venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency validation failed." }
& .\.venv\Scripts\python.exe tools\phase4_smoke.py
if ($LASTEXITCODE -ne 0) { throw "Release smoke failed." }
Write-Output "Installed. Run: .\.venv\Scripts\python.exe tools\run_dashboard.py"
