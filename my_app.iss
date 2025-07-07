; Script complet pour installer ton logiciel d’épargne
; Fichier : MonLogiciel.iss

[Setup]
AppName=Mon Logiciel d'Épargne
AppVersion=1.0
DefaultDirName={pf}\MonLogiciel
DefaultGroupName=Mon Logiciel d'Épargne
UninstallDisplayIcon={app}\form1.exe
OutputDir=.
OutputBaseFilename=MonLogiciel_Install
SetupIconFile=money.ico
Compression=lzma
SolidCompression=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
; Fichier exécutable principal
Source: "form1.exe"; DestDir: "{app}"; Flags: ignoreversion

; Fichiers Python nécessaires (peuvent être en .pyc ou .pyd si compilés)
Source: "fenetre_depot.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "interface_retrait.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "export_pdf.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "inscription_menu.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "export_carte.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "depot_export.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "interface_doublons.py"; DestDir: "{app}"; Flags: ignoreversion

; Fichier base de données, installé uniquement s'il n'existe pas déjà
Source: "base_epargne.db"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

; Icône
Source: "money.ico"; DestDir: "{app}"; Flags: ignoreversion

; Fichier updater.exe (facultatif)
Source: "updater.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Dossier images (et sous-dossiers)
Source: "images\*"; DestDir: "{app}\images"; Flags: recursesubdirs ignoreversion

[Icons]
; Raccourcis
Name: "{group}\Lancer Mon Logiciel"; Filename: "{app}\form1.exe"; IconFilename: "{app}\money.ico"
Name: "{group}\Mettre à jour le logiciel"; Filename: "{app}\updater.exe"; WorkingDir: "{app}"; IconFilename: "{app}\money.ico"; Flags: createonlyiffileexists
Name: "{group}\Désinstaller Mon Logiciel"; Filename: "{uninstallexe}"

; Raccourci sur le Bureau
Name: "{commondesktop}\Mon Logiciel d'Épargne"; Filename: "{app}\form1.exe"; IconFilename: "{app}\money.ico"

[Run]
; Lancer le logiciel juste après installation
Filename: "{app}\form1.exe"; Description: "Lancer Mon Logiciel"; Flags: nowait postinstall skipifsilent

[Registry]
; Lancement automatique au démarrage de Windows
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
Name: "MonLogiciel"; ValueType: string; ValueData: """{app}\form1.exe"""
