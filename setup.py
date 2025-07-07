import os
from cx_Freeze import setup, Executable

# Définir les fichiers à inclure
include_files = [
    ('fenetre_depot.py', '.'), 
    ('interface_retrait.py', '.'), 
    ('export_pdf.py', '.'), 
    ('inscription_menu.py', '.'), 
    ('export_carte.py', '.'), 
    ('depot_export.py', '.'), 
    ('interface_doublons.py', '.'), 
    ('data_epargne.db', '.'),          # base de données
    ('images', 'images'),              # dossier images
    ('money.ico', '.')                 # icône
]

# Configuration de l'exécutable
base = "Win32GUI"  # Pas de console (GUI app)

executables = [
    Executable(
        script="form1.py",
        base=base,
        icon="money.ico",
        target_name="form1.exe"
    )
]

# Setup
setup(
    name="MonLogicielEpargne",
    version="1.0",
    description="Application de gestion d'épargne",
    options={
        "build_exe": {
            "include_files": include_files,
            "packages": [],          # Ajoute ici des packages si nécessaire
            "excludes": [],
            "include_msvcr": True    # Important pour éviter certaines erreurs sur Windows
        }
    },
    executables=executables
)
