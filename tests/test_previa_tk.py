"""Pop-up grande (tkinter). Só roda onde existem tkinter, Pillow e uma tela (no Windows roda sempre)."""
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import tkinter
    from PIL import Image  # noqa: F401
    TEM_TELA = (sys.platform == "win32" or bool(os.environ.get("DISPLAY"))) and not os.environ.get("CI")
except ImportError:
    TEM_TELA = False


def png(caminho, cor):
    raw = b"".join(b"\x00" + bytes(cor) * 40 for _ in range(30))

    def ch(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    dados = b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 40, 30, 8, 2, 0, 0, 0)) \
        + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")
    Path(caminho).write_bytes(dados)
    return str(caminho)


@unittest.skipUnless(TEM_TELA, "sem tkinter/Pillow/tela")
class PreviaGrande(unittest.TestCase):
    def test_abre_alterna_fecha_sozinha_e_mostra_titulos(self):
        import ui_tk

        with tempfile.TemporaryDirectory() as tmp:
            foto = png(Path(tmp) / "a.png", (229, 72, 77))
            itens = [{"tecla": t, "titulo": "Livre", "imagem": None, "vazio": True} for t in "7894561230"]
            itens[0] = {"tecla": "7", "titulo": "Google", "imagem": foto, "vazio": False}
            itens[4] = {"tecla": "5", "titulo": "Relatório mensal do cliente", "imagem": "/nao/existe.png", "vazio": False}
            ui = ui_tk.InterfaceTk()
            r = {}

            def roteiro():
                try:
                    ui.previa(3, itens, 5, alternar=True); time.sleep(0.6)
                    r["abriu"] = ui.previa_visivel
                    ui.previa(3, itens, 5, alternar=True); time.sleep(0.3)
                    r["alternou"] = ui.previa_visivel
                    ui.previa(4, itens, 0.4, alternar=False); time.sleep(0.2)
                    r["reabriu"] = ui.previa_visivel
                    time.sleep(0.7)
                    r["sozinha"] = ui.previa_visivel
                    ui.previa(1, itens, 5, alternar=False); time.sleep(0.3)
                    ui.fechar_previa(); time.sleep(0.2)
                    r["fechou"] = ui.previa_visivel
                except Exception as e:  # pragma: no cover
                    r["erro"] = repr(e)
                finally:
                    ui.sair()

            threading.Thread(target=roteiro, daemon=True).start()
            ui.loop()
        self.assertNotIn("erro", r)
        self.assertEqual(r, {"abriu": True, "alternou": False, "reabriu": True, "sozinha": False, "fechou": False})


@unittest.skipUnless(TEM_TELA, "sem tkinter/Pillow/tela")
class AvisoNaTela(unittest.TestCase):
    _vivas: list = []      # o tkinter quebra se um Tk é coletado fora da thread que o criou

    @staticmethod
    def na_tela(ui, fn):
        """Roda fn na thread da interface (onde o tkinter pode ser tocado) e devolve o resultado."""
        from concurrent.futures import Future

        fut = Future()

        def faz():
            try:
                fut.set_result(fn())
            except Exception as e:  # pragma: no cover
                fut.set_exception(e)

        ui.post(faz)
        return fut.result(5)

    def rodar(self, roteiro):
        import ui_tk

        ui = ui_tk.InterfaceTk()
        self._vivas.append(ui)
        r = {}

        def corpo():
            try:
                roteiro(ui, r)
            except Exception as e:  # pragma: no cover
                r["erro"] = repr(e)
            finally:
                ui.sair()

        threading.Thread(target=corpo, daemon=True).start()
        ui.loop()
        self.assertNotIn("erro", r)
        return r

    @staticmethod
    def geo(ui):
        (w,) = ui._avisos.values()
        w.update_idletasks()
        return w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height()

    def test_popup_aparece_no_canto_com_o_tamanho_e_fecha_sozinho(self):
        def roteiro(ui, r):
            ui.aviso("Sistema", "Python já finalizou", "medio", "baixo_dir", None, 0.6); time.sleep(0.4)
            r["geo"], r["tela"] = self.na_tela(ui, lambda: (self.geo(ui), (ui.root.winfo_screenwidth(), ui.root.winfo_screenheight())))
            time.sleep(0.8)
            r["abertos"] = len(ui._avisos)

        r = self.rodar(roteiro)
        x, y, w, h = r["geo"]
        tw, th = r["tela"]
        self.assertGreater(x + w, tw * 0.9)
        self.assertLessEqual(x + w, tw)
        self.assertGreater(y + h, th * 0.9)
        self.assertLessEqual(y + h, th)
        self.assertEqual(r["abertos"], 0)

    def test_tamanhos_diferentes_e_zero_segundos_fica_ate_clicar(self):
        def roteiro(ui, r):
            tamanhos = []
            for t in ("pequeno", "medio", "grande"):
                ui.aviso("", "Teste", t, "centro", None, 0); time.sleep(0.3)
                g = self.na_tela(ui, lambda: self.geo(ui))
                tamanhos.append(g[2] * g[3])
                time.sleep(0.2)
            r["tamanhos"] = tamanhos
            r["abertos"] = len(ui._avisos)
            self.na_tela(ui, lambda: list(ui._avisos.values())[0].event_generate("<Button-1>", x=5, y=5)); time.sleep(0.3)
            r["depois_do_clique"] = len(ui._avisos)

        r = self.rodar(roteiro)
        a, b, c = r["tamanhos"]
        self.assertLess(a, b)
        self.assertLess(b, c)
        self.assertEqual(r["abertos"], 1)             # mesmo lugar: o novo substitui o antigo
        self.assertEqual(r["depois_do_clique"], 0)

    def test_posicao_personalizada(self):
        def roteiro(ui, r):
            ui.aviso("", "Aqui", "medio", "personalizado", {"x": 0.25, "y": 0.5, "l": 0.3, "a": 0.2}, 0); time.sleep(0.4)
            r["geo"], r["tela"] = self.na_tela(ui, lambda: (self.geo(ui), (ui.root.winfo_screenwidth(), ui.root.winfo_screenheight())))

        r = self.rodar(roteiro)
        tw, th = r["tela"]
        x, y, w, h = r["geo"]
        self.assertAlmostEqual(x, 0.25 * tw, delta=3)
        self.assertAlmostEqual(y, 0.5 * th, delta=3)
        self.assertAlmostEqual(w, 0.3 * tw, delta=3)
        self.assertAlmostEqual(h, 0.2 * th, delta=3)

    def test_desenhar_a_area_na_tela(self):
        def roteiro(ui, r):
            def arrastar():
                time.sleep(0.5)
                tela = self.na_tela(ui, lambda: ui._overlay.winfo_children()[0])
                W, H = self.na_tela(ui, lambda: (tela.winfo_width(), tela.winfo_height()))

                def ev(nome, fx, fy):
                    self.na_tela(ui, lambda: tela.event_generate(nome, x=int(fx * W), y=int(fy * H)))
                    time.sleep(0.1)
                ev("<ButtonPress-1>", 0.6, 0.7)
                ev("<B1-Motion>", 0.8, 0.9)
                ev("<ButtonRelease-1>", 0.8, 0.9)
            threading.Thread(target=arrastar, daemon=True).start()
            r["area"] = ui.capturar_area(5)

        r = self.rodar(roteiro)
        a = r["area"]
        self.assertIsNotNone(a)
        self.assertAlmostEqual(a["x"], 0.6, delta=0.01)
        self.assertAlmostEqual(a["y"], 0.7, delta=0.01)
        self.assertAlmostEqual(a["l"], 0.2, delta=0.01)
        self.assertAlmostEqual(a["a"], 0.2, delta=0.01)

    def test_esc_cancela_o_desenho(self):
        def roteiro(ui, r):
            def cancelar():
                time.sleep(0.5)
                self.na_tela(ui, lambda: ui._overlay.event_generate("<Escape>"))
            threading.Thread(target=cancelar, daemon=True).start()
            r["area"] = ui.capturar_area(5)

        self.assertIsNone(self.rodar(roteiro)["area"])


if __name__ == "__main__":
    unittest.main()
