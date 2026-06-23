; Gitora InnoSetup 打包脚本(InnoSetup 6/7)
; 编译: "C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss
; 前提: 先跑 build_nuitka.py 生成 build_dist\main_qml.dist\

#define MyAppName "Gitora"
#define MyAppVersion "1.0.2"
#define MyAppPublisher "aki-riko"
#define MyAppExeName "Gitora.exe"
#define MyDistDir "build_dist\main_qml.dist"

[Setup]
AppId={{8F3A9C2E-5B1D-4E7A-9C6F-A1B2C3D4E5F6}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist_installer
OutputBaseFilename=Gitora-Setup-{#MyAppVersion}
SetupIconFile=app\resource\images\logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 64 位应用
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 允许用户选择安装目录
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 打包整个 Nuitka dist 目录(递归)
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
