# OpenSayo v1.15 — PyInstaller one-folder Windows build
from pathlib import Path
root = Path(SPECPATH).resolve()
py = root / 'py'
datas = [
    (str(py / 'captures'), 'captures'),
]
a = Analysis([str(py / 'opensayo_v019_alpha22.py')], pathex=[str(py)],
    binaries=[], datas=datas, hiddenimports=['hid', 'eight_key_script_read_v111', 'eight_key_protocol_v111'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OpenSayo',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, icon=str(root / 'assets' / 'Shinobi_OpenSayo.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
    name='OpenSayo')
