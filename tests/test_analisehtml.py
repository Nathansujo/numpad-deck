import unittest

import analisehtml as a

PAGINA = """<html><body><form id="f">
<label for="u">Usuário</label><input id="u" name="usuario">
<input type="password" name="senha" placeholder="Senha">
<input type="hidden" name="csrf" value="x">
<button class="btn btn-primary" type="submit">Entrar</button>
<button class="btn btn-primary">Cancelar</button>
<a href="/esqueci">Esqueci a senha</a>
<div role="button" aria-label="Fechar"></div>
<div style="display:none"><button id="escondido">x</button></div>
<script>document.write('<button id="js">js</button>')</script>
<select name="uf"><option>BA</option></select>
<table><tr><td><button>Ok</button></td></tr></table>
</form></body></html>"""


class TesteAnalise(unittest.TestCase):
    def setUp(self):
        self.r = a.analisar(PAGINA)
        self.por_rotulo = {e["rotulo"]: e for e in self.r["elementos"]}

    def test_lista_so_o_que_importa(self):
        rotulos = [e["rotulo"] for e in self.r["elementos"]]
        self.assertEqual(len(rotulos), 8)
        self.assertNotIn("escondido", " ".join(rotulos))
        self.assertFalse(any("csrf" in r for r in rotulos))
        self.assertFalse(any(e["tag"] == "script" for e in self.r["elementos"]))

    def test_rotulos_e_acoes(self):
        e = self.por_rotulo["Campo de texto “Usuário”"]
        self.assertEqual((e["acao"], e["seletor"]), ("preencher", "#u"))
        self.assertEqual(self.por_rotulo["Campo de senha “Senha”"]["seletor"], "input[name='senha']")
        self.assertEqual(self.por_rotulo["Botão “Entrar”"]["acao"], "clicar")
        self.assertEqual(self.por_rotulo["Link “Esqueci a senha”"]["seletor"], "a[href='/esqueci']")
        self.assertEqual(self.por_rotulo["Botão “Fechar”"]["seletor"], "div[aria-label='Fechar']")
        self.assertEqual(self.por_rotulo["Lista de opções “uf”"]["acao"], "preencher")

    def test_botoes_iguais_caem_no_caminho_por_posicao(self):
        e = self.por_rotulo["Botão “Entrar”"]
        self.assertTrue(e["por_posicao"])
        self.assertEqual(e["seletor"], "#f > button:nth-of-type(1)")
        self.assertEqual(self.por_rotulo["Botão “Cancelar”"]["seletor"], "#f > button:nth-of-type(2)")

    def test_tbody_implicito(self):
        self.assertEqual(self.por_rotulo["Botão “Ok”"]["seletor"], "#f > table > tbody > tr > td > button")

    def test_seletor_unico_tem_prioridade_e_alternativas(self):
        r = a.analisar('<button id="enviar" class="ok forte" data-testid="send">Enviar</button><button class="ok">Outro</button>')
        e = r["elementos"][0]
        self.assertEqual(e["seletor"], "#enviar")
        self.assertIn("[data-testid='send']", e["alternativas"])
        self.assertFalse(e["por_posicao"])

    def test_ids_gerados_sao_evitados(self):
        r = a.analisar('<div><button id="btn-83921ab4c7">Salvar</button></div><div><button id="btn-11111999">Ver</button></div>')
        self.assertTrue(all(e["por_posicao"] for e in r["elementos"]))

    def test_aspas_e_acentos_no_valor(self):
        r = a.analisar("""<button aria-label="Dizer 'olá'">x</button>""")
        self.assertEqual(r["elementos"][0]["seletor"], "button[aria-label='Dizer \\'olá\\'']")

    def test_html_quebrado_nao_derruba(self):
        r = a.analisar("<div><p>oi<button>Ok</div></p></span><input")
        self.assertEqual(len(r["elementos"]), 1)

    def test_vazio(self):
        self.assertEqual(a.analisar("só texto")["elementos"], [])

    def test_limite(self):
        r = a.analisar("".join(f'<button id="b{i}x">B</button>' for i in range(200)))
        self.assertEqual((len(r["elementos"]), r["total"], r["cortado"]), (a.LIMITE_ELEMENTOS, 200, True))


class TesteHigiene(unittest.TestCase):
    def test_tira_o_que_executa(self):
        sujo = ('<script>alert(1)</script><p onclick="x()" onmouseover=y>oi</p><iframe src="http://x"></iframe>'
                '<a href="javascript:alert(1)">l</a><meta http-equiv="refresh" content="0;url=http://x"><base href="http://x">')
        limpo = a.higienizar(sujo)
        for ruim in ("<script", "onclick", "onmouseover", "<iframe", "javascript:", "refresh", "<base"):
            self.assertNotIn(ruim, limpo.lower())
        self.assertIn("<p", limpo)


if __name__ == "__main__":
    unittest.main()
