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
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

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
    if "--reiniciado" in sys.argv:    # acabou de se atualizar: espera o processo antigo largar a porta
        porta_antiga = Config().opcoes()["porta"]
        for _ in range(30):
            if not ja_esta_rodando(porta_antiga):
                break
            time.sleep(0.3)
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
    estado = {"reiniciar": False}
    exe = Path(sys.executable)
    empacotado = bool(getattr(sys, "frozen", False))

    def procurar_atualizacao(manual: bool = False) -> dict:
        """Procura, baixa e instala a versão nova do GitHub (só no .exe). Reinicia o programa se atualizou."""
        import atualizador
        from versao import VERSAO

        if not empacotado:
            return {"status": "dev", "tag": VERSAO}
        try:
            r = atualizador.verificar_e_atualizar(
                VERSAO, exe, ao_baixar=lambda tag: ui.toast("Atualizando o Numpad Deck", [f"Baixando a versão {tag}…"], 8000))
        except atualizador.ErroAtualizacao as e:
            logging.warning("Atualização: %s", e)
            if manual:
                raise
            return {"status": "erro", "tag": VERSAO}
        if r["status"] == "atualizado":
            logging.info("Atualizado para %s", r["tag"])
            ui.toast("Numpad Deck atualizado", [f"Versão {r['tag']} instalada. Reiniciando…"], 3000)
            estado["reiniciar"] = True
            threading.Timer(1.5, ui.sair).start()
        return r

    app = criar_app(cfg, nucleo, ui, plat, token, porta, atualizar=procurar_atualizacao)
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

    if empacotado:
        import atualizador

        atualizador.limpar_restos(exe)      # sobras da atualização anterior
        if cfg.opcoes()["atualizar_ao_abrir"]:
            threading.Thread(target=procurar_atualizacao, name="atualizador", daemon=True).start()

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
    if estado["reiniciar"]:
        # PYINSTALLER_RESET_ENVIRONMENT: o novo .exe desempacota na própria pasta temporária (a deste processo some ao sair)
        subprocess.Popen([str(exe), *(["--silencioso"] if silencioso else []), "--reiniciado"], close_fds=True,
                         env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
                         creationflags=0x00000008 | 0x00000200 if IS_WIN else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
