#ifndef AppSource
  #define AppSource "..\build\package-dist\ShortsStudio"
#endif
#ifndef ModelSource
  #define ModelSource "..\.tools\models"
#endif
#ifndef OutputDir
  #define OutputDir "..\build\installer"
#endif

[Setup]
AppId={{B0A4250D-C0FE-4AC0-B0A7-2F27C1078A23}
AppName=Shorts Studio
AppVersion=0.2.13
DefaultDirName={localappdata}\Programs\ShortsStudio
DefaultGroupName=Shorts Studio
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
OutputDir={#OutputDir}
OutputBaseFilename=ShortsStudio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallFilesDir={localappdata}\ShortsStudio\uninstall

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ModelSource}\craft_mlt_25k.pth"; DestDir: "{localappdata}\ShortsStudio\models"; Flags: ignoreversion
Source: "{#ModelSource}\inpainting_lama_2025jan.onnx"; DestDir: "{localappdata}\ShortsStudio\models"; Flags: ignoreversion
Source: "{#ModelSource}\user_network\*"; DestDir: "{localappdata}\ShortsStudio\models\user_network"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "..\licenses\LaMa-LICENSE.txt"; DestDir: "{app}"; DestName: "THIRD-PARTY-LAMA-LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Shorts Studio"; Filename: "{app}\ShortsStudio.exe"
Name: "{autodesktop}\Shorts Studio"; Filename: "{app}\ShortsStudio.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "바탕 화면 바로 가기 만들기"; GroupDescription: "추가 아이콘:"; Flags: unchecked

[Run]
Filename: "{app}\ShortsStudio.exe"; Description: "Shorts Studio 실행"; Flags: postinstall nowait skipifsilent
