import io
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from avisos import Segredos  # noqa: E402
from configuracao import Config  # noqa: E402
from falsos import PlataformaFalsa, UiFalsa  # noqa: E402
from nucleo import NucleoDeck  # noqa: E402
from servidor import criar_app  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
TOKEN = "segredo-de-teste"
PORTA = 5077
H = {"X-Painel-Token": TOKEN}


class TesteApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(self.tmp.name)
        self.plat = PlataformaFalsa(numlock=False)
        self.plat.segredos = Segredos(self.tmp.name)
        self.ui = UiFalsa()
        self.n = NucleoDeck(self.cfg, self.plat, sincrono=True)
        app = criar_app(self.cfg, self.n, self.ui, self.plat, TOKEN, PORTA)
        self.c = app.test_client()
        self.base = f"http://127.0.0.1:{PORTA}"

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, caminho, **kw):
        return self.c.get(caminho, base_url=self.base, **kw)

    def post(self, caminho, corpo=None, **kw):
        return self.c.post(caminho, json=corpo if corpo is not None else {}, base_url=self.base, headers=H, **kw)

    # -- segurança
    def test_sem_token_nao_entra(self):
        self.assertEqual(self.get("/api/config").status_code, 403)
        self.assertEqual(self.get("/api/config", headers={"X-Painel-Token": "errado"}).status_code, 403)
        self.assertEqual(self.c.post("/api/tecla", json={}, base_url=self.base).status_code, 403)

    def test_host_estranho_e_barrado(self):
        r = self.c.get("/api/config", base_url="http://site-malicioso.com", headers=H)
        self.assertEqual(r.status_code, 403)
        r = self.c.get("/", base_url="http://site-malicioso.com")
        self.assertEqual(r.status_code, 403)

    def test_pagina_inicial_leva_o_token(self):
        r = self.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn(TOKEN, html)
        self.assertNotIn("__TOKEN__", html)
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_ping(self):
        self.assertEqual(self.get("/ping").get_json(), {"app": "numpad-deck"})

    # -- estado
    def test_estado_e_config(self):
        e = self.get("/api/estado", headers=H).get_json()
        self.assertEqual((e["modo"], e["pagina"], e["gravando"]), ("deck", 1, False))
        c = self.get("/api/config", headers=H).get_json()
        self.assertEqual(c["pagina"], 1)
        self.assertEqual(set(c["teclas"]), set("0123456789"))
        self.assertEqual(c["teclas"]["5"]["descricao"], "Sem função")
        self.assertFalse(c["autostart"])

    def test_versao_muda_ao_salvar(self):
        v1 = self.get("/api/estado", headers=H).get_json()["versao"]
        self.post("/api/tecla", {"pagina": 1, "tecla": "1", "nome": "A", "imagem": None, "fluxo": []})
        self.post("/api/pagina", {"delta": 1})
        v2 = self.get("/api/estado", headers=H).get_json()["versao"]
        self.assertGreater(v2, v1)

    # -- páginas
    def test_paginas(self):
        self.assertEqual(self.post("/api/pagina", {"delta": 1}).get_json()["pagina"], 2)
        self.assertEqual(self.post("/api/pagina", {"delta": -1}).get_json()["pagina"], 1)
        self.assertEqual(self.post("/api/pagina", {"delta": -1}).get_json()["pagina"], 1)  # nunca abaixo de 1
        self.assertEqual(self.post("/api/pagina", {"ir_para": 40}).get_json()["pagina"], 40)
        self.assertEqual(self.post("/api/pagina", {"delta": 7}).status_code, 400)
        self.assertEqual(self.plat.toasts, [])  # o painel não dispara o pop-up das teclas
        self.assertEqual(self.plat.previas, [])

    def test_criar_renomear_e_remover_pagina(self):
        self.assertEqual(self.post("/api/pagina", {"nova": True}).get_json()["pagina"], 2)
        self.assertEqual(self.post("/api/pagina", {"renomear": {"pagina": 2, "nome": " ECAC "}}).get_json()["nome"], "ECAC")
        c = self.get("/api/config", headers=H).get_json()
        self.assertEqual((c["pagina"], c["pagina_nome"]), (2, "ECAC"))
        self.assertEqual(c["lista_paginas"], [{"numero": 1, "nome": "", "teclas": 0}, {"numero": 2, "nome": "ECAC", "teclas": 0}])
        self.assertEqual(self.post("/api/pagina", {"remover": 2}).status_code, 400)    # é a atual
        self.post("/api/pagina", {"ir_para": 1})
        self.assertEqual(self.post("/api/pagina", {"remover": 2}).status_code, 200)
        self.assertEqual(len(self.get("/api/config", headers=H).get_json()["lista_paginas"]), 1)

    def test_renomear_invalido(self):
        self.assertEqual(self.post("/api/pagina", {"renomear": 5}).status_code, 400)
        self.assertEqual(self.post("/api/pagina", {"renomear": {"pagina": 1, "nome": "x" * 40}}).status_code, 400)

    # -- respostas lembradas
    def test_esquecer_respostas(self):
        self.cfg.guardar_resposta("caminho", "2")
        self.cfg.guardar_resposta("cnpj", "123")
        self.assertEqual(self.get("/api/config", headers=H).get_json()["respostas"], {"caminho": "2", "cnpj": "123"})
        self.assertEqual(self.post("/api/respostas", {"esquecer": "caminho"}).get_json()["respostas"], {"cnpj": "123"})
        self.assertEqual(self.post("/api/respostas", {}).status_code, 400)
        self.assertEqual(self.post("/api/respostas", {"esquecer_tudo": True}).get_json()["respostas"], {})

    # -- analisar o HTML colado
    def test_analisar_html_lista_e_foto(self):
        html = '<form><input id="u" placeholder="Usuário"><button id="ok">Entrar</button><script>x()</script></form>'
        r = self.post("/api/analisar-html", {"html": html})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual([e["seletor"] for e in d["elementos"]], ["#u", "#ok"])
        self.assertTrue(d["imagem"].startswith("data:image/jpeg;base64,"))
        self.assertIsNone(d["aviso"])
        self.assertEqual(d["elementos"][0]["achados"], 1)
        self.assertNotIn("rect", d["elementos"][0])

    def test_analisar_html_sem_navegador_ainda_lista(self):
        self.plat.sem_foto = True
        d = self.post("/api/analisar-html", {"html": '<button id="ok">Entrar</button>'}).get_json()
        self.assertEqual(len(d["elementos"]), 1)
        self.assertIsNone(d["imagem"])
        self.assertIn("não consegui desenhar", d["aviso"])

    def test_analisar_html_vazio_ou_sem_elementos(self):
        self.assertEqual(self.post("/api/analisar-html", {"html": "  "}).status_code, 400)
        self.assertEqual(self.post("/api/analisar-html", {"html": 5}).status_code, 400)
        d = self.post("/api/analisar-html", {"html": "<p>nada</p>"}).get_json()
        self.assertEqual(d["elementos"], [])
        self.assertIn("Não achei", d["aviso"])

    # -- clique relativo à janela
    def test_capturar_clique_na_tela_nao_procura_janela(self):
        self.assertEqual(self.post("/api/capturar-clique").get_json(), {"x": 120, "y": 340})
        self.assertEqual(self.ui.mensagem, "Clique onde a tecla deve clicar")
        self.assertFalse(hasattr(self.plat, "marcados"))

    def test_capturar_clique_na_janela(self):
        r = self.post("/api/capturar-clique", {"alvo": "janela", "ancora": "proporcional"}).get_json()
        self.assertEqual((r["x"], r["y"], r["janela"], r["rx"], r["ry"]), (120, 340, "Planilha - Excel", 0.25, 0.5))
        r = self.post("/api/capturar-clique", {"alvo": "janela", "ancora": "baixo_dir"}).get_json()
        self.assertEqual((r["dx"], r["dy"]), (40, 12))
        self.assertEqual(self.plat.marcados[-1], (120, 340, "baixo_dir"))

    def test_capturar_clique_sem_janela_no_ponto(self):
        self.plat.sem_janela = True
        r = self.post("/api/capturar-clique", {"alvo": "janela"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("janela", r.get_json()["erro"])
        self.assertEqual(self.post("/api/capturar-clique", {"alvo": "janela", "ancora": "centro"}).status_code, 400)

    def test_salvar_clique_relativo(self):
        r = self.post("/api/tecla", {"pagina": 1, "tecla": "2", "nome": "", "imagem": None, "fluxo": [
            {"tipo": "clique", "alvo": "janela", "janela": "Excel", "ancora": "proporcional", "rx": 0.3, "ry": 0.4}]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("janela", r.get_json()["descricao"])

    # -- avisos
    def test_capturar_area(self):
        self.assertEqual(self.post("/api/capturar-area").get_json(), self.ui.area)
        self.ui.area = None
        self.assertEqual(self.post("/api/capturar-area").status_code, 408)

    def test_config_da_evolution_nunca_devolve_a_chave(self):
        r = self.post("/api/avisos-config", {"evolution_url": "http://localhost:8080", "evolution_instancia": "loja",
                                             "evolution_chave": "SEGREDO123"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("SEGREDO123", r.get_data(as_text=True))
        g = self.get("/api/avisos-config", headers=H)
        self.assertNotIn("SEGREDO123", g.get_data(as_text=True))
        self.assertEqual(g.get_json()["evolution_chave_definida"], True)
        self.assertNotIn("SEGREDO123", self.get("/api/config", headers=H).get_data(as_text=True))
        self.assertNotIn("SEGREDO123", (Path(self.tmp.name) / "config.json").read_text(encoding="utf-8") if (Path(self.tmp.name) / "config.json").exists() else "")

    def test_config_da_evolution_invalida(self):
        self.assertEqual(self.post("/api/avisos-config", {"evolution_url": "ftp://x"}).status_code, 400)
        self.assertEqual(self.post("/api/avisos-config", {"evolution_url": 5}).status_code, 400)

    def test_testar_whatsapp(self):
        r = self.post("/api/avisos-testar", {"numero": "+55 11 99999-8888"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.plat.whatsapps[0][0], "5511999998888")
        self.assertEqual(self.post("/api/avisos-testar", {"numero": "abc"}).status_code, 400)

    def test_salvar_fluxo_com_aviso(self):
        r = self.post("/api/tecla", {"pagina": 1, "tecla": "1", "nome": "", "imagem": None, "fluxo": [
            {"tipo": "aviso", "canal": "popup", "texto": "Fim", "tamanho": "grande", "posicao": "topo_esq", "segundos": 3}]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Aviso", r.get_json()["descricao"])

    # -- teclas
    def test_salvar_tecla_com_imagem(self):
        r = self.c.post("/api/imagem", data={"arquivo": (io.BytesIO(PNG), "foto.png")},
                        base_url=self.base, headers=H)
        self.assertEqual(r.status_code, 200)
        nome = r.get_json()["imagem"]
        self.assertEqual(self.get(f"/imagens/{nome}").get_data(), PNG)
        r = self.post("/api/tecla", {"pagina": 1, "tecla": "5", "nome": "Colar", "imagem": nome,
                                     "fluxo": [{"tipo": "atalho", "teclas": [{"vk": 162, "nome": "Ctrl"}, {"vk": 86, "nome": "V"}]},
                                               {"tipo": "pausa", "segundos": 1}, {"tipo": "clique", "x": 1, "y": 2}]})
        self.assertEqual(r.get_json()["descricao"], "3 etapas: Ctrl + V → Esperar 1 s → Clique")
        c = self.get("/api/config", headers=H).get_json()
        self.assertEqual(c["teclas"]["5"]["imagem"], nome)
        self.assertEqual(c["teclas"]["5"]["nome"], "Colar")

    def test_imagem_invalida_e_caminhos_perigosos(self):
        r = self.c.post("/api/imagem", data={"arquivo": (io.BytesIO(b"<svg onload=alert(1)>"), "x.svg")},
                        base_url=self.base, headers=H)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.get("/imagens/..%2Fconfig.json").status_code, 404)
        self.assertEqual(self.get("/imagens/naoexiste.png").status_code, 404)

    def test_tecla_invalida(self):
        r = self.post("/api/tecla", {"pagina": 1, "tecla": "x", "nome": "", "imagem": None, "fluxo": []})
        self.assertEqual(r.status_code, 400)
        r = self.c.post("/api/tecla", data="isso não é json", base_url=self.base, headers=H)
        self.assertEqual(r.status_code, 400)

    def test_limpar(self):
        self.post("/api/tecla", {"pagina": 1, "tecla": "2", "nome": "A", "imagem": None, "fluxo": []})
        self.post("/api/tecla/limpar", {"pagina": 1, "tecla": "2"})
        self.assertEqual(self.cfg.paginas_configuradas(), [])

    # -- captura
    def test_capturar_clique_e_arquivo(self):
        self.assertEqual(self.post("/api/capturar-clique").get_json(), {"x": 120, "y": 340})
        self.assertEqual(self.post("/api/escolher-arquivo").get_json(), {"caminho": r"C:\scripts\meu.py"})
        self.ui.clique = None
        self.assertEqual(self.post("/api/capturar-clique").status_code, 408)

    def test_gravar_macro(self):
        def digitar():
            while not self.n.gravando():
                time.sleep(0.01)
            ctrl, c = (0xA2, 0x1D, 0), (0x43, 0x2E, 0)
            self.n.evento(True, *ctrl)
            self.n.evento(True, *c)
            self.n.evento(False, *c)
            self.n.evento(False, *ctrl)

        t = threading.Thread(target=digitar)
        t.start()
        r = self.post("/api/gravar-macro")
        t.join(2)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["descricao"], "Atalho: Ctrl + C")
        self.assertEqual(r.get_json()["teclas"][0]["nome"], "Ctrl")

    def test_gravar_macro_cancelada(self):
        def cancelar():
            while not self.n.gravando():
                time.sleep(0.01)
            self.post("/api/cancelar")

        t = threading.Thread(target=cancelar)
        t.start()
        r = self.post("/api/gravar-macro")
        t.join(2)
        self.assertEqual(r.status_code, 408)

    def test_testar_executa_o_fluxo_do_rascunho(self):
        r = self.post("/api/testar", {"fluxo": [{"tipo": "clique", "x": 1, "y": 2},
                                                {"tipo": "pausa", "segundos": 0.05},
                                                {"tipo": "mover", "x": 3, "y": 4}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([b["tipo"] for b in self.plat.executadas], ["clique", "mover"])
        self.assertEqual(self.post("/api/testar", {"fluxo": [{"tipo": "voar"}]}).status_code, 400)
        self.assertEqual(self.post("/api/testar", {"fluxo": [{"tipo": None}]}).status_code, 400)

    # -- chamadas entre teclas
    def test_ciclo_e_recusado_com_mensagem(self):
        r = self.post("/api/tecla", {"pagina": 1, "tecla": "1", "nome": "", "imagem": None,
                                     "fluxo": [{"tipo": "chamar", "pagina": 1, "tecla": "1"}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Ciclo", r.get_json()["erro"])

    def test_tecla_info_para_o_bloco_chamar(self):
        self.post("/api/tecla", {"pagina": 7, "tecla": "3", "nome": "Abrir Google", "imagem": None,
                                 "fluxo": [{"tipo": "site", "url": "google.com"}]})
        d = self.get("/api/tecla-info?pagina=7&tecla=3", headers=H).get_json()
        self.assertEqual((d["nome"], d["etapas"], d["descricao"]), ("Abrir Google", 1, "Abrir site: google.com"))
        vazia = self.get("/api/tecla-info?pagina=8&tecla=3", headers=H).get_json()
        self.assertEqual(vazia["etapas"], 0)
        for q in ("pagina=0&tecla=3", "pagina=7&tecla=x", "tecla=3", "pagina=abc&tecla=3"):
            self.assertEqual(self.get("/api/tecla-info?" + q, headers=H).status_code, 400, q)
        self.assertEqual(self.get("/api/tecla-info?pagina=1&tecla=1").status_code, 403)

    # -- prévia
    def test_botao_ver_previa(self):
        self.post("/api/tecla", {"pagina": 1, "tecla": "7", "nome": "Google", "imagem": None,
                                 "fluxo": [{"tipo": "site", "url": "google.com"}]})
        self.assertEqual(self.post("/api/previa").status_code, 200)
        pagina, itens, segundos, alternar = self.plat.previas[-1]
        self.assertEqual((pagina, alternar), (1, False))
        self.assertEqual({i["tecla"]: i["titulo"] for i in itens}["7"], "Google")

    # -- opções
    def test_opcoes_autostart_e_encerrar(self):
        r = self.post("/api/opcoes", {"apitar_fora_do_deck": False, "perfil_segundos": 25})
        self.assertFalse(r.get_json()["apitar_fora_do_deck"])
        self.assertEqual(r.get_json()["perfil_segundos"], 25)
        self.assertEqual(self.post("/api/opcoes", {"perfil_segundos": 1}).status_code, 400)
        self.assertEqual(self.post("/api/opcoes", {"apitar_fora_do_deck": "oi"}).status_code, 400)
        self.assertTrue(self.post("/api/autostart", {"ligado": True}).get_json()["autostart"])
        self.assertEqual(self.post("/api/autostart", {"ligado": "sim"}).status_code, 400)
        self.assertEqual(self.post("/api/encerrar").status_code, 200)
        time.sleep(0.5)
        self.assertTrue(self.ui.saiu)


if __name__ == "__main__":
    unittest.main()
