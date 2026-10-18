"""Teste de verdade do navegador do Deck: sobe um Chromium/Chrome, abre uma página local e confere
esperar elemento, clicar e preencher. Pula se não houver navegador ou websocket-client."""
import http.server
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.path.insert(0, str(Path(__file__).resolve().parent))

from configuracao import Config  # noqa: E402
from falsos import PlataformaFalsa  # noqa: E402
from navegador import ErroNavegador, Navegador, achar_navegador  # noqa: E402
from nucleo import NucleoDeck  # noqa: E402

try:
    import websocket  # noqa: F401
    TEM_WS = True
except ImportError:
    TEM_WS = False

PAGINA = b"""<!doctype html><html><head><title>Pagina de teste</title></head><body>
<h1>Ola</h1><button id="ok" onclick="document.getElementById('res').textContent='clicou'">Ok</button>
<input id="campo" oninput="document.getElementById('eco').textContent=this.value">
<select id="sel"><option value="a">A</option><option value="b">B</option></select>
<div id="res"></div><div id="eco"></div><div id="escondido" style="display:none">x</div>
<script>setTimeout(()=>{const d=document.createElement('div');d.id='tardio';d.textContent='Pronto agora';document.body.appendChild(d)},1200)</script>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGINA)

    def log_message(self, *a):
        pass


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(TEM_WS and achar_navegador(), "sem Chrome/Chromium ou websocket-client")
class NavegadorReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/pagina?x=1"
        cls.tmp = tempfile.mkdtemp()
        cls.nav = Navegador(Path(cls.tmp) / "perfil", porta=porta_livre(),
                            args_extra=("--headless=new", "--no-sandbox", "--disable-gpu"))
        cls.nav.abrir(cls.url)

    @classmethod
    def tearDownClass(cls):
        import subprocess
        subprocess.run(["pkill", "-f", str(cls.tmp)], check=False)
        cls.srv.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def esperar(self, condicao, limite=15):
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            try:
                if condicao():
                    return True
            except ErroNavegador:
                pass
            time.sleep(0.15)
        return False

    def test_esperar_elemento_que_aparece_depois(self):
        self.assertTrue(self.esperar(lambda: self.nav.existe("h1")))        # a página carregou
        self.assertTrue(self.esperar(lambda: self.nav.existe("#tardio")))
        self.assertTrue(self.nav.tem_texto("pronto AGORA"))
        self.assertFalse(self.nav.existe("#nao-existe"))
        self.assertFalse(self.nav.existe("#escondido"))       # display:none não conta como "apareceu"
        self.assertFalse(self.nav.tem_texto("texto que nao esta la"))

    def test_clicar_e_preencher(self):
        self.assertTrue(self.esperar(lambda: self.nav.existe("#ok")))
        self.nav.clicar("#ok")
        self.assertEqual(self.nav.avaliar("document.getElementById('res').textContent"), "clicou")
        self.nav.preencher("#campo", 'Olá "mundo" \\ {x}')
        self.assertEqual(self.nav.avaliar("document.getElementById('eco').textContent"), 'Olá "mundo" \\ {x}')
        self.nav.preencher("#sel", "b")
        self.assertEqual(self.nav.avaliar("document.getElementById('sel').value"), "b")

    def test_erros_claros(self):
        with self.assertRaisesRegex(ErroNavegador, "não encontrado"):
            self.nav.clicar("#nao-existe")
        with self.assertRaisesRegex(ErroNavegador, "Seletor inválido"):
            self.nav.existe("###")

    def test_segunda_pagina_e_filtro_de_aba(self):
        self.nav.abrir(self.url.replace("pagina?x=1", "segunda?y=2"))
        self.assertTrue(self.esperar(lambda: self.nav.existe("#ok", aba="segunda")))
        self.assertTrue(self.esperar(lambda: self.nav.existe("#ok", aba="pagina?x=1")))
        self.assertFalse(self.nav.existe("#ok", aba="nenhuma-aba-assim"))   # aba que não existe = condição falsa

    def test_navegador_fechado_da_erro_claro(self):
        morto = Navegador(Path(self.tmp) / "outro", porta=porta_livre())
        self.assertFalse(morto.disponivel())
        with self.assertRaisesRegex(ErroNavegador, "não está aberto"):
            morto.existe("#x")


class PlataformaComNavegador(PlataformaFalsa):
    """Plataforma de mentira, mas com o navegador de verdade nos blocos da página web."""

    def __init__(self, nav):
        super().__init__(numlock=False)
        self.nav = nav

    def avaliar_condicao(self, c):
        assert c["tipo"] == "pagina"
        return self.nav.existe(c["valor"], c["aba"]) if c["alvo"] == "seletor" else self.nav.tem_texto(c["valor"], c["aba"])

    def executar(self, b):
        self.executadas.append(b)
        if b["tipo"] == "site":
            self.nav.abrir(b["url"])
        elif b["tipo"] == "web_clicar":
            self.nav.clicar(b["seletor"], b["aba"])
        elif b["tipo"] == "web_preencher":
            self.nav.preencher(b["seletor"], b["texto"], b["aba"])


@unittest.skipUnless(TEM_WS and achar_navegador(), "sem Chrome/Chromium ou websocket-client")
class FluxoComNavegadorReal(unittest.TestCase):
    """O fluxo inteiro: abre o site, ESPERA o elemento aparecer (sem pausa fixa), preenche, clica e decide com Se."""

    def test_fluxo_espera_elemento_da_pagina(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/fluxo"
        tmp = tempfile.mkdtemp()
        nav = Navegador(Path(tmp) / "perfil", porta=porta_livre(), args_extra=("--headless=new", "--no-sandbox", "--disable-gpu"))
        try:
            plat = PlataformaComNavegador(nav)
            cfg = Config(Path(tmp) / "dados")
            n = NucleoDeck(cfg, plat, sincrono=True)
            t0 = time.monotonic()
            n.testar([
                {"tipo": "site", "url": url, "controlado": True},
                {"tipo": "pausa", "modo": "condicao", "condicao": {"tipo": "pagina", "alvo": "seletor", "valor": "#tardio"},
                 "ate": "aparecer", "limite": 20},
                {"tipo": "web_preencher", "seletor": "#campo", "texto": "Pedido {n}"},
                {"tipo": "web_clicar", "seletor": "#ok", "limite": 5},
                {"tipo": "se", "condicao": {"tipo": "pagina", "alvo": "texto", "valor": "CLICOU"}, "entao": 1, "senao": 1},
                {"tipo": "aviso", "canal": "popup", "texto": "deu certo"},
                {"tipo": "aviso", "canal": "popup", "texto": "nao deu"},
            ])
            self.assertGreaterEqual(time.monotonic() - t0, 0.8)    # esperou o elemento que só nasce depois de ~1,2 s
            self.assertEqual(plat.executadas[-1]["texto"], "deu certo")
            self.assertEqual(nav.avaliar("document.getElementById('eco').textContent"), "Pedido {n}")
        finally:
            import subprocess
            subprocess.run(["pkill", "-f", tmp], check=False)
            srv.shutdown()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
