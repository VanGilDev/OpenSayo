# PyInstaller onedir build, Windows x64
from pathlib import Path
root = Path(SPECPATH)
py = root / 'py'
datas = [
    (str(root / 'DEFAULT_QUANTUM.osayo'), '.'),
    (str(py / 'captures'), 'captures'),
]
a = Analysis([str(py / 'opensayo_v019_alpha22.py')], pathex=[str(py)], binaries=[], datas=datas, hiddenimports=['hid'], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OpenSayo', debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, icon=str(root / 'assets' / 'Shinobi_OpenSayo.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='OpenSayo')
