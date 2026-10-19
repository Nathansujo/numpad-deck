"""Navegador do Deck: Chrome (ou Edge) aberto com um perfil só do Numpad Deck e com a porta de
depuração ligada (somente em 127.0.0.1). É assim que o fluxo consegue olhar o HTML da página:
esperar um elemento aparecer, clicar nele ou preencher um campo.

Por que um perfil próprio: o Chrome não aceita controle remoto no seu perfil de uso diário.
Entre uma vez nas contas que precisar (Google, WhatsApp Web...) e o login fica guardado nesse perfil.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PORTA_CDP = 9333
CREATE_NO_WINDOW = 0x08000000
TOLERANCIA_PARTIDA = 25.0   # segundos em que "navegador ainda abrindo" não é erro


class ErroNavegador(Exception):
    pass


def _candidatos() -> list[str]:
    achados = []
    env = os.environ.get("NUMPAD_DECK_NAVEGADOR")
    if env:
        achados.append(env)
    if sys.platform == "win32":
        bases = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
        for base in filter(None, bases):
            achados.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
        for base in filter(None, bases):
            achados.append(str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
        try:
            import winreg

            for nome in ("chrome.exe", "msedge.exe"):
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{nome}") as k:
                    achados.append(winreg.QueryValue(k, None))
        except Exception:
            pass
    for nome in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        achado = shutil.which(nome)
        if achado:
            achados.append(achado)
    return achados


def achar_navegador() -> str | None:
    for caminho in _candidatos():
        if caminho and Path(caminho).is_file():
            return caminho
    return None


class Navegador:
    def __init__(self, pasta_perfil: Path, porta: int = PORTA_CDP, executavel: str | None = None,
                 args_extra: tuple = ()):
        self.pasta_perfil = Path(pasta_perfil)
        self.porta = porta
        self.executavel = executavel
        self.args_extra = tuple(args_extra)
        self._lancado_em = 0.0

    # ------------------------------------------------------------ conexão
    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.porta}"

    def _http(self, caminho: str, metodo: str = "GET", timeout: float = 2.0):
        req = urllib.request.Request(self.base + caminho, method=metodo)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            corpo = r.read()
        return json.loads(corpo) if corpo else None

    def disponivel(self) -> bool:
        try:
            self._http("/json/version", timeout=1.0)
            return True
        except Exception:
            return False

    def fotografar_html(self, html: str, seletores: list[str]) -> dict:
        return fotografar_html(html, seletores, self.executavel, self.args_extra)

    # ------------------------------------------------------------ abrir
    def abrir(self, url: str, destino: str = "nova", segundo_plano: bool = False) -> None:
        """Abre a página no navegador do Deck (aproveita ele se já estiver aberto).
        destino "atual": usa a aba que já está aberta (só vai para `url` se ela foi informada), sem abrir outra.
        segundo_plano: a aba nova abre sem passar na frente da que você está usando."""
        if destino == "atual":
            if not self.disponivel():
                if not url:
                    raise ErroNavegador("O navegador do Deck não está aberto. Abra-o antes (bloco \"Abrir site\" em aba nova).")
            else:
                if url:
                    aba = self._escolher_aba("")
                    if aba is not None:
                        sessao = _Sessao(aba["webSocketDebuggerUrl"])
                        try:
                            sessao.chamar("Page.navigate", url=url)
                        finally:
                            sessao.fechar()
                        return
                else:
                    return                      # nada a abrir: os próximos blocos usam a página que já está lá
        if self.disponivel() and segundo_plano:
            try:
                sessao = _Sessao(self._http("/json/version")["webSocketDebuggerUrl"])
                try:
                    sessao.chamar("Target.createTarget", url=url, background=True)
                finally:
                    sessao.fechar()
                return
            except Exception:
                pass                            # cai para a abertura normal abaixo
        if self.disponivel():
            try:
                self._http("/json/new?" + urllib.parse.quote(url, safe=":/?&=#%@+,;~!*'()$[]"), "PUT", timeout=5)
                return
            except Exception:
                pass  # cai para a abertura por linha de comando abaixo (abre nova aba na mesma janela)
        exe = self.executavel or achar_navegador()
        if not exe:
            raise ErroNavegador("Não encontrei o Chrome nem o Edge instalados.")
        self.pasta_perfil.mkdir(parents=True, exist_ok=True)
        args = [exe, f"--remote-debugging-port={self.porta}", "--remote-debugging-address=127.0.0.1",
                f"--user-data-dir={self.pasta_perfil}", "--no-first-run", "--no-default-browser-check",
                *self.args_extra, url]
        subprocess.Popen(args, creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        self._lancado_em = time.monotonic()

    # ------------------------------------------------------------ abas
    def _abas(self) -> list[dict]:
        try:
            alvos = self._http("/json/list") or []
        except Exception:
            if time.monotonic() - self._lancado_em < TOLERANCIA_PARTIDA:
                return []   # acabou de abrir: ainda subindo
            raise ErroNavegador("O navegador do Deck não está aberto. Use um bloco \"Abrir site\" marcando "
                                "\"no navegador do Deck\" antes deste bloco.") from None
        return [a for a in alvos if a.get("type") == "page" and a.get("webSocketDebuggerUrl")]

    def _conversar(self, ws_url: str, expressao: str, timeout: float = 5.0):
        import websocket  # websocket-client

        ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        try:
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": expressao, "returnByValue": True}}))
            while True:
                resp = json.loads(ws.recv())
                if resp.get("id") == 1:
                    break
        finally:
            ws.close()
        if "error" in resp:
            raise ErroNavegador(resp["error"].get("message", "Erro do navegador"))
        resultado = resp.get("result", {})
        if "exceptionDetails" in resultado:
            detalhe = resultado["exceptionDetails"].get("exception", {}).get("description") or "erro no script"
            raise ErroNavegador("Seletor inválido ou erro na página: " + str(detalhe).splitlines()[0])
        return resultado.get("result", {}).get("value")

    def _escolher_aba(self, filtro: str):
        abas = self._abas()
        filtro = (filtro or "").strip().lower()
        if filtro:
            abas = [a for a in abas if filtro in (a.get("url", "") + " " + a.get("title", "")).lower()]
        if not abas:
            return None
        if len(abas) == 1:
            return abas[0]
        melhor = None
        for aba in abas[:12]:     # várias abas: prefere a que está visível e com foco
            try:
                estado = self._conversar(aba["webSocketDebuggerUrl"], "document.visibilityState + '|' + document.hasFocus()", 2)
            except Exception:
                continue
            if estado == "visible|true":
                return aba
            if estado and estado.startswith("visible") and melhor is None:
                melhor = aba
        return melhor or abas[0]

    def avaliar(self, expressao: str, aba: str = ""):
        alvo = self._escolher_aba(aba)
        if alvo is None:
            return None
        return self._conversar(alvo["webSocketDebuggerUrl"], expressao)

    # ------------------------------------------------------------ operações
    def existe(self, seletor: str, aba: str = "") -> bool:
        s = json.dumps(seletor)
        return bool(self.avaliar(f"(()=>{{const e=document.querySelector({s});return !!e&&e.getClientRects().length>0}})()", aba))

    def tem_texto(self, texto: str, aba: str = "") -> bool:
        t = json.dumps(texto.lower())
        return bool(self.avaliar(f"!!(document.body&&document.body.innerText.toLowerCase().includes({t}))", aba))

    def clicar(self, seletor: str, aba: str = "") -> None:
        s = json.dumps(seletor)
        ok = self.avaliar(f"(()=>{{const e=document.querySelector({s});if(!e)return false;"
                          f"e.scrollIntoView({{block:'center'}});e.click();return true}})()", aba)
        if not ok:
            raise ErroNavegador(f"Elemento não encontrado na página: {seletor}")

    def preencher(self, seletor: str, texto: str, aba: str = "") -> None:
        s, t = json.dumps(seletor), json.dumps(texto)
        ok = self.avaliar(
            "(()=>{const e=document.querySelector(" + s + ");if(!e)return false;e.focus();"
            "if(e.isContentEditable){e.textContent=" + t + ";}"
            "else{const p=e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:"
            "e instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype;"
            "Object.getOwnPropertyDescriptor(p,'value').set.call(e," + t + ");}"
            "e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));"
            "return true})()", aba)
        if not ok:
            raise ErroNavegador(f"Campo não encontrado na página: {seletor}")


# ---------------------------------------------------------------- foto de um HTML colado (sem tocar no navegador do Deck)
def _porta_livre() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Sessao:
    """Conversa simples com uma aba pelo protocolo do Chrome (um comando por vez, ignora eventos)."""

    def __init__(self, ws_url: str, timeout: float = 15.0):
        import websocket

        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self._id = 0

    def chamar(self, metodo: str, **params):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": metodo, "params": params}))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self._id:
                break
        if "error" in resp:
            raise ErroNavegador(resp["error"].get("message", "Erro do navegador"))
        return resp.get("result", {})

    def js(self, expressao: str):
        r = self.chamar("Runtime.evaluate", expression=expressao, returnByValue=True)
        if "exceptionDetails" in r:
            raise ErroNavegador("Erro ao medir a página.")
        return r.get("result", {}).get("value")

    def fechar(self):
        try:
            self.ws.close()
        except Exception:
            pass


def fotografar_html(html: str, seletores: list[str], executavel: str | None = None, args_extra: tuple = (),
                    largura: int = 1280, altura_max: int = 2600) -> dict:
    """Desenha o HTML num Chrome/Edge temporário e invisível (perfil descartável, sem scripts) e devolve
    {"png": bytes, "retangulos": {seletor: {x, y, w, h, achados}}, "altura": int}. Nada é executado nem salvo."""
    exe = executavel or achar_navegador()
    if not exe:
        raise ErroNavegador("Não encontrei o Chrome nem o Edge instalados para desenhar a página.")
    porta = _porta_livre()
    pasta = Path(tempfile.mkdtemp(prefix="numpad-deck-foto-"))
    proc = subprocess.Popen(
        [exe, "--headless=new", f"--remote-debugging-port={porta}", "--remote-debugging-address=127.0.0.1",
         f"--user-data-dir={pasta}", "--no-first-run", "--no-default-browser-check", "--disable-gpu",
         "--hide-scrollbars", "--mute-audio", *args_extra, "about:blank"],
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    sessao = None
    try:
        base = f"http://127.0.0.1:{porta}"
        alvo = None
        for _ in range(60):
            if proc.poll() is not None:
                raise ErroNavegador("O navegador fechou sozinho ao tentar desenhar a página.")
            try:
                with urllib.request.urlopen(base + "/json/list", timeout=1) as r:
                    abas = [a for a in json.load(r) if a.get("type") == "page" and a.get("webSocketDebuggerUrl")]
                if abas:
                    alvo = abas[0]
                    break
            except Exception:
                pass
            time.sleep(0.25)
        if alvo is None:
            raise ErroNavegador("O navegador não respondeu a tempo.")
        sessao = _Sessao(alvo["webSocketDebuggerUrl"])
        sessao.chamar("Page.enable")
        sessao.chamar("Emulation.setScriptExecutionDisabled", value=True)
        sessao.chamar("Emulation.setDeviceMetricsOverride", width=largura, height=800, deviceScaleFactor=1, mobile=False)
        quadro = sessao.chamar("Page.getFrameTree")["frameTree"]["frame"]["id"]
        csp = '<meta http-equiv="Content-Security-Policy" content="script-src \'none\'; frame-src \'none\'; object-src \'none\'">'
        sessao.chamar("Page.setDocumentContent", frameId=quadro, html=csp + html)
        for _ in range(40):                       # espera estilos e imagens carregarem (até ~4 s)
            if sessao.js("document.readyState") == "complete":
                break
            time.sleep(0.1)
        time.sleep(0.4)
        medidas = sessao.js(
            "(()=>{const sels=" + json.dumps(seletores) + ";const saida={};"
            "for(const s of sels){try{const todos=document.querySelectorAll(s);const e=todos[0];"
            "if(!e){saida[s]={achados:0};continue}"
            "const r=e.getBoundingClientRect();saida[s]={achados:todos.length,x:Math.round(r.left+scrollX),"
            "y:Math.round(r.top+scrollY),w:Math.round(r.width),h:Math.round(r.height)}}"
            "catch(_){saida[s]={achados:-1}}}"
            "return {altura:Math.max(document.documentElement.scrollHeight,document.body?document.body.scrollHeight:0),retangulos:saida}})()")
        altura = max(200, min(int(medidas["altura"]), altura_max))
        foto = sessao.chamar("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                             clip={"x": 0, "y": 0, "width": largura, "height": altura, "scale": 1})
        import base64

        return {"png": base64.b64decode(foto["data"]), "retangulos": medidas["retangulos"], "altura": altura}
    finally:
        if sessao is not None:
            sessao.fechar()
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()
        shutil.rmtree(pasta, ignore_errors=True)
