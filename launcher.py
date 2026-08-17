"""
Launcher Entry Point for Paradox2Firebird Studio Desktop / Standalone Package.
Handles frozen PyInstaller paths, writable AppData storage, local server lifecycle, and automatic browser launch.
"""

import sys
import os
import time
import webbrowser
import threading

def get_base_dir():
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle directory
        return sys._MEIPASS
    return os.path.abspath(os.path.dirname(__file__))

def get_user_data_dir():
    """Returns a writable directory in %APPDATA% or user home for uploads and output."""
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        target = os.path.join(appdata, 'Paradox2FirebirdStudio')
    else:
        target = os.path.join(os.path.expanduser('~'), '.paradox2firebird')
    os.makedirs(target, exist_ok=True)
    return target

# Set environment before importing backend.app
os.environ['P2F_BASE_DIR'] = get_base_dir()
os.environ['P2F_USER_DATA_DIR'] = get_user_data_dir()

# Import the Flask application
from backend.app import app, SAMPLES_DIR, UPLOADS_DIR, OUTPUT_DIR

def open_browser_delayed(url, delay=1.2):
    time.sleep(delay)
    print(f"Abrindo navegador em: {url}")
    webbrowser.open(url)

def main():
    port = 5000
    url = f"http://127.0.0.1:{port}"

    print("=" * 70)
    print("   PARADOX 2 FIREBIRD CONVERSION STUDIO")
    print("   Versão 2.0 Desktop / Web Edition")
    print("=" * 70)
    print(f" * Servidor local: {url}")
    print(f" * Pasta de dados: {get_user_data_dir()}")
    print(" * Feche esta janela para encerrar o aplicativo.")
    print("=" * 70)

    # Start browser in background
    threading.Thread(target=open_browser_delayed, args=(url,), daemon=True).start()

    # Run Flask server
    try:
        app.run(host='127.0.0.1', port=port, debug=False)
    except KeyboardInterrupt:
        print("\nAplicativo finalizado.")

if __name__ == '__main__':
    main()
