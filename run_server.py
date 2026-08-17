"""
Paradox2Firebird Studio Launcher
Starts the Web Server and opens the application in your default browser.
"""

import os
import sys
import webbrowser
import threading
import time

# Ensure UTF-8 output on Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def main():
    print("=" * 70)
    print("   [PARADOX 2 FIREBIRD CONVERSION STUDIO - Web Edition]")
    print("=" * 70)
    print("   * Motor Paradox: Leitura e escrita binaria direta (.DB, .PX, .MB)")
    print("   * Gerador Firebird: DDL, DML, Sequences, Triggers (v2.5, v3.0, v4.0, v5.0)")
    print("   * Bancos de Teste: Clientes, Produtos, Fornecedores, Vendas, Itens")
    print("=" * 70)

    from backend.app import app, generate_all_samples, SAMPLES_DIR

    # Guarantee samples are generated
    generate_all_samples(SAMPLES_DIR)
    print("   [OK] Bases de teste Paradox geradas e prontas em ./samples")

    port = 5000
    url = f"http://127.0.0.1:{port}"
    print(f"\n   -> Aplicacao Web iniciada com sucesso em: {url}")
    print("   -> Pressione Ctrl+C para encerrar o servidor.\n")

    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    app.run(host='127.0.0.1', port=port, debug=False)

if __name__ == '__main__':
    main()
