# Execute pelo GERAR_EXE.bat no Windows.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('nicegui')
a = Analysis(['main.py'], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FeAbbehusenFlow',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FeAbbehusenFlow')
