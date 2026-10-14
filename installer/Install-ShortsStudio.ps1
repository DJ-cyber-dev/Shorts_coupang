param([switch]$NoShortcut)
$ErrorActionPreference = "Stop"
$sourceApp = Join-Path $PSScriptRoot "ShortsStudio"
$sourceModels = Join-Path $PSScriptRoot "models"
if (-not (Test-Path -LiteralPath (Join-Path $sourceApp "ShortsStudio.exe"))) {
    throw "압축을 해제한 ShortsStudioPortable 폴더에서 실행하세요."
}
$installDir = Join-Path $env:LOCALAPPDATA "Programs\ShortsStudio"
$modelDir = Join-Path $env:LOCALAPPDATA "ShortsStudio\models"
New-Item -ItemType Directory -Force $installDir, $modelDir | Out-Null
Copy-Item -Path (Join-Path $sourceApp "*") -Destination $installDir -Recurse -Force
Copy-Item -Path (Join-Path $sourceModels "*") -Destination $modelDir -Recurse -Force
$uninstaller = Join-Path $installDir "Uninstall-ShortsStudio.ps1"
if (-not $NoShortcut) {
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Shorts Studio"
    New-Item -ItemType Directory -Force $startMenu | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $startMenu "Shorts Studio.lnk"))
    $shortcut.TargetPath = Join-Path $installDir "ShortsStudio.exe"
    $shortcut.WorkingDirectory = $installDir
    $shortcut.Save()
    $uninstallShortcut = $shell.CreateShortcut((Join-Path $startMenu "Shorts Studio 제거.lnk"))
    $uninstallShortcut.TargetPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $uninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$uninstaller`""
    $uninstallShortcut.Save()
}
Write-Host "설치 완료: $(Join-Path $installDir 'ShortsStudio.exe')"
