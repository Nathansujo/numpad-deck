import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime  # noqa: E402

from configuracao import (Config, ErroConfig, aplicar_variaveis, descrever_bloco, descrever_fluxo,  # noqa: E402
                          titulo_curto, validar_bloco, validar_condicao, validar_fluxo)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
ATALHO = {"tipo": "atalho", "teclas": [{"vk": 0xA2, "nome": "Ctrl"}, {"vk": 0x56, "nome": "V"}]}
CLIQUE = {"tipo": "clique", "x": 5, "y": 6}


def chamar(pagina, tecla):
    return {"tipo": "chamar", "pagina": pagina, "tecla": tecla}


class TesteBlocos(unittest.TestCase):
    def test_blocos_validos_normalizados(self):
        self.assertEqual(validar_bloco(CLIQUE), {"tipo": "clique", "alvo": "tela", "x": 5, "y": 6, "botao": "esquerdo", "duplo": False})
        self.assertEqual(validar_bloco({"tipo": "pausa", "segundos": 1.234})["segundos"], 1.23)
        self.assertEqual(validar_bloco({"tipo": "rolagem"}), {"tipo": "rolagem", "direcao": "baixo", "quantidade": 3})
        self.assertEqual(validar_bloco({"tipo": "site", "url": " google.com "})["url"], "https://google.com")
        self.assertEqual(validar_bloco({"tipo": "abrir", "caminho": " chrome ", "argumentos": " https://x.com "}),
                         {"tipo": "abrir", "caminho": "chrome", "argumentos": "https://x.com"})

    def test_blocos_invalidos(self):
        for ruim in [
            {"tipo": None}, {"tipo": "voar"}, "texto", None,
            {"tipo": "atalho", "teclas": []},
            {"tipo": "atalho", "teclas": [{"vk": 999}]},
            {"tipo": "texto", "texto": "   "},
            {"tipo": "texto", "texto": "x" * 2001},
            {"tipo": "clique", "x": "a", "y": 1},
            {"tipo": "clique", "x": True, "y": 1},
            {"tipo": "clique", "x": 1, "y": 1, "botao": "xyz"},
            {"tipo": "mover", "x": 1},
            {"tipo": "rolagem", "direcao": "lado"},
            {"tipo": "rolagem", "quantidade": 0},
            {"tipo": "pausa", "segundos": 0},
            {"tipo": "pausa", "segundos": 601},
            {"tipo": "pausa", "segundos": "2"},
            {"tipo": "abrir", "caminho": "  "},
            {"tipo": "site", "url": ""},
            {"tipo": "site", "url": "javascript:alert(1)"},
            {"tipo": "site", "url": "file:///c:/windows/system.ini"},
            {"tipo": "site", "url": "a b.com"},
            {"tipo": "chamar", "pagina": 0, "tecla": "1"},
            {"tipo": "chamar", "pagina": 1, "tecla": "x"},
            {"tipo": "ir_pagina", "numero": 0},
            {"tipo": "aviso", "texto": ""},
        ]:
            with self.assertRaises(ErroConfig, msg=str(ruim)):
                validar_bloco(ruim)

    def test_fluxo_mensagem_indica_o_bloco(self):
        with self.assertRaisesRegex(ErroConfig, "^Bloco 2:"):
            validar_fluxo([CLIQUE, {"tipo": None}])
        with self.assertRaises(ErroConfig):
            validar_fluxo([CLIQUE] * 41)
        with self.assertRaises(ErroConfig):
            validar_fluxo("nao e lista")

    def test_descricoes(self):
        self.assertEqual(descrever_bloco(validar_bloco(CLIQUE)), "Clique em (5, 6)")
        self.assertEqual(descrever_bloco(validar_bloco({**CLIQUE, "botao": "direito", "duplo": True})),
                         "Duplo clique direito em (5, 6)")
        self.assertEqual(descrever_bloco(validar_bloco(ATALHO)), "Atalho: Ctrl + V")
        self.assertEqual(descrever_bloco(validar_bloco({"tipo": "pausa", "segundos": 0.5})), "Esperar 0,5 s")
        self.assertEqual(descrever_bloco(validar_bloco({"tipo": "abrir", "caminho": r"C:\a\b\x.py"})), "Abrir: x.py")
        self.assertEqual(descrever_bloco(validar_bloco({"tipo": "site", "url": "www.google.com/maps"})),
                         "Abrir site: www.google.com")
        self.assertEqual(descrever_bloco(validar_bloco(chamar(7, "3"))), "Chamar a tecla 3 da página 7")

    def test_descricao_do_fluxo(self):
        self.assertEqual(descrever_fluxo([]), "Sem função")
        self.assertEqual(descrever_fluxo([validar_bloco(ATALHO)]), "Atalho: Ctrl + V")
        fluxo = validar_fluxo([CLIQUE, {"tipo": "pausa", "segundos": 2}, ATALHO])
        self.assertEqual(descrever_fluxo(fluxo), "3 etapas: Clique → Esperar 2 s → Ctrl + V")
        longo = validar_fluxo([{"tipo": "abrir", "caminho": "x" * 60 + ".exe"}] * 10)
        self.assertLessEqual(len(descrever_fluxo(longo)), 160)

    def test_titulo_curto(self):
        self.assertEqual(titulo_curto({"nome": "", "imagem": None, "fluxo": []}), "Livre")
        self.assertEqual(titulo_curto({"nome": "", "imagem": None, "fluxo": [validar_bloco(ATALHO)]}), "Ctrl + V")
        self.assertEqual(titulo_curto({"nome": "", "imagem": None, "fluxo": validar_fluxo([CLIQUE, CLIQUE])}), "2 etapas")
        self.assertEqual(titulo_curto({"nome": "Abrir o Google", "imagem": None, "fluxo": []}), "Abrir o Google")
        self.assertEqual(len(titulo_curto({"nome": "N" * 40, "imagem": None, "fluxo": []})), 24)


class TesteConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_padrao(self):
        self.assertEqual(self.cfg.pagina_atual, 1)
        self.assertEqual(self.cfg.tecla(1, "5"), {"nome": "", "imagem": None, "fluxo": []})
        self.assertTrue(self.cfg.opcoes()["apitar_fora_do_deck"])
        self.assertEqual(self.cfg.opcoes()["perfil_segundos"], 10)

    def test_salva_e_recarrega_fluxo_em_ordem(self):
        self.cfg.definir_tecla(3, "7", "Colar", None, [CLIQUE, {"tipo": "pausa", "segundos": 1}, ATALHO])
        self.cfg.ir_para(3)
        outra = Config(self.tmp.name)
        self.assertEqual(outra.pagina_atual, 3)
        t = outra.tecla(3, "7")
        self.assertEqual(t["nome"], "Colar")
        self.assertEqual([b["tipo"] for b in t["fluxo"]], ["clique", "pausa", "atalho"])
        self.assertEqual(outra.paginas_configuradas(), [3])

    def test_tecla_vazia_remove_pagina(self):
        self.cfg.definir_tecla(2, "1", "x", None, [ATALHO])
        self.cfg.limpar_tecla(2, "1")
        self.assertEqual(self.cfg.paginas_configuradas(), [])

    def test_nome_sem_fluxo_continua_salvo(self):
        self.cfg.definir_tecla(1, "1", "Só um nome", None, [])
        self.assertEqual(self.cfg.tecla(1, "1")["nome"], "Só um nome")

    def test_validacoes_de_tecla(self):
        with self.assertRaises(ErroConfig):
            self.cfg.definir_tecla(0, "1", "", None, [])
        with self.assertRaises(ErroConfig):
            self.cfg.definir_tecla(1, "10", "", None, [])
        with self.assertRaises(ErroConfig):
            self.cfg.definir_tecla(1, "1", "", None, [{"tipo": None}])

    # -- chamadas entre teclas
    def test_chamar_outra_pagina_e_permitido(self):
        self.cfg.definir_tecla(7, "3", "Alvo", None, [ATALHO])
        self.cfg.definir_tecla(1, "1", "", None, [chamar(7, "3")])
        self.assertEqual(self.cfg.tecla(1, "1")["fluxo"][0]["pagina"], 7)

    def test_ciclo_direto_e_indireto_sao_barrados(self):
        with self.assertRaisesRegex(ErroConfig, "Ciclo"):
            self.cfg.definir_tecla(1, "1", "", None, [chamar(1, "1")])
        self.cfg.definir_tecla(2, "2", "", None, [chamar(3, "3")])
        self.cfg.definir_tecla(3, "3", "", None, [chamar(4, "4")])
        with self.assertRaisesRegex(ErroConfig, "pág. 2 tecla 2"):
            self.cfg.definir_tecla(4, "4", "", None, [chamar(2, "2")])
        self.assertEqual(self.cfg.tecla(4, "4")["fluxo"], [])  # nada foi salvo

    def test_dois_chamando_a_mesma_nao_e_ciclo(self):
        self.cfg.definir_tecla(5, "5", "", None, [ATALHO])
        self.cfg.definir_tecla(1, "1", "", None, [chamar(5, "5"), chamar(5, "5")])
        self.cfg.definir_tecla(1, "2", "", None, [chamar(1, "1"), chamar(5, "5")])

    # -- imagens
    def test_imagens(self):
        with self.assertRaises(ErroConfig):
            self.cfg.salvar_imagem(b"isso nao e imagem")
        nome = self.cfg.salvar_imagem(PNG)
        self.assertTrue(self.cfg.caminho_imagem(nome).is_file())
        self.cfg.definir_tecla(1, "1", "", nome, [])
        self.assertEqual(self.cfg.tecla(1, "1")["imagem"], nome)
        self.cfg.definir_tecla(1, "1", "", None, [ATALHO])  # trocar/remover apaga o arquivo antigo
        self.assertIsNone(self.cfg.caminho_imagem(nome))
        with self.assertRaises(ErroConfig):
            self.cfg.definir_tecla(1, "1", "", "../../etc/passwd", [ATALHO])
        self.assertIsNone(self.cfg.caminho_imagem("../config.json"))

    def test_orfas_na_partida(self):
        nome = self.cfg.salvar_imagem(PNG)
        self.cfg.limpar_imagens_orfas()
        self.assertIsNone(self.cfg.caminho_imagem(nome))

    # -- prévia grande
    def test_itens_da_previa(self):
        nome = self.cfg.salvar_imagem(PNG)
        self.cfg.definir_tecla(2, "7", "Google", nome, [{"tipo": "site", "url": "google.com"}])
        self.cfg.definir_tecla(2, "0", "", None, [CLIQUE, ATALHO])
        itens = self.cfg.itens_previa(2)
        self.assertEqual([i["tecla"] for i in itens], ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0"])
        por = {i["tecla"]: i for i in itens}
        self.assertEqual(por["7"]["titulo"], "Google")
        self.assertTrue(por["7"]["imagem"].endswith(nome))
        self.assertFalse(por["7"]["vazio"])
        self.assertEqual(por["0"]["titulo"], "2 etapas")
        self.assertEqual((por["5"]["titulo"], por["5"]["vazio"], por["5"]["imagem"]), ("Livre", True, None))

    def test_info_tecla_e_snapshot(self):
        self.cfg.definir_tecla(1, "5", "Colar", None, [ATALHO, CLIQUE])
        info = self.cfg.info_tecla(1, "5")
        self.assertEqual((info["nome"], info["etapas"]), ("Colar", 2))
        self.assertTrue(info["descricao"].startswith("2 etapas"))
        s = self.cfg.snapshot()
        self.assertEqual(s["teclas"]["5"]["fluxo"][0]["descricao"], "Atalho: Ctrl + V")
        self.assertEqual(s["teclas"]["1"]["descricao"], "Sem função")
        self.assertEqual(s["teclas"]["1"]["etapas"], 0)

    # -- arquivo
    def test_migra_formato_antigo(self):
        antigo = {"pagina_atual": 2, "paginas": {"2": {
            "5": {"nome": "Colar", "acao": {"tipo": "macro", "teclas": [{"vk": 162, "nome": "Ctrl"}, {"vk": 86, "nome": "V"}]}},
            "6": {"nome": "", "acao": {"tipo": "clique", "x": 1, "y": 2, "botao": "direito", "duplo": False}},
            "7": {"nome": "", "acao": {"tipo": "script", "caminho": r"C:\a\b.py"}},
            "8": {"nome": "sem acao", "acao": {"tipo": "nenhuma"}}}}}
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(antigo), encoding="utf-8")
        nova = Config(self.tmp.name)
        self.assertEqual(nova.tecla(2, "5")["fluxo"][0]["tipo"], "atalho")
        self.assertEqual(nova.tecla(2, "6")["fluxo"][0]["botao"], "direito")
        self.assertEqual(nova.tecla(2, "7")["fluxo"][0], {"tipo": "abrir", "caminho": r"C:\a\b.py", "argumentos": ""})
        self.assertEqual(nova.tecla(2, "8"), {"nome": "sem acao", "imagem": None, "fluxo": []})

    def test_arquivo_corrompido(self):
        (Path(self.tmp.name) / "config.json").write_text("{ não é json", encoding="utf-8")
        nova = Config(self.tmp.name)
        self.assertEqual(nova.pagina_atual, 1)
        self.assertTrue((Path(self.tmp.name) / "config.corrompido.json").exists())

    def test_arquivo_com_lixo_e_saneado(self):
        bruto = {"pagina_atual": -4,
                 "opcoes": {"porta": 80, "apitar_fora_do_deck": "sim", "perfil_segundos": 9999},
                 "paginas": {"2": {"5": {"nome": "ok", "fluxo": [{"tipo": "voar"}]}, "99": {},
                                   "6": {"nome": "", "fluxo": "x"}}, "x": {}}}
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(bruto), encoding="utf-8")
        nova = Config(self.tmp.name)
        self.assertEqual(nova.pagina_atual, 1)
        self.assertEqual(nova.opcoes()["porta"], 5077)
        self.assertEqual(nova.opcoes()["perfil_segundos"], 10)
        self.assertTrue(nova.opcoes()["apitar_fora_do_deck"])
        self.assertEqual(nova.paginas_configuradas(), [])

    def test_opcoes(self):
        self.cfg.definir_opcoes({"apitar_fora_do_deck": False, "porta": 1234, "inventada": True, "perfil_segundos": 30})
        self.assertFalse(self.cfg.opcoes()["apitar_fora_do_deck"])
        self.assertEqual(self.cfg.opcoes()["porta"], 5077)  # porta não muda pelo painel
        self.assertEqual(self.cfg.opcoes()["perfil_segundos"], 30)
        for ruim in ({"popup_ao_trocar_modo": "talvez"}, {"perfil_segundos": 1}, {"perfil_segundos": "5"}):
            with self.assertRaises(ErroConfig):
                self.cfg.definir_opcoes(ruim)


JANELA = {"tipo": "janela", "texto": "Excel"}
PIXEL = {"tipo": "pixel", "x": 10, "y": 20, "cor": "#00FF00"}
PAGINA = {"tipo": "pagina", "alvo": "seletor", "valor": "#enviar"}
PAUSA = {"tipo": "pausa", "segundos": 1}


class TesteNovosBlocos(unittest.TestCase):
    def test_condicoes(self):
        self.assertEqual(validar_condicao(JANELA), {"tipo": "janela", "modo": "ativa", "texto": "Excel"})
        self.assertEqual(validar_condicao(PIXEL), {"tipo": "pixel", "x": 10, "y": 20, "cor": "#00ff00", "tolerancia": 24})
        self.assertEqual(validar_condicao(PAGINA)["aba"], "")
        for ruim in [None, {}, {"tipo": "janela", "texto": " "}, {"tipo": "janela", "texto": "x", "modo": "voando"},
                     {"tipo": "pixel", "x": 1, "y": 2, "cor": "verde"}, {"tipo": "pixel", "x": 1, "y": 2, "cor": "#00ff00", "tolerancia": 300},
                     {"tipo": "pagina", "valor": ""}, {"tipo": "pagina", "alvo": "xyz", "valor": "a"}]:
            with self.assertRaises(ErroConfig, msg=str(ruim)):
                validar_condicao(ruim)

    def test_esperar_condicao(self):
        b = validar_bloco({"tipo": "pausa", "modo": "condicao", "condicao": PAGINA})
        self.assertEqual((b["ate"], b["limite"], b["ao_expirar"]), ("aparecer", 30, "parar"))
        self.assertEqual(descrever_bloco(b), "Esperar aparecer: elemento #enviar na página (máx. 30 s)")
        self.assertEqual(descrever_bloco(validar_bloco({**b, "ate": "sumir", "condicao": JANELA})),
                         'Esperar sumir: janela ativa com "Excel" (máx. 30 s)')
        self.assertEqual(validar_bloco(PAUSA)["modo"], "tempo")   # formato antigo continua valendo
        for ruim in [{"tipo": "pausa", "modo": "condicao"}, {"tipo": "pausa", "modo": "condicao", "condicao": JANELA, "ate": "nunca"},
                     {"tipo": "pausa", "modo": "condicao", "condicao": JANELA, "limite": 0},
                     {"tipo": "pausa", "modo": "condicao", "condicao": JANELA, "ao_expirar": "explodir"},
                     {"tipo": "pausa", "modo": "magia"}]:
            with self.assertRaises(ErroConfig, msg=str(ruim)):
                validar_bloco(ruim)

    def test_repetir_e_se(self):
        self.assertEqual(validar_bloco({"tipo": "repetir", "vezes": 3, "blocos": 2}), {"tipo": "repetir", "vezes": 3, "blocos": 2})
        se = validar_bloco({"tipo": "se", "condicao": JANELA, "entao": 2, "senao": 1})
        self.assertEqual((se["entao"], se["senao"], se["negar"]), (2, 1, False))
        self.assertIn("senão os 1 seguintes", descrever_bloco(se))
        for ruim in [{"tipo": "repetir", "vezes": 0, "blocos": 1}, {"tipo": "repetir", "vezes": 1001, "blocos": 1},
                     {"tipo": "repetir", "vezes": 2, "blocos": 0}, {"tipo": "se", "condicao": JANELA, "entao": 0}]:
            with self.assertRaises(ErroConfig, msg=str(ruim)):
                validar_bloco(ruim)

    def test_grupos_nao_passam_do_fim_nem_da_borda(self):
        rep = lambda v, n: {"tipo": "repetir", "vezes": v, "blocos": n}   # noqa: E731
        validar_fluxo([rep(2, 2), CLIQUE, CLIQUE, CLIQUE])
        with self.assertRaisesRegex(ErroConfig, "Bloco 1: o grupo passa do fim"):
            validar_fluxo([rep(2, 3), CLIQUE, CLIQUE])
        with self.assertRaisesRegex(ErroConfig, "Bloco 2: o grupo dele passa da borda"):
            validar_fluxo([rep(2, 2), rep(2, 2), CLIQUE, CLIQUE])        # o interno sai do externo
        validar_fluxo([rep(2, 3), rep(2, 1), CLIQUE, CLIQUE])            # aninhado certinho
        se = {"tipo": "se", "condicao": JANELA, "entao": 1, "senao": 1}
        validar_fluxo([se, CLIQUE, CLIQUE])
        with self.assertRaisesRegex(ErroConfig, "Bloco 2"):
            validar_fluxo([se, rep(2, 1), CLIQUE])      # repetir dentro do "então" invade o "senão"
        with self.assertRaisesRegex(ErroConfig, "Bloco 1: o grupo passa do fim"):
            validar_fluxo([se, CLIQUE])

    def test_variaveis_e_texto(self):
        self.assertEqual(validar_bloco({"tipo": "variavel", "nome": " Pedido ", "operacao": "somar"})["nome"], "pedido")
        self.assertEqual(validar_bloco({"tipo": "variavel", "nome": "n", "operacao": "zerar", "valor": 9})["valor"], 0)
        for ruim in [{"tipo": "variavel", "nome": "com espaco"}, {"tipo": "variavel", "nome": "data"},
                     {"tipo": "variavel", "nome": "1a"}, {"tipo": "variavel", "nome": "a", "operacao": "dividir"},
                     {"tipo": "variavel", "nome": "a", "valor": 1.5}]:
            with self.assertRaises(ErroConfig, msg=str(ruim)):
                validar_bloco(ruim)
        agora = datetime(2026, 10, 18, 9, 5)
        self.assertEqual(aplicar_variaveis("Pedido {n} em {data} às {hora} {desconhecida} {}", {"n": 7}, agora),
                         "Pedido 7 em 18/10/2026 às 09:05 {desconhecida} {}")
        self.assertEqual(aplicar_variaveis("sem chaves", {"n": 1}), "sem chaves")

    def test_outros_blocos(self):
        self.assertEqual(validar_bloco({"tipo": "colar", "texto": "Olá\nmundo"})["texto"], "Olá\nmundo")
        self.assertEqual(validar_bloco({"tipo": "midia", "acao": "mudo"}), {"tipo": "midia", "acao": "mudo", "vezes": 1})
        self.assertEqual(validar_bloco({"tipo": "captura"}), {"tipo": "captura", "tela": "todas"})
        self.assertEqual(validar_bloco({"tipo": "sistema", "acao": "bloquear"})["acao"], "bloquear")
        self.assertEqual(validar_bloco({"tipo": "comando", "comando": " Get-Date "}),
                         {"tipo": "comando", "shell": "powershell", "comando": "Get-Date", "esperar": False})
        self.assertEqual(validar_bloco({"tipo": "site", "url": "x.com", "controlado": True})["controlado"], True)
        w = validar_bloco({"tipo": "whatsapp", "numero": "+55 (75) 99999-8888", "mensagem": "Oi"})
        self.assertEqual(w["numero"], "5575999998888")
        self.assertEqual(validar_bloco({"tipo": "web_clicar", "seletor": "#a"})["limite"], 10)
        self.assertEqual(validar_bloco({"tipo": "web_preencher", "seletor": "#a"})["texto"], "")
        for ruim in [{"tipo": "colar", "texto": ""}, {"tipo": "midia", "acao": "explodir"}, {"tipo": "captura", "tela": "lua"},
                     {"tipo": "sistema", "acao": "desligar"}, {"tipo": "comando", "comando": ""},
                     {"tipo": "comando", "comando": "x", "shell": "bash"}, {"tipo": "whatsapp"},
                     {"tipo": "whatsapp", "numero": "abc", "mensagem": "x"}, {"tipo": "whatsapp", "numero": "123"},
                     {"tipo": "web_clicar", "seletor": " "}, {"tipo": "web_clicar", "seletor": "a", "limite": 301}]:
            with self.assertRaises(ErroConfig, msg=str(ruim)):
                validar_bloco(ruim)

    def test_descricoes_novas(self):
        d = lambda b: descrever_bloco(validar_bloco(b))   # noqa: E731
        self.assertEqual(d({"tipo": "midia", "acao": "volume_mais", "vezes": 5}), "Volume + (5x)")
        self.assertEqual(d({"tipo": "variavel", "nome": "n", "operacao": "somar", "valor": 2}), "Somar 2 a {n}")
        self.assertEqual(d({"tipo": "variavel", "nome": "n", "operacao": "zerar"}), "Zerar {n}")
        self.assertEqual(d({"tipo": "comando", "shell": "cmd", "comando": "dir"}), "CMD: dir")
        self.assertEqual(d({"tipo": "web_clicar", "seletor": "#ok"}), "Clicar na página: #ok")
        self.assertTrue(d({"tipo": "se", "condicao": PIXEL, "negar": True, "entao": 2}).startswith("Se NÃO cor #00ff00"))
        self.assertEqual(descrever_fluxo(validar_fluxo([{"tipo": "repetir", "vezes": 3, "blocos": 1}, CLIQUE])),
                         "2 etapas: Repetir 3x → Clique")


class TesteVariaveisNoArquivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_contador_persiste(self):
        self.assertEqual(self.cfg.aplicar_variavel("pedido", "somar", 1), 1)
        self.assertEqual(self.cfg.aplicar_variavel("pedido", "somar", 4), 5)
        self.assertEqual(Config(self.tmp.name).variaveis(), {"pedido": 5})
        self.assertEqual(self.cfg.aplicar_variavel("pedido", "definir", 100), 100)
        self.assertEqual(self.cfg.aplicar_variavel("pedido", "zerar", 0), 0)
        self.assertEqual(self.cfg.snapshot()["variaveis"], {"pedido": 0})

    def test_arquivo_com_variaveis_ruins(self):
        bruto = {"variaveis": {"ok": 3, "Maiuscula": 1, "x": "texto", "y": True, "z": 10**12}}
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(bruto), encoding="utf-8")
        self.assertEqual(Config(self.tmp.name).variaveis(), {"ok": 3})

    def test_chamada_dentro_de_grupo_conta_para_ciclo(self):
        se = {"tipo": "se", "condicao": JANELA, "entao": 1, "senao": 0}
        self.cfg.definir_tecla(2, "2", "", None, [se, chamar(3, "3")])
        with self.assertRaisesRegex(ErroConfig, "Ciclo"):
            self.cfg.definir_tecla(3, "3", "", None, [chamar(2, "2")])

class TestePaginasNomeadas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_nova_pagina_e_o_proximo_numero_que_existe(self):
        self.assertEqual(self.cfg.criar_pagina(), 2)
        self.assertEqual(self.cfg.pagina_atual, 2)
        self.assertEqual(self.cfg.criar_pagina(), 3)
        self.cfg.definir_tecla(10, "1", "x", None, [CLIQUE])
        self.assertEqual(self.cfg.criar_pagina(), 11)     # depois da maior que existe
        self.assertEqual([p["numero"] for p in self.cfg.lista_paginas()], [1, 2, 3, 10, 11])

    def test_renomear_e_apagar_nome(self):
        self.cfg.criar_pagina()
        self.assertEqual(self.cfg.renomear_pagina(2, "  ECAC  "), "ECAC")
        self.assertEqual(self.cfg.nome_pagina(2), "ECAC")
        self.assertEqual(Config(self.tmp.name).nome_pagina(2), "ECAC")      # persiste
        self.assertEqual(self.cfg.info_tecla(2, "1")["pagina_nome"], "ECAC")
        self.assertEqual(self.cfg.snapshot()["pagina_nome"], "ECAC")      # a atual é a 2
        self.assertEqual(self.cfg.renomear_pagina(2, "   "), "")
        self.assertEqual(self.cfg.nome_pagina(2), "")

    def test_pagina_alta_pode_ter_nome_sem_existir_antes(self):
        self.cfg.renomear_pagina(10, "Programas Python")
        self.assertIn({"numero": 10, "nome": "Programas Python", "teclas": 0}, self.cfg.lista_paginas())

    def test_nome_invalido(self):
        for ruim in (5, ["a"]):
            with self.assertRaises(ErroConfig):
                self.cfg.renomear_pagina(1, ruim)
        with self.assertRaises(ErroConfig):
            self.cfg.renomear_pagina(0, "x")
        with self.assertRaises(ErroConfig):
            self.cfg.renomear_pagina(True, "x")
        with self.assertRaisesRegex(ErroConfig, "30 letras"):
            self.cfg.renomear_pagina(1, "a" * 31)
        with self.assertRaises(ErroConfig):
            self.cfg.renomear_pagina(1, "linha\nquebrada")

    def test_remover_pagina(self):
        self.cfg.criar_pagina()
        self.cfg.renomear_pagina(2, "Teste")
        self.cfg.ir_para(1)
        self.cfg.remover_pagina(2)
        self.assertEqual([p["numero"] for p in self.cfg.lista_paginas()], [1])
        self.assertEqual(self.cfg.nome_pagina(2), "")

    def test_nao_remove_a_1_a_atual_nem_pagina_com_teclas(self):
        self.cfg.criar_pagina()
        with self.assertRaises(ErroConfig):
            self.cfg.remover_pagina(1)
        with self.assertRaises(ErroConfig):
            self.cfg.remover_pagina(2)    # é a atual
        self.cfg.definir_tecla(2, "3", "x", None, [CLIQUE])
        self.cfg.ir_para(1)
        with self.assertRaisesRegex(ErroConfig, "teclas"):
            self.cfg.remover_pagina(2)

    def test_arquivo_com_nomes_ruins(self):
        bruto = {"nomes_paginas": {"2": "Ok", "x": "ruim", "3": 5, "0": "zero"}, "paginas_criadas": [4, "a", -1, 4]}
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(bruto), encoding="utf-8")
        cfg = Config(self.tmp.name)
        self.assertEqual(cfg.nome_pagina(2), "Ok")
        self.assertEqual(cfg.nome_pagina(3), "")
        self.assertEqual([p["numero"] for p in cfg.lista_paginas()], [1, 2, 4])


class TesteSeletor(unittest.TestCase):
    def test_classes_coladas_do_html_ganham_pontos(self):
        from configuracao import corrigir_seletor
        self.assertEqual(corrigir_seletor("btn btn-primary btn-block"), ".btn.btn-primary.btn-block")
        self.assertEqual(corrigir_seletor("botao enviar"), ".botao.enviar")

    def test_seletores_de_verdade_nao_mudam(self):
        from configuracao import corrigir_seletor
        for ok in ("#enviar", "button.ok", ".btn.btn-primary", "div span", "ul li", "[data-testid='send']",
                   "form > button", "a:hover", "btn-primary", "input[name=x]", "div .caixa"):
            self.assertEqual(corrigir_seletor(ok), ok, ok)

    def test_vale_nos_blocos_e_nas_condicoes(self):
        b = validar_bloco({"tipo": "web_clicar", "seletor": " btn btn-primary btn-block ", "aba": "", "limite": 10})
        self.assertEqual(b["seletor"], ".btn.btn-primary.btn-block")
        p = validar_bloco({"tipo": "pausa", "modo": "condicao", "ate": "aparecer", "limite": 30,
                           "condicao": {"tipo": "pagina", "alvo": "seletor", "valor": "btn btn-primary"}})
        self.assertEqual(p["condicao"]["valor"], ".btn.btn-primary")
        t = validar_condicao({"tipo": "pagina", "alvo": "texto", "valor": "Entrar agora"})
        self.assertEqual(t["valor"], "Entrar agora")                         # texto nunca é mexido


class TestePerguntasETextoDeArquivo(unittest.TestCase):
    ESCOLHA = {"tipo": "perguntar", "nome": " Caminho ", "tipo_pergunta": "escolha", "titulo": "Qual?",
               "opcoes": [{"nome": "Antiga", "descricao": "copia a nota"}, {"nome": "CNPJ"}, {"nome": "Do zero"}]}

    def test_pergunta_de_escolha(self):
        b = validar_bloco(self.ESCOLHA)
        self.assertEqual((b["nome"], b["lembrar"], len(b["opcoes"])), ("caminho", "sempre", 3))
        self.assertEqual(b["opcoes"][1], {"nome": "CNPJ", "descricao": ""})
        self.assertIn("caminho entre 3", descrever_bloco(b))

    def test_pergunta_invalida(self):
        for ruim in ({**self.ESCOLHA, "opcoes": [{"nome": "só uma"}]},
                     {**self.ESCOLHA, "opcoes": [{"nome": "a"}] * 9},
                     {**self.ESCOLHA, "opcoes": [{"nome": ""}, {"nome": "b"}]},
                     {**self.ESCOLHA, "nome": "Com Espaço"}, {**self.ESCOLHA, "nome": "data"},
                     {**self.ESCOLHA, "tipo_pergunta": "foto"}, {**self.ESCOLHA, "lembrar": "talvez"},
                     {**self.ESCOLHA, "titulo": ""}):
            with self.assertRaises(ErroConfig):
                validar_bloco(ruim)

    def test_pergunta_de_texto_e_arquivo(self):
        b = validar_bloco({"tipo": "perguntar", "nome": "cnpj", "tipo_pergunta": "texto", "titulo": "CNPJ?", "padrao": "00",
                           "lembrar": "primeira_vez", "opcoes": [{"nome": "lixo"}]})
        self.assertEqual((b["opcoes"], b["padrao"], b["lembrar"]), ([], "00", "primeira_vez"))

    def test_condicao_resposta(self):
        b = validar_bloco({"tipo": "se", "condicao": {"tipo": "resposta", "nome": "Caminho", "valor": " 2 "}, "entao": 1, "senao": 0})
        self.assertEqual(b["condicao"], {"tipo": "resposta", "nome": "caminho", "valor": "2"})
        self.assertIn('resposta {caminho} = "2"', descrever_bloco(b))
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "se", "condicao": {"tipo": "resposta", "nome": "x y", "valor": "1"}, "entao": 1})
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "se", "condicao": {"tipo": "resposta", "nome": "x", "valor": ""}, "entao": 1})

    def test_caminhos_aninhados_validam_como_fluxo(self):
        def se(v, e, s):
            return {"tipo": "se", "condicao": {"tipo": "resposta", "nome": "caminho", "valor": v}, "entao": e, "senao": s}
        ph = {"tipo": "texto", "texto": "x"}
        fluxo = validar_fluxo([self.ESCOLHA, se("1", 1, 3), ph, se("2", 1, 1), ph, ph])
        self.assertEqual(len(fluxo), 6)

    def test_texto_de_arquivo(self):
        b = validar_bloco({"tipo": "colar", "fonte": "arquivo", "arquivo": " C:\\x\\a.txt ", "texto": "ignorado"})
        self.assertEqual((b["fonte"], b["arquivo"], b["perguntar"], b["texto"]), ("arquivo", "C:\\x\\a.txt", "nunca", ""))
        self.assertRegex(b["chave"], r"^[a-z0-9]{8}$")
        self.assertIn("a.txt", descrever_bloco(b))
        b2 = validar_bloco({"tipo": "texto", "fonte": "arquivo", "perguntar": "primeira_vez", "chave": b["chave"]})
        self.assertEqual((b2["arquivo"], b2["chave"]), ("", b["chave"]))
        self.assertIn("1ª vez", descrever_bloco(b2))
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "colar", "fonte": "arquivo"})                 # fixo sem caminho
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "colar", "fonte": "arquivo", "arquivo": "a", "perguntar": "às vezes"})

    def test_texto_continua_igual_sem_arquivo(self):
        self.assertEqual(validar_bloco({"tipo": "colar", "texto": "oi", "fonte": "texto"}), {"tipo": "colar", "texto": "oi"})

    def test_site_pagina_atual(self):
        b = validar_bloco({"tipo": "site", "controlado": True, "destino": "atual", "url": ""})
        self.assertEqual(b, {"tipo": "site", "url": "", "controlado": True, "destino": "atual"})
        self.assertEqual(descrever_bloco(b), "Usar a página atual do navegador do Deck")
        b = validar_bloco({"tipo": "site", "controlado": True, "destino": "atual", "url": "x.com/a"})
        self.assertEqual(b["url"], "https://x.com/a")
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "site", "controlado": True, "url": ""})       # aba nova exige endereço
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "site", "controlado": True, "destino": "outra", "url": "x.com"})
        # fora do navegador do Deck não existe "página atual": abre normal
        self.assertNotIn("destino", validar_bloco({"tipo": "site", "controlado": False, "destino": "atual", "url": "x.com"}))
        seg = validar_bloco({"tipo": "site", "controlado": True, "segundo_plano": True, "url": "x.com"})
        self.assertTrue(seg["segundo_plano"])
        self.assertIn("segundo plano", descrever_bloco(seg))


class TesteBlocoDeNotasComWhatsapp(unittest.TestCase):
    BASE = {"tipo": "aviso", "canal": "bloco_notas", "origem": "arquivo", "arquivo": "r.txt"}

    def test_padrao_abre_e_nao_envia(self):
        b = validar_bloco(dict(self.BASE))
        self.assertEqual((b["abrir"], b["whatsapp"]), (True, None))

    def test_envia_por_whatsapp(self):
        b = validar_bloco({**self.BASE, "abrir": False, "whatsapp": {"numero": "+55 (77) 99183-1413", "modo": "evolution"}})
        self.assertEqual(b["whatsapp"], {"numero": "5577991831413", "modo": "evolution", "espera": 10})
        self.assertFalse(b["abrir"])
        self.assertIn("WhatsApp 5577991831413", descrever_bloco(b))

    def test_precisa_de_alguma_saida_e_numero_valido(self):
        with self.assertRaises(ErroConfig):
            validar_bloco({**self.BASE, "abrir": False})
        with self.assertRaises(ErroConfig):
            validar_bloco({**self.BASE, "whatsapp": {"numero": ""}})
        with self.assertRaises(ErroConfig):
            validar_bloco({**self.BASE, "whatsapp": {"numero": "5577991831413", "modo": "x"}})
        with self.assertRaises(ErroConfig):
            validar_bloco({**self.BASE, "abrir": "sim"})


class TesteValidacaoAvisos(unittest.TestCase):
    def test_popup_padrao(self):
        b = validar_bloco({"tipo": "aviso", "texto": "Terminou"})
        self.assertEqual(b, {"tipo": "aviso", "canal": "popup", "titulo": "", "texto": "Terminou",
                             "tamanho": "medio", "posicao": "baixo_dir", "segundos": 5})

    def test_popup_personalizado_exige_area(self):
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "aviso", "texto": "x", "posicao": "personalizado"})
        b = validar_bloco({"tipo": "aviso", "texto": "x", "posicao": "personalizado",
                           "area": {"x": 0.12345678, "y": 0.5, "l": 0.3, "a": 0.2}})
        self.assertEqual(b["area"], {"x": 0.1235, "y": 0.5, "l": 0.3, "a": 0.2})

    def test_area_fora_da_tela_ou_minuscula(self):
        for area in ({"x": 0.9, "y": 0.1, "l": 0.3, "a": 0.2}, {"x": 0, "y": 0, "l": 0.01, "a": 0.2},
                     {"x": 0, "y": 0, "l": "a", "a": 0.2}, None):
            with self.assertRaises(ErroConfig):
                validar_bloco({"tipo": "aviso", "texto": "x", "posicao": "personalizado", "area": area})

    def test_popup_valores_invalidos(self):
        for extra in ({"tamanho": "gigante"}, {"posicao": "lua"}, {"segundos": -1}, {"segundos": 999}, {"texto": ""}):
            with self.assertRaises(ErroConfig):
                validar_bloco({"tipo": "aviso", **{"texto": "x"}, **extra})

    def test_area_so_fica_no_personalizado(self):
        b = validar_bloco({"tipo": "aviso", "texto": "x", "posicao": "topo", "area": {"x": 0, "y": 0, "l": 0.5, "a": 0.5}})
        self.assertNotIn("area", b)

    def test_whatsapp(self):
        b = validar_bloco({"tipo": "aviso", "canal": "whatsapp", "numero": "+55 (11) 99999-8888", "texto": "Fim"})
        self.assertEqual((b["numero"], b["canal"], b["modo"], b["espera"]), ("5511999998888", "whatsapp", "link", 10))
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "aviso", "canal": "whatsapp", "modo": "pombo", "numero": "5511999998888", "texto": "x"})
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "aviso", "canal": "whatsapp", "espera": 0, "numero": "5511999998888", "texto": "x"})
        for ruim in ("", "abc", "123"):
            with self.assertRaises(ErroConfig):
                validar_bloco({"tipo": "aviso", "canal": "whatsapp", "numero": ruim, "texto": "Fim"})
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "aviso", "canal": "whatsapp", "numero": "5511999998888", "texto": ""})

    def test_bloco_de_notas_arquivo(self):
        b = validar_bloco({"tipo": "aviso", "canal": "bloco_notas", "origem": "arquivo", "arquivo": "lista.txt", "pasta": "C:/x"})
        self.assertEqual((b["origem"], b["arquivo"], b["pasta"]), ("arquivo", "lista.txt", "C:/x"))
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "aviso", "canal": "bloco_notas", "origem": "arquivo", "arquivo": ""})

    def test_bloco_de_notas_saida(self):
        b = validar_bloco({"tipo": "aviso", "canal": "bloco_notas", "origem": "saida", "shell": "python",
                           "comando": "C:/s/lista.py", "arquivo": "r.txt"})
        self.assertEqual((b["shell"], b["limite"], b["comando"]), ("python", 120, "C:/s/lista.py"))
        for ruim in ({"shell": "bash", "comando": "x"}, {"shell": "cmd", "comando": ""}, {"shell": "cmd", "comando": "x", "limite": 0}):
            with self.assertRaises(ErroConfig):
                validar_bloco({"tipo": "aviso", "canal": "bloco_notas", "origem": "saida", **ruim})

    def test_canal_desconhecido(self):
        with self.assertRaises(ErroConfig):
            validar_bloco({"tipo": "aviso", "canal": "pombo", "texto": "x"})

    def test_descricoes(self):
        self.assertEqual(descrever_bloco(validar_bloco({"tipo": "aviso", "texto": "Fim"})), 'Aviso: "Fim"')
        self.assertIn("WhatsApp", descrever_bloco(validar_bloco({"tipo": "aviso", "canal": "whatsapp", "numero": "5511999998888", "texto": "Fim"})))
        self.assertIn("Bloco de Notas", descrever_bloco(validar_bloco(
            {"tipo": "aviso", "canal": "bloco_notas", "origem": "arquivo", "arquivo": "lista.txt"})))


if __name__ == "__main__":
    unittest.main()
