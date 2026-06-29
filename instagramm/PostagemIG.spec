# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o Postagem IG.

Empacota toda a UI (customtkinter) e a engine (instagrapi + dependências)
num app de pasta única (onedir). A pasta `data/` é criada ao lado do .exe
na primeira execução (ver core/config.py).
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Bibliotecas que precisam levar dados/binários e submódulos junto
for pkg in ("customtkinter", "instagrapi", "moviepy", "imageio_ffmpeg"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("PIL")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "test"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PostagemIG",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PostagemIG",
)
