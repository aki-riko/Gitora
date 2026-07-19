; Gitora InnoSetup 打包脚本(InnoSetup 6/7)
; 编译: "C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss
; 前提: 先跑 build_nuitka.py 生成 build_dist\main_qml.dist\

#define MyAppName "Gitora"
#define MyAppVersion "1.2.12"
#define MyAppPublisher "aki-riko"
#define MyAppExeName "Gitora.exe"
#define MyDistDir "build_dist\main_qml.dist"
#define MyAppUserModelID "PrismQML.Gitora"

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
; 按系统 UI 语言自动选(中文系统→中文,英文系统→英文);auto=匹配上就不弹框直接用,
; 仅在无匹配语言时才弹选择框。配合 LanguageDetectionMethod=uilanguage 实现"自动识别"。
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage
; 64 位应用
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 允许用户选择安装目录
UninstallDisplayIcon={app}\{#MyAppExeName}
; 安装到 Program Files 需管理员权限;manifest 标记 admin,启动时由 Windows 自动弹 UAC 提权
PrivilegesRequired=admin
; 自动更新:安装时若 Gitora 正在运行,自动关闭并在安装完成后重启
CloseApplications=yes
RestartApplications=yes

[Languages]
; 双语;中文 isl 跟随项目(installer/),无需装到 Inno 全局目录。
; 按系统 UI 语言自动识别(见 [Setup] ShowLanguageDialog=auto + LanguageDetectionMethod):
; 中文系统直接走中文向导、英文系统走英文,均不弹语言框;仅当系统语言两者都不匹配时才弹框。
Name: "chinesesimplified"; MessagesFile: "installer\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 打包整个 Nuitka dist 目录(递归)
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
