import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import plataforma_win  # noqa: E402
import posicao  # noqa: E402
from configuracao import ErroConfig, descrever_bloco, validar_bloco  # noqa: E402
from falsos import PlataformaFalsa, UiFalsa  # noqa: E402

GRANDE = (0, 0, 1920, 1080)       # janela em tela cheia (Full HD)
PEQUENA = (300, 200, 1000, 400)   # a mesma janela depois de redimensionada e movida


def prop(rx, ry, **extra):
    return {"tipo": "clique", "alvo": "janela", "janela": "Excel", "ancora": "proporcional", "rx": rx, "ry": ry, **extra}


class Conta(unittest.TestCase):
    def test_proporcional_acompanha_o_tamanho_e_o_lugar(self):
        b = prop(0.5, 0.5)
        self.assertEqual(posicao.calcular_ponto(b, GRANDE), (960, 540))
        x, y = posicao.calcular_ponto(b, PEQUENA)
        self.assertEqual((x, y), (300 + 500, 200 + 200))          # meio da janela pequena, no lugar novo

    def test_cantos_da_janela(self):
        self.assertEqual(posicao.calcular_ponto(prop(0, 0), PEQUENA), (300, 200))
        self.assertEqual(posicao.calcular_ponto(prop(1, 1), PEQUENA), (1299, 599))

    def test_ancora_no_canto_mantem_a_distancia_em_pixels(self):
        sup_dir = {"ancora": "topo_dir", "dx": 30, "dy": 20}
        self.assertEqual(posicao.calcular_ponto(sup_dir, GRANDE), (1920 - 1 - 30, 20))
        self.assertEqual(posicao.calcular_ponto(sup_dir, PEQUENA), (300 + 1000 - 1 - 30, 200 + 20))
        inf_esq = {"ancora": "baixo_esq", "dx": 10, "dy": 15}
        self.assertEqual(posicao.calcular_ponto(inf_esq, PEQUENA), (310, 200 + 400 - 1 - 15))

    def test_nunca_sai_da_janela(self):
        self.assertEqual(posicao.calcular_ponto({"ancora": "topo_esq", "dx": 5000, "dy": 5000}, (10, 20, 100, 50)), (109, 69))

    def test_janela_sem_area(self):
        with self.assertRaises(ValueError):
            posicao.calcular_ponto(prop(0.5, 0.5), (0, 0, 0, 0))

    def test_marcar_e_calcular_de_volta(self):
        for ancora in posicao.ANCORAS:
            campos = posicao.referencia(500, 300, PEQUENA, ancora)
            b = {"ancora": ancora, **campos}
            self.assertEqual(posicao.calcular_ponto(b, PEQUENA), (500, 300), ancora)

    def test_marcar_na_tela_cheia_e_reaplicar_na_pequena(self):
        campos = posicao.referencia(1440, 270, GRANDE, "proporcional")   # 75% da largura, 25% da altura
        self.assertAlmostEqual(campos["rx"], 0.75, places=2)
        self.assertAlmostEqual(campos["ry"], 0.25, places=2)
        x, y = posicao.calcular_ponto({"ancora": "proporcional", **campos}, PEQUENA)
        self.assertAlmostEqual(x, 300 + 0.75 * 999, delta=1)
        self.assertAlmostEqual(y, 200 + 0.25 * 399, delta=1)

    def test_ponto_fora_da_janela(self):
        with self.assertRaises(posicao.ForaDaJanela):
            posicao.referencia(5, 5, PEQUENA, "proporcional")


class Validacao(unittest.TestCase):
    def test_tela_continua_igual_e_ganha_alvo(self):
        self.assertEqual(validar_bloco({"tipo": "mover", "x": 1, "y": 2}), {"tipo": "mover", "alvo": "tela", "x": 1, "y": 2})

    def test_janela_proporcional(self):
        b = validar_bloco(prop(0.123456, 0.9))
        self.assertEqual((b["alvo"], b["janela"], b["rx"], b["ry"], b["trazer"]), ("janela", "Excel", 0.1235, 0.9, True))
        self.assertNotIn("x", b)

    def test_janela_com_canto(self):
        b = validar_bloco({"tipo": "mover", "alvo": "janela", "janela": " Chrome ", "ancora": "baixo_dir", "dx": 12, "dy": 8, "trazer": False})
        self.assertEqual((b["janela"], b["dx"], b["dy"], b["trazer"]), ("Chrome", 12, 8, False))
        self.assertNotIn("rx", b)

    def test_invalidos(self):
        for ruim in (prop(1.5, 0.5), prop(0.5, -0.1), prop("a", 0.5), {**prop(0.5, 0.5), "janela": ""},
                     {**prop(0.5, 0.5), "ancora": "meio"}, {**prop(0.5, 0.5), "alvo": "monitor"},
                     {"tipo": "clique", "alvo": "janela", "janela": "x", "ancora": "topo_esq", "dx": -1, "dy": 0}):
            with self.assertRaises(ErroConfig):
                validar_bloco(ruim)

    def test_descricoes(self):
        self.assertEqual(descrever_bloco(validar_bloco({"tipo": "clique", "x": 5, "y": 6})), "Clique em (5, 6)")
        self.assertEqual(descrever_bloco(validar_bloco(prop(0.375, 0.2))), 'Clique em (37,5%, 20%) da janela "Excel"')
        d = descrever_bloco(validar_bloco({"tipo": "mover", "alvo": "janela", "janela": "Excel", "ancora": "topo_dir", "dx": 30, "dy": 20}))
        self.assertEqual(d, 'Mover o mouse para a (30, 20) px do canto superior direito da janela "Excel"')


class PlataformaJanela(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.plat = plataforma_win.PlataformaWindows(UiFalsa(), "http://x", Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_tela_nao_precisa_do_windows(self):
        self.assertEqual(self.plat._ponto({"alvo": "tela", "x": 10, "y": 20}), (10, 20))
        self.assertEqual(self.plat._ponto({"x": 10, "y": 20}), (10, 20))      # bloco antigo, sem "alvo"

    def test_janela_segue_a_janela_de_agora(self):
        b = validar_bloco(prop(0.5, 0.5))
        tela = {"rect": GRANDE}
        with mock.patch.object(plataforma_win, "IS_WIN", True), \
                mock.patch.object(plataforma_win.PlataformaWindows, "_achar_janela", return_value=77), \
                mock.patch.object(plataforma_win.PlataformaWindows, "_area_da_janela", side_effect=lambda h: tela["rect"]), \
                mock.patch.object(plataforma_win.PlataformaWindows, "_trazer_para_frente") as frente:
            self.assertEqual(self.plat._ponto(b), (960, 540))
            tela["rect"] = PEQUENA                      # o programa foi redimensionado
            self.assertEqual(self.plat._ponto(b), (800, 400))
            frente.assert_called_with(77)
            frente.reset_mock()
            self.assertEqual(self.plat._ponto({**b, "trazer": False}), (800, 400))
            frente.assert_not_called()

    def test_janela_nao_encontrada_explica(self):
        with mock.patch.object(plataforma_win, "IS_WIN", True), \
                mock.patch.object(plataforma_win.PlataformaWindows, "_achar_janela", return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Janela não encontrada: "Excel"'):
                self.plat._ponto(validar_bloco(prop(0.5, 0.5)))

    def test_executar_clique_usa_o_ponto_calculado(self):
        usado = []
        with mock.patch.object(plataforma_win.PlataformaWindows, "_ponto", return_value=(800, 400)), \
                mock.patch.object(plataforma_win.PlataformaWindows, "_clique", side_effect=lambda b, p: usado.append(p)), \
                mock.patch.object(plataforma_win.time, "sleep"):
            self.plat.executar(validar_bloco(prop(0.5, 0.5)))
        self.assertEqual(usado, [(800, 400)])


class PainelEResolucao(unittest.TestCase):
    def test_janela_aceita_variavel(self):
        from configuracao import Config
        from nucleo import NucleoDeck
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(tmp)
            plat = PlataformaFalsa(numlock=False)
            n = NucleoDeck(cfg, plat, sincrono=True)
            cfg.aplicar_variavel("programa", "definir", 0)
            n.testar([prop(0.5, 0.5, janela="Pedido {programa}")])
            self.assertEqual(plat.executadas[-1]["janela"], "Pedido 0")


if __name__ == "__main__":
    unittest.main()
