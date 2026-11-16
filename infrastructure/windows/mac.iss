#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppSource
  #error Defina AppSource com o build Windows em pasta.
#endif

[Setup]
AppId={{78223AC7-F410-4F9A-8EF2-E4110EA413D0}
AppName=MAC Performance
AppVersion={#AppVersion}
DefaultDirName={autopf}\MAC Performance
DefaultGroupName=MAC Performance
OutputDir=..\..\dist\installer
OutputBaseFilename=MAC-Setup-{#AppVersion}-x64
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppMutex=Global\MACPerformanceDesktop
SetupMutex=Global\MACPerformanceSetup
UninstallDisplayIcon={app}\MAC Performance.exe
CloseApplications=no
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MAC Performance"; Filename: "{app}\MAC Performance.exe"
Name: "{autodesktop}\MAC Performance"; Filename: "{app}\MAC Performance.exe"

[Code]
var
  UserPage: TInputQueryWizardPage;
  RebootRequired: Boolean;

function IsWow64Process2(Process: THandle; var ProcessMachine, NativeMachine: Word): Boolean;
  external 'IsWow64Process2@kernel32.dll stdcall';
function GetCurrentProcess(): THandle;
  external 'GetCurrentProcess@kernel32.dll stdcall';

function InitializeSetup(): Boolean;
var ProcessMachine, NativeMachine: Word; Previous: String; OldVersion, NewVersion: Int64;
begin
  Result := IsWow64Process2(GetCurrentProcess(), ProcessMachine, NativeMachine) and (NativeMachine = $8664);
  if not Result then MsgBox('Este instalador exige Windows x64 em processador Intel/AMD. ARM não foi homologado.', mbError, MB_OK);
  if Result and RegQueryStringValue(HKLM64, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{78223AC7-F410-4F9A-8EF2-E4110EA413D0}_is1', 'DisplayVersion', Previous) then begin
    if StrToVersion(Previous, OldVersion) and StrToVersion('{#AppVersion}', NewVersion) then begin
      if ComparePackedVersion(OldVersion, NewVersion) > 0 then begin
        MsgBox('Já existe uma versão mais recente. O downgrade foi bloqueado para proteger o banco.', mbError, MB_OK);
        Result := False;
      end;
    end;
  end;
end;

procedure InitializeWizard();
begin
  UserPage := CreateInputQueryPage(wpSelectDir, 'Usuário autorizado',
    'Quem utilizará o aplicativo neste computador?',
    'Informe o usuário Windows (por exemplo COMPUTADOR\carlos). Se a instalação foi elevada com outra conta, selecione o usuário real do aplicativo.');
  UserPage.Add('Usuário Windows:', False);
  UserPage.Values[0] := ExpandConstant('{username}');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer; Binary, Previous: String;
begin
  Result := '';
  Binary := ExpandConstant('{app}\MAC Performance.exe');
  if FileExists(Binary) then begin
    if not RegQueryStringValue(HKLM64, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{78223AC7-F410-4F9A-8EF2-E4110EA413D0}_is1', 'DisplayVersion', Previous) then begin
      Result := 'O diretório contém outro pacote. Selecione uma pasta vazia; bancos antigos não serão adotados automaticamente.';
      Exit;
    end;
    if (not Exec(Binary, '--setup-action stop', '', SW_HIDE, ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
      Result := 'Não foi possível preparar a atualização. Feche o aplicativo e execute novamente.';
  end;
end;

procedure RunChecked(Binary, Arguments: String; AllowNewer: Boolean);
var ExitCode: Integer;
begin
  if not Exec(Binary, Arguments, '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    RaiseException('Não foi possível executar uma dependência do instalador.');
  if ExitCode = 3010 then RebootRequired := True
  else if (ExitCode <> 0) and not (AllowNewer and (ExitCode = 1638)) then
    RaiseException('A preparação falhou (código ' + IntToStr(ExitCode) + '). Os dados existentes foram preservados.');
end;

function HasMachineWebView2(): Boolean;
var Version: String; Packed: Int64;
begin
  Result := RegQueryStringValue(HKLM32,
    'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  if Result then Result := StrToVersion(Version, Packed) and (Packed > 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    WizardForm.StatusLabel.Caption := 'Preparando dependências e banco local...';
    RunChecked(ExpandConstant('{app}\runtime\prerequisites\VC_redist.x64.exe'), '/install /quiet /norestart', True);
    if not HasMachineWebView2() then
      RunChecked(ExpandConstant('{app}\runtime\prerequisites\WebView2Setup.exe'), '/silent /install', False);
    RunChecked(ExpandConstant('{app}\MAC Performance.exe'), '--setup-action install --authorized-user ' + AddQuotes(Trim(UserPage.Values[0])), False);
  end;
end;

function NeedRestart(): Boolean;
begin
  Result := RebootRequired;
end;

function InitializeUninstall(): Boolean;
var ExitCode: Integer;
begin
  Result := Exec(ExpandConstant('{app}\MAC Performance.exe'), '--setup-action uninstall-service', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) and (ExitCode = 0);
  if not Result then MsgBox('O serviço não foi encerrado/removido com segurança. A desinstalação foi cancelada.', mbError, MB_OK);
end;

// Não há UninstallDelete: ProgramData e dados do usuário são preservados.
