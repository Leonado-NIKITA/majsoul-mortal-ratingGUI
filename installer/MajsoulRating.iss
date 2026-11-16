; 雀魂 Rating 跑谱工具 安装包脚本 (Inno Setup 6.5+)
; 一般不直接编译这个文件, 用 build_installer.bat: 先 PyInstaller 打包, 再把版本号传进来编译.
; 手动编译: ISCC.exe /DMyAppVersion=1.2.0 installer\MajsoulRating.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "雀魂 Rating 跑谱工具"
#define MyAppExe "MajsoulRating.exe"
#define DistDir "..\dist\MajsoulRating"

[Setup]
; AppId 固定不变, 升级安装才会覆盖旧版本而不是装出第二份
AppId={{6F1C2B7E-4D5A-4E8B-9C3F-2A7D1E0B5C94}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=MajsoulRating
VersionInfoVersion={#MyAppVersion}
; 默认按当前用户安装 (%LOCALAPPDATA%\Programs), 不用管理员; 也可以在对话框里改成所有用户
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\MajsoulRating
DisableDirPage=no
UsePreviousAppDir=yes
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=MajsoulRating-Setup-{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 程序开着时提示关闭, 避免文件被占用装不上
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
chinesesimplified.DataNote=玩家数据 (players\) 和输出 (rating_out\) 会保存在安装目录下。
chinesesimplified.ProtectedDir=当前是「仅为我安装」模式, 没有权限写入:%n%n%1%n%n请换一个目录, 或返回第一步选择「为所有用户安装」。
chinesesimplified.AskDeleteData=是否同时删除玩家数据和输出结果?%n%n%1%n%n选「否」会保留它们, 重新安装后可以继续使用。
chinesesimplified.NeedBrowser=跑谱需要本机装有 Microsoft Edge 或 Google Chrome。
english.DataNote=Player data (players\) and output (rating_out\) are stored in the install folder.
english.ProtectedDir=Installing for the current user only; this folder is not writable:%n%n%1%n%nChoose another folder, or go back and install for all users.
english.AskDeleteData=Also delete player data and output?%n%n%1%n%nChoose No to keep them for a later reinstall.
english.NeedBrowser=Reviewing requires Microsoft Edge or Google Chrome.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; 升级时先清掉旧版的依赖目录, 免得残留旧 dll; 用户数据不在这里
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; 数据目录: 装到 Program Files 时普通用户也要能写; 卸载时不自动删 (由下面的 [Code] 询问)
Name: "{app}\players"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{app}\rating_out"; Permissions: users-modify; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\玩家数据目录"; Filename: "{app}\players"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function UnderDir(const Path, Base: String): Boolean;
var
  P, B: String;
begin
  P := Lowercase(AddBackslash(Path));
  B := Lowercase(AddBackslash(Base));
  Result := (B <> '\') and (Copy(P, 1, Length(B)) = B);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir: String;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and not IsAdminInstallMode then
  begin
    Dir := WizardDirValue;
    if UnderDir(Dir, ExpandConstant('{commonpf64}')) or UnderDir(Dir, ExpandConstant('{commonpf32}'))
       or UnderDir(Dir, ExpandConstant('{win}')) then
    begin
      MsgBox(FmtMessage(CustomMessage('ProtectedDir'), [Dir]), mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then
    WizardForm.SelectDirLabel.Caption := WizardForm.SelectDirLabel.Caption + #13#10 + CustomMessage('DataNote');
  if CurPageID = wpFinished then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + CustomMessage('NeedBrowser');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  App: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  App := ExpandConstant('{app}');
  if not DirExists(App + '\players') and not DirExists(App + '\rating_out') then
    Exit;
  // 静默卸载时不问, 一律保留数据
  if UninstallSilent then
    Exit;
  if MsgBox(FmtMessage(CustomMessage('AskDeleteData'), [App + '\players' + #13#10 + App + '\rating_out']),
            mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
  begin
    DelTree(App + '\players', True, True, True);
    DelTree(App + '\rating_out', True, True, True);
    RemoveDir(App);
  end;
end;
