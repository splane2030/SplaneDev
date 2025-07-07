; MonLogiciel.iss – Installe le logiciel avec mise à jour locale et protection de la base

[Setup]
AppName=Mon Logiciel d'Épargne
AppVersion=1.1
DefaultDirName={pf}\MonLogiciel
DefaultGroupName=Mon Logiciel d'Épargne
UninstallDisplayIcon={app}\form1.exe
OutputDir=D:\FINALITE\installeur
OutputBaseFilename=MonLogiciel_Install
SetupIconFile=money.ico
Compression=lzma
SolidCompression=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "dist\form1.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "base_epargne.db"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "money.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "updater.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "images\*"; DestDir: "{app}\images"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Lancer Mon Logiciel"; Filename: "{app}\form1.exe"; IconFilename: "{app}\money.ico"
Name: "{group}\Mettre à jour le logiciel"; Filename: "{app}\updater.exe"; WorkingDir: "{app}"; IconFilename: "{app}\money.ico"; Flags: createonlyiffileexists
Name: "{group}\Désinstaller Mon Logiciel"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Mon Logiciel d'Épargne"; Filename: "{app}\form1.exe"; IconFilename: "{app}\money.ico"

[Run]
Filename: "{app}\form1.exe"; Description: "Lancer Mon Logiciel"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU
Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"
ValueType: string
ValueName: "MonLogiciel"
ValueData: "{app}\form1.exe"
