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
from nucleo import NucleoDeck  # noqa: E402

DOWN, UP = True, False
EXT = 0x01
INJ = 0x10

# (vk, scan, flags) como o Windows entrega
NUMLOCK = (0x90, 0x45, 0)
BARRA = (0x6F, 0x35, EXT)
ASTERISCO = (0x6A, 0x37, 0)
MENOS = (0x6D, 0x4A, 0)
# número 5 do bloco numérico: com Num Lock ligado é VK_NUMPAD5; desligado vira VK_CLEAR
NUM5_PADRAO = (0x65, 0x4C, 0)
NUM5_DECK = (0x0C, 0x4C, 0)
NUM7_DECK = (0x24, 0x47, 0)
HOME_REAL = (0x24, 0x47, EXT)  # tecla Home do bloco de navegação (estendida)
LETRA_A = (0x41, 0x1E, 0)

ATALHO = {"tipo": "atalho", "teclas": [{"vk": 0xA2, "nome": "Ctrl"}, {"vk": 0x56, "nome": "V"}]}
MACRO = [ATALHO]   # fluxo de um bloco só
ATALHO_OK = {"tipo": "atalho", "teclas": ATALHO["teclas"]}


def chamar(pagina, tecla):
    return {"tipo": "chamar", "pagina": pagina, "tecla": tecla}


class Base(unittest.TestCase):
    numlock = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(self.tmp.name)
        self.plat = PlataformaFalsa(numlock=self.numlock)
        self.n = NucleoDeck(self.cfg, self.plat, sincrono=True)

    def tearDown(self):
        self.tmp.cleanup()

    def tecla(self, k, descendo=DOWN, extra=0):
        vk, scan, flags = k
        return self.n.evento(descendo, vk, scan, flags | extra)

    def aperta(self, k):
        """Aperta e solta; devolve (engoliu_ao_apertar, engoliu_ao_soltar)."""
        return self.tecla(k, DOWN), self.tecla(k, UP)


class ModoPadrao(Base):
    numlock = True

    def test_teclado_numerico_funciona_normal(self):
        self.cfg.definir_tecla(1, "5", "", None, MACRO)
        self.assertEqual(self.aperta(NUM5_PADRAO), (False, False))
        self.assertEqual(self.plat.executadas, [])

    def test_barra_apita_mas_continua_digitando(self):
        self.assertEqual(self.aperta(BARRA), (False, False))
        self.assertEqual(self.plat.apitos, [False])
        self.assertEqual(self.cfg.pagina_atual, 1)

    def test_asterisco_e_menos_nao_executam_deck_no_modo_padrao(self):
        self.aperta(ASTERISCO)
        self.aperta(MENOS)
        self.assertEqual(self.cfg.pagina_atual, 1)
        self.assertEqual(self.plat.previas, [])
        self.assertEqual(self.plat.apitos, [False, False])

    def test_repeticao_automatica_apita_so_uma_vez(self):
        for _ in range(5):
            self.tecla(BARRA, DOWN)
        self.tecla(BARRA, UP)
        self.assertEqual(self.plat.apitos, [False])

    def test_opcao_de_apitar_desligada(self):
        self.cfg.definir_opcoes({"apitar_fora_do_deck": False})
        self.aperta(BARRA)
        self.assertEqual(self.plat.apitos, [])

    def test_outras_teclas_passam(self):
        self.assertEqual(self.aperta(LETRA_A), (False, False))


class ModoDeck(Base):
    numlock = False

    def test_numero_executa_acao_e_nao_digita(self):
        self.cfg.definir_tecla(1, "5", "Colar", None, MACRO)
        self.assertEqual(self.aperta(NUM5_DECK), (True, True))
        self.assertEqual(self.plat.executadas, [ATALHO_OK])

    def test_repeticao_executa_uma_vez(self):
        self.cfg.definir_tecla(1, "5", "", None, MACRO)
        for _ in range(4):
            self.assertTrue(self.tecla(NUM5_DECK, DOWN))
        self.tecla(NUM5_DECK, UP)
        self.assertEqual(len(self.plat.executadas), 1)

    def test_tecla_sem_funcao_mostra_aviso_e_nao_executa(self):
        self.assertTrue(self.tecla(NUM5_DECK, DOWN))
        self.assertEqual(self.plat.executadas, [])
        self.assertIn("Sem função", self.plat.toasts[-1][1][0])
        self.assertEqual(self.plat.previas, [])

    def test_home_de_verdade_nao_e_confundido_com_7(self):
        self.cfg.definir_tecla(1, "7", "", None, MACRO)
        self.assertEqual(self.aperta(HOME_REAL), (False, False))
        self.assertEqual(self.plat.executadas, [])

    def test_asterisco_avanca_e_barra_volta_mostrando_a_previa(self):
        self.cfg.definir_tecla(2, "1", "Abrir", None, [{"tipo": "abrir", "caminho": r"C:\x\a.py"}])
        self.assertEqual(self.aperta(ASTERISCO), (True, True))
        self.assertEqual(self.cfg.pagina_atual, 2)
        pagina, itens, segundos, alternar = self.plat.previas[-1]
        self.assertEqual((pagina, alternar), (2, False))
        self.assertEqual(len(itens), 10)
        self.assertEqual([i["titulo"] for i in itens if i["tecla"] == "1"], ["Abrir"])
        self.assertEqual(self.aperta(BARRA), (True, True))
        self.assertEqual(self.cfg.pagina_atual, 1)
        self.assertEqual(self.plat.previas[-1][0], 1)
        self.assertEqual(self.plat.apitos, [])

    def test_barra_na_primeira_pagina_apita(self):
        self.assertTrue(self.tecla(BARRA, DOWN))
        self.tecla(BARRA, UP)
        self.assertEqual(self.cfg.pagina_atual, 1)
        self.assertEqual(self.plat.apitos, [False])

    def test_paginas_infinitas(self):
        for _ in range(250):
            self.aperta(ASTERISCO)
        self.assertEqual(self.cfg.pagina_atual, 251)
        self.assertEqual(self.cfg.paginas_configuradas(), [])  # páginas vazias não ocupam espaço

    def test_previa_ao_trocar_pagina_pode_ser_desligada(self):
        self.cfg.definir_opcoes({"popup_ao_trocar_pagina": False})
        self.aperta(ASTERISCO)
        self.assertEqual(self.plat.previas, [])

    def test_menos_abre_a_previa_grande_e_de_novo_fecha(self):
        self.cfg.definir_tecla(1, "9", "Nove", None, MACRO)
        self.assertEqual(self.aperta(MENOS), (True, True))
        pagina, itens, segundos, alternar = self.plat.previas[-1]
        self.assertEqual((pagina, segundos, alternar), (1, 10, True))
        self.assertEqual({i["tecla"]: i["titulo"] for i in itens}["9"], "Nove")
        self.assertTrue(self.plat.previa_aberta)
        self.aperta(MENOS)
        self.assertEqual(self.plat.previas[-1], ("fechou", 1))
        self.assertFalse(self.plat.previa_aberta)

    def test_previa_mostra_o_nome_da_pagina(self):
        self.cfg.renomear_pagina(1, "ECAC")
        self.aperta(MENOS)
        self.assertEqual(self.plat.nomes_previa[-1], "ECAC")
        self.aperta(MENOS)
        self.cfg.renomear_pagina(2, "Programas Python")
        self.aperta(ASTERISCO)
        self.assertEqual(self.plat.nomes_previa[-1], "Programas Python")

    def test_previa_aberta_acompanha_a_troca_de_pagina_mesmo_com_opcao_desligada(self):
        self.cfg.definir_opcoes({"popup_ao_trocar_pagina": False, "perfil_segundos": 20})
        self.aperta(MENOS)
        self.aperta(ASTERISCO)
        pagina, _itens, segundos, _alt = self.plat.previas[-1]
        self.assertEqual((pagina, segundos), (2, 20))

    def test_apertar_tecla_do_deck_fecha_a_previa(self):
        self.cfg.definir_tecla(1, "5", "", None, MACRO)
        self.aperta(MENOS)
        self.aperta(NUM5_DECK)
        self.assertFalse(self.plat.previa_aberta)

    def test_acao_executa_na_pagina_atual(self):
        self.cfg.definir_tecla(2, "7", "", None, MACRO)
        self.aperta(ASTERISCO)
        self.aperta(NUM7_DECK)
        self.assertEqual(len(self.plat.executadas), 1)

    def test_teclas_injetadas_sao_ignoradas(self):
        self.cfg.definir_tecla(1, "5", "", None, MACRO)
        self.assertFalse(self.tecla(NUM5_DECK, DOWN, extra=INJ))
        self.assertEqual(self.plat.executadas, [])

    def test_erro_na_acao_aparece_no_modo_sincrono(self):
        def quebra(_):
            raise RuntimeError("falhou")
        self.plat.executar = quebra
        self.cfg.definir_tecla(1, "5", "", None, MACRO)
        with self.assertRaises(RuntimeError):  # no modo síncrono o erro aparece; na thread vira aviso
            self.aperta(NUM5_DECK)


class Fluxos(Base):
    numlock = False

    def test_blocos_rodam_na_ordem_definida(self):
        fluxo = [{"tipo": "abrir", "caminho": "chrome", "argumentos": ""},
                 {"tipo": "pausa", "segundos": 0.05},
                 {"tipo": "clique", "x": 1, "y": 2},
                 {"tipo": "clique", "x": 3, "y": 4},
                 ATALHO]
        self.cfg.definir_tecla(1, "5", "", None, fluxo)
        t0 = time.monotonic()
        self.aperta(NUM5_DECK)
        self.assertGreaterEqual(time.monotonic() - t0, 0.05)
        self.assertEqual([b["tipo"] for b in self.plat.executadas], ["abrir", "clique", "clique", "atalho"])
        self.assertEqual([(b["x"], b["y"]) for b in self.plat.executadas[1:3]], [(1, 2), (3, 4)])

    def test_tecla_chama_tecla_de_outra_pagina(self):
        self.cfg.definir_tecla(7, "3", "Alvo", None, [{"tipo": "texto", "texto": "oi"}, ATALHO])
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "site", "url": "google.com"}, chamar(7, "3"),
                                                   {"tipo": "clique", "x": 9, "y": 9}])
        self.aperta(NUM5_DECK)
        self.assertEqual([b["tipo"] for b in self.plat.executadas], ["site", "texto", "atalho", "clique"])
        self.assertEqual(self.cfg.pagina_atual, 1)

    def test_chamadas_em_cadeia(self):
        self.cfg.definir_tecla(3, "1", "", None, [ATALHO])
        self.cfg.definir_tecla(2, "1", "", None, [chamar(3, "1"), chamar(3, "1")])
        self.cfg.definir_tecla(1, "5", "", None, [chamar(2, "1")])
        self.aperta(NUM5_DECK)
        self.assertEqual(len(self.plat.executadas), 2)

    def test_chamar_tecla_sem_funcao_avisa(self):
        self.cfg.definir_tecla(1, "5", "", None, [chamar(9, "9")])
        with self.assertRaises(Exception) as ctx:    # na thread real isto vira apito + aviso
            self.aperta(NUM5_DECK)
        self.assertIn("sem função", str(ctx.exception))

    def test_ciclo_que_escapou_da_validacao_e_contido_na_execucao(self):
        # edição manual do config.json: A chama B, B chama A
        self.cfg._dados["paginas"] = {
            "1": {"1": {"nome": "", "imagem": None, "fluxo": [chamar(2, "1")]}},
            "2": {"1": {"nome": "", "imagem": None, "fluxo": [ATALHO, chamar(1, "1")]}}}
        with self.assertRaisesRegex(Exception, "ciclo"):
            self.n._tecla_deck("1")
        self.assertEqual(len(self.plat.executadas), 1)   # parou na primeira volta

    def test_ir_pagina_muda_a_pagina_e_mostra_previa(self):
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "ir_pagina", "numero": 7}, ATALHO])
        self.aperta(NUM5_DECK)
        self.assertEqual(self.cfg.pagina_atual, 7)
        self.assertEqual(self.plat.previas[-1][0], 7)
        self.assertEqual(len(self.plat.executadas), 1)

    def test_aviso_mostra_texto(self):
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "aviso", "texto": "Feito!", "posicao": "baixo_dir", "tamanho": "medio"}])
        self.aperta(NUM5_DECK)
        self.assertEqual(len(self.plat.executadas), 1)
        b = self.plat.executadas[0]
        self.assertEqual((b["tipo"], b["canal"], b["texto"], b["posicao"], b["tamanho"]), ("aviso", "popup", "Feito!", "baixo_dir", "medio"))

    def test_testar_rascunho(self):
        self.n.testar([{"tipo": "clique", "x": 1, "y": 2}, {"tipo": "pausa", "segundos": 0.05}, ATALHO])
        self.assertEqual([b["tipo"] for b in self.plat.executadas], ["clique", "atalho"])
        with self.assertRaises(Exception):
            self.n.testar([{"tipo": None}])
        self.n.testar([])   # fluxo vazio não faz nada
        self.assertEqual(len(self.plat.executadas), 2)


class FluxosEmThreads(unittest.TestCase):
    """Executa com as threads reais: pausa não pode travar o teclado e Num Lock cancela."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(self.tmp.name)
        self.plat = PlataformaFalsa(numlock=False)
        self.n = NucleoDeck(self.cfg, self.plat)
        self.n.iniciar()

    def tearDown(self):
        self.n.encerrar()
        time.sleep(0.3)
        self.tmp.cleanup()

    def esperar(self, condicao, limite=3.0):
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            if condicao():
                return True
            time.sleep(0.01)
        return False

    def test_hook_responde_na_hora_mesmo_com_pausa_longa(self):
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "pausa", "segundos": 5}, ATALHO])
        t0 = time.monotonic()
        self.assertTrue(self.n.evento(True, *NUM5_DECK))
        self.assertLess(time.monotonic() - t0, 0.05)

    def test_navegar_enquanto_o_fluxo_espera(self):
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "pausa", "segundos": 5}, ATALHO])
        self.n.evento(True, *NUM5_DECK)
        self.n.evento(False, *NUM5_DECK)
        self.n.evento(True, *ASTERISCO)
        self.assertTrue(self.esperar(lambda: self.cfg.pagina_atual == 2))  # a fila rápida não ficou presa

    def test_numlock_cancela_fluxo_em_andamento(self):
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "pausa", "segundos": 0.6}, ATALHO])
        self.n.evento(True, *NUM5_DECK)
        self.n.evento(False, *NUM5_DECK)
        self.assertTrue(self.esperar(lambda: self.n._fluxo_ativo))
        self.plat.numlock = True
        self.n.evento(True, *NUMLOCK)
        self.n.evento(False, *NUMLOCK)
        self.assertTrue(self.esperar(lambda: any(t[0] == "Fluxo cancelado" for t in self.plat.toasts)))
        time.sleep(0.8)
        self.assertEqual(self.plat.executadas, [])
        self.assertFalse(self.n._fluxo_ativo)

    def test_numlock_limpa_fila_de_fluxos_esperando(self):
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "pausa", "segundos": 0.5}, ATALHO])
        self.cfg.definir_tecla(1, "6", "", None, [{"tipo": "aviso", "texto": "nao deve aparecer"}])
        self.n.evento(True, *NUM5_DECK)
        self.n.evento(True, *(0x66, 0x4D, 0))   # tecla 6 (VK não importa, o scan é que vale)
        self.assertTrue(self.esperar(lambda: self.n._fluxo_ativo))
        self.n.evento(True, *NUMLOCK)
        time.sleep(1.0)
        self.assertEqual(self.plat.executadas, [])
        self.assertFalse(any(b["tipo"] == "aviso" for b in self.plat.executadas))

    def test_fluxo_depois_do_cancelamento_funciona_normal(self):
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "pausa", "segundos": 0.3}, ATALHO])
        self.n.evento(True, *NUM5_DECK)
        self.n.evento(False, *NUM5_DECK)
        self.assertTrue(self.esperar(lambda: self.n._fluxo_ativo))
        self.n.evento(True, *NUMLOCK)
        self.n.evento(False, *NUMLOCK)
        time.sleep(0.5)
        self.plat.numlock = False
        self.n._sincronizar()
        self.n.evento(True, *NUM5_DECK)
        self.assertTrue(self.esperar(lambda: len(self.plat.executadas) == 1, 3))

    def test_erro_em_bloco_vira_apito_e_aviso_sem_derrubar_a_thread(self):
        def quebra(_b):
            raise RuntimeError("arquivo sumiu")
        self.plat.executar = quebra
        self.cfg.definir_tecla(1, "5", "", None, MACRO)
        self.n.evento(True, *NUM5_DECK)
        self.assertTrue(self.esperar(lambda: self.plat.apitos == [False]))
        self.assertEqual(self.plat.toasts[-1][0], "Não funcionou")
        self.plat.executar = lambda b: self.plat.executadas.append(b)
        self.n.evento(False, *NUM5_DECK)
        self.n.evento(True, *NUM5_DECK)
        self.assertTrue(self.esperar(lambda: len(self.plat.executadas) == 1))


JANELA = {"tipo": "janela", "texto": "Excel"}
ESPERA_PAGINA = {"tipo": "pagina", "alvo": "seletor", "valor": "#pronto"}


def esperar(cond, ate="aparecer", limite=2, ao_expirar="parar"):
    return {"tipo": "pausa", "modo": "condicao", "condicao": cond, "ate": ate, "limite": limite, "ao_expirar": ao_expirar}


class FluxosAvancados(Base):
    numlock = False

    def rodar(self, fluxo):
        self.cfg.definir_tecla(1, "5", "", None, fluxo)
        self.aperta(NUM5_DECK)

    def tipos(self):
        return [b["tipo"] for b in self.plat.executadas]

    # -- repetir / se
    def test_repetir_os_proximos_blocos(self):
        self.rodar([{"tipo": "repetir", "vezes": 3, "blocos": 2}, {"tipo": "clique", "x": 1, "y": 1}, ATALHO,
                    {"tipo": "texto", "texto": "fim"}])
        self.assertEqual(self.tipos(), ["clique", "atalho"] * 3 + ["texto"])

    def test_repetir_dentro_de_repetir(self):
        self.rodar([{"tipo": "repetir", "vezes": 2, "blocos": 3}, {"tipo": "repetir", "vezes": 3, "blocos": 1},
                    {"tipo": "clique", "x": 1, "y": 1}, ATALHO])
        self.assertEqual(self.tipos(), (["clique"] * 3 + ["atalho"]) * 2)

    def test_se_entao_e_senao(self):
        fluxo = [{"tipo": "se", "condicao": JANELA, "entao": 1, "senao": 2},
                 {"tipo": "texto", "texto": "ENTAO"},
                 {"tipo": "texto", "texto": "SENAO1"}, {"tipo": "texto", "texto": "SENAO2"},
                 {"tipo": "texto", "texto": "depois"}]
        self.plat.condicoes = [True]
        self.rodar(fluxo)
        self.assertEqual([b["texto"] for b in self.plat.executadas], ["ENTAO", "depois"])
        self.plat.executadas.clear()
        self.plat.condicoes = [False]
        self.aperta(NUM5_DECK)
        self.assertEqual([b["texto"] for b in self.plat.executadas], ["SENAO1", "SENAO2", "depois"])

    def test_se_negado_e_sem_senao(self):
        fluxo = [{"tipo": "se", "condicao": JANELA, "negar": True, "entao": 1}, ATALHO, {"tipo": "texto", "texto": "depois"}]
        self.plat.condicoes = [True]       # condição verdadeira + "NÃO" = pula
        self.rodar(fluxo)
        self.assertEqual(self.tipos(), ["texto"])
        self.plat.executadas.clear()
        self.plat.condicoes = [False]
        self.aperta(NUM5_DECK)
        self.assertEqual(self.tipos(), ["atalho", "texto"])

    def test_se_dentro_de_repetir_reavalia_a_cada_volta(self):
        self.plat.condicoes = [True, False, True]
        self.rodar([{"tipo": "repetir", "vezes": 3, "blocos": 3},
                    {"tipo": "se", "condicao": JANELA, "entao": 1, "senao": 0}, {"tipo": "texto", "texto": "T"},
                    {"tipo": "clique", "x": 1, "y": 1}])
        self.assertEqual(self.tipos(), ["texto", "clique", "clique", "texto", "clique"])

    # -- esperar
    def test_esperar_ate_aparecer(self):
        self.plat.condicoes = [False, False, True]
        t0 = time.monotonic()
        self.rodar([esperar(JANELA), ATALHO])
        self.assertGreaterEqual(time.monotonic() - t0, 0.45)       # 2 conferências falhas, de 0,25 s cada
        self.assertEqual(self.tipos(), ["atalho"])
        self.assertEqual(len(self.plat.avaliadas), 3)

    def test_esperar_ate_sumir(self):
        self.plat.condicoes = [True, True, False]
        self.rodar([esperar(JANELA, ate="sumir"), ATALHO])
        self.assertEqual(self.tipos(), ["atalho"])

    def test_tempo_esgotado_para_o_fluxo_com_aviso(self):
        self.plat.condicoes = [False]
        with self.assertRaisesRegex(Exception, "Tempo esgotado"):    # na thread real vira apito + aviso
            self.rodar([esperar(JANELA, limite=1), ATALHO])
        self.assertEqual(self.tipos(), [])

    def test_tempo_esgotado_pode_continuar(self):
        self.plat.condicoes = [False]
        self.rodar([esperar(JANELA, limite=1, ao_expirar="continuar"), ATALHO])
        self.assertEqual(self.tipos(), ["atalho"])

    def test_condicao_recebe_variaveis(self):
        self.cfg.aplicar_variavel("n", "definir", 7)
        self.plat.condicoes = [True]
        self.rodar([esperar({"tipo": "janela", "modo": "ativa", "texto": "Pedido {n}"}), ATALHO])
        self.assertEqual(self.plat.avaliadas[0]["texto"], "Pedido 7")

    # -- variáveis
    def test_contador_e_texto_com_variavel(self):
        self.rodar([{"tipo": "variavel", "nome": "pedido", "operacao": "somar", "valor": 1},
                    {"tipo": "texto", "texto": "Pedido {pedido}"}, {"tipo": "aviso", "texto": "Foi o {pedido}"}])
        self.aperta(NUM5_DECK)
        self.assertEqual([b["texto"] for b in self.plat.executadas if b["tipo"] == "texto"], ["Pedido 1", "Pedido 2"])
        self.assertEqual(self.plat.executadas[-1]["texto"], "Foi o 2")
        self.assertEqual(self.cfg.variaveis(), {"pedido": 2})

    def test_variavel_nao_altera_o_que_esta_salvo(self):
        self.rodar([{"tipo": "variavel", "nome": "n", "operacao": "definir", "valor": 9}, {"tipo": "texto", "texto": "{n}"}])
        self.assertEqual(self.cfg.tecla(1, "5")["fluxo"][1]["texto"], "{n}")

    # -- sites e whatsapp
    def test_site_revalida_endereco_depois_das_variaveis(self):
        self.cfg.aplicar_variavel("pg", "definir", 3)
        self.rodar([{"tipo": "site", "url": "exemplo.com/lista?p={pg}", "controlado": True}])
        self.assertEqual(self.plat.executadas[0], {"tipo": "site", "url": "https://exemplo.com/lista?p=3", "controlado": True})

    def test_whatsapp_vira_site(self):
        self.rodar([{"tipo": "whatsapp", "numero": "5575999998888", "mensagem": "Olá, tudo bem? Pedido {n}"}])
        self.assertEqual(self.plat.executadas[0], {"tipo": "site", "controlado": False,
                         "url": "https://wa.me/5575999998888?text=Ol%C3%A1%2C%20tudo%20bem%3F%20Pedido%20%7Bn%7D"})
        self.plat.executadas.clear()
        self.rodar([{"tipo": "whatsapp", "numero": "5575999998888", "mensagem": "", "controlado": True}])
        self.assertEqual(self.plat.executadas[0]["url"], "https://web.whatsapp.com/send?phone=5575999998888")
        self.plat.executadas.clear()
        self.rodar([{"tipo": "whatsapp", "mensagem": "oi"}])
        self.assertEqual(self.plat.executadas[0]["url"], "https://wa.me/?text=oi")

    # -- blocos da página web
    def test_web_clicar_espera_o_elemento_antes(self):
        self.plat.condicoes = [False, True]
        self.rodar([{"tipo": "web_clicar", "seletor": "#enviar", "aba": "whats", "limite": 5}, ATALHO])
        self.assertEqual(self.plat.avaliadas[0], {"tipo": "pagina", "alvo": "seletor", "valor": "#enviar", "aba": "whats"})
        self.assertEqual(self.tipos(), ["web_clicar", "atalho"])

    def test_web_clicar_sem_elemento_para_o_fluxo(self):
        self.plat.condicoes = [False]
        with self.assertRaisesRegex(Exception, "não apareceu"):
            self.rodar([{"tipo": "web_preencher", "seletor": "#x", "texto": "a", "limite": 1}, ATALHO])
        self.assertEqual(self.tipos(), [])

    # -- cancelamento no meio de uma espera
    def test_chamada_dentro_de_grupo(self):
        self.cfg.definir_tecla(7, "7", "", None, [ATALHO])
        self.plat.condicoes = [True]
        self.rodar([{"tipo": "se", "condicao": JANELA, "entao": 1, "senao": 1}, chamar(7, "7"), {"tipo": "texto", "texto": "x"}])
        self.assertEqual(self.tipos(), ["atalho"])


class EsperaEmThreads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(self.tmp.name)
        self.plat = PlataformaFalsa(numlock=False)
        self.plat.condicoes = [False]
        self.n = NucleoDeck(self.cfg, self.plat)
        self.n.iniciar()

    def tearDown(self):
        self.n.encerrar()
        time.sleep(0.3)
        self.tmp.cleanup()

    def test_numlock_cancela_espera_longa(self):
        self.cfg.definir_tecla(1, "5", "", None, [esperar(JANELA, limite=60), ATALHO])
        self.n.evento(True, *NUM5_DECK)
        t0 = time.monotonic()
        while not self.plat.avaliadas and time.monotonic() - t0 < 3:
            time.sleep(0.02)
        self.assertTrue(self.plat.avaliadas)
        self.n.evento(True, *NUMLOCK)
        t0 = time.monotonic()
        while not any(t[0] == "Fluxo cancelado" for t in self.plat.toasts) and time.monotonic() - t0 < 3:
            time.sleep(0.02)
        self.assertTrue(any(t[0] == "Fluxo cancelado" for t in self.plat.toasts))
        time.sleep(0.6)
        self.assertEqual(self.plat.executadas, [])
        n_antes = len(self.plat.avaliadas)
        time.sleep(0.6)
        self.assertEqual(len(self.plat.avaliadas), n_antes)       # parou de conferir a condição


class AlternarModo(Base):
    numlock = True

    def test_numlock_nunca_e_engolido_e_troca_o_modo(self):
        self.assertEqual(self.n.modo(), "padrao")
        self.plat.numlock = False  # o Windows apaga a luz depois do hook
        self.assertEqual(self.aperta(NUMLOCK), (False, False))
        self.assertEqual(self.n.modo(), "deck")
        self.assertEqual(self.plat.toasts[-1][0], "Modo deck")
        self.plat.numlock = True
        self.aperta(NUMLOCK)
        self.assertEqual(self.n.modo(), "padrao")
        self.assertEqual(self.plat.toasts[-1][0], "Modo padrão")

    def test_trocar_modo_com_tecla_segurada_nao_deixa_tecla_presa(self):
        self.tecla(NUM5_PADRAO, DOWN)          # apertada no modo padrão (passou)
        self.plat.numlock = False
        self.aperta(NUMLOCK)
        self.assertFalse(self.tecla(NUM5_DECK, UP))  # soltar tem que passar também

    def test_soltar_tecla_do_deck_depois_de_voltar_ao_padrao_e_engolido(self):
        self.plat.numlock = False
        self.aperta(NUMLOCK)
        self.tecla(NUM5_DECK, DOWN)            # engolida, ação do deck
        self.plat.numlock = True
        self.aperta(NUMLOCK)
        self.assertTrue(self.tecla(NUM5_PADRAO, UP))  # o soltar também é engolido (senão a tecla fica presa)

    def test_aviso_de_modo_pode_ser_desligado(self):
        self.cfg.definir_opcoes({"popup_ao_trocar_modo": False})
        self.plat.numlock = False
        self.aperta(NUMLOCK)
        self.assertEqual(self.plat.toasts, [])

    def test_encerrar_religa_numlock(self):
        self.plat.numlock = False
        self.n.encerrar()
        self.assertTrue(self.plat.numlock)


class GravacaoDeMacro(Base):
    numlock = False

    def gravar_em_thread(self):
        resultado = {}

        def alvo():
            resultado["teclas"] = self.n.gravar_macro(timeout=3)

        t = threading.Thread(target=alvo)
        t.start()
        while not self.n.gravando():
            time.sleep(0.01)
        return t, resultado

    def test_grava_ctrl_v(self):
        t, res = self.gravar_em_thread()
        CTRL, V = (0xA2, 0x1D, 0), (0x56, 0x2F, 0)
        self.assertTrue(self.tecla(CTRL, DOWN))     # durante a gravação as teclas não chegam ao programa
        self.assertTrue(self.tecla(V, DOWN))
        self.assertTrue(self.tecla(V, UP))
        self.assertTrue(self.tecla(CTRL, UP))
        t.join(2)
        self.assertEqual([x["nome"] for x in res["teclas"]], ["Ctrl", "V"])
        self.assertFalse(self.n.gravando())
        self.assertFalse(self.tecla(CTRL, UP))      # depois da gravação volta ao normal

    def test_durante_a_gravacao_o_deck_nao_dispara(self):
        self.cfg.definir_tecla(1, "5", "", None, MACRO)
        t, res = self.gravar_em_thread()
        self.tecla(NUM5_DECK, DOWN)
        self.tecla(NUM5_DECK, UP)
        t.join(2)
        self.assertEqual(self.plat.executadas, [])
        self.assertEqual(len(res["teclas"]), 1)

    def test_cancelar(self):
        t, res = self.gravar_em_thread()
        self.n.cancelar_gravacao()
        t.join(2)
        self.assertIsNone(res["teclas"])

    def test_tempo_esgotado(self):
        self.assertIsNone(self.n.gravar_macro(timeout=0.05))
        self.assertFalse(self.n.gravando())

    def test_numlock_passa_durante_gravacao(self):
        t, _ = self.gravar_em_thread()
        self.assertFalse(self.tecla(NUMLOCK, DOWN))
        self.tecla(NUMLOCK, UP)
        self.n.cancelar_gravacao()
        t.join(2)


PERGUNTA_CAMINHO = {"tipo": "perguntar", "nome": "caminho", "tipo_pergunta": "escolha", "titulo": "Qual caminho?", "lembrar": "sempre",
                    "padrao": "", "opcoes": [{"nome": "Nota antiga", "descricao": "copia"}, {"nome": "CNPJ", "descricao": ""},
                                             {"nome": "Do zero", "descricao": ""}]}


def se_resposta(valor, entao=1, senao=0):
    return {"tipo": "se", "condicao": {"tipo": "resposta", "nome": "caminho", "valor": valor}, "entao": entao, "senao": senao}


def txt(t):
    return {"tipo": "texto", "texto": t}


class PerguntasECaminhos(Base):
    numlock = False

    def rodar(self, fluxo):
        self.cfg.definir_tecla(1, "5", "", None, fluxo)
        self.aperta(NUM5_DECK)

    def textos(self):
        return [b["texto"] for b in self.plat.executadas]

    # se caminho = 1: A, senão (se caminho = 2: B, senão C)
    CAMINHOS = [PERGUNTA_CAMINHO, se_resposta("1", 1, 3), txt("A"), se_resposta("2", 1, 1), txt("B"), txt("C"), txt("fim")]

    def test_cada_resposta_segue_o_seu_caminho(self):
        for resposta, esperado in (("1", ["A", "fim"]), ("2", ["B", "fim"]), ("3", ["C", "fim"])):
            self.plat.executadas.clear()
            self.plat.respostas_prontas = [resposta]
            self.rodar(self.CAMINHOS)
            self.assertEqual(self.textos(), esperado)
        self.assertEqual(self.plat.perguntas[0]["opcoes"][2]["nome"], "Do zero")

    def test_fechar_a_pergunta_cancela_o_fluxo(self):
        self.plat.respostas_prontas = [None]
        self.rodar(self.CAMINHOS)
        self.assertEqual(self.plat.executadas, [])

    def test_resposta_vira_variavel_no_texto(self):
        self.plat.respostas_prontas = ["12.345.678/0001-90"]
        self.plat.condicoes = [True]
        self.rodar([{"tipo": "perguntar", "nome": "cnpj", "tipo_pergunta": "texto", "titulo": "CNPJ de {data}?", "lembrar": "sempre",
                     "padrao": "", "opcoes": []},
                    {"tipo": "web_preencher", "seletor": "#cnpj", "texto": "{cnpj}", "aba": "", "limite": 1}])
        self.assertEqual(self.plat.perguntas[0]["titulo"].startswith("CNPJ de "), True)
        self.assertEqual(self.plat.executadas[-1]["texto"], "12.345.678/0001-90")

    def test_primeira_vez_lembra_e_nao_pergunta_de_novo(self):
        fluxo = [{**PERGUNTA_CAMINHO, "lembrar": "primeira_vez"}, se_resposta("2", 1, 1), txt("dois"), txt("outro")]
        self.plat.respostas_prontas = ["2"]
        self.rodar(fluxo)
        self.aperta(NUM5_DECK)
        self.assertEqual(len(self.plat.perguntas), 1)                  # só perguntou na primeira
        self.assertEqual(self.textos(), ["dois", "dois"])
        self.assertEqual(self.cfg.respostas(), {"caminho": "2"})
        self.cfg.esquecer_respostas("caminho")                          # "esquecer" faz perguntar de novo
        self.plat.respostas_prontas = ["1"]
        self.aperta(NUM5_DECK)
        self.assertEqual(len(self.plat.perguntas), 2)

    def test_resposta_lembrada_sobrevive_ao_reabrir(self):
        self.cfg.guardar_resposta("caminho", "3")
        self.assertEqual(Config(self.tmp.name).respostas(), {"caminho": "3"})

    def test_sempre_pergunta_toda_vez(self):
        self.plat.respostas_prontas = ["1", "2"]
        self.rodar(self.CAMINHOS)
        self.aperta(NUM5_DECK)
        self.assertEqual(self.textos(), ["A", "fim", "B", "fim"])
        self.assertEqual(self.cfg.respostas(), {})


class TextoDeArquivo(Base):
    numlock = False

    def setUp(self):
        super().setUp()
        self.arq = Path(self.tmp.name) / "texto.txt"
        self.arq.write_bytes("Linha 1\r\nAção ñ\r\n".encode("cp1252"))

    def rodar(self, fluxo):
        self.cfg.definir_tecla(1, "5", "", None, fluxo)
        self.aperta(NUM5_DECK)

    def bloco(self, **kw):
        return {"tipo": "colar", "fonte": "arquivo", "arquivo": str(self.arq), "perguntar": "nunca", "chave": "abcd1234", **kw}

    def test_arquivo_fixo(self):
        self.rodar([self.bloco()])
        self.assertEqual(self.plat.executadas, [{"tipo": "colar", "texto": "Linha 1\nAção ñ"}])

    def test_arquivo_com_variavel_no_caminho(self):
        self.cfg.aplicar_variavel("n", "definir", 7)
        self.arq.rename(Path(self.tmp.name) / "texto7.txt")
        self.rodar([self.bloco(arquivo=str(Path(self.tmp.name) / "texto{n}.txt"))])
        self.assertEqual(self.plat.executadas[0]["texto"], "Linha 1\nAção ñ")

    def test_pergunta_o_arquivo_na_primeira_vez_e_depois_lembra(self):
        self.plat.respostas_prontas = [str(self.arq)]
        fluxo = [self.bloco(arquivo="", perguntar="primeira_vez", tipo="texto")]
        self.rodar(fluxo)
        self.aperta(NUM5_DECK)
        self.assertEqual(len(self.plat.perguntas), 1)
        self.assertEqual(self.plat.perguntas[0]["tipo_pergunta"], "arquivo")
        self.assertEqual(self.cfg.respostas(), {"arq_abcd1234": str(self.arq)})
        self.assertEqual([b["tipo"] for b in self.plat.executadas], ["texto", "texto"])

    def test_arquivo_lembrado_que_sumiu_pergunta_de_novo(self):
        self.cfg.guardar_resposta("arq_abcd1234", str(Path(self.tmp.name) / "sumiu.txt"))
        self.plat.respostas_prontas = [str(self.arq)]
        self.rodar([self.bloco(arquivo="", perguntar="primeira_vez")])
        self.assertEqual(self.plat.executadas[0]["texto"], "Linha 1\nAção ñ")
        self.assertEqual(self.cfg.respostas()["arq_abcd1234"], str(self.arq))

    def test_sempre_pergunta_e_nao_guarda(self):
        self.plat.respostas_prontas = [str(self.arq)]
        self.rodar([self.bloco(arquivo="", perguntar="sempre")])
        self.assertEqual(self.cfg.respostas(), {})
        self.assertEqual(len(self.plat.executadas), 1)

    def test_cancelar_a_escolha_do_arquivo(self):
        self.plat.respostas_prontas = [None]
        self.rodar([self.bloco(arquivo="", perguntar="sempre")])
        self.assertEqual(self.plat.executadas, [])

    def test_arquivo_inexistente_ou_vazio_ou_grande_para_digitar(self):
        for conteudo, trecho in ((None, "não encontrado"), (b"  \n", "vazio"), (b"x" * 25000, "máximo para digitar")):
            if conteudo is None:
                self.arq.unlink()
            else:
                self.arq.write_bytes(conteudo)
            self.plat.executadas.clear()
            with self.assertRaisesRegex(Exception, trecho):      # na thread real vira apito + aviso
                self.rodar([self.bloco(tipo="texto")])
            self.tecla(NUM5_DECK, UP)        # o erro interrompeu o "soltar" da tecla
            self.assertEqual(self.plat.executadas, [])


class SiteNaPaginaAtual(Base):
    numlock = False

    def test_pagina_atual_sem_endereco_nao_exige_url(self):
        self.cfg.definir_tecla(1, "5", "", None, [{"tipo": "site", "url": "", "controlado": True, "destino": "atual"}])
        self.aperta(NUM5_DECK)
        self.assertEqual(self.plat.executadas, [{"tipo": "site", "url": "", "controlado": True, "destino": "atual"}])


if __name__ == "__main__":
    unittest.main()
