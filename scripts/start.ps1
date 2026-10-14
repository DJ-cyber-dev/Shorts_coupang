$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if ((Test-Path .tools/models) -and -not $env:SHORTS_MODEL_DIR) {
    $env:SHORTS_MODEL_DIR = (Resolve-Path .tools/models).Path
}
if ((Test-Path .tools/runtime.json) -and -not $env:SHORTS_JS_RUNTIME) {
    $runtimeSettings = Get-Content .tools/runtime.json -Raw | ConvertFrom-Json
    if ($runtimeSettings.node -and (Test-Path -LiteralPath $runtimeSettings.node)) {
        $env:SHORTS_JS_RUNTIME = $runtimeSettings.node
    }
}
$localFFmpeg = Get-ChildItem .tools/ffmpeg -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($localFFmpeg -and -not $env:FFMPEG_BINARY) { $env:FFMPEG_BINARY = $localFFmpeg.FullName }
$localFFprobe = Get-ChildItem .tools/ffmpeg -Recurse -Filter ffprobe.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($localFFprobe -and -not $env:FFPROBE_BINARY) { $env:FFPROBE_BINARY = $localFFprobe.FullName }
& ./.venv/Scripts/python.exe -m shorts_studio.ui.desktop
if ($LASTEXITCODE -ne 0) { throw "Application failed to start." }
