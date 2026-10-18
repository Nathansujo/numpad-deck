"""Cérebro do deck: decide o que cada tecla faz.

Regras:
  * Luz do Num Lock ACESA  = modo padrão (o teclado numérico funciona normal).
  * Luz do Num Lock APAGADA = modo deck (teclas 0-9 executam o fluxo da página atual).
  * O próprio Num Lock nunca é bloqueado: é o Windows que acende/apaga a luz.
    Apertar o Num Lock também CANCELA qualquer fluxo em andamento.
  * No modo deck:  /  volta uma página,  *  avança uma página,  -  mostra a prévia grande da página.
  * No modo padrão essas três teclas continuam funcionando normalmente, mas apitam
    (opção "apitar_fora_do_deck") para avisar que a função de deck não foi executada.

Este módulo não depende do Windows: tudo que é do sistema passa pelo objeto `plataforma`.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from urllib.parse import quote

from configuracao import Config, aplicar_variaveis, descrever_condicao, normalizar_url, validar_fluxo
from teclas import nome_vk

VK_NUMLOCK = 0x90
VK_MULTIPLY, VK_SUBTRACT, VK_DIVIDE = 0x6A, 0x6D, 0x6F
FLAG_EXT, FLAG_INJETADO = 0x01, 0x10

# Scan codes do bloco numérico (não estendidos). Com o Num Lock apagado o Windows
# troca o VK (Home, End, setas...), mas o scan code físico continua o mesmo.
SCAN_NUMPAD = {
    0x52: "0", 0x4F: "1", 0x50: "2", 0x51: "3", 0x4B: "4",
    0x4C: "5", 0x4D: "6", 0x47: "7", 0x48: "8", 0x49: "9",
}
NAVEGACAO = {VK_DIVIDE: "voltar", VK_MULTIPLY: "avancar", VK_SUBTRACT: "perfil"}

PROFUNDIDADE_MAX = 10          # quantas teclas podem chamar umas às outras em cadeia
SEGUNDOS_PREVIA_TROCA = 3.5    # prévia que aparece ao trocar de página
INTERVALO_CONDICAO = 0.25      # de quanto em quanto tempo "Esperar" confere a condição


class FluxoCancelado(Exception):
    pass


class ErroFluxo(Exception):
    """Problema ao executar um fluxo (aparece como aviso para o usuário)."""


class GravacaoMacro:
    """Junta as teclas apertadas juntas; termina quando todas são soltas."""

    def __init__(self):
        self.ordem: list[int] = []
        self.por_tecla: dict[tuple, int] = {}
        self.fim = threading.Event()
        self.resultado: list[int] | None = None
        self.cancelada = False

    def tecla(self, descendo: bool, ident: tuple, vk: int) -> None:
        if descendo:
            if ident not in self.por_tecla:
                self.por_tecla[ident] = vk
                if vk not in self.ordem:
                    self.ordem.append(vk)
        else:
            self.por_tecla.pop(ident, None)
            if not self.por_tecla and self.ordem and not self.fim.is_set():
                self.resultado = list(self.ordem)
                self.fim.set()

    def cancelar(self) -> None:
        self.cancelada = True
        self.fim.set()


class NucleoDeck:
    def __init__(self, cfg: Config, plataforma, sincrono: bool = False):
        self.cfg = cfg
        self.p = plataforma
        self._sincrono = sincrono          # nos testes tudo roda na hora, sem threads
        self._fila: queue.Queue = queue.Queue()          # coisas rápidas (navegar, avisos)
        self._fila_fluxos: queue.Queue = queue.Queue()   # fluxos (podem demorar por causa das pausas)
        self._parar = threading.Event()
        self._geracao = 0                  # cada cancelamento troca o número; fluxos antigos desistem
        self._fluxo_ativo = False
        self._numlock_ligado = bool(plataforma.numlock_ligado())
        self._modo_anunciado = self.modo()
        self._numlock_apertado = False
        self._suprimidas: set[tuple] = set()       # teclas cujo "soltar" também deve ser engolido
        self._padrao_apertadas: set[tuple] = set()  # evita apitar em repetição de tecla
        self._gravacao: GravacaoMacro | None = None

    # ------------------------------------------------------------ ciclo de vida
    def iniciar(self) -> None:
        if self._sincrono:
            return
        for nome, alvo in (("deck-rapido", lambda: self._laco(self._fila)),
                           ("deck-fluxos", lambda: self._laco(self._fila_fluxos)),
                           ("deck-numlock", self._vigiar_numlock)):
            threading.Thread(target=alvo, name=nome, daemon=True).start()

    def encerrar(self) -> None:
        self._parar.set()
        self._geracao += 1
        try:
            if self.cfg.opcoes()["restaurar_numlock_ao_sair"] and not self.p.numlock_ligado():
                self.p.alternar_numlock()
        except Exception:
            logging.exception("Falha ao restaurar o Num Lock")

    def agendar(self, fn) -> None:
        if self._sincrono:
            fn()
        else:
            self._fila.put(fn)

    def _laco(self, fila: queue.Queue) -> None:
        while not self._parar.is_set():
            try:
                fn = fila.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                fn()
            except Exception as erro:
                logging.exception("Erro ao executar ação")
                self._avisar_erro(erro)

    def _vigiar_numlock(self) -> None:
        # Corrige a leitura caso o Num Lock mude por outro meio (teclado na tela, etc.)
        while not self._parar.wait(0.25):
            try:
                self._sincronizar()
            except Exception:
                logging.exception("Falha ao ler o Num Lock")

    def _avisar_erro(self, erro: Exception) -> None:
        try:
            self.p.apitar(False)
            self.p.toast("Não funcionou", [str(erro)[:160]], 4000)
        except Exception:
            pass

    # ------------------------------------------------------------ estado
    def modo(self) -> str:
        return "padrao" if self._numlock_ligado else "deck"

    def gravando(self) -> bool:
        return self._gravacao is not None

    def _sincronizar(self) -> None:
        self._numlock_ligado = bool(self.p.numlock_ligado())
        modo = self.modo()
        if modo == self._modo_anunciado:
            return
        self._modo_anunciado = modo
        if not self.cfg.opcoes()["popup_ao_trocar_modo"]:
            return
        if modo == "deck":
            self.p.toast("Modo deck", ["Luz do Num Lock apagada", f"Página {self.cfg.pagina_atual}"], 2200)
        else:
            self.p.toast("Modo padrão", ["Luz do Num Lock acesa", "Teclado numérico normal"], 2200)

    def _depois_do_numlock(self) -> None:
        if not self._sincrono:
            time.sleep(0.06)  # dá tempo do Windows alternar o estado
        self._sincronizar()

    # ------------------------------------------------------------ hook de teclado
    def evento(self, descendo: bool, vk: int, scan: int, flags: int) -> bool:
        """Chamado pelo hook para CADA tecla. Devolve True para engolir a tecla.

        Precisa ser rápido: nada de esperar, abrir janela ou tocar som aqui.
        """
        if flags & FLAG_INJETADO:
            return False  # teclas geradas por nós mesmos (macros) passam direto
        ext = bool(flags & FLAG_EXT)
        ident = (scan, ext)

        if vk == VK_NUMLOCK:
            if descendo and not self._numlock_apertado:
                self._numlock_apertado = True
                self._numlock_ligado = not self._numlock_ligado  # estimativa; a vigia corrige
                self.agendar(self.cancelar_fluxos)
                self.agendar(self._depois_do_numlock)
            elif not descendo:
                self._numlock_apertado = False
            return False

        if not descendo:
            self._padrao_apertadas.discard(ident)
            if ident in self._suprimidas:
                self._suprimidas.discard(ident)
                if self._gravacao is not None:
                    self._gravacao.tecla(False, ident, vk)
                return True
            return False

        if ident in self._suprimidas:
            return True  # repetição automática de uma tecla já tratada

        if self._gravacao is not None:
            self._suprimidas.add(ident)
            self._gravacao.tecla(True, ident, vk)
            return True

        deck = not self._numlock_ligado
        numero = None if ext else SCAN_NUMPAD.get(scan)
        nav = NAVEGACAO.get(vk)

        if numero is not None and deck:
            self._suprimidas.add(ident)
            self.agendar(lambda: self._tecla_deck(numero))
            return True

        if nav is not None:
            if deck:
                self._suprimidas.add(ident)
                self.agendar(lambda: self._navegar(nav))
                return True
            if ident not in self._padrao_apertadas:
                self._padrao_apertadas.add(ident)
                if self.cfg.opcoes()["apitar_fora_do_deck"]:
                    self.agendar(lambda: self.p.apitar(False))
        return False

    # ------------------------------------------------------------ teclas do deck
    def _tecla_deck(self, numero: str) -> None:
        pagina = self.cfg.pagina_atual
        fluxo = self.cfg.tecla(pagina, numero)["fluxo"]
        if not fluxo:
            self.p.toast(f"Página {pagina} · Tecla {numero}", ["Sem função configurada"], 1500)
            return
        self.p.fechar_previa()
        self._enfileirar(fluxo, (pagina, numero))

    def _navegar(self, comando: str) -> None:
        if comando == "voltar":
            if self.cfg.pagina_atual <= 1:
                self.p.apitar(False)
                self.p.toast("Página 1", ["Você já está na primeira página"], 1800)
            else:
                self.mudar_pagina(-1, popup=True)
        elif comando == "avancar":
            self.mudar_pagina(+1, popup=True)
        elif comando == "perfil":
            self.mostrar_previa(alternar=True)

    def mudar_pagina(self, delta: int, popup: bool = False) -> int:
        nova = self.cfg.ir_para(max(1, self.cfg.pagina_atual + delta))
        if popup:
            self._previa_ao_trocar(nova)
        return nova

    def ir_para_pagina(self, numero: int) -> int:
        return self.cfg.ir_para(numero)

    # ------------------------------------------------------------ prévia grande (pop-up com imagens)
    def mostrar_previa(self, alternar: bool = False) -> None:
        """Tecla `-` (alternar=True abre/fecha) ou botão do painel (alternar=False)."""
        pagina = self.cfg.pagina_atual
        self.p.mostrar_previa(pagina, self.cfg.itens_previa(pagina), self.cfg.opcoes()["perfil_segundos"], alternar,
                              self.cfg.nome_pagina(pagina))

    def _previa_ao_trocar(self, pagina: int) -> None:
        opcoes = self.cfg.opcoes()
        visivel = self.p.previa_visivel()
        if not (opcoes["popup_ao_trocar_pagina"] or visivel):
            return
        segundos = opcoes["perfil_segundos"] if visivel else SEGUNDOS_PREVIA_TROCA
        self.p.mostrar_previa(pagina, self.cfg.itens_previa(pagina), segundos, False, self.cfg.nome_pagina(pagina))

    # ------------------------------------------------------------ execução dos fluxos
    def _enfileirar(self, fluxo: list[dict], origem) -> None:
        geracao = self._geracao

        def trabalho():
            self._rodar(fluxo, origem, geracao)

        if self._sincrono:
            trabalho()
        else:
            self._fila_fluxos.put(trabalho)

    def _rodar(self, fluxo, origem, geracao) -> None:
        self._fluxo_ativo = True
        try:
            self._executar_fluxo(fluxo, (origem,) if origem else (), geracao)
        except FluxoCancelado:
            pass
        finally:
            self._fluxo_ativo = False

    def _executar_fluxo(self, fluxo, pilha: tuple, geracao: int) -> None:
        i = 0
        while i < len(fluxo):
            if geracao != self._geracao:
                raise FluxoCancelado()
            bloco = fluxo[i]
            tipo = bloco["tipo"]
            if tipo == "repetir":        # os próximos N blocos, X vezes
                corpo = fluxo[i + 1:i + 1 + bloco["blocos"]]
                for _ in range(bloco["vezes"]):
                    self._executar_fluxo(corpo, pilha, geracao)
                i += 1 + bloco["blocos"]
            elif tipo == "se":           # então = próximos K blocos; senão = os K2 seguintes
                verdade = bool(self.p.avaliar_condicao(self._resolver_condicao(bloco["condicao"])))
                if bloco.get("negar"):
                    verdade = not verdade
                k, k2 = bloco["entao"], bloco["senao"]
                escolhido = fluxo[i + 1:i + 1 + k] if verdade else fluxo[i + 1 + k:i + 1 + k + k2]
                self._executar_fluxo(escolhido, pilha, geracao)
                i += 1 + k + k2
            else:
                self._executar_bloco(bloco, pilha, geracao)
                i += 1

    # -- textos com {variáveis} e condições
    def _resolver_texto(self, texto: str) -> str:
        return aplicar_variaveis(texto, self.cfg.variaveis())

    def _resolver_condicao(self, cond: dict) -> dict:
        saida = dict(cond)
        for campo in ("texto", "valor"):
            if isinstance(saida.get(campo), str):
                saida[campo] = self._resolver_texto(saida[campo])
        return saida

    def _resolver(self, bloco: dict) -> dict:
        """Cópia do bloco com as {variáveis} trocadas pelos valores de agora."""
        campos = {"texto": ("texto",), "colar": ("texto",), "comando": ("comando",),
                  "abrir": ("argumentos",), "web_preencher": ("texto",), "whatsapp": ("mensagem",), "site": ("url",),
                  "aviso": ("titulo", "texto", "arquivo", "pasta", "comando"),
                  "clique": ("janela",), "mover": ("janela",)}
        resolvido = dict(bloco)
        for campo in campos.get(bloco["tipo"], ()):
            if isinstance(bloco.get(campo), str):
                resolvido[campo] = self._resolver_texto(bloco[campo])
        return resolvido

    def _esperar_condicao(self, cond: dict, ate: str, limite: float, geracao: int) -> bool:
        """Espera (sem travar o cancelamento) até a condição aparecer/sumir. False se o tempo acabar."""
        cond = self._resolver_condicao(cond)
        fim = time.monotonic() + limite
        while True:
            if geracao != self._geracao:
                raise FluxoCancelado()
            presente = bool(self.p.avaliar_condicao(cond))
            if presente == (ate == "aparecer"):
                return True
            restante = fim - time.monotonic()
            if restante <= 0:
                return False
            self._dormir(min(INTERVALO_CONDICAO, restante), geracao)

    def _executar_bloco(self, bloco: dict, pilha: tuple, geracao: int) -> None:
        tipo = bloco["tipo"]
        if tipo == "pausa":
            if bloco.get("modo", "tempo") == "tempo":
                self._dormir(bloco["segundos"], geracao)
            elif not self._esperar_condicao(bloco["condicao"], bloco["ate"], bloco["limite"], geracao):
                if bloco["ao_expirar"] == "parar":
                    raise ErroFluxo(f"Tempo esgotado ({bloco['limite']} s) esperando: {descrever_condicao(bloco['condicao'])}")
        elif tipo == "variavel":
            self.cfg.aplicar_variavel(bloco["nome"], bloco["operacao"], bloco["valor"])
        elif tipo == "chamar":
            alvo = (bloco["pagina"], bloco["tecla"])
            if alvo in pilha or len(pilha) >= PROFUNDIDADE_MAX:
                raise ErroFluxo("As teclas se chamam em ciclo (ou em cadeia longa demais).")
            sub = self.cfg.tecla(*alvo)["fluxo"]
            if not sub:
                raise ErroFluxo(f"A tecla {alvo[1]} da página {alvo[0]} está sem função.")
            self._executar_fluxo(sub, pilha + (alvo,), geracao)
        elif tipo == "ir_pagina":
            nova = self.cfg.ir_para(bloco["numero"])
            self._previa_ao_trocar(nova)
        elif tipo == "aviso":
            self.p.executar(self._resolver(bloco))
        elif tipo == "whatsapp":
            self.p.executar(self._bloco_whatsapp(self._resolver(bloco)))
        elif tipo == "site":
            resolvido = self._resolver(bloco)
            resolvido["url"] = normalizar_url(resolvido["url"])
            self.p.executar(resolvido)
        elif tipo in ("web_clicar", "web_preencher"):
            cond = {"tipo": "pagina", "alvo": "seletor", "valor": bloco["seletor"], "aba": bloco["aba"]}
            if not self._esperar_condicao(cond, "aparecer", bloco["limite"], geracao):
                raise ErroFluxo(f"Elemento não apareceu na página em {bloco['limite']} s: {bloco['seletor']}")
            self.p.executar(self._resolver(bloco))
        else:
            self.p.executar(self._resolver(bloco))

    @staticmethod
    def _bloco_whatsapp(b: dict) -> dict:
        """WhatsApp é só um site com o endereço certo (a mensagem fica preenchida; quem envia é você)."""
        texto = "text=" + quote(b["mensagem"], safe="") if b["mensagem"] else ""
        if b["controlado"]:
            partes = ([f"phone={b['numero']}"] if b["numero"] else []) + ([texto] if texto else [])
            url = "https://web.whatsapp.com/send?" + "&".join(partes)
        elif b["numero"]:
            url = f"https://wa.me/{b['numero']}" + (f"?{texto}" if texto else "")
        else:
            url = f"https://wa.me/?{texto}"
        return {"tipo": "site", "url": url, "controlado": b["controlado"]}

    def _dormir(self, segundos: float, geracao: int) -> None:
        fim = time.monotonic() + segundos
        while True:
            if geracao != self._geracao:
                raise FluxoCancelado()
            restante = fim - time.monotonic()
            if restante <= 0:
                return
            time.sleep(min(0.05, restante))

    def cancelar_fluxos(self) -> None:
        """Num Lock apertado: desiste do fluxo em andamento e dos que estavam esperando."""
        havia = self._fluxo_ativo or not self._fila_fluxos.empty()
        self._geracao += 1
        with self._fila_fluxos.mutex:
            self._fila_fluxos.queue.clear()
        if havia:
            self.p.toast("Fluxo cancelado", ["Num Lock apertado"], 1500)

    def testar(self, fluxo) -> None:
        fluxo = validar_fluxo(fluxo)
        if fluxo:
            self._enfileirar(fluxo, None)

    # ------------------------------------------------------------ gravação de atalho (painel)
    def gravar_macro(self, timeout: float = 20.0) -> list[dict] | None:
        """Bloqueia até o usuário fazer o comando (ex.: Ctrl+V) e soltar tudo."""
        if self._gravacao is not None:
            raise RuntimeError("Já existe uma gravação em andamento.")
        gravacao = GravacaoMacro()
        self._gravacao = gravacao
        try:
            gravacao.fim.wait(timeout)
        finally:
            self._gravacao = None
        if gravacao.cancelada or gravacao.resultado is None:
            return None
        return [{"vk": vk, "nome": nome_vk(vk)} for vk in gravacao.resultado]

    def cancelar_gravacao(self) -> None:
        if self._gravacao is not None:
            self._gravacao.cancelar()
