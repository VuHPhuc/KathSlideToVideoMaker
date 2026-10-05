# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

datas = [
    ('app/resources', 'app/resources'),
]

binaries = []
if os.path.exists('.venv/Scripts/ffmpeg.exe'):
    binaries.append(('.venv/Scripts/ffmpeg.exe', '.'))
if os.path.exists('.venv/Scripts/ffprobe.exe'):
    binaries.append(('.venv/Scripts/ffprobe.exe', '.'))

hiddenimports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtMultimedia',
    'PyQt6.QtMultimediaWidgets',
    'faster_whisper',
    'ctranslate2',
    'piper',
    'edge_tts',
    'pydub',
    'docx',
    'pptx',
    'fitz',
    'comtypes',
    'google.genai',
    'imageio_ffmpeg',
    'xlsxwriter',
]

for pkg in ['ctranslate2', 'faster_whisper', 'piper', 'onnxruntime', 'google.genai']:
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hiddenimports
    except Exception as e:
        print(f"Warning collecting {pkg}: {e}")

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KathFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app/resources/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='KathFlow',
)
