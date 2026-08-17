# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

added_files = [
    ('frontend', 'frontend'),
    ('samples', 'samples'),
    ('documentacao', 'documentacao'),
]

excluded_modules = [
    'matplotlib', 'tkinter', '_tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    'IPython', 'sphinx', 'docutils', 'jedi', 'black', 'pytest', 'yapf',
    'scipy', 'pandas', 'torch', 'sympy', 'zmq', 'PIL', 'Pillow',
    'nbformat', 'jsonschema', 'cryptography', 'setuptools', 'distutils'
]

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'backend',
        'backend.app',
        'backend.paradox_engine',
        'backend.firebird_engine',
        'backend.sample_generator',
        'backend.csv_engine',
        'backend.fb_migrator',
        'backend.diagnostics_engine',
        'backend.relations_engine',
        'backend.audit_engine',
        'firebird.driver',
        'werkzeug',
        'flask',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Paradox2Firebird',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
