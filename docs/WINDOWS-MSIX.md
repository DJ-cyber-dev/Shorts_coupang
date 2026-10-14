# Windows MSIX and local Korean TTS

Shorts Studio's TTS uses the installed Windows `Microsoft Heami` Korean voice through WinRT. It sends no narration to a TTS API. The Windows Runtime speech synthesis API requires package identity, so use the MSIX build; portable ZIP and Inno Setup builds do not provide local TTS.

## Build

Run `scripts/package-windows.ps1` to build the desktop app and worker. The build installs the `windows-tts` projection dependencies. Then run `scripts/package-msix.ps1`. Install Windows 10/11 SDK for `MakeAppx.exe` and `SignTool.exe`.

For a signed build, create or use a code-signing certificate whose subject exactly matches the manifest Publisher (`CN=Shorts Studio Developer` by default), then pass its thumbprint:

```powershell
New-Item -ItemType Directory -Force .\build\installer | Out-Null
$cert = New-SelfSignedCertificate -Type Custom -Subject "CN=Shorts Studio Developer" `
  -KeyUsage DigitalSignature -CertStoreLocation Cert:\CurrentUser\My `
  -NotAfter (Get-Date).AddYears(3) `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
Export-Certificate -Cert $cert -FilePath .\build\installer\ShortsStudio-DevCert.cer
.\scripts\package-msix.ps1 -CertificateThumbprint $cert.Thumbprint
```

For local test installation, an administrator must explicitly add that public certificate to the machine's `Trusted People` store before installing the MSIX:

```powershell
Import-Certificate -FilePath .\build\installer\ShortsStudio-DevCert.cer `
  -CertStoreLocation Cert:\LocalMachine\TrustedPeople
```

The script never creates or trusts a certificate automatically. Unsigned MSIX output is useful for packaging validation only and Windows will not install it. Use a publicly trusted signing certificate for distribution. Never commit private signing keys.

Install a signed package with `scripts/install-msix.ps1`. Ensure the Windows Korean Heami voice is installed under **Settings > Time & language > Speech**. The app's TTS status reports whether the local voice is available.

Windows speech voice availability varies by Windows edition and installed language packs. Verify on each target PC; Windows Runtime speech synthesis voice quality/language is supplied by Windows.
