"""Painel web (Flask) em 127.0.0.1.

O navegador só mostra e edita a configuração. Quem lê o teclado e o mouse de verdade é o
programa em segundo plano; por isso gravar macro, marcar clique e escolher arquivo são
chamadas que ficam esperando o resultado.

Segurança: como qualquer site aberto no navegador consegue chamar 127.0.0.1, toda chamada
/api exige um token que só existe dentro da página servida por este programa, e o cabeçalho
Host precisa ser o do próprio painel (protege contra DNS rebinding).
"""
from __future__ import annotations

import hmac
import logging
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_from_directory
from werkzeug.serving import make_server

from avisos import ErroAviso
from configuracao import ANCORAS_JANELA, ErroConfig, TECLAS, descrever_bloco, descrever_fluxo, validar_bloco


def recurso(*partes: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base.joinpath(*partes)


def criar_app(cfg, nucleo, ui, plat, token: str, porta: int) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
    hosts_ok = {f"127.0.0.1:{porta}", f"localhost:{porta}"}

    def erro(msg: str, codigo: int = 400):
        return jsonify({"erro": msg}), codigo

    @app.before_request
    def proteger():
        if request.host not in hosts_ok:
            abort(403)
        if request.path.startswith("/api/"):
            enviado = request.headers.get("X-Painel-Token", "")
            if not hmac.compare_digest(enviado.encode(), token.encode()):
                abort(403)

    @app.after_request
    def cabecalhos(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
        )
        return resp

    @app.errorhandler(ErroConfig)
    def _erro_config(e):
        return erro(str(e))

    @app.errorhandler(ErroAviso)
    def _erro_aviso(e):
        return erro(str(e), 502)

    @app.errorhandler(413)
    def _grande(_e):
        return erro("Arquivo grande demais (máximo 6 MB).", 413)

    def corpo() -> dict:
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            raise ErroConfig("Pedido inválido.")
        return dados

    # ---------------------------------------------------------------- páginas
    @app.get("/")
    def pagina():
        html = recurso("web", "index.html").read_text(encoding="utf-8")
        return Response(html.replace("__TOKEN__", token), mimetype="text/html")

    @app.get("/ping")
    def ping():
        return jsonify({"app": "numpad-deck"})

    @app.get("/imagens/<nome>")
    def imagem(nome):
        caminho = cfg.caminho_imagem(nome)
        if caminho is None:
            abort(404)
        return send_from_directory(cfg.pasta_imagens, caminho.name)

    # ---------------------------------------------------------------- estado
    @app.get("/api/estado")
    def estado():
        return jsonify({
            "versao": cfg.versao,
            "modo": nucleo.modo(),
            "pagina": cfg.pagina_atual,
            "gravando": nucleo.gravando(),
        })

    @app.get("/api/config")
    def config():
        dados = cfg.snapshot()
        dados["autostart"] = bool(plat.autostart_ligado())
        return jsonify(dados)

    @app.post("/api/pagina")
    def mudar_pagina():
        dados = corpo()
        if dados.get("nova"):
            return jsonify({"pagina": cfg.criar_pagina()})
        if "renomear" in dados:
            r = dados["renomear"]
            if not isinstance(r, dict):
                raise ErroConfig("Pedido inválido.")
            return jsonify({"nome": cfg.renomear_pagina(r.get("pagina"), r.get("nome"))})
        if "remover" in dados:
            cfg.remover_pagina(dados["remover"])
            return jsonify({"ok": True})
        if "ir_para" in dados:
            nova = nucleo.ir_para_pagina(dados["ir_para"])
        else:
            delta = dados.get("delta")
            if delta not in (-1, 1):
                raise ErroConfig("Movimento de página inválido.")
            nova = nucleo.mudar_pagina(delta, popup=False)
        return jsonify({"pagina": nova})

    # ---------------------------------------------------------------- teclas
    @app.post("/api/tecla")
    def salvar_tecla():
        d = corpo()
        salva = cfg.definir_tecla(d.get("pagina"), d.get("tecla"), d.get("nome"), d.get("imagem"), d.get("fluxo"))
        return jsonify({"ok": True, "descricao": descrever_fluxo(salva["fluxo"])})

    @app.get("/api/tecla-info")
    def info_tecla():
        pagina = request.args.get("pagina", type=int)
        tecla = request.args.get("tecla", "")
        if pagina is None or not 1 <= pagina <= 100000 or tecla not in TECLAS:
            raise ErroConfig("Página ou tecla inválida.")
        return jsonify(cfg.info_tecla(pagina, tecla))

    @app.post("/api/tecla/limpar")
    def limpar_tecla():
        d = corpo()
        if d.get("tecla") not in TECLAS:
            raise ErroConfig("Tecla inválida.")
        cfg.limpar_tecla(d.get("pagina"), d["tecla"])
        return jsonify({"ok": True})

    @app.post("/api/imagem")
    def enviar_imagem():
        arquivo = request.files.get("arquivo")
        if arquivo is None:
            raise ErroConfig("Nenhum arquivo enviado.")
        return jsonify({"imagem": cfg.salvar_imagem(arquivo.read())})

    # ---------------------------------------------------------------- captura (esperam o usuário)
    @app.post("/api/gravar-macro")
    def gravar_macro():
        try:
            teclas = nucleo.gravar_macro(20)
        except RuntimeError as e:
            return erro(str(e), 409)
        if not teclas:
            return erro("Nada foi gravado (cancelado ou tempo esgotado).", 408)
        bloco = validar_bloco({"tipo": "atalho", "teclas": teclas})
        return jsonify({"teclas": bloco["teclas"], "descricao": descrever_bloco(bloco)})

    @app.post("/api/capturar-clique")
    def capturar_clique():
        d = request.get_json(silent=True) or {}
        janela = d.get("alvo") == "janela"
        ancora = d.get("ancora", "proporcional")
        if janela and ancora not in ANCORAS_JANELA:
            raise ErroConfig("Escolha como a posição acompanha a janela.")
        xy = ui.capturar_clique(60, "Clique no ponto da janela do programa" if janela else "Clique onde a tecla deve clicar")
        if xy is None:
            return erro("Clique cancelado.", 408)
        x, y = int(xy[0]), int(xy[1])
        if not janela:
            return jsonify({"x": x, "y": y})
        time.sleep(0.3)   # a tela escura precisa sumir para achar a janela que está embaixo
        try:
            return jsonify({"x": x, "y": y, **plat.marcar_em_janela(x, y, ancora)})
        except RuntimeError as e:
            return erro(str(e), 400)

    @app.post("/api/capturar-cor")
    def capturar_cor():
        xy = ui.capturar_clique(60, "Clique no ponto cuja cor deve ser observada")
        if xy is None:
            return erro("Clique cancelado.", 408)
        time.sleep(0.3)   # a tela escura precisa sumir antes de ler a cor
        x, y = int(xy[0]), int(xy[1])
        cor = plat.ler_cor(x, y)
        if cor is None:
            return erro("Não consegui ler a cor desse ponto (só funciona no Windows).", 500)
        return jsonify({"x": x, "y": y, "cor": cor})

    @app.post("/api/capturar-area")
    def capturar_area():
        area = ui.capturar_area(120)
        if area is None:
            return erro("Desenho cancelado.", 408)
        return jsonify(area)

    @app.post("/api/escolher-pasta")
    def escolher_pasta():
        pasta = ui.escolher_pasta()
        if not pasta:
            return erro("Nenhuma pasta escolhida.", 408)
        return jsonify({"caminho": pasta})

    @app.post("/api/escolher-arquivo")
    def escolher_arquivo():
        caminho = ui.escolher_arquivo()
        if not caminho:
            return erro("Nenhum arquivo escolhido.", 408)
        return jsonify({"caminho": caminho})

    @app.post("/api/cancelar")
    def cancelar():
        nucleo.cancelar_gravacao()
        ui.cancelar_overlay()
        return jsonify({"ok": True})

    @app.post("/api/testar")
    def testar():
        nucleo.testar(corpo().get("fluxo"))
        return jsonify({"ok": True})

    @app.post("/api/previa")
    def previa():
        nucleo.mostrar_previa(alternar=False)
        return jsonify({"ok": True})

    # ---------------------------------------------------------------- opções
    @app.post("/api/opcoes")
    def opcoes():
        return jsonify(cfg.definir_opcoes(corpo()))

    # ---------------------------------------------------------------- Evolution API (WhatsApp)
    @app.get("/api/avisos-config")
    def avisos_config():
        return jsonify(plat.segredos.publico())   # a chave nunca volta para o painel

    @app.post("/api/avisos-config")
    def avisos_config_salvar():
        d = corpo()
        for campo in ("evolution_url", "evolution_instancia"):
            if not isinstance(d.get(campo, ""), str):
                raise ErroConfig("Valor inválido.")
        chave = d.get("evolution_chave")
        if chave is not None and not isinstance(chave, str):
            raise ErroConfig("Valor inválido.")
        try:
            plat.segredos.salvar(d.get("evolution_url", ""), d.get("evolution_instancia", ""),
                                 chave, bool(d.get("limpar_chave")))
        except ErroAviso as e:
            raise ErroConfig(str(e)) from None
        return jsonify(plat.segredos.publico())

    @app.post("/api/avisos-testar")
    def avisos_testar():
        numero = validar_bloco({"tipo": "aviso", "canal": "whatsapp", "numero": corpo().get("numero"), "texto": "x"})["numero"]
        plat.enviar_whatsapp(numero, "Teste do Numpad Deck: a Evolution API está funcionando.")
        return jsonify({"ok": True})

    @app.post("/api/autostart")
    def autostart():
        ligado = corpo().get("ligado")
        if not isinstance(ligado, bool):
            raise ErroConfig("Valor inválido.")
        plat.definir_autostart(ligado)
        return jsonify({"autostart": bool(plat.autostart_ligado())})

    @app.post("/api/encerrar")
    def encerrar():
        threading.Timer(0.3, ui.sair).start()
        return jsonify({"ok": True})

    return app


def iniciar_servidor(app: Flask, porta: int):
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    servidor = make_server("127.0.0.1", porta, app, threaded=True)
    threading.Thread(target=servidor.serve_forever, name="painel-web", daemon=True).start()
    return servidor
