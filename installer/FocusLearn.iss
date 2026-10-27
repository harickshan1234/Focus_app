; Inno Setup script for Focus Learn.
; Build with:  python build_installer.py   (runs PyInstaller first, then this script)

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Focus Learn"
#define AppExe "FocusLearn.exe"

[Setup]
; Keep AppId the same in every release so upgrades replace the old install.
AppId={{F7D3CA0D-8C13-42AE-94FA-7105F90492B9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=harickshan1234
AppPublisherURL=https://github.com/harickshan1234/Focus_app
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installs for the current user without admin rights; the user can pick "all users" instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=FocusLearn-Setup-{#AppVersion}
SetupIconFile=..\focuslearn\assets\focuslearn.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Ask the user to close Focus Learn if it is running (the app holds this mutex).
AppMutex=FocusLearn.SingleInstance
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "runasadmin"; Description: "Always start with system-wide blocking (Windows asks for administrator permission each time)"; GroupDescription: "YouTube blocking:"; Flags: unchecked

[Files]
Source: "..\dist\FocusLearn\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Windows' own "Run this program as an administrator" setting for FocusLearn.exe.
Root: HKA; Subkey: "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\{#AppExe}"; ValueData: "~ RUNASADMIN"; Tasks: runasadmin; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent shellexec

[Code]
const
  BeginMark = '# >>> Focus Learn study block (removed automatically when the session ends) >>>';
  EndMark = '# <<< Focus Learn study block <<<';

{ The app removes its hosts-file block itself when a session ends. This only
  matters if it crashed while blocking and is then uninstalled, which would
  otherwise leave YouTube blocked with no app left to unblock it. }
procedure RemoveHostsBlock();
var
  HostsPath: String;
  Lines, Kept: TArrayOfString;
  I, Count: Integer;
  Inside, Found: Boolean;
begin
  HostsPath := ExpandConstant('{sys}\drivers\etc\hosts');
  if not LoadStringsFromFile(HostsPath, Lines) then
    Exit;
  Count := 0;
  Inside := False;
  Found := False;
  SetArrayLength(Kept, GetArrayLength(Lines));
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    if Trim(Lines[I]) = BeginMark then
    begin
      Inside := True;
      Found := True;
    end
    else if Inside then
    begin
      if Trim(Lines[I]) = EndMark then
        Inside := False;
    end
    else
    begin
      Kept[Count] := Lines[I];
      Count := Count + 1;
    end;
  end;
  if not Found then
    Exit;
  SetArrayLength(Kept, Count);
  if not SaveStringsToFile(HostsPath, Kept, False) then
    MsgBox('Focus Learn could not remove its website block from the Windows hosts file.' + #13#10 + #13#10 +
           'Open ' + HostsPath + ' as administrator and delete the lines between the "Focus Learn study block" markers.',
           mbError, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RemoveHostsBlock();
end;
