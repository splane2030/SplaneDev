# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['form1.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('fenetre_depot.py', '.'), 
        ('interface_retrait.py', '.'), 
        ('export_pdf.py', '.'), 
        ('inscription_menu.py', '.'), 
        ('export_carte.py', '.'), 
        ('depot_export.py', '.'), 
        ('interface_doublons.py', '.'), 
        ('data_epargne.db', '.'),                    # ✅ base de données
        ('images', 'images')                         # ✅ dossier images
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='form1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                         # ✅ pas de console pour app GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='money.ico'                       # ✅ ton icône
)
