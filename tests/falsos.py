"""Objetos de mentira para testar o núcleo e o painel sem Windows."""
import tempfile

from avisos import Segredos


class PlataformaFalsa:
    def __init__(self, numlock=True):
        self.numlock = numlock
        self.segredos = Segredos(tempfile.mkdtemp(prefix="segredos-teste-"))
        self.executadas = []
        self.apitos = []
        self.toasts = []
        self.previas = []          # (pagina, itens, segundos, alternar)
        self.previa_aberta = False
        self.nomes_previa = []
        self.whatsapps = []
        self.fechamentos = 0
        self.autostart = False
        self.condicoes = []        # respostas de avaliar_condicao, na ordem (a última se repete)
        self.avaliadas = []
        self.cor = "#00ff00"

    def perguntar(self, b):
        self.perguntas = getattr(self, "perguntas", []) + [b]
        prontas = getattr(self, "respostas_prontas", [])
        return prontas.pop(0) if prontas else None

    def fotografar_html(self, html, seletores):
        if getattr(self, "sem_foto", False):
            raise RuntimeError("sem navegador")
        import base64, io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1280, 300), "white").save(buf, "PNG")
        return {"png": buf.getvalue(), "altura": 300,
                "retangulos": {s: {"achados": 1, "x": 10, "y": 10 + 40 * i, "w": 100, "h": 30} for i, s in enumerate(seletores)}}

    def avaliar_condicao(self, cond):
        self.avaliadas.append(cond)
        if callable(self.condicoes):
            return self.condicoes(cond)
        if len(self.condicoes) > 1:
            return self.condicoes.pop(0)
        return self.condicoes[0] if self.condicoes else False

    def ler_cor(self, x, y):
        return self.cor

    def numlock_ligado(self):
        return self.numlock

    def alternar_numlock(self):
        self.numlock = not self.numlock

    def apitar(self, sucesso=True):
        self.apitos.append(sucesso)

    def toast(self, titulo, linhas=(), ms=3500):
        self.toasts.append((titulo, list(linhas)))

    def mostrar_previa(self, pagina, itens, segundos, alternar, nome=""):
        if alternar and self.previa_aberta:
            self.previa_aberta = False
            self.previas.append(("fechou", pagina))
            return
        self.previa_aberta = True
        self.previas.append((pagina, itens, segundos, alternar))
        self.nomes_previa.append(nome)

    def marcar_em_janela(self, x, y, ancora):
        self.marcados = getattr(self, "marcados", []) + [(x, y, ancora)]
        if getattr(self, "sem_janela", False):
            raise RuntimeError("Não encontrei uma janela de programa nesse ponto (área de trabalho?).")
        campos = {"rx": 0.25, "ry": 0.5} if ancora == "proporcional" else {"dx": 40, "dy": 12}
        return {"janela": "Planilha - Excel", "ancora": ancora, **campos}

    def enviar_whatsapp(self, numero, texto):
        self.whatsapps.append((numero, texto))

    def previa_visivel(self):
        return self.previa_aberta

    def fechar_previa(self):
        self.fechamentos += 1
        self.previa_aberta = False

    def executar(self, bloco):
        self.executadas.append(bloco)

    def autostart_ligado(self):
        return self.autostart

    def definir_autostart(self, ligado):
        self.autostart = ligado


class UiFalsa:
    def __init__(self):
        self.clique = (120, 340)
        self.arquivo = r"C:\scripts\meu.py"
        self.pasta = r"C:\Relatorios"
        self.mensagem = None
        self.saiu = False
        self.area = {"x": 0.5, "y": 0.6, "l": 0.3, "a": 0.2}

    def capturar_clique(self, timeout=60, mensagem=None, espera=0):
        self.mensagem = mensagem
        return self.clique

    def capturar_area(self, timeout=120, espera=0):
        return self.area

    def escolher_arquivo(self, timeout=300, texto=False):
        return self.arquivo

    def escolher_pasta(self, timeout=300):
        return self.pasta

    def cancelar_overlay(self):
        pass

    def sair(self):
        self.saiu = True
