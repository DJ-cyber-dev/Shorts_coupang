$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force .tools/models | Out-Null
$env:SHORTS_MODEL_DIR = (Resolve-Path .tools/models).Path
& ./.venv/Scripts/python.exe -m pip install -e '.[text]'
if ($LASTEXITCODE -ne 0) { throw 'Text removal dependency installation failed.' }
& ./.venv/Scripts/python.exe -m shorts_studio.text_removal.worker --prepare
if ($LASTEXITCODE -ne 0) { throw 'Text detector model setup failed.' }
