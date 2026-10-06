"""Inicia o servidor local: python -m app"""
import threading
import webbrowser

import uvicorn

from .config import HOST, PORTA


def main() -> None:
    url = f"http://{HOST}:{PORTA}"
    print(f"\n  Transcritor Local em {url}  (Ctrl+C para encerrar)\n")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=HOST, port=PORTA, log_level="warning")


if __name__ == "__main__":
    main()
