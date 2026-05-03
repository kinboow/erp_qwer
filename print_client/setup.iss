; ============================================================
; ERP 打印客户端 - Inno Setup 安装脚本
; ============================================================
; 使用方法:
;   1. 安装 Inno Setup: https://jrsoftware.org/isdl.php
;   2. 下载 SumatraPDF 安装版放到 deps\ 目录:
;      https://www.sumatrapdfreader.org/download-free-pdf-viewer
;      文件名: SumatraPDF-3.5.2-64-install.exe (或类似)
;   3. 先运行 build.bat 生成 dist\ERP打印客户端.exe
;   4. 用 Inno Setup 编译本文件即可生成安装包
; ============================================================

#define MyAppName "ERP打印客户端"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ERP"
#define MyAppExeName "ERP打印客户端.exe"
#ifndef SumatraInstaller
  #define SumatraInstaller "SumatraPDF-3.5.2-64-install.exe"
#endif

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=ERP打印客户端_Setup_{#MyAppVersion}
SetupIconFile=logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
; 中文支持
ShowLanguageDialog=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: checked
Name: "autostart"; Description: "开机自动启动"; GroupDescription: "附加选项:"; Flags: checked
Name: "installsumatra"; Description: "安装 SumatraPDF (PDF 静默打印所需)"; GroupDescription: "依赖组件:"; Flags: checked

[Files]
; 主程序
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; 图标文件
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
; SumatraPDF 安装包 (放在 deps 目录下)
Source: "deps\{#SumatraInstaller}"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall; Check: ShouldInstallSumatra

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Registry]
; 开机自启动
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; 静默安装 SumatraPDF
Filename: "{tmp}\{#SumatraInstaller}"; Parameters: "-s"; StatusMsg: "正在安装 SumatraPDF..."; Flags: waituntilterminated; Check: ShouldInstallSumatra
; 安装完成后启动程序
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载时关闭程序
Filename: "taskkill"; Parameters: "/F /IM ""{#MyAppExeName}"""; Flags: runhidden

[Code]
function ShouldInstallSumatra: Boolean;
begin
  Result := IsTaskSelected('installsumatra');
end;

function IsSumatraInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{pf}\SumatraPDF\SumatraPDF.exe')) or
            FileExists(ExpandConstant('{pf32}\SumatraPDF\SumatraPDF.exe'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsSumatraInstalled then
      Log('SumatraPDF 已检测到安装')
    else if IsTaskSelected('installsumatra') then
      Log('SumatraPDF 将被安装');
  end;
end;
