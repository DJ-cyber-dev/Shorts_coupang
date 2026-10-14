param([string]$Package = "build/installer/ShortsStudio.msix")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$path = (Resolve-Path -LiteralPath $Package).Path
$signature = Get-AuthenticodeSignature -FilePath $path
if ($signature.Status -ne "Valid") {
    throw "MSIX signature is not valid ($($signature.Status)). Sign and trust the publisher certificate first; see docs/WINDOWS-MSIX.md."
}
Add-AppxPackage -Path $path
Write-Host "Shorts Studio installed. Launch it from the Start menu."
