param(
    [string]$FFmpegDir = ".tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin",
    [string]$ModelDir = ".tools/models",
    [string]$DistDir = "build/package-dist",
    [string]$WorkDir = "build/package-work",
    [string]$InnoCompiler = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    [switch]$SkipPyInstaller,
    [switch]$SkipPortableZip
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$ffmpegPath = (Resolve-Path -LiteralPath $FFmpegDir).Path
$modelPath = (Resolve-Path -LiteralPath $ModelDir).Path
foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
    if (-not (Test-Path -LiteralPath (Join-Path $ffmpegPath $name))) { throw "Missing $name under $ffmpegPath" }
}
if (-not (Test-Path -LiteralPath (Join-Path $modelPath "craft_mlt_25k.pth"))) { throw "Missing EasyOCR craft_mlt_25k.pth under $modelPath" }
if (-not (Test-Path -LiteralPath (Join-Path $modelPath "inpainting_lama_2025jan.onnx"))) { throw "Missing LaMa ONNX model under $modelPath. Run scripts/setup-text-removal.ps1." }
$python = Join-Path (Get-Location) ".venv/Scripts/python.exe"
if (-not $SkipPyInstaller) {
    & $python -m pip install --quiet --no-build-isolation -e ".[packaging,text,secrets,upload,windows-tts]"
    if ($LASTEXITCODE -ne 0) { throw "Packaging dependency installation failed." }
}
$dist = Join-Path (Get-Location) $DistDir
$work = Join-Path (Get-Location) $WorkDir
New-Item -ItemType Directory -Force $dist | Out-Null
if (-not $SkipPyInstaller) {
    Write-Host "Building ShortsStudio Desktop…"
    & $python -m PyInstaller --noconfirm --clean --distpath $dist --workpath (Join-Path $work "app") ShortsStudio.spec
    if ($LASTEXITCODE -ne 0) { throw "Desktop packaging failed." }
    Write-Host "Building mandatory multilingual text-removal worker…"
    $torchvisionDir = (Resolve-Path ".venv/Lib/site-packages/torchvision").Path
    $nativeExtensions = @()
    foreach ($name in @("_C_stable.pyd", "_C.pyd", "image_stable.pyd", "image.pyd")) {
        $candidate = Join-Path $torchvisionDir $name
        if (Test-Path -LiteralPath $candidate) { $nativeExtensions += $candidate }
    }
    if (-not ($nativeExtensions | Where-Object { (Split-Path $_ -Leaf) -in @("_C_stable.pyd", "_C.pyd") })) {
        throw "Torchvision C++ extension was not found under $torchvisionDir."
    }
    $extensionArgs = @()
    foreach ($extension in $nativeExtensions) { $extensionArgs += @("--add-binary", "$extension;torchvision") }
    & $python -m PyInstaller --noconfirm --clean --onedir --console --paths src --collect-all easyocr --collect-all cv2 --collect-binaries torchvision @extensionArgs --hidden-import torchvision.transforms --name ShortsStudioWorker --distpath $dist --workpath (Join-Path $work "worker") src/shorts_studio/text_removal/worker.py
    if ($LASTEXITCODE -ne 0) { throw "Text-removal worker packaging failed." }
}
$workerDist = Join-Path $dist "ShortsStudioWorker"
if (-not (Test-Path -LiteralPath (Join-Path $dist "ShortsStudio/ShortsStudio.exe"))) { throw "Prebuilt ShortsStudio app is missing. Run without -SkipPyInstaller." }
if (-not (Test-Path -LiteralPath (Join-Path $workerDist "ShortsStudioWorker.exe"))) { throw "Prebuilt ShortsStudioWorker is missing. Run without -SkipPyInstaller." }
$app = Join-Path $dist "ShortsStudio"
$workerTarget = Join-Path $app "worker"
if (Test-Path -LiteralPath $workerTarget) { Remove-Item -LiteralPath $workerTarget -Recurse -Force }
New-Item -ItemType Directory -Force $workerTarget, (Join-Path $app "ffmpeg") | Out-Null
Copy-Item -Path (Join-Path $workerDist "*") -Destination $workerTarget -Recurse -Force
Copy-Item -LiteralPath (Join-Path $ffmpegPath "ffmpeg.exe"), (Join-Path $ffmpegPath "ffprobe.exe") -Destination (Join-Path $app "ffmpeg") -Force
$archive = $null
if (-not $SkipPortableZip) {
    $portable = Join-Path $dist "ShortsStudioPortable"
    if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Recurse -Force }
    New-Item -ItemType Directory -Force (Join-Path $portable "ShortsStudio"), (Join-Path $portable "models") | Out-Null
    Copy-Item -Path (Join-Path $app "*") -Destination (Join-Path $portable "ShortsStudio") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $modelPath "craft_mlt_25k.pth") -Destination (Join-Path $portable "models") -Force
    Copy-Item -LiteralPath (Join-Path $modelPath "inpainting_lama_2025jan.onnx") -Destination (Join-Path $portable "models") -Force
    Copy-Item -LiteralPath (Join-Path (Get-Location) "licenses/LaMa-LICENSE.txt") -Destination (Join-Path $portable "THIRD-PARTY-LAMA-LICENSE.txt") -Force
    $networkPath = Join-Path $modelPath "user_network"
    if (Test-Path -LiteralPath $networkPath) { Copy-Item -Path (Join-Path $networkPath "*") -Destination (Join-Path $portable "models") -Recurse -Force }
    Copy-Item -LiteralPath (Join-Path (Get-Location) "installer/Install-ShortsStudio.ps1") -Destination $portable -Force
    Copy-Item -LiteralPath (Join-Path (Get-Location) "Apply-ShortsStudioUpdate.ps1") -Destination $portable -Force
    Copy-Item -LiteralPath (Join-Path (Get-Location) "installer/Uninstall-ShortsStudio.ps1") -Destination (Join-Path $portable "ShortsStudio") -Force
    $archive = Join-Path $dist "ShortsStudio-Portable.zip"
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $portable, $archive, [System.IO.Compression.CompressionLevel]::Fastest, $false
    )
    Remove-Item -LiteralPath $portable -Recurse -Force
}
$iss = Join-Path (Get-Location) "installer/ShortsStudio.iss"
if (Test-Path -LiteralPath $InnoCompiler) {
    & $InnoCompiler "/DAppSource=$app" "/DModelSource=$modelPath" "/DOutputDir=$(Join-Path (Get-Location) 'build/installer')" $iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup installer compilation failed." }
    Write-Host "Inno Setup installer is in build/installer."
} elseif (-not $SkipPortableZip) {
    Write-Warning "Inno Setup is not installed; created a self-contained portable ZIP with per-user install/uninstall scripts instead."
} else {
    Write-Warning "Portable ZIP skipped by request; the MSIX build can use $app."
}
if ($archive) { Write-Host "Portable package: $archive" }
Write-Host "Review third-party license notices before redistribution."
