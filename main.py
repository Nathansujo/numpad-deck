"""Numpad Deck — ponto de entrada.

  NumpadDeck.exe              abre o painel (e inicia o programa em segundo plano se ainda não estiver)
  NumpadDeck.exe --silencioso inicia só em segundo plano (é o que o início automático usa)
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import secrets
import sys
import urllib.request
import webbrowser

from configuracao import Config

IS_WIN = sys.platform == "win32"


def aviso(texto: str) -> None:
    if IS_WIN:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, texto, "Numpad Deck", 0x30)
    else:
        print(texto, file=sys.stderr)


def ja_esta_rodando(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/ping", timeout=1.5) as r:
            return json.load(r).get("app") == "numpad-deck"
    except Exception:
        return False


def configurar_log(cfg: Config) -> None:
    # Sem console (--noconsole) não existe stdout/stderr: tudo vai para o arquivo de log.
    destino = logging.handlers.RotatingFileHandler(cfg.pasta / "numpad_deck.log", maxBytes=200_000,
                                                   backupCount=1, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[destino],
                        format="%(asctime)s %(levelname)s %(message)s")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def main() -> int:
    silencioso = "--silencioso" in sys.argv
    cfg = Config()
    porta = cfg.opcoes()["porta"]
    url = f"http://127.0.0.1:{porta}/"

    if ja_esta_rodando(porta):
        if not silencioso:
            webbrowser.open(url)  # já está ativo: só mostra o painel
        return 0

    configurar_log(cfg)
    if IS_WIN:  # coordenadas do clique iguais em qualquer escala do Windows
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()

    from nucleo import NucleoDeck
    from plataforma_win import PlataformaWindows
    from servidor import criar_app, iniciar_servidor
    from ui_tk import InterfaceTk

    cfg.limpar_imagens_orfas()
    ui = InterfaceTk()
    plat = PlataformaWindows(ui, url, cfg.pasta)
    nucleo = NucleoDeck(cfg, plat)
    token = secrets.token_urlsafe(24)
    app = criar_app(cfg, nucleo, ui, plat, token, porta)
    try:
        servidor = iniciar_servidor(app, porta)
    except OSError:
        aviso(f"A porta {porta} está ocupada por outro programa.\n"
              f"Mude o valor de \"porta\" em {cfg.arquivo} e abra de novo.")
        return 2

    nucleo.iniciar()
    listener = None
    if IS_WIN:
        from hook_win import iniciar_hook

        listener = iniciar_hook(nucleo)
    else:
        logging.warning("Fora do Windows só o painel funciona (sem captura global de teclado).")

    ui.toast("Numpad Deck ativo", [f"Página {cfg.pagina_atual} · Num Lock apagado = modo deck"], 2500)
    if not silencioso:
        webbrowser.open(url)

    try:
        ui.loop()
    finally:
        if listener is not None:
            listener.stop()
        nucleo.encerrar()
        servidor.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
