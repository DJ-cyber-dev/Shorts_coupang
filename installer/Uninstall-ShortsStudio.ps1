$ErrorActionPreference = "Stop"
$installDir = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs\ShortsStudio"))
$expectedDir = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs\ShortsStudio"))
if (-not [string]::Equals($installDir, $expectedDir, [StringComparison]::OrdinalIgnoreCase)) {
    throw "설치 경로 확인에 실패하여 제거를 중단했습니다."
}
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Shorts Studio"
if (Test-Path -LiteralPath $startMenu) { Remove-Item -LiteralPath $startMenu -Recurse -Force }
if (Test-Path -LiteralPath $installDir) { Remove-Item -LiteralPath $installDir -Recurse -Force }
Write-Host "Shorts Studio 앱을 제거했습니다. 작업 기록과 모델 캐시는 유지했습니다."
