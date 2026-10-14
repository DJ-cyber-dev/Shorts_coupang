param(
    [Parameter(Mandatory=$true)][int]$WaitPid,
    [Parameter(Mandatory=$true)][string]$Archive,
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$DataDir
)
$ErrorActionPreference = 'Stop'
$localRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'ShortsStudio'))
$expectedInstall = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\ShortsStudio'))
$expectedData = [IO.Path]::GetFullPath($localRoot)
$archivePath = [IO.Path]::GetFullPath($Archive)
$installPath = [IO.Path]::GetFullPath($InstallDir)
$dataPath = [IO.Path]::GetFullPath($DataDir)
$expectedUpdates = [IO.Path]::GetFullPath((Join-Path $expectedData 'updates'))
if (-not [string]::Equals($installPath, $expectedInstall, [StringComparison]::OrdinalIgnoreCase) -or
    -not [string]::Equals($dataPath, $expectedData, [StringComparison]::OrdinalIgnoreCase) -or
    -not $archivePath.StartsWith($expectedUpdates + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw '업데이트 경로 검증에 실패했습니다.'
}
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf) -or -not (Test-Path -LiteralPath $installPath -PathType Container)) {
    throw '업데이트 파일 또는 설치 경로가 없습니다.'
}
try { Wait-Process -Id $WaitPid -Timeout 120 -ErrorAction Stop } catch {
    if (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { throw '앱이 종료되지 않아 업데이트를 중단했습니다.' }
}
$stage = Join-Path $expectedUpdates ('stage-' + [Guid]::NewGuid().ToString('N'))
$extract = Join-Path $stage 'extract'
$replacement = Join-Path $extract 'ShortsStudio'
$backup = $installPath + '.previous'
$swapped = $false
New-Item -ItemType Directory -Force -Path $extract | Out-Null
try {
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extract -Force
    if (-not (Test-Path -LiteralPath (Join-Path $replacement 'ShortsStudio.exe') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $replacement 'worker\ShortsStudioWorker.exe') -PathType Leaf)) {
        throw '업데이트 패키지의 앱 또는 필수 Worker 파일을 찾지 못했습니다.'
    }
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
    Move-Item -LiteralPath $installPath -Destination $backup
    Move-Item -LiteralPath $replacement -Destination $installPath
    $swapped = $true
    Start-Process -FilePath (Join-Path $installPath 'ShortsStudio.exe') -WorkingDirectory $installPath
} catch {
    if ($swapped -and (Test-Path -LiteralPath $installPath)) {
        Remove-Item -LiteralPath $installPath -Recurse -Force
    }
    if (Test-Path -LiteralPath $backup) {
        Move-Item -LiteralPath $backup -Destination $installPath
    }
    $swapped = $false
    $logPath = Join-Path $expectedUpdates 'last-update-error.txt'
    $_ | Out-String | Set-Content -LiteralPath $logPath -Encoding UTF8
    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            "Shorts Studio 업데이트를 적용하지 못했습니다. 기존 앱 복구를 시도했습니다.`n$logPath",
            'Shorts Studio 업데이트', 'OK', 'Error'
        ) | Out-Null
    } catch {}
    throw
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath -Force }
}
if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
