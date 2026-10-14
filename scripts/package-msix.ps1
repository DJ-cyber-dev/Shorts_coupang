param(
    [string]$AppDir = "build/package-dist/ShortsStudio",
    [string]$ModelDir = ".tools/models",
    [string]$OutputDir = "build/installer",
    [string]$StageDir = "build/msix-stage",
    [string]$Publisher = "CN=Shorts Studio Developer",
    [string]$CertificateThumbprint = ""
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$app = (Resolve-Path -LiteralPath $AppDir).Path
$models = (Resolve-Path -LiteralPath $ModelDir).Path
$projectVersionLine = Select-String -Path (Join-Path (Get-Location) "pyproject.toml") `
    -Pattern '^version = "([0-9]+\.[0-9]+\.[0-9]+)"$' | Select-Object -First 1
if (-not $projectVersionLine) { throw "Could not read the project version from pyproject.toml." }
$projectVersion = [regex]::Match($projectVersionLine.Line, '^version = "([0-9]+\.[0-9]+\.[0-9]+)"$').Groups[1].Value
$packageVersion = "$projectVersion.0"
$versionParts = $packageVersion.Split('.') | ForEach-Object { [int]$_ }
if ($versionParts.Count -ne 4 -or ($versionParts | Where-Object { $_ -gt 65535 })) {
    throw "MSIX package version is outside the supported 4-part range: $packageVersion"
}
$out = Join-Path (Get-Location) $OutputDir
$stage = Join-Path (Get-Location) $StageDir
foreach ($required in @(
    "ShortsStudio.exe",
    "worker/ShortsStudioWorker.exe",
    "ffmpeg/ffmpeg.exe",
    "ffmpeg/ffprobe.exe"
)) {
    $requiredPath = Join-Path $app $required
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required packaged component is missing: $requiredPath. Run scripts/package-windows.ps1 first."
    }
}
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits/10/bin"
$sdkVersions = Get-ChildItem -Path $sdkRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } | Sort-Object { [version]$_.Name } -Descending
$makeAppx = $null
$signTool = $null
foreach ($sdkVersion in $sdkVersions) {
    $x64 = Join-Path $sdkVersion.FullName "x64"
    if (-not $makeAppx -and (Test-Path -LiteralPath (Join-Path $x64 "MakeAppx.exe"))) { $makeAppx = Get-Item (Join-Path $x64 "MakeAppx.exe") }
    if (-not $signTool -and (Test-Path -LiteralPath (Join-Path $x64 "SignTool.exe"))) { $signTool = Get-Item (Join-Path $x64 "SignTool.exe") }
    if ($makeAppx -and $signTool) { break }
}
if (-not $makeAppx) { throw "MakeAppx.exe not found. Install Windows 10/11 SDK." }
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage, (Join-Path $stage "Assets"), $out | Out-Null
Copy-Item -Path (Join-Path $app "*") -Destination $stage -Recurse -Force
Copy-Item -LiteralPath (Join-Path (Get-Location) "licenses/LaMa-LICENSE.txt") `
    -Destination (Join-Path $stage "THIRD-PARTY-LAMA-LICENSE.txt") -Force
New-Item -ItemType Directory -Force (Join-Path $stage "models") | Out-Null
foreach ($modelName in @("craft_mlt_25k.pth", "inpainting_lama_2025jan.onnx")) {
    $source = Join-Path $models $modelName
    if (-not (Test-Path -LiteralPath $source)) { throw "Required text-removal model is missing: $source" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $stage "models") -Force
}
$net = Join-Path $models "user_network"
if (Test-Path -LiteralPath $net) {
    $networkTarget = Join-Path $stage "models/user_network"
    New-Item -ItemType Directory -Force $networkTarget | Out-Null
    Copy-Item -Path (Join-Path $net "*") -Destination $networkTarget -Recurse -Force
}

# Keep package identity stable; version must increase for each upgrade build.
$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 IgnorableNamespaces="uap rescap">
 <Identity Name="ShortsStudio.Local" Publisher="$( [System.Security.SecurityElement]::Escape($Publisher) )" Version="$packageVersion" ProcessorArchitecture="x64" />
 <Properties><DisplayName>Shorts Studio</DisplayName><PublisherDisplayName>Shorts Studio</PublisherDisplayName><Logo>Assets\StoreLogo.png</Logo></Properties>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26100.0" /></Dependencies>
 <Resources><Resource Language="ko-KR" /></Resources>
 <Applications><Application Id="ShortsStudio" Executable="ShortsStudio.exe" EntryPoint="Windows.FullTrustApplication">
  <uap:VisualElements DisplayName="Shorts Studio" Description="Short-form video studio" BackgroundColor="#151a22" Square150x150Logo="Assets\Square150x150Logo.png" Square44x44Logo="Assets\Square44x44Logo.png" />
 </Application></Applications>
 <Capabilities><rescap:Capability Name="runFullTrust" /></Capabilities>
</Package>
"@
Set-Content -LiteralPath (Join-Path $stage "AppxManifest.xml") -Value $manifest -Encoding UTF8
Add-Type -AssemblyName System.Drawing
foreach ($item in @(@("StoreLogo.png", 50), @("Square150x150Logo.png", 150), @("Square44x44Logo.png", 44))) {
    $bitmap = [System.Drawing.Bitmap]::new($item[1], $item[1])
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.Clear([System.Drawing.Color]::FromArgb(151, 240, 93))
    $font = [System.Drawing.Font]::new("Arial", [Math]::Max(12, [int]($item[1] / 3)), [System.Drawing.FontStyle]::Bold)
    $graphics.DrawString("S", $font, [System.Drawing.Brushes]::Black, 4, 3)
    $bitmap.Save((Join-Path $stage ("Assets/" + $item[0])), [System.Drawing.Imaging.ImageFormat]::Png)
    $font.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
}
$package = Join-Path $out "ShortsStudio.msix"
if (Test-Path -LiteralPath $package) { Remove-Item -LiteralPath $package -Force }
& $makeAppx.FullName pack /d $stage /p $package /o
if ($LASTEXITCODE -ne 0) { throw "MakeAppx package creation failed." }
if ($CertificateThumbprint) {
    if (-not $signTool) { throw "SignTool.exe not found. Install Windows 10/11 SDK." }
    $certificate = Get-Item -LiteralPath "Cert:\CurrentUser\My\$CertificateThumbprint" -ErrorAction SilentlyContinue
    if (-not $certificate) { $certificate = Get-Item -LiteralPath "Cert:\LocalMachine\My\$CertificateThumbprint" -ErrorAction SilentlyContinue }
    if (-not $certificate) { throw "Signing certificate thumbprint not found in CurrentUser or LocalMachine Personal store." }
    if ($certificate.Subject -ne $Publisher) { throw "Certificate subject '$($certificate.Subject)' does not match manifest Publisher '$Publisher'." }
    & $signTool.FullName sign /fd SHA256 /sha1 $CertificateThumbprint $package
    if ($LASTEXITCODE -ne 0) { throw "MSIX signing failed." }
    & $signTool.FullName verify /pa /v $package
    if ($LASTEXITCODE -ne 0) { throw "MSIX signature verification failed." }
} else {
    Write-Warning "Created an unsigned MSIX. It cannot be installed until signed with a certificate whose subject matches Publisher."
}
Write-Host "MSIX: $package"
