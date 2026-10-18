"""Tudo que depende do Windows: ler o Num Lock, apitar, executar os blocos (teclas, mouse,
programas, sites), mostrar a prévia e registrar o início automático."""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import shutil
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import avisos
import posicao
from navegador import Navegador

IS_WIN = sys.platform == "win32"
CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME_RUN = "NumpadDeck"
CREATE_NO_WINDOW = 0x08000000
PAUSA_ENTRE_BLOCOS = 0.03  # respiro para o programa em foco reagir antes do próximo bloco


class PlataformaWindows:
    def __init__(self, ui, url_painel: str, pasta_dados: Path | None = None):
        self.ui = ui
        self.url = url_painel
        pasta = Path(pasta_dados) if pasta_dados else Path.home() / ".numpad_deck"
        self.pasta_dados = pasta
        self.navegador = Navegador(pasta / "perfil-navegador")
        self.segredos = avisos.Segredos(pasta)
        self.pasta_saidas = pasta / "saidas"

    # ------------------------------------------------------------ Num Lock
    def numlock_ligado(self) -> bool:
        if not IS_WIN:
            return True
        return bool(ctypes.windll.user32.GetKeyState(0x90) & 1)

    def alternar_numlock(self) -> None:
        from pynput.keyboard import Controller, Key

        teclado = Controller()
        teclado.press(Key.num_lock)
        teclado.release(Key.num_lock)

    # ------------------------------------------------------------ avisos
    def apitar(self, sucesso: bool = True) -> None:
        try:
            import winsound

            if sucesso:
                winsound.Beep(900, 80)
            else:  # dois tons descendo = "não funcionou"
                winsound.Beep(420, 130)
                winsound.Beep(300, 210)
        except Exception:
            print("\a", end="", flush=True)

    def toast(self, titulo, linhas=(), ms=3500) -> None:
        self.ui.toast(titulo, linhas, ms)

    # ------------------------------------------------------------ prévia grande
    def mostrar_previa(self, pagina, itens, segundos, alternar, nome="") -> None:
        self.ui.previa(pagina, itens, segundos, alternar, nome)

    def previa_visivel(self) -> bool:
        return self.ui.previa_visivel

    def fechar_previa(self) -> None:
        self.ui.fechar_previa()

    # ------------------------------------------------------------ blocos
    def executar(self, bloco: dict) -> None:
        """Executa um bloco "de verdade". Esperar, repetir, se, chamar, ir_pagina, variavel e aviso são do núcleo."""
        tipo = bloco["tipo"]
        if tipo == "atalho":
            self._atalho(bloco["teclas"])
        elif tipo == "texto":
            self._texto(bloco["texto"])
        elif tipo == "colar":
            self._colar(bloco["texto"])
        elif tipo == "clique":
            self._clique(bloco, self._ponto(bloco))
        elif tipo == "mover":
            self._mover(self._ponto(bloco))
        elif tipo == "rolagem":
            self._rolagem(bloco)
        elif tipo == "abrir":
            self._abrir(bloco)
        elif tipo == "site":
            if bloco.get("controlado"):
                self.navegador.abrir(bloco["url"])
            else:
                webbrowser.open(bloco["url"])
        elif tipo == "comando":
            self._comando(bloco)
        elif tipo == "web_clicar":
            self.navegador.clicar(bloco["seletor"], bloco["aba"])
        elif tipo == "web_preencher":
            self.navegador.preencher(bloco["seletor"], bloco["texto"], bloco["aba"])
        elif tipo == "midia":
            self._midia(bloco)
        elif tipo == "captura":
            self._captura(bloco)
        elif tipo == "sistema":
            self._sistema(bloco["acao"])
        elif tipo == "aviso":
            self._aviso(bloco)
        else:
            raise RuntimeError(f"Bloco não suportado: {tipo}")
        time.sleep(PAUSA_ENTRE_BLOCOS)

    # ------------------------------------------------------------ avisos (pop-up, WhatsApp, Bloco de Notas)
    def _aviso(self, bloco: dict) -> None:
        canal = bloco["canal"]
        if canal == "popup":
            self.ui.aviso(bloco["titulo"], bloco["texto"], bloco["tamanho"], bloco["posicao"],
                          bloco.get("area"), bloco["segundos"])
        elif canal == "whatsapp":
            if bloco.get("modo", "link") == "evolution":
                self.enviar_whatsapp(bloco["numero"], bloco["texto"])
            else:
                self._whatsapp_link(bloco["numero"], bloco["texto"], bloco.get("espera", 10))
        elif canal == "bloco_notas":
            self._bloco_notas(bloco)
        else:
            raise RuntimeError(f"Tipo de aviso não suportado: {canal}")

    def _whatsapp_link(self, numero: str, texto: str, espera: float) -> None:
        """Abre o link wa.me (WhatsApp Web ou app, conforme o computador), espera carregar e aperta Enter."""
        webbrowser.open(avisos.link_whatsapp(numero, texto))
        time.sleep(espera)
        self._apertar_enter()

    @staticmethod
    def _apertar_enter() -> None:
        from pynput.keyboard import Controller, Key

        teclado = Controller()
        teclado.press(Key.enter)
        teclado.release(Key.enter)

    def enviar_whatsapp(self, numero: str, texto: str) -> None:
        url, instancia, chave = self.segredos.evolution()
        avisos.enviar_whatsapp(url, instancia, chave, numero, texto)

    def _bloco_notas(self, bloco: dict) -> None:
        if bloco["origem"] == "saida":
            arquivo = avisos.gerar_txt_da_saida(bloco, self.pasta_saidas, self._interpretador())
        else:
            arquivo = avisos.resolver_arquivo(bloco, self.pasta_saidas)
            if not arquivo.is_file():
                raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
        if not IS_WIN:
            raise RuntimeError(f"O Bloco de Notas só existe no Windows (arquivo: {arquivo})")
        self._abrir_no_bloco_de_notas(arquivo)

    @staticmethod
    def _abrir_no_bloco_de_notas(arquivo: Path) -> None:
        subprocess.Popen(["notepad.exe", str(arquivo)])

    # ------------------------------------------------------------ condições (Esperar / Se)
    def avaliar_condicao(self, c: dict) -> bool:
        tipo = c["tipo"]
        if tipo == "pagina":
            if c["alvo"] == "seletor":
                return self.navegador.existe(c["valor"], c.get("aba", ""))
            return self.navegador.tem_texto(c["valor"], c.get("aba", ""))
        if not IS_WIN:
            raise RuntimeError("Essa condição só funciona no Windows.")
        if tipo == "janela":
            alvo = c["texto"].lower()
            if c["modo"] == "ativa":
                return alvo in self._titulo_janela_ativa().lower()
            return any(alvo in t.lower() for t in self._titulos_janelas())
        if tipo == "pixel":
            cor = self.ler_cor(c["x"], c["y"])
            if cor is None:
                return False
            quero = tuple(int(c["cor"][i:i + 2], 16) for i in (1, 3, 5))
            tem = tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))
            return all(abs(a - b) <= c["tolerancia"] for a, b in zip(quero, tem))
        raise RuntimeError(f"Condição não suportada: {tipo}")

    @staticmethod
    def _titulo_janela_ativa() -> str:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        tamanho = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(hwnd, buf, tamanho + 1)
        return buf.value

    @staticmethod
    def _titulos_janelas() -> list[str]:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        titulos: list[str] = []
        enum = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cada(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                tamanho = user32.GetWindowTextLengthW(hwnd)
                if tamanho:
                    buf = ctypes.create_unicode_buffer(tamanho + 1)
                    user32.GetWindowTextW(hwnd, buf, tamanho + 1)
                    titulos.append(buf.value)
            return True

        user32.EnumWindows.argtypes = [enum, wintypes.LPARAM]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.EnumWindows(enum(cada), 0)
        return titulos

    @staticmethod
    def ler_cor(x: int, y: int) -> str | None:
        """Cor do pixel na tela, como #rrggbb (None se o Windows não conseguir ler)."""
        if not IS_WIN:
            return None
        from ctypes import wintypes

        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        user32.GetDC.restype = wintypes.HDC
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        gdi32.GetPixel.restype = wintypes.DWORD
        gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        dc = user32.GetDC(None)
        try:
            valor = gdi32.GetPixel(dc, int(x), int(y))
        finally:
            user32.ReleaseDC(None, dc)
        if valor == 0xFFFFFFFF:
            return None
        return "#{:02x}{:02x}{:02x}".format(valor & 0xFF, (valor >> 8) & 0xFF, (valor >> 16) & 0xFF)

    # ------------------------------------------------------------ colar, mídia, print, sistema, comando
    def _colar(self, texto: str) -> None:
        self.ui.copiar_texto(texto)
        time.sleep(0.05)
        self._atalho([{"vk": 0xA2}, {"vk": 0x56}])   # Ctrl + V
        time.sleep(0.15)                              # o programa lê a área de transferência logo em seguida

    @staticmethod
    def _midia(bloco: dict) -> None:
        from pynput.keyboard import Controller, Key

        tecla = {"volume_mais": Key.media_volume_up, "volume_menos": Key.media_volume_down,
                 "mudo": Key.media_volume_mute, "play_pausa": Key.media_play_pause,
                 "proxima": Key.media_next, "anterior": Key.media_previous}[bloco["acao"]]
        teclado = Controller()
        for _ in range(bloco["vezes"]):
            teclado.press(tecla)
            teclado.release(tecla)
            time.sleep(0.02)

    def _captura(self, bloco: dict) -> None:
        from PIL import ImageGrab

        pasta = Path.home() / "Pictures" / "NumpadDeck"
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / f"print_{datetime.now():%Y%m%d_%H%M%S}.png"
        ImageGrab.grab(all_screens=bloco["tela"] == "todas").save(arquivo)
        self.ui.toast("Print salvo", [str(arquivo)], 2500)

    @staticmethod
    def _sistema(acao: str) -> None:
        if not IS_WIN:
            raise RuntimeError("Essa ação só funciona no Windows.")
        user32 = ctypes.windll.user32
        if acao == "bloquear":
            user32.LockWorkStation()
        elif acao == "monitor_off":
            user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)   # HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, desligar

    @staticmethod
    def _comando(bloco: dict) -> None:
        if bloco["shell"] == "powershell":
            exe = shutil.which("powershell") or shutil.which("pwsh")
            if not exe:
                raise RuntimeError("PowerShell não encontrado.")
            args = [exe, "-NoProfile", "-NonInteractive", "-Command", bloco["comando"]]
        else:
            args = ["cmd", "/c", bloco["comando"]]
        flags = CREATE_NO_WINDOW if IS_WIN else 0
        if not bloco["esperar"]:
            subprocess.Popen(args, creationflags=flags, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        try:
            r = subprocess.run(args, creationflags=flags, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, errors="replace", timeout=120)
        except subprocess.TimeoutExpired:
            raise RuntimeError("O comando passou de 120 segundos e foi interrompido.") from None
        if r.returncode != 0:
            detalhe = (r.stderr or r.stdout or "").strip().splitlines()
            raise RuntimeError(f"O comando terminou com erro {r.returncode}" + (f": {detalhe[0][:120]}" if detalhe else ""))

    @staticmethod
    def _atalho(teclas) -> None:
        from pynput.keyboard import Controller, KeyCode

        teclado = Controller()
        codigos = [KeyCode.from_vk(t["vk"]) for t in teclas]
        for k in codigos:
            teclado.press(k)
            time.sleep(0.02)
        for k in reversed(codigos):
            teclado.release(k)
            time.sleep(0.01)

    @staticmethod
    def _texto(texto: str) -> None:
        from pynput.keyboard import Controller

        Controller().type(texto)

    @staticmethod
    def _clique(bloco: dict, ponto: tuple) -> None:
        from pynput.mouse import Button, Controller

        mouse = Controller()
        botao = {"esquerdo": Button.left, "direito": Button.right, "meio": Button.middle}[bloco["botao"]]
        original = mouse.position
        mouse.position = ponto
        time.sleep(0.03)
        mouse.click(botao, 2 if bloco.get("duplo") else 1)
        time.sleep(0.03)
        mouse.position = original  # devolve o cursor para onde estava

    @staticmethod
    def _mover(ponto: tuple) -> None:
        from pynput.mouse import Controller

        Controller().position = ponto  # fica lá: o próximo bloco continua dali

    # ------------------------------------------------------------ posição relativa a uma janela
    def _ponto(self, bloco: dict) -> tuple:
        """Ponto da tela onde clicar/mover: fixo, ou calculado a partir de onde a janela está agora."""
        if bloco.get("alvo", "tela") == "tela":
            return bloco["x"], bloco["y"]
        if not IS_WIN:
            raise RuntimeError("A posição relativa a uma janela só funciona no Windows.")
        hwnd = self._achar_janela(bloco["janela"])
        if not hwnd:
            raise RuntimeError(f'Janela não encontrada: "{bloco["janela"]}". Abra o programa (ou use “Esperar” pela janela) antes do clique.')
        if bloco.get("trazer", True):
            self._trazer_para_frente(hwnd)
        rect = self._area_da_janela(hwnd)
        try:
            return posicao.calcular_ponto(bloco, rect)
        except ValueError as e:
            raise RuntimeError(f'Janela "{bloco["janela"]}": {e}') from None

    @staticmethod
    def _enum_janelas() -> list:
        """(hwnd, título) das janelas visíveis com título, da que está na frente para a de trás."""
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        achadas: list = []
        enum = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cada(hwnd, _l):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    achadas.append((hwnd, buf.value))
            return True

        user32.EnumWindows.argtypes = [enum, wintypes.LPARAM]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.EnumWindows(enum(cada), 0)
        return achadas

    def _achar_janela(self, texto: str):
        """A janela cujo título contém o texto; se a que está em primeiro plano serve, é ela."""
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        alvo = texto.lower()
        janelas = self._enum_janelas()
        frente = user32.GetForegroundWindow()
        for hwnd, titulo in janelas:
            if hwnd == frente and alvo in titulo.lower():
                return hwnd
        for hwnd, titulo in janelas:
            if alvo in titulo.lower():
                return hwnd
        return None

    @staticmethod
    def _area_da_janela(hwnd) -> tuple:
        """(esquerda, topo, largura, altura), na tela, da área útil da janela (sem barra de título e bordas)."""
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        r, p = wintypes.RECT(), wintypes.POINT(0, 0)
        user32.GetClientRect(hwnd, ctypes.byref(r))
        user32.ClientToScreen(hwnd, ctypes.byref(p))
        return p.x, p.y, r.right - r.left, r.bottom - r.top

    @staticmethod
    def _trazer_para_frente(hwnd) -> None:
        """Restaura (se minimizada) e põe a janela na frente, para o clique cair nela e não em outra por cima."""
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.25)
        frente = user32.GetForegroundWindow()
        if frente != hwnd:
            minha, dela = kernel32.GetCurrentThreadId(), user32.GetWindowThreadProcessId(frente, None)
            user32.AttachThreadInput(minha, dela, True)   # o Windows só deixa trocar o foco quem "participa" dele
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(minha, dela, False)
        time.sleep(0.15)

    def marcar_em_janela(self, x: int, y: int, ancora: str) -> dict:
        """Para o painel: qual janela está no ponto (x, y) e onde ele fica dentro dela."""
        if not IS_WIN:
            raise RuntimeError("Marcar um ponto numa janela só funciona no Windows.")
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        hwnd = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(int(x), int(y))), 2)   # GA_ROOT: a janela de cima
        titulo = ""
        if hwnd:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            titulo = buf.value
        if not titulo:
            raise RuntimeError("Não encontrei uma janela de programa nesse ponto (área de trabalho?).")
        try:
            campos = posicao.referencia(int(x), int(y), self._area_da_janela(hwnd), ancora)
        except posicao.ForaDaJanela as e:
            raise RuntimeError(str(e)) from None
        return {"janela": titulo, "ancora": ancora, **campos}

    @staticmethod
    def _rolagem(bloco: dict) -> None:
        from pynput.mouse import Controller

        passos = bloco["quantidade"] if bloco["direcao"] == "cima" else -bloco["quantidade"]
        Controller().scroll(0, passos)

    @staticmethod
    def _interpretador() -> str:
        if not getattr(sys, "frozen", False):
            return sys.executable
        for nome in ("pythonw", "python", "py"):
            achado = shutil.which(nome)
            if achado:
                return achado
        raise RuntimeError("Python não encontrado. Instale o Python ou use um .bat/.exe.")

    def _abrir(self, bloco: dict) -> None:
        caminho, argumentos = bloco["caminho"], bloco.get("argumentos", "")
        arquivo = Path(caminho)
        so_nome = not re.search(r"[\\/]", caminho)  # ex.: "chrome" (o Windows acha pelo "App Paths")
        if arquivo.is_dir():  # pasta: abre no Explorer
            if not IS_WIN:
                raise RuntimeError("Só é possível abrir pastas no Windows.")
            os.startfile(str(arquivo))
            return
        if not arquivo.is_file() and not so_nome:
            raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
        if arquivo.suffix.lower() in (".py", ".pyw") and arquivo.is_file():
            import shlex

            subprocess.Popen([self._interpretador(), str(arquivo), *shlex.split(argumentos, posix=False)],
                             cwd=str(arquivo.parent), creationflags=CREATE_NO_WINDOW if IS_WIN else 0)
        elif IS_WIN:
            if argumentos:
                os.startfile(str(arquivo) if arquivo.is_file() else caminho, arguments=argumentos)
            else:
                os.startfile(str(arquivo) if arquivo.is_file() else caminho)
        else:
            raise RuntimeError("Só é possível abrir esse tipo de arquivo no Windows.")

    # ------------------------------------------------------------ iniciar com o Windows
    @staticmethod
    def _comando_autostart() -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --silencioso'
        interpretador = Path(sys.executable)
        sem_console = interpretador.with_name("pythonw.exe")
        if sem_console.exists():
            interpretador = sem_console
        return f'"{interpretador}" "{Path(sys.argv[0]).resolve()}" --silencioso'

    def autostart_ligado(self) -> bool:
        if not IS_WIN:
            return False
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as chave:
                winreg.QueryValueEx(chave, NOME_RUN)
            return True
        except FileNotFoundError:
            return False

    def definir_autostart(self, ligado: bool) -> None:
        if not IS_WIN:
            raise RuntimeError("Início automático só existe no Windows.")
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as chave:
            if ligado:
                winreg.SetValueEx(chave, NOME_RUN, 0, winreg.REG_SZ, self._comando_autostart())
            else:
                try:
                    winreg.DeleteValue(chave, NOME_RUN)
                except FileNotFoundError:
                    pass
