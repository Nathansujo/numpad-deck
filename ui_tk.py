"""Janelas auxiliares (tkinter): pop-up de aviso, tela escura para marcar clique e seletor de arquivo.

Tudo roda na thread principal; as outras threads só enfileiram pedidos (`post`).
"""
from __future__ import annotations

import logging
import queue
import sys
from concurrent.futures import Future

import avisos

COR_FUNDO = "#202024"
COR_VERDE = "#04d361"
COR_TEXTO = "#e1e1e6"
COR_CARTAO = "#2a2a30"


class InterfaceTk:
    def __init__(self):
        import tkinter as tk

        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self._fila: queue.Queue = queue.Queue()
        self._toast = None
        self._avisos: dict = {}           # pop-ups de aviso abertos, por posição
        self._overlay = None
        self._overlay_fut: Future | None = None
        self._pergunta = None             # janela de pergunta aberta (bloco Perguntar)
        self._pergunta_fut: Future | None = None
        self._previa = None
        self._previa_depois = None
        self._fotos: list = []            # o tkinter some com a imagem se ninguém guardar a referência
        self.previa_visivel = False
        self._linhas_titulo = 2
        self.root.after(30, self._drenar)

    # ------------------------------------------------------------ infraestrutura
    def post(self, fn) -> None:
        self._fila.put(fn)

    def _drenar(self) -> None:
        while True:
            try:
                fn = self._fila.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                logging.exception("Erro na interface")
        self.root.after(30, self._drenar)

    def loop(self) -> None:
        self.root.mainloop()
        try:
            self.root.destroy()
        except Exception:
            pass

    def sair(self) -> None:
        self.post(self.root.quit)

    # ------------------------------------------------------------ pop-up (toast)
    def toast(self, titulo: str, linhas=(), ms: int = 3500) -> None:
        self.post(lambda: self._toast_ui(titulo, list(linhas)[:14], ms))

    def _toast_ui(self, titulo, linhas, ms) -> None:
        tk = self.tk
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
        w = tk.Toplevel(self.root)
        self._toast = w
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", 0.96)
        except tk.TclError:
            pass
        quadro = tk.Frame(w, bg=COR_FUNDO, highlightbackground=COR_VERDE, highlightthickness=2)
        quadro.pack()
        tk.Label(quadro, text=titulo, bg=COR_FUNDO, fg=COR_VERDE, font=("Segoe UI", 14, "bold"),
                 anchor="w", justify="left").pack(fill="x", padx=16, pady=(12, 4))
        for linha in linhas:
            tk.Label(quadro, text=linha, bg=COR_FUNDO, fg=COR_TEXTO, font=("Segoe UI", 10),
                     anchor="w", justify="left").pack(fill="x", padx=16)
        tk.Frame(quadro, height=10, bg=COR_FUNDO).pack()
        w.update_idletasks()
        x = (w.winfo_screenwidth() - w.winfo_reqwidth()) // 2
        w.geometry(f"+{x}+24")
        self._sem_foco(w)
        w.after(ms, lambda: self._fechar_toast(w))

    def _fechar_toast(self, w) -> None:
        try:
            w.destroy()
        except self.tk.TclError:
            pass
        if self._toast is w:
            self._toast = None

    @staticmethod
    def _sem_foco(w) -> None:
        """Evita que o pop-up roube o foco de quem está digitando."""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(w.winfo_id()) or w.winfo_id()
            estilo = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            user32.SetWindowLongW(hwnd, -20, estilo | 0x08000000 | 0x00000080)  # NOACTIVATE | TOOLWINDOW
        except Exception:
            pass

    # ------------------------------------------------------------ tela escura para marcar clique
    def capturar_clique(self, timeout: float = 60, mensagem: str = "Clique onde a tecla deve clicar", espera: float = 5):
        """Contagem de `espera` segundos (dá tempo de trocar de aba/janela) e depois a tela escura para clicar."""
        fut: Future = Future()
        self.post(lambda: self._com_contagem(fut, mensagem, espera, lambda: self._overlay_ui(fut, mensagem)))
        try:
            return fut.result(timeout + espera)
        except Exception:
            self.cancelar_overlay()
            return None

    def _com_contagem(self, fut: Future, mensagem: str, espera: float, abrir) -> None:
        """Mostra um aviso pequeno com a contagem (a tela continua livre para mexer); no zero, chama `abrir`."""
        if espera <= 0:
            abrir()
            return
        tk = self.tk
        self._fim_overlay(self._overlay_fut, None)
        top = tk.Toplevel(self.root)
        self._overlay, self._overlay_fut = top, fut
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg="#1d1d22", highlightbackground=COR_VERDE, highlightthickness=3)
        ux, uy, uw, _uh = self._area_util()
        larg, alt = 560, 150
        top.geometry(f"{larg}x{alt}{ux + (uw - larg) // 2:+d}{uy + 24:+d}")
        resta = [int(espera)]
        texto = tk.StringVar()
        tk.Label(top, textvariable=texto, bg="#1d1d22", fg="white", font=("Segoe UI", 15, "bold"),
                 justify="center", wraplength=larg - 30).pack(pady=(18, 8), padx=15)
        botao = tk.Button(top, text="Cancelar", command=lambda: self._fim_overlay(fut, None), relief="flat",
                          bg="#3a3a44", fg="white", activebackground="#4a4a56", activeforeground="white",
                          font=("Segoe UI", 11), padx=16)
        botao.pack()
        top.bind("<Escape>", lambda _e: self._fim_overlay(fut, None))

        def tique():
            if self._overlay is not top:          # cancelado
                return
            if resta[0] <= 0:
                try:
                    top.destroy()
                except tk.TclError:
                    pass
                self._overlay = self._overlay_fut = None
                abrir()
                return
            texto.set(f"{mensagem}\nTroque de aba ou janela agora: a tela de clique abre em {resta[0]} s")
            resta[0] -= 1
            self.root.after(1000, tique)

        tique()

    def _tela_virtual(self):
        if sys.platform == "win32":
            import ctypes

            m = ctypes.windll.user32.GetSystemMetrics
            return m(76), m(77), m(78), m(79)  # x, y, largura, altura de todos os monitores
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _overlay_ui(self, fut: Future, mensagem: str = "Clique onde a tecla deve clicar") -> None:
        tk = self.tk
        self._fim_overlay(self._overlay_fut, None)
        x, y, w, h = self._tela_virtual()
        top = tk.Toplevel(self.root)
        self._overlay, self._overlay_fut = top, fut
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.attributes("-alpha", 0.30)
        top.configure(bg="black", cursor="crosshair")
        top.geometry(f"{w}x{h}{x:+d}{y:+d}")
        rotulo = tk.Label(top, text=f"{mensagem}   (Esc cancela)",
                          bg="black", fg="white", font=("Segoe UI", 22, "bold"), cursor="crosshair")
        rotulo.place(relx=0.5, rely=0.1, anchor="center")

        def clicou(ev):
            self._fim_overlay(fut, (ev.x_root, ev.y_root))

        def cancelou(_ev=None):
            self._fim_overlay(fut, None)

        for alvo in (top, rotulo):
            alvo.bind("<Button-1>", clicou)
        top.bind("<Escape>", cancelou)
        top.focus_force()

    def _fim_overlay(self, fut, valor) -> None:
        if self._overlay is not None:
            try:
                self._overlay.destroy()
            except self.tk.TclError:
                pass
            self._overlay = None
        if fut is not None and not fut.done():
            fut.set_result(valor)

    def cancelar_overlay(self) -> None:
        self.post(lambda: self._fim_overlay(self._overlay_fut, None))

    # ------------------------------------------------------------ pop-up de aviso (tamanho e lugar escolhidos)
    def _area_util(self):
        """Área de trabalho do monitor principal (descontando a barra de tarefas)."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                r = wintypes.RECT()
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):  # SPI_GETWORKAREA
                    return r.left, r.top, r.right - r.left, r.bottom - r.top
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def aviso(self, titulo: str, texto: str, tamanho: str = "medio", posicao: str = "baixo_dir",
              area: dict | None = None, segundos: float = 5) -> None:
        self.post(lambda: self._aviso_ui(titulo, texto, tamanho, posicao, area, segundos))

    def _aviso_ui(self, titulo, texto, tamanho, posicao, area, segundos) -> None:
        tk = self.tk
        x, y, largura, altura = avisos.calcular_retangulo(self._area_util(), tamanho, posicao, area, self._tela_virtual())
        chave = posicao if posicao != "personalizado" else (x, y, largura, altura)   # um aviso novo cobre o antigo do mesmo lugar
        antigo = self._avisos.pop(chave, None)
        if antigo is not None:
            try:
                antigo.destroy()
            except tk.TclError:
                pass
        escala = max(0.8, min(2.2, min(largura / 380, altura / 130)))
        w = tk.Toplevel(self.root)
        self._avisos[chave] = w
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        quadro = tk.Frame(w, bg=COR_FUNDO, highlightbackground=COR_VERDE, highlightthickness=3)
        quadro.pack(fill="both", expand=True)
        miolo = tk.Frame(quadro, bg=COR_FUNDO)
        miolo.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.92)
        if titulo:
            tk.Label(miolo, text=titulo, bg=COR_FUNDO, fg=COR_VERDE, wraplength=int(largura * 0.88),
                     font=("Segoe UI", int(11 * escala), "bold"), justify="center").pack()
        tk.Label(miolo, text=texto, bg=COR_FUNDO, fg=COR_TEXTO, wraplength=int(largura * 0.88),
                 font=("Segoe UI", int(10 * escala)), justify="center").pack(pady=(4 if titulo else 0, 0))
        w.geometry(f"{largura}x{altura}{x:+d}{y:+d}")
        for alvo in (w, quadro, miolo, *miolo.winfo_children()):
            alvo.bind("<Button-1>", lambda _e, w=w, k=chave: self._fechar_aviso(k, w))
        self._sem_foco(w)
        if segundos > 0:   # 0 = fica até você clicar nele
            w.after(int(segundos * 1000), lambda: self._fechar_aviso(chave, w))

    def _fechar_aviso(self, chave, w) -> None:
        try:
            w.destroy()
        except self.tk.TclError:
            pass
        if self._avisos.get(chave) is w:
            self._avisos.pop(chave, None)

    # ------------------------------------------------------------ desenhar na tela onde o aviso aparece
    def capturar_area(self, timeout: float = 120, espera: float = 5):
        """Tela escura: o usuário arrasta um retângulo. Devolve {x, y, l, a} em frações (0 a 1) da tela
        virtual, ou None se cancelar."""
        fut: Future = Future()
        self.post(lambda: self._com_contagem(fut, "Desenhe onde o aviso vai aparecer", espera, lambda: self._area_ui(fut)))
        try:
            return fut.result(timeout + espera)
        except Exception:
            self.cancelar_overlay()
            return None

    def _area_ui(self, fut: Future) -> None:
        tk = self.tk
        self._fim_overlay(self._overlay_fut, None)
        x0, y0, W, H = self._tela_virtual()
        top = tk.Toplevel(self.root)
        self._overlay, self._overlay_fut = top, fut
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.attributes("-alpha", 0.45)
        top.configure(bg="black", cursor="crosshair")
        top.geometry(f"{W}x{H}{x0:+d}{y0:+d}")
        tela = tk.Canvas(top, width=W, height=H, bg="black", highlightthickness=0, cursor="crosshair")
        tela.pack()
        tela.create_text(W // 2, int(H * 0.08), fill="white", font=("Segoe UI", 22, "bold"),
                         text="Arraste para desenhar onde o aviso vai aparecer   (Esc cancela)")
        # tamanhos de referência (pequeno, médio, grande) no centro da tela principal
        ux, uy, uw, uh = self._area_util()
        for nome, (fl, fa) in avisos.TAMANHOS.items():
            rw, rh = fl * uw, fa * uh
            cx, cy = ux - x0 + (uw - rw) / 2, uy - y0 + (uh - rh) / 2
            tela.create_rectangle(cx, cy, cx + rw, cy + rh, outline="#8a8a94", dash=(6, 4))
            tela.create_text(cx + 8, cy + 6, anchor="nw", fill="#b4b4be", font=("Segoe UI", 11), text=nome)
        estado = {"ini": None, "ret": None}

        def apertou(ev):
            estado["ini"] = (ev.x, ev.y)
            if estado["ret"] is not None:
                tela.delete(estado["ret"])
            estado["ret"] = tela.create_rectangle(ev.x, ev.y, ev.x, ev.y, outline=COR_VERDE, width=4,
                                                  fill=COR_VERDE, stipple="gray25")

        def arrastou(ev):
            if estado["ini"] is not None:
                tela.coords(estado["ret"], estado["ini"][0], estado["ini"][1], ev.x, ev.y)

        def soltou(ev):
            if estado["ini"] is None:
                return
            ax, ay = estado["ini"]
            esq, dir_ = sorted((ax, ev.x))
            cima, baixo = sorted((ay, ev.y))
            if dir_ - esq < 0.03 * W or baixo - cima < 0.03 * H:   # pequeno demais: desenhe de novo
                tela.delete(estado["ret"])
                estado["ini"] = estado["ret"] = None
                return
            self._fim_overlay(fut, {"x": round(esq / W, 4), "y": round(cima / H, 4),
                                    "l": round((dir_ - esq) / W, 4), "a": round((baixo - cima) / H, 4)})

        tela.bind("<ButtonPress-1>", apertou)
        tela.bind("<B1-Motion>", arrastou)
        tela.bind("<ButtonRelease-1>", soltou)
        top.bind("<Escape>", lambda _e: self._fim_overlay(fut, None))
        top.focus_force()

    # ------------------------------------------------------------ seletor de arquivo
    def escolher_arquivo(self, timeout: float = 300, texto: bool = False):
        fut: Future = Future()
        self.post(lambda: self._arquivo_ui(fut, texto))
        try:
            return fut.result(timeout)
        except Exception:
            return None

    def _arquivo_ui(self, fut: Future, texto: bool = False) -> None:
        from tkinter import filedialog

        try:
            self.root.attributes("-topmost", True)
            caminho = filedialog.askopenfilename(
                parent=self.root,
                title="Escolha o arquivo de texto" if texto else "Escolha o programa ou script",
                filetypes=[("Textos", "*.txt *.csv *.md *.log"), ("Todos os arquivos", "*.*")] if texto else
                          [("Python, programas e atalhos", "*.py *.pyw *.bat *.cmd *.exe *.lnk"), ("Todos os arquivos", "*.*")],
            )
        finally:
            self.root.attributes("-topmost", False)
        fut.set_result(caminho or None)

    # ------------------------------------------------------------ perguntas do bloco "Perguntar"
    def _perguntar_ui(self, montar, timeout: float):
        fut: Future = Future()
        self.post(lambda: montar(fut))
        try:
            return fut.result(timeout)
        except Exception:
            self.post(lambda: self._fechar_pergunta(self._pergunta_fut, None))
            return None

    def _fechar_pergunta(self, fut, valor=None) -> None:
        w, self._pergunta = self._pergunta, None
        if w is not None:
            try:
                w.destroy()
            except self.tk.TclError:
                pass
        if fut is not None and not fut.done():
            fut.set_result(valor)

    def _janela_pergunta(self, titulo: str, fut: Future, largura: int = 540):
        tk = self.tk
        self._fechar_pergunta(self._pergunta_fut, None)
        w = tk.Toplevel(self.root)
        self._pergunta, self._pergunta_fut = w, fut
        w.title("Numpad Deck")
        w.configure(bg=COR_FUNDO, highlightbackground=COR_VERDE, highlightthickness=2)
        w.attributes("-topmost", True)
        w.resizable(False, False)
        tk.Label(w, text=titulo, bg=COR_FUNDO, fg=COR_VERDE, font=("Segoe UI", 14, "bold"), anchor="w",
                 justify="left", wraplength=largura - 40).pack(fill="x", padx=20, pady=(16, 8))
        w.protocol("WM_DELETE_WINDOW", lambda: self._fechar_pergunta(fut, None))
        w.bind("<Escape>", lambda _e: self._fechar_pergunta(fut, None))
        return w

    def _mostrar_pergunta(self, w, foco=None) -> None:
        w.update_idletasks()
        ux, uy, uw, uh = self._area_util()
        w.geometry(f"+{ux + max(0, (uw - w.winfo_reqwidth()) // 2)}+{uy + max(0, (uh - w.winfo_reqheight()) // 3)}")
        if sys.platform == "win32":      # o Windows só deixa a janela ir à frente se o programa "acabou de receber uma tecla"
            try:
                import ctypes

                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)   # Alt solto logo em seguida: libera o primeiro plano
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            except Exception:
                pass
        w.lift()
        w.focus_force()
        if foco is not None:
            foco.focus_set()

    def perguntar_texto(self, titulo: str, padrao: str = "", timeout: float = 600):
        return self._perguntar_ui(lambda fut: self._texto_ui(fut, titulo, padrao), timeout)

    def _texto_ui(self, fut: Future, titulo: str, padrao: str) -> None:
        tk = self.tk
        w = self._janela_pergunta(titulo, fut)
        campo = tk.Entry(w, font=("Segoe UI", 13), width=44, bg=COR_CARTAO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
                         relief="flat", highlightthickness=1, highlightbackground="#3a3a44", highlightcolor=COR_VERDE)
        campo.pack(padx=20, pady=(0, 12), ipady=6)
        campo.insert(0, padrao)
        campo.select_range(0, "end")

        def ok(_e=None):
            valor = campo.get().strip()
            if valor:
                self._fechar_pergunta(fut, valor)

        botoes = tk.Frame(w, bg=COR_FUNDO)
        botoes.pack(fill="x", padx=20, pady=(0, 16))
        tk.Button(botoes, text="OK", command=ok, bg=COR_VERDE, fg="black", relief="flat", font=("Segoe UI", 11, "bold"),
                  padx=22, pady=4).pack(side="right")
        tk.Button(botoes, text="Cancelar", command=lambda: self._fechar_pergunta(fut, None), bg="#3a3a44", fg="white",
                  relief="flat", font=("Segoe UI", 11), padx=16, pady=4).pack(side="right", padx=(0, 10))
        campo.bind("<Return>", ok)
        self._mostrar_pergunta(w, campo)

    def perguntar_escolha(self, titulo: str, opcoes: list, timeout: float = 600):
        """Mostra os caminhos (nome + descrição) e devolve "1", "2"... conforme o escolhido (ou None)."""
        return self._perguntar_ui(lambda fut: self._escolha_ui(fut, titulo, opcoes), timeout)

    def _escolha_ui(self, fut: Future, titulo: str, opcoes: list) -> None:
        tk = self.tk
        w = self._janela_pergunta(titulo, fut, 620)
        w.cartoes = []

        def escolher(i):
            self._fechar_pergunta(fut, str(i + 1))

        for i, op in enumerate(opcoes):
            cartao = tk.Frame(w, bg=COR_CARTAO, highlightbackground="#3a3a44", highlightthickness=1, cursor="hand2")
            cartao.pack(fill="x", padx=20, pady=5)
            nome = tk.Label(cartao, text=f"{i + 1}   {op['nome']}", bg=COR_CARTAO, fg=COR_TEXTO, font=("Segoe UI", 13, "bold"),
                            anchor="w", cursor="hand2")
            nome.pack(fill="x", padx=14, pady=(10, 2 if op.get("descricao") else 10))
            partes = [cartao, nome]
            if op.get("descricao"):
                desc = tk.Label(cartao, text=op["descricao"], bg=COR_CARTAO, fg="#a8a8b3", font=("Segoe UI", 10), anchor="w",
                                justify="left", wraplength=560, cursor="hand2")
                desc.pack(fill="x", padx=14, pady=(0, 10))
                partes.append(desc)
            for p in partes:
                p.bind("<Button-1>", lambda _e, i=i: escolher(i))
                p.bind("<Enter>", lambda _e, c=cartao: c.configure(highlightbackground=COR_VERDE))
                p.bind("<Leave>", lambda _e, c=cartao: c.configure(highlightbackground="#3a3a44"))
            w.cartoes.append(cartao)
            if i < 9:
                w.bind(str(i + 1), lambda _e, i=i: escolher(i))
        tk.Label(w, text="Clique no caminho ou aperte o número dele no teclado (Esc cancela)", bg=COR_FUNDO, fg="#7c7c88",
                 font=("Segoe UI", 9)).pack(pady=(6, 14))
        self._mostrar_pergunta(w)

    def perguntar_arquivo(self, titulo: str, inicial: str = "", timeout: float = 600):
        fut: Future = Future()
        self.post(lambda: self._pergunta_arquivo_ui(fut, titulo, inicial))
        try:
            return fut.result(timeout)
        except Exception:
            return None

    def _pergunta_arquivo_ui(self, fut: Future, titulo: str, inicial: str) -> None:
        from pathlib import Path
        from tkinter import filedialog

        pasta = Path(inicial).parent if inicial and Path(inicial).parent.is_dir() else None
        try:
            self.root.attributes("-topmost", True)
            caminho = filedialog.askopenfilename(parent=self.root, title=titulo or "Escolha o arquivo",
                                                 initialdir=str(pasta) if pasta else None,
                                                 filetypes=[("Textos", "*.txt *.csv *.md *.log"), ("Todos os arquivos", "*.*")])
        finally:
            self.root.attributes("-topmost", False)
        fut.set_result(caminho or None)

    def escolher_pasta(self, timeout: float = 300):
        fut: Future = Future()
        self.post(lambda: self._pasta_ui(fut))
        try:
            return fut.result(timeout)
        except Exception:
            return None

    def _pasta_ui(self, fut: Future) -> None:
        from tkinter import filedialog

        try:
            self.root.attributes("-topmost", True)
            pasta = filedialog.askdirectory(parent=self.root, title="Escolha a pasta")
        finally:
            self.root.attributes("-topmost", False)
        fut.set_result(pasta or None)

    # ------------------------------------------------------------ área de transferência
    def copiar_texto(self, texto: str, timeout: float = 3) -> None:
        """Põe o texto na área de transferência (feito na thread da interface; espera terminar)."""
        fut: Future = Future()

        def fazer():
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(texto)
                self.root.update()   # o Windows só guarda o conteúdo depois de processar o evento
                fut.set_result(True)
            except Exception as e:  # noqa: BLE001
                fut.set_exception(e)

        self.post(fazer)
        fut.result(timeout)

    # ------------------------------------------------------------ prévia grande da página
    def previa(self, pagina: int, itens: list, segundos: float, alternar: bool, nome: str = "") -> None:
        """Mostra (ou, com alternar=True e já aberta, fecha) a prévia com imagem + nome de cada tecla."""
        self.post(lambda: self._previa_ui(pagina, itens, segundos, alternar, nome))

    def fechar_previa(self) -> None:
        self.post(self._fechar_previa_ui)

    def _fechar_previa_ui(self) -> None:
        if self._previa_depois is not None:
            try:
                self.root.after_cancel(self._previa_depois)
            except Exception:
                pass
            self._previa_depois = None
        if self._previa is not None:
            try:
                self._previa.destroy()
            except self.tk.TclError:
                pass
            self._previa = None
        self._fotos = []
        self.previa_visivel = False

    def _foto(self, caminho: str | None, lado: int):
        if not caminho:
            return None
        try:
            from PIL import Image, ImageOps, ImageTk

            with Image.open(caminho) as img:
                img = ImageOps.fit(img.convert("RGBA"), (lado, lado), method=Image.LANCZOS)
            return ImageTk.PhotoImage(img, master=self.root)
        except Exception:
            logging.exception("Não foi possível carregar a imagem %s", caminho)
            return None

    def _previa_ui(self, pagina, itens, segundos, alternar, nome="") -> None:
        tk = self.tk
        if alternar and self._previa is not None:
            self._fechar_previa_ui()
            return
        self._fechar_previa_ui()

        # tamanho da imagem de cada tecla: cabe em 4 linhas dentro de ~90% da altura da tela
        altura_tela, largura_tela = self.root.winfo_screenheight(), self.root.winfo_screenwidth()
        disponivel = altura_tela * 0.9 - 110
        lado, linhas_titulo = int(min(150, disponivel / 4 - 78)), 2
        if lado < 110:  # tela pequena: imagens menores e espaço para títulos de 3 linhas
            lado, linhas_titulo = int(max(56, disponivel / 4 - 95)), 3
        self._linhas_titulo = linhas_titulo

        w = tk.Toplevel(self.root)
        self._previa = w
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", 0.98)
        except tk.TclError:
            pass
        quadro = tk.Frame(w, bg=COR_FUNDO, highlightbackground=COR_VERDE, highlightthickness=3)
        quadro.pack()
        tk.Label(quadro, text=f"Página {pagina}" + (f" · {nome}" if nome else ""), bg=COR_FUNDO, fg=COR_VERDE,
                 font=("Segoe UI", 22, "bold")).pack(pady=(14, 0), padx=20)
        tk.Label(quadro, text="O que cada botão faz", bg=COR_FUNDO, fg="#a8a8b3",
                 font=("Segoe UI", 10)).pack(pady=(0, 8))
        grade = tk.Frame(quadro, bg=COR_FUNDO)
        grade.pack(padx=16)

        por_tecla = {item["tecla"]: item for item in itens}
        ordem = [["7", "8", "9"], ["4", "5", "6"], ["1", "2", "3"]]
        for linha, teclas in enumerate(ordem):
            for coluna, numero in enumerate(teclas):
                self._celula(grade, por_tecla[numero], lado).grid(row=linha, column=coluna, padx=6, pady=6)
        self._celula(grade, por_tecla["0"], lado).grid(row=3, column=0, columnspan=3, padx=6, pady=6)

        tk.Label(quadro, text="Aperte  −  de novo ou clique aqui para fechar", bg=COR_FUNDO, fg="#6b6b75",
                 font=("Segoe UI", 9)).pack(pady=(4, 10))

        self._ligar_clique(w)
        w.update_idletasks()
        x = max(0, (largura_tela - w.winfo_reqwidth()) // 2)
        y = max(0, (altura_tela - w.winfo_reqheight()) // 2)
        w.geometry(f"+{x}+{y}")
        self._sem_foco(w)
        self.previa_visivel = True
        self._previa_depois = self.root.after(int(segundos * 1000), self._fechar_previa_ui)

    def _celula(self, pai, item: dict, lado: int):
        tk = self.tk
        vazio = item["vazio"]
        fundo = "#1a1a1d" if vazio else "#29292e"
        celula = tk.Frame(pai, bg=fundo, highlightbackground="#323238", highlightthickness=1)
        tk.Label(celula, text=item["tecla"], bg=fundo, fg=COR_VERDE, anchor="w",
                 font=("Segoe UI", 11, "bold")).pack(fill="x", padx=8, pady=(6, 0))
        foto = self._foto(item["imagem"], lado)
        if foto is not None:
            self._fotos.append(foto)
            tk.Label(celula, image=foto, bg=fundo, borderwidth=0).pack(padx=8, pady=4)
        else:
            vazio_img = tk.Frame(celula, width=lado, height=lado, bg="#202024")
            vazio_img.pack_propagate(False)
            vazio_img.pack(padx=8, pady=4)
            tk.Label(vazio_img, text="—" if vazio else item["tecla"], bg="#202024", fg="#4b4b55",
                     font=("Segoe UI", max(14, lado // 3), "bold")).pack(expand=True)
        tk.Label(celula, text=item["titulo"], bg=fundo, fg="#6b6b75" if vazio else COR_TEXTO,
                 wraplength=lado + 8, justify="center", height=self._linhas_titulo, anchor="n",
                 font=("Segoe UI", 10, "bold")).pack(padx=6, pady=(0, 8))
        return celula

    def _ligar_clique(self, widget) -> None:
        widget.bind("<Button-1>", lambda _e: self._fechar_previa_ui())
        for filho in widget.winfo_children():
            self._ligar_clique(filho)
