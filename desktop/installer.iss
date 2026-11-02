; Windows installer of the desktop app (F14), built by the Desktop app workflow:
;   iscc /DAppVersion=1.0.0 desktop\installer.iss      (after PyInstaller: desktop\dist\MyFinancePlace)
; For this user only, no administrator rights: the program in %LOCALAPPDATA%\Programs\MyFinancePlace, the data stays
; in %APPDATA%\MyFinancePlace (an update or an uninstall never touches it).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6F1D2C8A-3B57-4E0B-9C2E-6A4D8E1F7B23}
AppName=MyFinancePlace
AppVersion={#AppVersion}
AppPublisher=MyFinancePlace
DefaultDirName={localappdata}\Programs\MyFinancePlace
DefaultGroupName=MyFinancePlace
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=MyFinancePlace-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\MyFinancePlace.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
it.AutoStart=Avvia MyFinancePlace all'accensione del computer (in background, per le notifiche dei promemoria)
en.AutoStart=Start MyFinancePlace when the computer starts (in the background, for the reminder notifications)
it.Options=Opzioni:
en.Options=Options:

[Tasks]
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "{cm:Options}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\MyFinancePlace\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; the Start menu entry carries the app's identity: its notifications show its name and icon
Name: "{userprograms}\MyFinancePlace"; Filename: "{app}\MyFinancePlace.exe"; AppUserModelID: "MyFinancePlace.App"
Name: "{userdesktop}\MyFinancePlace"; Filename: "{app}\MyFinancePlace.exe"; Tasks: desktopicon

[Registry]
; the same entries the app keeps up to date at every start (desktop/windows.py, app/services/autostart.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MyFinancePlace"; \
  ValueData: """{app}\MyFinancePlace.exe"" --background"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\myfinanceplace"; ValueType: string; ValueName: ""; ValueData: "URL:MyFinancePlace"; \
  Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\myfinanceplace"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\myfinanceplace\shell\open\command"; ValueType: string; ValueName: ""; \
  ValueData: """{app}\MyFinancePlace.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\MyFinancePlace.App"; ValueType: string; ValueName: "DisplayName"; \
  ValueData: "MyFinancePlace"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\MyFinancePlace.App"; ValueType: string; ValueName: "IconUri"; \
  ValueData: "{app}\_internal\assets\icon.ico"

[Run]
Filename: "{app}\MyFinancePlace.exe"; Description: "{cm:LaunchProgram,MyFinancePlace}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; close the app cleanly (window, server, database) before its files are removed
Filename: "{app}\MyFinancePlace.exe"; Parameters: "--stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopApp"

[Code]
// An update: the open app (maybe in the background, started with the computer) closes cleanly first
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Installed: String;
begin
  Installed := ExpandConstant('{app}\MyFinancePlace.exe');
  if FileExists(Installed) then
    Exec(Installed, '--stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

// Uninstall: "start with the computer" may have been switched on later from Settings, App desktop
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'MyFinancePlace');
end;
