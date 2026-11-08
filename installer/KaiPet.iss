; Установщик Кая: KaiPet-Setup.exe. Без прав администратора, без вопросов про папку — пара кликов.
; Сборка: python build_exe.py && iscc /DAppVersion=1.2.0 installer\KaiPet.iss  →  dist\KaiPet-Setup.exe

#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif

[Setup]
AppId={{6F0B1C1E-7A3D-4C51-9E0B-4B5A0C9E6A11}
AppName=Кай
AppVersion={#AppVersion}
AppVerName=Кай {#AppVersion}
AppPublisher=Shoxiazam
AppPublisherURL=https://shoxiazam.github.io/kai-pet/
AppSupportURL=https://github.com/Shoxiazam/kai-pet/issues
DefaultDirName={localappdata}\Programs\KaiPet
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=KaiPet-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\KaiPet.exe
UninstallDisplayName=Кай — питомец на рабочем столе
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=100
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ru.Autostart=Запускать Кая вместе с Windows
en.Autostart=Start Kai with Windows
ru.Desktop=Значок на рабочем столе
en.Desktop=Desktop shortcut
ru.RunKai=Запустить Кая
en.RunKai=Start Kai

[Tasks]
Name: "autostart"; Description: "{cm:Autostart}"
Name: "desktopicon"; Description: "{cm:Desktop}"

[Files]
Source: "..\dist\KaiPet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Кай"; Filename: "{app}\KaiPet.exe"
Name: "{autodesktop}\Кай"; Filename: "{app}\KaiPet.exe"; Tasks: desktopicon

[Registry]
; то же значение, что ставит галочка «Запускать вместе с Windows» в меню Кая (kai_pet/autostart.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KaiPet"; \
  ValueData: """{app}\KaiPet.exe"""; Flags: uninsdeletevalue; Tasks: autostart

; ссылки kaipet:// из приглашений на сайте открывает Кай (удаление Кая их убирает)
Root: HKCU; Subkey: "Software\Classes\kaipet"; ValueType: string; ValueName: ""; ValueData: "URL:Кай"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\kaipet"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\kaipet\shell\open\command"; ValueType: string; ValueName: ""; \
  ValueData: """{app}\KaiPet.exe"" ""%1"""

[Run]
Filename: "{app}\KaiPet.exe"; Description: "{cm:RunKai}"; Flags: nowait postinstall

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im KaiPet.exe"; Flags: runhidden; RunOnceId: "StopKai"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\KaiPet\looks"
Type: filesandordirs; Name: "{localappdata}\KaiPet\friend"
