# -*- mode: python ; coding: utf-8 -*-
# Macondo Logger.
# Build:  build_exe.bat   (o: python -m PyInstaller MacondoLogger.spec --noconfirm)
# Resultado: dist\MacondoLogger.exe
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

# Archivos .py de la app. Streamlit los carga en tiempo de ejecucion (no los ve
# el analisis estatico de PyInstaller), asi que hay que empaquetarlos como datos
# para que queden juntos y se puedan importar entre si.
APP_FILES = [
    "launcher_macondo.py",
    "macondo_app.py",
    "bug_logger_ui.py",
    "core.py",
    "macondo_theme.py",
    "macondo_login.py",
    "_launcher_base.py",
    "macondo_logo.jpg",
    "config.json",   # configuracion de EA, va dentro del .exe
]

datas = [(f, ".") for f in APP_FILES]
binaries = []
hiddenimports = [
    "streamlit.web.cli",
    "streamlit.runtime.scriptrunner.magic_funcs",
    "groq", "requests", "keyring",
]

datas += collect_data_files("streamlit")
for pkg in ("streamlit", "groq", "requests", "keyring"):
    datas += copy_metadata(pkg)

# groq trae su codigo que streamlit no arrastra solo: lo recogemos completo.
for pkg in ("groq",):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

# keyring descubre su backend de Windows (Credential Manager) en tiempo de
# ejecucion: hay que empaquetarlo completo o el .exe falla con "No module named keyring".
for pkg in ("keyring", "jaraco.classes", "jaraco.functools", "jaraco.context", "win32ctypes"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass
hiddenimports += collect_submodules("keyring.backends")

a = Analysis(
    ["launcher_macondo.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="MacondoLogger",
    console=False,  # sin ventana negra de consola
    upx=False,
)
