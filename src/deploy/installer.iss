; installer.iss — Inno Setup script for the OpenFOAM UI one-file installer.
;
; Build (from the deploy\ directory):
;   ISCC /DMyAppVersion=1.1.0 installer.iss
; or run build.bat, which locates ISCC and passes the version automatically.
; Output: dist\OpenFOAM_UI_Setup_<version>.exe
;
; What the installer does:
;   * installs app\* to {localappdata}\Programs\OpenFOAM-UI — per-user,
;     no admin rights needed (folder name has no space on purpose: the WSL
;     side single-quotes the path, but no-space is one less thing to break)
;   * copies the Demo-01 / Demo-02 sample cases to Documents\OpenFOAM-Projects
;     — never overwrites files the user already has, never uninstalled
;   * desktop + Start-Menu shortcuts, replaced in place on reinstall/upgrade
;   * writes {app}\install_info.json with the projects folder as a WSL path,
;     so the GUI's New-project Location defaults there (ui_landing.py)
;   * one hard gate: Windows build >= 21362 (WSLg needs it — the GUI cannot
;     work below that on any retry). Everything deeper (WSL, Ubuntu, apt
;     packages, OpenFOAM) stays in the launcher's self-healing pre-flight.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "OpenFOAM UI"
#define MyAppExeName "OpenFOAM_UI.exe"

[Setup]
AppId={{7F3D9A61-52E4-4C8B-9B0A-D2F14E6C0A55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Affan Najiy
DefaultDirName={localappdata}\Programs\OpenFOAM-UI
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=OpenFOAM_UI_Setup_{#MyAppVersion}
SetupIconFile=icons\openfoam_ui.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
MinVersion=10.0

[Files]
Source: "..\app\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion; Excludes: "__pycache__\*"
; Sample cases → Documents\OpenFOAM-Projects. onlyifdoesntexist: a user's
; meshed/modified copy is their data — never clobber it on reinstall.
Source: "..\..\Demo-01\*"; DestDir: "{userdocs}\OpenFOAM-Projects\Demo-01"; Flags: recursesubdirs onlyifdoesntexist uninsneveruninstall; Excludes: "polyMesh\*,*.foam,snappy_inputs.json,log.*,processor*"
Source: "..\..\Demo-02\*"; DestDir: "{userdocs}\OpenFOAM-Projects\Demo-02"; Flags: recursesubdirs onlyifdoesntexist uninsneveruninstall; Excludes: "polyMesh\*,*.foam,snappy_inputs.json,log.*,processor*"

[Dirs]
Name: "{userdocs}\OpenFOAM-Projects"; Flags: uninsneveruninstall

[Icons]
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\openfoam_ui.ico"
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\openfoam_ui.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; WSL python writes __pycache__ into {app}, and [Code] writes
; install_info.json — neither is in the install log, so sweep the whole dir.
Type: filesandordirs; Name: "{app}"

[Code]
const
  // First Windows build that ships WSLg (GUI apps out of WSL2). The launcher
  // enforces the same gate; failing here saves the user a dead install.
  MIN_WSLG_BUILD = 21362;

function InitializeSetup(): Boolean;
var
  BuildStr: string;
begin
  Result := True;
  if RegQueryStringValue(HKEY_LOCAL_MACHINE,
      'SOFTWARE\Microsoft\Windows NT\CurrentVersion',
      'CurrentBuildNumber', BuildStr) then
  begin
    if StrToIntDef(BuildStr, 0) < MIN_WSLG_BUILD then
    begin
      MsgBox('This app needs a newer Windows.' + #13#10#13#10 +
             'Your Windows build is ' + BuildStr + ', but at least build ' +
             IntToStr(MIN_WSLG_BUILD) + ' (Windows 10 21H2 / Windows 11) is ' +
             'required for WSL GUI support.' + #13#10#13#10 +
             'Update Windows via Settings > Windows Update, then run this ' +
             'installer again.', mbCriticalError, MB_OK);
      Result := False;
    end;
  end;
end;

function ToWslPath(const WinPath: string): string;
var
  S: string;
begin
  // C:\Users\X\Documents  ->  /mnt/c/Users/X/Documents
  S := WinPath;
  StringChangeEx(S, '\', '/', True);
  if (Length(S) >= 2) and (S[2] = ':') then
    S := '/mnt/' + Lowercase(S[1]) + Copy(S, 3, MaxInt);
  Result := S;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Info: string;
begin
  if CurStep = ssPostInstall then
  begin
    // GUI reads this with encoding='utf-8-sig', so the BOM from
    // SaveStringsToUTF8File is harmless.
    Info := '{"projects_dir": "' +
            ToWslPath(ExpandConstant('{userdocs}\OpenFOAM-Projects')) + '"}';
    // [Info] must not start a line — Inno's section scanner would read it
    // as a section tag even inside [Code].
    SaveStringsToUTF8File(ExpandConstant('{app}\install_info.json'), [Info], False);
  end;
end;
