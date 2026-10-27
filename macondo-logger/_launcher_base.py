"""
Arranque del .exe.

launcher_macondo.py solo dice que archivo de app arranca y llama a run(). Aqui esta toda la fontaneria: buscar un puerto libre, abrir el
navegador y lanzar Streamlit en modo headless con el tema Macondo embebido
(para no depender de la carpeta .streamlit junto al .exe).
"""

import os
import socket
import sys
import threading
import time
import webbrowser

from streamlit.web import cli as stcli

import macondo_theme  # para reutilizar exactamente los mismos colores del tema

PREFERRED_PORT = 8501


def _resource_path(name):
    """Ruta a un archivo, funcione desde el .exe (carpeta temporal de PyInstaller) o desde el codigo."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _free_port(preferred):
    """Usa el puerto preferido; si esta ocupado (otra app abierta), toma uno libre."""
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    return preferred


def _open_browser(port):
    time.sleep(3)  # darle tiempo a Streamlit a levantar antes de abrir el navegador
    webbrowser.open(f"http://localhost:{port}")


def run(app_file):
    """Arranca la app indicada. app_file es el nombre del .py (ej. 'macondo_app.py')."""
    port = _free_port(PREFERRED_PORT)
    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
    sys.argv = [
        "streamlit", "run", _resource_path(app_file),
        "--global.developmentMode=false",
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
        # Tema Macondo embebido, tomando los colores del propio macondo_theme.
        "--theme.base=light",
        f"--theme.primaryColor={macondo_theme.MOSTAZA}",
        f"--theme.backgroundColor={macondo_theme.FONDO}",
        f"--theme.secondaryBackgroundColor={macondo_theme.BEIGE}",
        f"--theme.textColor={macondo_theme.MARRON}",
        "--theme.font=sans serif",
    ]
    sys.exit(stcli.main())
