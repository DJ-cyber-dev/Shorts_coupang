# -*- mode: python ; coding: utf-8 -*-
from importlib.util import find_spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_all

datas = []
torchvision_spec = find_spec('torchvision')
if not torchvision_spec or not torchvision_spec.origin:
    raise SystemExit('torchvision must be installed in the active build environment.')
torchvision_dir = Path(torchvision_spec.origin).parent
native_extensions = [
    torchvision_dir / name
    for name in ('_C_stable.pyd', '_C.pyd', 'image_stable.pyd', 'image.pyd')
    if (torchvision_dir / name).is_file()
]
if not any(path.name in {'_C_stable.pyd', '_C.pyd'} for path in native_extensions):
    raise SystemExit(f'torchvision C++ extension was not found under {torchvision_dir}.')
binaries = [(str(path), 'torchvision') for path in native_extensions]
hiddenimports = ['torchvision.transforms']
binaries += collect_dynamic_libs('torchvision')
tmp_ret = collect_all('easyocr')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['src/shorts_studio/text_removal/worker.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShortsStudioWorker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='ShortsStudioWorker',
)
