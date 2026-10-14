param([string]$Python = "py")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required." }
New-Item -ItemType Directory -Force .tools/models | Out-Null
$env:SHORTS_MODEL_DIR = (Resolve-Path .tools/models).Path
& ./.venv/Scripts/python.exe -m pip install -e '.[secrets,text]'
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& ./.venv/Scripts/python.exe -m shorts_studio.text_removal.worker --prepare
if ($LASTEXITCODE -ne 0) { throw "Text detector model setup failed." }
Write-Host "Ready. Install FFmpeg/ffprobe, then run scripts/start.ps1."
