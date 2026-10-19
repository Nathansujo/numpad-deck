import json
import sys
import tempfile
import threading
import urllib.parse
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import avisos  # noqa: E402
import plataforma_win  # noqa: E402
from avisos import ErroAviso, Segredos  # noqa: E402

AREA = (0, 0, 1920, 1040)


class Geometria(unittest.TestCase):
    def test_tamanhos_crescem(self):
        p, m, g = (avisos.calcular_retangulo(AREA, t, "centro") for t in ("pequeno", "medio", "grande"))
        self.assertLess(p[2], m[2] < g[2] and m[2] or 0)
        self.assertLess(p[3], m[3])
        self.assertLess(m[3], g[3])

    def test_centro_esta_no_meio(self):
        x, y, w, h = avisos.calcular_retangulo(AREA, "medio", "centro")
        self.assertAlmostEqual(x + w / 2, 960, delta=1)
        self.assertAlmostEqual(y + h / 2, 520, delta=1)

    def test_cantos_ficam_dentro_da_area(self):
        for pos in avisos.TAMANHOS and ("topo", "baixo", "topo_esq", "topo_dir", "baixo_esq", "baixo_dir", "centro"):
            for t in avisos.TAMANHOS:
                x, y, w, h = avisos.calcular_retangulo(AREA, t, pos)
                self.assertGreaterEqual(x, 0); self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + w, 1920); self.assertLessEqual(y + h, 1040)

    def test_canto_inferior_direito(self):
        x, y, w, h = avisos.calcular_retangulo(AREA, "medio", "baixo_dir")
        self.assertGreater(x, 960); self.assertGreater(y, 520)
        self.assertLess(1920 - (x + w), 60)

    def test_respeita_area_de_trabalho_deslocada(self):
        x, y, w, h = avisos.calcular_retangulo((100, 50, 1000, 600), "pequeno", "topo_esq")
        self.assertTrue(x >= 100 and y >= 50)

    def test_personalizado_usa_fracoes_da_tela_virtual(self):
        r = avisos.calcular_retangulo(AREA, "medio", "personalizado", {"x": 0.5, "y": 0.25, "l": 0.25, "a": 0.2},
                                      (-1920, 0, 3840, 1080))
        self.assertEqual(r, (0, 270, 960, 216))

    def test_personalizado_sem_area_da_erro(self):
        with self.assertRaises(ErroAviso):
            avisos.calcular_retangulo(AREA, "medio", "personalizado", None)


class FalsaEvolution(BaseHTTPRequestHandler):
    recebidos: list = []
    modo = "v2"

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).recebidos.append((self.path, self.headers.get("apikey"), corpo))
        if type(self).modo == "401":
            codigo = 401
        elif type(self).modo == "v1" and "text" in corpo:
            codigo = 400
        else:
            codigo = 201
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *a):
        pass


class LinkWhatsapp(unittest.TestCase):
    def test_exemplo_do_usuario(self):
        self.assertEqual(avisos.link_whatsapp("5577991831413", "Aviso: Teste"), "https://wa.me/5577991831413?text=Aviso%3A%20Teste")

    def test_acentos_quebras_e_simbolos(self):
        l = avisos.link_whatsapp("5511999998888", "Olá!\nR$ 10 & 20% ✅")
        self.assertTrue(l.startswith("https://wa.me/5511999998888?text="))
        self.assertNotIn(" ", l); self.assertNotIn("\n", l); self.assertNotIn("&", l.split("text=")[1])
        self.assertEqual(urllib.parse.unquote(l.split("text=")[1]), "Olá!\nR$ 10 & 20% ✅")


class Whatsapp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FalsaEvolution)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        FalsaEvolution.recebidos = []
        FalsaEvolution.modo = "v2"

    def test_v2(self):
        avisos.enviar_whatsapp(self.url + "/", "minha inst", "CHAVE", "5511999998888", "Oi")
        caminho, chave, corpo = FalsaEvolution.recebidos[0]
        self.assertEqual(caminho, "/message/sendText/minha%20inst")
        self.assertEqual(chave, "CHAVE")
        self.assertEqual(corpo, {"number": "5511999998888", "text": "Oi"})

    def test_cai_para_formato_v1(self):
        FalsaEvolution.modo = "v1"
        avisos.enviar_whatsapp(self.url, "i", "K", "5511999998888", "Oi")
        self.assertEqual(len(FalsaEvolution.recebidos), 2)
        self.assertEqual(FalsaEvolution.recebidos[1][2]["textMessage"], {"text": "Oi"})

    def test_chave_errada_explica(self):
        FalsaEvolution.modo = "401"
        with self.assertRaisesRegex(ErroAviso, "401.*chave"):
            avisos.enviar_whatsapp(self.url, "i", "K", "5511999998888", "Oi")

    def test_servidor_fora_do_ar(self):
        with self.assertRaisesRegex(ErroAviso, "Não consegui falar"):
            avisos.enviar_whatsapp("http://127.0.0.1:9", "i", "K", "5511999998888", "Oi", timeout=2)


class SegredosTeste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Segredos(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chave_nunca_aparece_na_visao_publica(self):
        self.s.salvar("http://localhost:8080/", "loja", "SUPERSECRETA")
        pub = self.s.publico()
        self.assertEqual(pub, {"evolution_url": "http://localhost:8080", "evolution_instancia": "loja",
                               "evolution_chave_definida": True})
        self.assertNotIn("SUPERSECRETA", json.dumps(pub))
        self.assertEqual(self.s.evolution(), ("http://localhost:8080", "loja", "SUPERSECRETA"))

    def test_salvar_sem_chave_mantem_a_antiga(self):
        self.s.salvar("http://a.com", "x", "K1")
        self.s.salvar("http://b.com", "y", "")
        self.assertEqual(self.s.evolution(), ("http://b.com", "y", "K1"))

    def test_limpar_chave(self):
        self.s.salvar("http://a.com", "x", "K1")
        self.s.salvar("http://a.com", "x", None, limpar_chave=True)
        self.assertFalse(self.s.publico()["evolution_chave_definida"])
        with self.assertRaisesRegex(ErroAviso, "Configure"):
            self.s.evolution()

    def test_url_invalida(self):
        with self.assertRaises(ErroAviso):
            self.s.salvar("ftp://x", "i", "k")
        with self.assertRaises(ErroAviso):
            self.s.salvar("http://x.com", "a/b", "k")

    def test_sem_configurar(self):
        with self.assertRaises(ErroAviso):
            self.s.evolution()


class BlocoDeNotas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def bloco(self, **kw):
        base = {"tipo": "aviso", "canal": "bloco_notas", "origem": "saida", "arquivo": "", "pasta": "",
                "shell": "python", "comando": "", "limite": 20}
        base.update(kw)
        return base

    def test_script_python_vira_txt_na_pasta_do_script(self):
        script = self.pasta / "lista.py"
        script.write_text("print('Imposto: R$ 10,00 — ação concluída')\nimport sys; print('aviso', file=sys.stderr)\n", encoding="utf-8")
        destino = avisos.gerar_txt_da_saida(self.bloco(comando=str(script), arquivo="resultado.txt"), self.pasta / "saidas", sys.executable)
        self.assertEqual(destino, self.pasta / "resultado.txt")
        texto = destino.read_text(encoding="utf-8-sig")
        self.assertIn("Imposto: R$ 10,00 — ação concluída", texto)
        self.assertIn("aviso", texto)
        self.assertTrue(destino.read_bytes().startswith(b"\xef\xbb\xbf"))   # BOM: o Bloco de Notas acerta os acentos

    def test_sem_nome_vai_para_a_pasta_de_saidas(self):
        script = self.pasta / "a.py"
        script.write_text("print('ok')", encoding="utf-8")
        destino = avisos.gerar_txt_da_saida(self.bloco(comando=str(script)), self.pasta / "saidas", sys.executable)
        self.assertEqual(destino.parent, self.pasta / "saidas")
        self.assertTrue(destino.name.startswith("saida_"))

    def test_pasta_informada_vale_mais_que_a_do_script(self):
        script = self.pasta / "a.py"
        script.write_text("print('ok')", encoding="utf-8")
        destino = avisos.gerar_txt_da_saida(self.bloco(comando=str(script), arquivo="x.txt", pasta=str(self.pasta / "outra")),
                                            self.pasta / "saidas", sys.executable)
        self.assertEqual(destino, self.pasta / "outra" / "x.txt")

    def test_script_com_argumentos_e_aspas(self):
        script = self.pasta / "meu script.py"
        script.write_text("import sys; print(' '.join(sys.argv[1:]))", encoding="utf-8")
        destino = avisos.gerar_txt_da_saida(self.bloco(comando=f'"{script}" um dois', arquivo="r.txt"), self.pasta / "s", sys.executable)
        self.assertIn("um dois", destino.read_text(encoding="utf-8-sig"))

    def test_erro_do_script_aparece_no_txt(self):
        script = self.pasta / "e.py"
        script.write_text("raise SystemExit('deu ruim')", encoding="utf-8")
        destino = avisos.gerar_txt_da_saida(self.bloco(comando=str(script), arquivo="r.txt"), self.pasta / "s", sys.executable)
        texto = destino.read_text(encoding="utf-8-sig")
        self.assertIn("deu ruim", texto)
        self.assertIn("código de erro 1", texto)

    def test_script_inexistente(self):
        with self.assertRaisesRegex(ErroAviso, "não encontrado"):
            avisos.gerar_txt_da_saida(self.bloco(comando=str(self.pasta / "nao.py")), self.pasta, sys.executable)

    def test_tempo_limite(self):
        script = self.pasta / "l.py"
        script.write_text("import time; time.sleep(30)", encoding="utf-8")
        with self.assertRaisesRegex(ErroAviso, "passou de 1 segundos"):
            avisos.gerar_txt_da_saida(self.bloco(comando=str(script), limite=1), self.pasta, sys.executable)

    def test_pythonw_vira_python_para_capturar_a_saida(self):
        pasta = Path(self.tmp.name) / "py"
        pasta.mkdir()
        (pasta / "pythonw.exe").write_text("")
        self.assertEqual(avisos.interpretador_com_console(str(pasta / "pythonw.exe")), str(pasta / "pythonw.exe"))   # sem python.exe: fica
        (pasta / "python.exe").write_text("")
        self.assertEqual(avisos.interpretador_com_console(str(pasta / "pythonw.exe")), str(pasta / "python.exe"))
        self.assertEqual(avisos.interpretador_com_console("/usr/bin/python3"), "/usr/bin/python3")

    def test_resolver_arquivo(self):
        self.assertEqual(avisos.resolver_arquivo({"arquivo": "a.txt", "pasta": "C:/x"}, self.pasta), Path("C:/x") / "a.txt")
        self.assertEqual(avisos.resolver_arquivo({"arquivo": "a.txt", "pasta": ""}, self.pasta), self.pasta / "a.txt")
        absoluto = self.pasta / "z.txt"
        self.assertEqual(avisos.resolver_arquivo({"arquivo": str(absoluto), "pasta": "/outra"}, self.pasta), absoluto)


class UiMarcada:
    def __init__(self):
        self.chamadas = []

    def aviso(self, *a):
        self.chamadas.append(a)


class PlataformaAvisos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ui = UiMarcada()
        self.plat = plataforma_win.PlataformaWindows(self.ui, "http://x", Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_popup_chama_a_interface(self):
        self.plat.executar({"tipo": "aviso", "canal": "popup", "titulo": "T", "texto": "Fim", "tamanho": "grande",
                            "posicao": "baixo_dir", "segundos": 4})
        self.assertEqual(self.ui.chamadas, [("T", "Fim", "grande", "baixo_dir", None, 4)])

    def test_whatsapp_sem_configurar_explica(self):
        with self.assertRaisesRegex(ErroAviso, "Configure a Evolution"):
            self.plat.executar({"tipo": "aviso", "canal": "whatsapp", "modo": "evolution", "numero": "5511999998888", "texto": "oi"})

    def test_whatsapp_link_abre_espera_e_aperta_enter(self):
        ordem = []
        with mock.patch("webbrowser.open", side_effect=lambda u: ordem.append(("abrir", u))), \
                mock.patch.object(plataforma_win.time, "sleep", side_effect=lambda s: ordem.append(("espera", s))), \
                mock.patch.object(plataforma_win.PlataformaWindows, "_apertar_enter", side_effect=lambda: ordem.append(("enter",))):
            self.plat.executar({"tipo": "aviso", "canal": "whatsapp", "modo": "link", "numero": "5577991831413",
                                "texto": "Aviso: Teste", "espera": 7})
        self.assertEqual(ordem[0], ("abrir", "https://wa.me/5577991831413?text=Aviso%3A%20Teste"))
        self.assertEqual(ordem[1:3], [("espera", 7), ("enter",)])

    def test_whatsapp_usa_segredos(self):
        self.plat.segredos.salvar("http://evo", "inst", "K")
        with mock.patch("avisos.enviar_whatsapp") as env:
            self.plat.executar({"tipo": "aviso", "canal": "whatsapp", "modo": "evolution", "numero": "5511999998888", "texto": "oi"})
        env.assert_called_once_with("http://evo", "inst", "K", "5511999998888", "oi")

    def test_bloco_de_notas_abre_o_txt(self):
        txt = Path(self.tmp.name) / "lista.txt"
        txt.write_text("a", encoding="utf-8")
        with mock.patch.object(plataforma_win, "IS_WIN", True), mock.patch.object(plataforma_win.PlataformaWindows, "_abrir_no_bloco_de_notas") as popen:
            self.plat.executar({"tipo": "aviso", "canal": "bloco_notas", "origem": "arquivo", "arquivo": "lista.txt",
                                "pasta": self.tmp.name})
        popen.assert_called_once_with(txt)

    def test_texto_do_bloco_de_notas_vai_por_whatsapp_link(self):
        txt = Path(self.tmp.name) / "lista.txt"
        txt.write_text("Linha 1\nLinha 2 ação", encoding="utf-8")
        ordem = []
        with mock.patch.object(plataforma_win, "IS_WIN", True), \
                mock.patch.object(plataforma_win.PlataformaWindows, "_abrir_no_bloco_de_notas") as popen, \
                mock.patch("webbrowser.open", side_effect=lambda u: ordem.append(u)), \
                mock.patch.object(plataforma_win.time, "sleep"), \
                mock.patch.object(plataforma_win.PlataformaWindows, "_apertar_enter", side_effect=lambda: ordem.append("enter")):
            self.plat.executar({"tipo": "aviso", "canal": "bloco_notas", "origem": "arquivo", "arquivo": "lista.txt",
                                "pasta": self.tmp.name, "abrir": True,
                                "whatsapp": {"numero": "5577991831413", "modo": "link", "espera": 3}})
        self.assertEqual(ordem, ["https://wa.me/5577991831413?text=Linha%201%0ALinha%202%20a%C3%A7%C3%A3o", "enter"])
        popen.assert_called_once_with(txt)

    def test_texto_so_por_whatsapp_evolution_sem_abrir_bloco_de_notas(self):
        txt = Path(self.tmp.name) / "lista.txt"
        txt.write_bytes("Relatório pronto".encode("cp1252"))        # arquivo salvo em ANSI também funciona
        self.plat.segredos.salvar("http://evo", "inst", "K")
        with mock.patch.object(plataforma_win.PlataformaWindows, "_abrir_no_bloco_de_notas") as popen, \
                mock.patch("avisos.enviar_whatsapp") as env:
            self.plat.executar({"tipo": "aviso", "canal": "bloco_notas", "origem": "arquivo", "arquivo": "lista.txt",
                                "pasta": self.tmp.name, "abrir": False,
                                "whatsapp": {"numero": "5577991831413", "modo": "evolution"}})
        env.assert_called_once_with("http://evo", "inst", "K", "5577991831413", "Relatório pronto")
        popen.assert_not_called()

    def test_texto_longo_e_cortado(self):
        import avisos
        txt = Path(self.tmp.name) / "g.txt"
        txt.write_text("x" * 5000, encoding="utf-8")
        curto = avisos.ler_texto_para_whatsapp(txt, "link")
        self.assertLess(len(curto), 1400)
        self.assertIn("cortado", curto)
        self.assertLess(len(avisos.ler_texto_para_whatsapp(txt, "evolution")), 4000)
        vazio = Path(self.tmp.name) / "v.txt"
        vazio.write_text("  \n", encoding="utf-8")
        self.assertEqual(avisos.ler_texto_para_whatsapp(vazio), "(sem conteúdo)")

    def test_bloco_de_notas_arquivo_inexistente(self):
        with mock.patch.object(plataforma_win, "IS_WIN", True), mock.patch.object(plataforma_win.PlataformaWindows, "_abrir_no_bloco_de_notas") as popen:
            with self.assertRaises(FileNotFoundError):
                self.plat.executar({"tipo": "aviso", "canal": "bloco_notas", "origem": "arquivo", "arquivo": "nao.txt",
                                    "pasta": self.tmp.name})
        popen.assert_not_called()

    def test_bloco_de_notas_com_saida_do_script(self):
        script = Path(self.tmp.name) / "p.py"
        script.write_text("print('lista pronta')", encoding="utf-8")
        with mock.patch.object(plataforma_win, "IS_WIN", True), mock.patch.object(plataforma_win.PlataformaWindows, "_abrir_no_bloco_de_notas") as popen:
            self.plat.executar({"tipo": "aviso", "canal": "bloco_notas", "origem": "saida", "arquivo": "r.txt", "pasta": "",
                                "shell": "python", "comando": str(script), "limite": 20})
        alvo = popen.call_args[0][0]
        self.assertEqual(alvo, Path(self.tmp.name) / "r.txt")
        self.assertIn("lista pronta", alvo.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
