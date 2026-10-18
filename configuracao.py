"""Configuração do deck: páginas, teclas, fluxos de blocos e imagens (JSON + pasta de imagens).

Cada tecla tem um FLUXO: uma lista de blocos executados de cima para baixo.
Tipos de bloco:
  atalho, texto, colar        teclado (colar usa a área de transferência)
  clique, mover, rolagem      mouse
  pausa                       "Esperar": um tempo, ou uma condição (janela, cor na tela, algo na página web)
  repetir, se (+ senão)       valem para os blocos que vêm logo depois deles
  variavel                    contador usado como {nome} nos textos
  abrir, site, comando        programas, sites (no navegador do Deck ou no padrão), PowerShell/CMD
  whatsapp, web_clicar, web_preencher
  midia, captura, sistema     volume/mídia, print da tela, bloquear PC/desligar monitor
  chamar, ir_pagina, aviso    chamar outra tecla, trocar de página, mostrar aviso
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from teclas import nome_vk

# Ordem visual do teclado numérico (de cima para baixo)
TECLAS = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0"]

OPCOES_PADRAO = {
    "popup_ao_trocar_pagina": True,   # mostra a prévia (imagens + nomes) ao trocar de página
    "popup_ao_trocar_modo": True,     # aviso ao alternar padrão <-> deck
    "apitar_fora_do_deck": True,      # / * - apitam no modo padrão (a tecla continua normal)
    "restaurar_numlock_ao_sair": True,
    "atualizar_ao_abrir": True,       # o .exe procura versão nova no GitHub ao abrir, baixa e reinicia
    "perfil_segundos": 10,            # quanto tempo a prévia aberta com "-" fica na tela
    "porta": 5077,
}
LIMITES_INT = {"porta": (1024, 65535), "perfil_segundos": (2, 120)}

ANCORAS_JANELA = ("proporcional", "topo_esq", "topo_dir", "baixo_esq", "baixo_dir")
TIPOS_BLOCO = ("atalho", "texto", "colar", "clique", "mover", "rolagem", "pausa", "repetir", "se", "variavel",
               "abrir", "site", "comando", "whatsapp", "web_clicar", "web_preencher",
               "midia", "captura", "sistema", "chamar", "ir_pagina", "aviso")
BOTOES = ("esquerdo", "direito", "meio")
MIDIA = {"volume_mais": "Volume +", "volume_menos": "Volume −", "mudo": "Mudo / som",
         "play_pausa": "Play / Pausa", "proxima": "Próxima faixa", "anterior": "Faixa anterior"}
SISTEMA = {"bloquear": "Bloquear o computador", "monitor_off": "Desligar o monitor"}
TAMANHOS_AVISO = ("pequeno", "medio", "grande")
POSICOES_AVISO = ("centro", "topo", "baixo", "topo_esq", "topo_dir", "baixo_esq", "baixo_dir", "personalizado")
SHELLS_SAIDA = ("powershell", "cmd", "python")
MAX_BLOCOS = 40
MAX_NOME_PAGINA = 30
NOME_IMAGEM_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|gif|webp)$")
NOME_VARIAVEL_RE = re.compile(r"^[a-z_][a-z0-9_]{0,19}$")
VARIAVEL_NO_TEXTO_RE = re.compile(r"\{([a-z_][a-z0-9_]{0,19})\}")
COR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
LIMITE_PAGINA = 100000
VARIAVEIS_RESERVADAS = ("data", "hora", "dataiso")
LIMITE_VARIAVEL = 10**9


class ErroConfig(ValueError):
    """Dado inválido recebido do painel ou do arquivo."""


# ---------------------------------------------------------------- pastas

def pasta_dados() -> Path:
    base = os.environ.get("NUMPAD_DECK_DIR")
    if base:
        return Path(base)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home()) / "NumpadDeck"
    return Path.home() / ".numpad_deck"


# ---------------------------------------------------------------- blocos

def _inteiro(valor, minimo: int, maximo: int, msg: str) -> int:
    if not isinstance(valor, int) or isinstance(valor, bool) or not minimo <= valor <= maximo:
        raise ErroConfig(msg)
    return valor


def _texto(valor, minimo: int, maximo: int, msg: str) -> str:
    if not isinstance(valor, str) or "\x00" in valor or not minimo <= len(valor.strip()) or len(valor) > maximo:
        raise ErroConfig(msg)
    return valor


def _opcional(valor, maximo: int, msg: str) -> str:
    if valor is None:
        return ""
    if not isinstance(valor, str) or "\x00" in valor or len(valor) > maximo:
        raise ErroConfig(msg)
    return valor.strip()


def _url(valor) -> str:
    if not isinstance(valor, str):
        raise ErroConfig("Informe o endereço do site.")
    url = valor.strip()
    if not url or len(url) > 500 or any(c.isspace() for c in url):
        raise ErroConfig("Endereço do site inválido.")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)", url):  # javascript:, mailto:, data: ... (localhost:8080 passa)
            raise ErroConfig("Use um endereço http:// ou https://.")
        url = "https://" + url
    analisada = urlparse(url)
    if analisada.scheme not in ("http", "https") or not analisada.netloc:
        raise ErroConfig("Use um endereço http:// ou https://.")
    return url


def _erro(msg: str):
    raise ErroConfig(msg)


normalizar_url = _url   # o núcleo revalida o endereço depois de trocar as {variáveis}


def validar_condicao(c) -> dict:
    """Condição usada por "Esperar" e por "Se": janela, cor de um pixel ou algo na página web."""
    if not isinstance(c, dict):
        raise ErroConfig("Condição inválida.")
    tipo = c.get("tipo")
    if tipo == "janela":
        modo = c.get("modo", "ativa")
        if modo not in ("ativa", "existe"):
            raise ErroConfig("Modo de janela inválido.")
        return {"tipo": tipo, "modo": modo,
                "texto": _texto(c.get("texto"), 1, 100, "Escreva parte do título da janela.").strip()}
    if tipo == "pixel":
        cor = c.get("cor")
        if not (isinstance(cor, str) and COR_RE.match(cor)):
            raise ErroConfig("Marque a cor na tela (ponto e cor).")
        return {"tipo": tipo,
                "x": _inteiro(c.get("x"), -32768, 32768, "Posição inválida: marque um ponto na tela."),
                "y": _inteiro(c.get("y"), -32768, 32768, "Posição inválida: marque um ponto na tela."),
                "cor": cor.lower(),
                "tolerancia": _inteiro(c.get("tolerancia", 24), 0, 255, "Tolerância da cor: de 0 a 255.")}
    if tipo == "pagina":
        alvo = c.get("alvo", "seletor")
        if alvo not in ("seletor", "texto"):
            raise ErroConfig("Escolha o que procurar na página.")
        valor = _texto(c.get("valor"), 1, 300, "Escreva o seletor ou o texto a procurar na página.").strip()
        return {"tipo": tipo, "alvo": alvo, "valor": corrigir_seletor(valor) if alvo == "seletor" else valor,
                "aba": _opcional(c.get("aba"), 100, "Filtro de aba inválido.")}
    raise ErroConfig("Escolha o tipo de condição.")


def descrever_condicao(c: dict) -> str:
    t = c["tipo"]
    if t == "janela":
        return f'janela ativa com "{c["texto"]}"' if c["modo"] == "ativa" else f'janela "{c["texto"]}" aberta'
    if t == "pixel":
        return f"cor {c['cor']} em ({c['x']}, {c['y']})"
    if t == "pagina":
        return f"elemento {c['valor']} na página" if c["alvo"] == "seletor" else f'texto "{c["valor"]}" na página'
    return "condição"


def tamanho_grupo(b: dict) -> tuple[int, int]:
    """Quantos blocos seguintes pertencem ao bloco (repetir: corpo; se: então, senão)."""
    if b["tipo"] == "repetir":
        return b["blocos"], 0
    if b["tipo"] == "se":
        return b["entao"], b["senao"]
    return 0, 0


def validar_bloco(bloco) -> dict:
    """Devolve o bloco normalizado ou levanta ErroConfig."""
    if not isinstance(bloco, dict):
        raise ErroConfig("Bloco inválido.")
    tipo = bloco.get("tipo")

    if tipo == "atalho":
        teclas = bloco.get("teclas")
        if not isinstance(teclas, list) or not 1 <= len(teclas) <= 8:
            raise ErroConfig("O atalho precisa ter de 1 a 8 teclas. Grave o comando.")
        saida = []
        for item in teclas:
            vk = item.get("vk") if isinstance(item, dict) else None
            vk = _inteiro(vk, 1, 254, "Tecla do atalho inválida.")
            saida.append({"vk": vk, "nome": str(item.get("nome") or nome_vk(vk))[:30]})
        return {"tipo": tipo, "teclas": saida}

    if tipo == "texto":
        return {"tipo": tipo, "texto": _texto(bloco.get("texto"), 1, 2000, "Escreva o texto a digitar (até 2000 letras).")}

    if tipo == "colar":
        return {"tipo": tipo, "texto": _texto(bloco.get("texto"), 1, 5000, "Escreva o texto a colar (até 5000 letras).")}

    if tipo in ("clique", "mover"):
        saida = {"tipo": tipo, **_validar_posicao(bloco)}
        if tipo == "mover":
            return saida
        botao = bloco.get("botao", "esquerdo")
        if botao not in BOTOES:
            raise ErroConfig("Botão do mouse inválido.")
        return {**saida, "botao": botao, "duplo": bool(bloco.get("duplo", False))}

    if tipo == "rolagem":
        direcao = bloco.get("direcao", "baixo")
        if direcao not in ("cima", "baixo"):
            raise ErroConfig("Direção da rolagem inválida.")
        return {"tipo": tipo, "direcao": direcao,
                "quantidade": _inteiro(bloco.get("quantidade", 3), 1, 50, "Quantidade de rolagem: de 1 a 50.")}

    if tipo == "pausa":   # no painel o nome é "Esperar"
        modo = bloco.get("modo", "tempo")
        if modo == "tempo":
            seg = bloco.get("segundos")
            if isinstance(seg, bool) or not isinstance(seg, (int, float)) or not 0.05 <= seg <= 600:
                raise ErroConfig("A pausa deve ter entre 0,05 e 600 segundos.")
            return {"tipo": tipo, "modo": "tempo", "segundos": round(float(seg), 2)}
        if modo == "condicao":
            ate = bloco.get("ate", "aparecer")
            expirar = bloco.get("ao_expirar", "parar")
            if ate not in ("aparecer", "sumir"):
                raise ErroConfig("Escolha esperar até aparecer ou até sumir.")
            if expirar not in ("parar", "continuar"):
                raise ErroConfig("Escolha o que fazer se o tempo acabar.")
            return {"tipo": tipo, "modo": "condicao", "condicao": validar_condicao(bloco.get("condicao")),
                    "ate": ate, "ao_expirar": expirar,
                    "limite": _inteiro(bloco.get("limite", 30), 1, 3600, "Tempo máximo de espera: de 1 a 3600 segundos.")}
        raise ErroConfig("Escolha o que esperar.")

    if tipo == "repetir":
        return {"tipo": tipo,
                "vezes": _inteiro(bloco.get("vezes", 2), 1, 1000, "Repetir de 1 a 1000 vezes."),
                "blocos": _inteiro(bloco.get("blocos", 1), 1, MAX_BLOCOS, "Quantos blocos seguintes repetir (1 a 40).")}

    if tipo == "se":
        return {"tipo": tipo, "condicao": validar_condicao(bloco.get("condicao")), "negar": bool(bloco.get("negar", False)),
                "entao": _inteiro(bloco.get("entao", 1), 1, MAX_BLOCOS, "Quantos blocos executar quando for verdade (1 a 40)."),
                "senao": _inteiro(bloco.get("senao", 0), 0, MAX_BLOCOS, "Quantos blocos executar quando não for (0 a 40).")}

    if tipo == "variavel":
        nome = bloco.get("nome")
        nome = nome.strip().lower() if isinstance(nome, str) else None
        if not nome or not NOME_VARIAVEL_RE.match(nome) or nome in VARIAVEIS_RESERVADAS:
            raise ErroConfig("Nome da variável: letras minúsculas, números e _ (até 20), sem espaços.")
        op = bloco.get("operacao", "somar")
        if op not in ("somar", "definir", "zerar"):
            raise ErroConfig("Operação da variável inválida.")
        valor = 0 if op == "zerar" else _inteiro(bloco.get("valor", 1), -LIMITE_VARIAVEL, LIMITE_VARIAVEL, "Valor da variável inválido.")
        return {"tipo": tipo, "nome": nome, "operacao": op, "valor": valor}

    if tipo == "abrir":
        caminho = _texto(bloco.get("caminho"), 1, 500, "Informe o caminho do programa.").strip()
        argumentos = bloco.get("argumentos", "")
        if not isinstance(argumentos, str) or len(argumentos) > 500 or "\x00" in argumentos:
            raise ErroConfig("Argumentos inválidos.")
        return {"tipo": tipo, "caminho": caminho, "argumentos": argumentos.strip()}

    if tipo == "site":
        return {"tipo": tipo, "url": _url(bloco.get("url")), "controlado": bool(bloco.get("controlado", False))}

    if tipo == "comando":
        shell = bloco.get("shell", "powershell")
        if shell not in ("powershell", "cmd"):
            raise ErroConfig("Escolha PowerShell ou CMD.")
        return {"tipo": tipo, "shell": shell,
                "comando": _texto(bloco.get("comando"), 1, 1000, "Escreva o comando (até 1000 letras).").strip(),
                "esperar": bool(bloco.get("esperar", False))}

    if tipo == "whatsapp":
        bruto = bloco.get("numero", "")
        if not isinstance(bruto, str) or len(bruto) > 40:
            raise ErroConfig("Número de WhatsApp inválido.")
        numero = re.sub(r"[\s+()\-.]", "", bruto)
        if numero and not (numero.isdigit() and 8 <= len(numero) <= 15):
            raise ErroConfig("Número de WhatsApp: só dígitos com DDI e DDD (ex.: 5575999999999).")
        mensagem = _opcional(bloco.get("mensagem"), 1000, "Mensagem muito longa (até 1000 letras).")
        if not numero and not mensagem:
            raise ErroConfig("Informe o número e/ou a mensagem.")
        return {"tipo": tipo, "numero": numero, "mensagem": mensagem, "controlado": bool(bloco.get("controlado", False))}

    if tipo in ("web_clicar", "web_preencher"):
        saida = {"tipo": tipo,
                 "seletor": corrigir_seletor(_texto(bloco.get("seletor"), 1, 300, "Escreva o seletor do elemento (ex.: #enviar ou button.ok).").strip()),
                 "aba": _opcional(bloco.get("aba"), 100, "Filtro de aba inválido."),
                 "limite": _inteiro(bloco.get("limite", 10), 1, 300, "Tempo máximo para o elemento aparecer: de 1 a 300 segundos.")}
        if tipo == "web_preencher":
            texto = bloco.get("texto", "")
            if not isinstance(texto, str) or len(texto) > 2000 or "\x00" in texto:
                raise ErroConfig("Texto do campo inválido (até 2000 letras).")
            saida["texto"] = texto
        return saida

    if tipo == "midia":
        acao = bloco.get("acao")
        if acao not in MIDIA:
            raise ErroConfig("Escolha a função de mídia.")
        return {"tipo": tipo, "acao": acao, "vezes": _inteiro(bloco.get("vezes", 1), 1, 50, "Repetições: de 1 a 50.")}

    if tipo == "captura":
        tela = bloco.get("tela", "todas")
        if tela not in ("todas", "principal"):
            raise ErroConfig("Escolha qual tela capturar.")
        return {"tipo": tipo, "tela": tela}

    if tipo == "sistema":
        acao = bloco.get("acao")
        if acao not in SISTEMA:
            raise ErroConfig("Escolha a ação do sistema.")
        return {"tipo": tipo, "acao": acao}

    if tipo == "chamar":
        return {"tipo": tipo,
                "pagina": _inteiro(bloco.get("pagina"), 1, LIMITE_PAGINA, "Página da tecla chamada inválida."),
                "tecla": bloco.get("tecla") if bloco.get("tecla") in TECLAS else _erro("Tecla chamada inválida.")}

    if tipo == "ir_pagina":
        return {"tipo": tipo, "numero": _inteiro(bloco.get("numero"), 1, LIMITE_PAGINA, "Número de página inválido.")}

    if tipo == "aviso":
        return _validar_aviso(bloco)

    raise ErroConfig("Escolha a função do bloco.")


def _validar_posicao(bloco: dict) -> dict:
    """Onde clicar/mover: um ponto fixo da tela, ou um ponto dentro da janela de um programa
    (que acompanha a janela se ela mudar de tamanho ou de lugar)."""
    alvo = bloco.get("alvo", "tela")
    if alvo == "tela":
        return {"alvo": "tela",
                "x": _inteiro(bloco.get("x"), -32768, 32768, "Posição inválida: marque um ponto na tela."),
                "y": _inteiro(bloco.get("y"), -32768, 32768, "Posição inválida: marque um ponto na tela.")}
    if alvo != "janela":
        raise ErroConfig("Escolha se a posição vale para a tela inteira ou para a janela de um programa.")
    janela = _texto(bloco.get("janela"), 1, 100, "Informe parte do título da janela do programa (até 100 letras).").strip()
    ancora = bloco.get("ancora", "proporcional")
    if ancora not in ANCORAS_JANELA:
        raise ErroConfig("Escolha como a posição acompanha a janela.")
    saida = {"alvo": "janela", "janela": janela, "ancora": ancora, "trazer": bool(bloco.get("trazer", True))}
    if ancora == "proporcional":
        for chave in ("rx", "ry"):
            v = bloco.get(chave)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
                raise ErroConfig("Marque o ponto dentro da janela (a posição fica entre 0% e 100%).")
            saida[chave] = round(float(v), 4)
    else:
        for chave in ("dx", "dy"):
            saida[chave] = _inteiro(bloco.get(chave), 0, 20000, "Marque o ponto dentro da janela (distância do canto em pixels).")
    return saida


_TAGS_HTML = frozenset("""a abbr article aside b body br button canvas caption code div em fieldset footer form h1 h2 h3 h4 h5 h6
header hr i iframe img input label legend li main nav ol option p pre section select small span strong sub summary
sup table tbody td textarea tfoot th thead tr u ul""".split())


def corrigir_seletor(seletor: str) -> str:
    """Quem copia o atributo class do HTML ("btn btn-primary btn-block") escreve só nomes separados por
    espaço; em CSS isso procuraria elementos <btn>. Aqui vira ".btn.btn-primary.btn-block". Seletores de
    verdade (com ponto, #, [, >, : ou só nomes de tags HTML, como "div span") ficam como estão."""
    palavras = seletor.split()
    if len(palavras) >= 2 and all(re.fullmatch(r"[A-Za-z_][\w-]*", p) for p in palavras) \
            and not all(p.lower() in _TAGS_HTML for p in palavras):
        return "." + ".".join(palavras)
    return seletor


def _numero_whatsapp(bruto, obrigatorio: bool) -> str:
    if bruto is None:
        bruto = ""
    if not isinstance(bruto, str) or len(bruto) > 40:
        raise ErroConfig("Número de WhatsApp inválido.")
    numero = re.sub(r"[\s+()\-.]", "", bruto)
    if (obrigatorio and not numero) or (numero and not (numero.isdigit() and 8 <= len(numero) <= 15)):
        raise ErroConfig("Número de WhatsApp: só dígitos com DDI e DDD (ex.: 5575999999999).")
    return numero


def _validar_area(area) -> dict:
    """Retângulo desenhado na tela, em frações (0 a 1) da tela: independe da resolução."""
    msg = "Desenhe na tela a área onde o aviso deve aparecer."
    if not isinstance(area, dict):
        raise ErroConfig(msg)
    saida = {}
    for chave in ("x", "y", "l", "a"):
        v = area.get(chave)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
            raise ErroConfig(msg)
        saida[chave] = round(float(v), 4)
    if saida["l"] < 0.03 or saida["a"] < 0.03 or saida["x"] + saida["l"] > 1.001 or saida["y"] + saida["a"] > 1.001:
        raise ErroConfig(msg)
    return saida


def _validar_aviso(bloco: dict) -> dict:
    canal = bloco.get("canal", "popup")
    if canal == "popup":
        tamanho = bloco.get("tamanho", "medio")
        posicao = bloco.get("posicao", "baixo_dir")
        if tamanho not in TAMANHOS_AVISO:
            raise ErroConfig("Escolha o tamanho do aviso.")
        if posicao not in POSICOES_AVISO:
            raise ErroConfig("Escolha onde o aviso aparece.")
        saida = {"tipo": "aviso", "canal": "popup", "titulo": _opcional(bloco.get("titulo"), 60, "Título muito longo (até 60 letras)."),
                 "texto": _texto(bloco.get("texto"), 1, 500, "Escreva o aviso (até 500 letras)."),
                 "tamanho": tamanho, "posicao": posicao,
                 "segundos": _inteiro(bloco.get("segundos", 5), 0, 120, "Tempo na tela: de 0 (até clicar) a 120 segundos.")}
        if posicao == "personalizado":
            saida["area"] = _validar_area(bloco.get("area"))
        return saida
    if canal == "whatsapp":
        modo = bloco.get("modo", "link")
        if modo not in ("link", "evolution"):
            raise ErroConfig("Escolha como enviar o WhatsApp: link (wa.me) ou Evolution API.")
        return {"tipo": "aviso", "canal": "whatsapp", "modo": modo, "numero": _numero_whatsapp(bloco.get("numero"), True),
                "texto": _texto(bloco.get("texto"), 1, 1000, "Escreva a mensagem (até 1000 letras)."),
                "espera": _inteiro(bloco.get("espera", 10), 1, 120, "Tempo de espera antes do Enter: de 1 a 120 segundos.")}
    if canal == "bloco_notas":
        origem = bloco.get("origem", "arquivo")
        if origem not in ("arquivo", "saida"):
            raise ErroConfig("Escolha o que abrir no Bloco de Notas.")
        arquivo = _opcional(bloco.get("arquivo"), 500, "Nome do arquivo inválido.")
        pasta = _opcional(bloco.get("pasta"), 500, "Pasta inválida.")
        saida = {"tipo": "aviso", "canal": "bloco_notas", "origem": origem, "arquivo": arquivo, "pasta": pasta}
        if origem == "arquivo":
            if not arquivo:
                raise ErroConfig("Informe o arquivo de texto que será aberto.")
            return saida
        shell = bloco.get("shell", "powershell")
        if shell not in SHELLS_SAIDA:
            raise ErroConfig("Escolha como rodar: PowerShell, CMD ou script Python.")
        saida.update({"shell": shell, "comando": _texto(bloco.get("comando"), 1, 1000, "Escreva o comando ou o caminho do script.").strip(),
                      "limite": _inteiro(bloco.get("limite", 120), 1, 3600, "Tempo máximo para terminar: de 1 a 3600 segundos.")})
        return saida
    raise ErroConfig("Escolha como avisar: pop-up, WhatsApp ou Bloco de Notas.")


def _conferir_grupos(fluxo: list[dict]) -> None:
    """Repetir e Se valem para os blocos que vêm logo depois: o grupo não pode passar do fim nem
    atravessar a borda de outro grupo."""
    n = len(fluxo)
    faixas = []   # (primeiro, ultimo) de cada parte de grupo
    fins = {}     # índice do bloco -> último índice que ele ocupa
    for i, b in enumerate(fluxo):
        a, c = tamanho_grupo(b)
        if a + c == 0:
            fins[i] = i
            continue
        fim = i + a + c
        if fim >= n:
            raise ErroConfig(f"Bloco {i + 1}: o grupo passa do fim do fluxo. Diminua a quantidade de blocos ou adicione blocos depois dele.")
        fins[i] = fim
        faixas.append((i + 1, i + a))
        if c:
            faixas.append((i + a + 1, fim))
    for j, b in enumerate(fluxo):
        for ini, ult in faixas:
            if ini <= j <= ult and fins[j] > ult:
                raise ErroConfig(f"Bloco {j + 1}: o grupo dele passa da borda do grupo em que está. Ajuste as quantidades.")


def validar_fluxo(fluxo) -> list[dict]:
    if not isinstance(fluxo, list):
        raise ErroConfig("Fluxo inválido.")
    if len(fluxo) > MAX_BLOCOS:
        raise ErroConfig(f"Máximo de {MAX_BLOCOS} blocos por tecla.")
    saida = []
    for numero, bloco in enumerate(fluxo, start=1):
        try:
            saida.append(validar_bloco(bloco))
        except ErroConfig as e:
            raise ErroConfig(f"Bloco {numero}: {e}") from None
    _conferir_grupos(saida)
    return saida


def aplicar_variaveis(texto: str, variaveis: dict | None = None, agora=None) -> str:
    """Troca {nome} pelo valor da variável; {data} e {hora} também existem. Nomes desconhecidos ficam como estão."""
    if not isinstance(texto, str) or "{" not in texto:
        return texto
    variaveis = variaveis or {}
    agora = agora or datetime.now()

    def troca(m):
        nome = m.group(1)
        if nome == "data":
            return agora.strftime("%d/%m/%Y")
        if nome == "hora":
            return agora.strftime("%H:%M")
        if nome == "dataiso":
            return agora.strftime("%Y-%m-%d")   # boa para nome de arquivo
        return str(variaveis[nome]) if nome in variaveis else m.group(0)

    return VARIAVEL_NO_TEXTO_RE.sub(troca, texto)


def _seg(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def _nome_arquivo(caminho: str) -> str:
    return re.split(r"[\\/]", caminho.rstrip("\\/"))[-1] or caminho


def _curto(texto: str, limite: int = 30) -> str:
    texto = texto.replace("\n", " ")
    return texto[:limite] + ("…" if len(texto) > limite else "")


def _onde(b: dict) -> str:
    if b.get("alvo", "tela") == "tela":
        return f"em ({b['x']}, {b['y']})"
    nome = f'da janela "{_curto(b["janela"], 24)}"'
    if b["ancora"] == "proporcional":
        return f"em ({_pct(b['rx'])}, {_pct(b['ry'])}) {nome}"
    canto = {"topo_esq": "superior esquerdo", "topo_dir": "superior direito",
             "baixo_esq": "inferior esquerdo", "baixo_dir": "inferior direito"}[b["ancora"]]
    return f"a ({b['dx']}, {b['dy']}) px do canto {canto} {nome}"


def _pct(v: float) -> str:
    return f"{round(v * 100, 1):g}%".replace(".", ",")


def descrever_bloco(b: dict) -> str:
    t = b["tipo"]
    if t == "atalho":
        return "Atalho: " + " + ".join(x["nome"] for x in b["teclas"])
    if t == "texto":
        return f'Digitar: "{_curto(b["texto"])}"'
    if t == "colar":
        return f'Colar: "{_curto(b["texto"])}"'
    if t == "clique":
        nome = {"esquerdo": "clique", "direito": "clique direito", "meio": "clique do meio"}[b["botao"]]
        texto = ("Duplo " if b.get("duplo") else "") + nome
        return f"{texto[0].upper()}{texto[1:]} {_onde(b)}"
    if t == "mover":
        return f"Mover o mouse para {_onde(b)}"
    if t == "rolagem":
        return f"Rolar para {b['direcao']} ({b['quantidade']}x)"
    if t == "pausa":
        if b.get("modo", "tempo") == "tempo":
            return f"Esperar {_seg(b['segundos'])} s"
        verbo = "aparecer" if b["ate"] == "aparecer" else "sumir"
        return f"Esperar {verbo}: {descrever_condicao(b['condicao'])} (máx. {b['limite']} s)"
    if t == "repetir":
        return f"Repetir {b['vezes']}x os próximos {b['blocos']} bloco(s)"
    if t == "se":
        cond = ("NÃO " if b.get("negar") else "") + descrever_condicao(b["condicao"])
        senao = f", senão os {b['senao']} seguintes" if b["senao"] else ""
        return f"Se {cond}: próximos {b['entao']} bloco(s){senao}"
    if t == "variavel":
        if b["operacao"] == "zerar":
            return f"Zerar {{{b['nome']}}}"
        return f"{'Somar ' + str(b['valor']) + ' a' if b['operacao'] == 'somar' else 'Definir'} {{{b['nome']}}}" + \
               ("" if b["operacao"] == "somar" else f" = {b['valor']}")
    if t == "abrir":
        return "Abrir: " + _nome_arquivo(b["caminho"]) + (f" {b['argumentos']}" if b.get("argumentos") else "")
    if t == "site":
        return "Abrir site: " + (urlparse(b["url"]).netloc or b["url"]) + (" (navegador do Deck)" if b.get("controlado") else "")
    if t == "comando":
        return f'{"PowerShell" if b["shell"] == "powershell" else "CMD"}: {_curto(b["comando"])}'
    if t == "whatsapp":
        return "WhatsApp" + (f" para {b['numero']}" if b["numero"] else "") + (f': "{_curto(b["mensagem"], 24)}"' if b["mensagem"] else "")
    if t == "web_clicar":
        return f"Clicar na página: {b['seletor']}"
    if t == "web_preencher":
        return f"Preencher na página: {b['seletor']}"
    if t == "midia":
        return MIDIA[b["acao"]] + (f" ({b['vezes']}x)" if b["vezes"] > 1 else "")
    if t == "captura":
        return "Print da tela" + (" principal" if b["tela"] == "principal" else "")
    if t == "sistema":
        return SISTEMA[b["acao"]]
    if t == "chamar":
        return f"Chamar a tecla {b['tecla']} da página {b['pagina']}"
    if t == "ir_pagina":
        return f"Ir para a página {b['numero']}"
    if t == "aviso":
        canal = b.get("canal", "popup")
        if canal == "whatsapp":
            return f'Avisar no WhatsApp ({b["numero"]}): "{_curto(b["texto"], 30)}"'
        if canal == "bloco_notas":
            if b["origem"] == "arquivo":
                return "Bloco de Notas: " + _nome_arquivo(b["arquivo"])
            return "Bloco de Notas com a saída de: " + _curto(b["comando"], 30)
        return f'Aviso: "{_curto(b["texto"], 30)}"'
    return "Bloco vazio"


def rotulo_bloco(b: dict) -> str:
    """Nome curtinho (para a prévia)."""
    t = b["tipo"]
    if t == "atalho":
        return " + ".join(x["nome"] for x in b["teclas"])
    if t == "texto":
        return "Digitar texto"
    if t == "colar":
        return "Colar texto"
    if t == "clique":
        return "Duplo clique" if b.get("duplo") else "Clique"
    if t == "mover":
        return "Mover mouse"
    if t == "rolagem":
        return "Rolar " + ("↑" if b["direcao"] == "cima" else "↓")
    if t == "pausa":
        return f"Esperar {_seg(b['segundos'])} s" if b.get("modo", "tempo") == "tempo" else "Esperar"
    if t == "repetir":
        return f"Repetir {b['vezes']}x"
    if t == "se":
        return "Se…"
    if t == "variavel":
        return f"{{{b['nome']}}}"
    if t == "abrir":
        return _nome_arquivo(b["caminho"])
    if t == "site":
        return (urlparse(b["url"]).netloc or b["url"]).removeprefix("www.")
    if t == "comando":
        return "Comando"
    if t == "whatsapp":
        return "WhatsApp"
    if t == "web_clicar":
        return "Clicar na página"
    if t == "web_preencher":
        return "Preencher campo"
    if t == "midia":
        return MIDIA[b["acao"]]
    if t == "captura":
        return "Print"
    if t == "sistema":
        return "Bloquear PC" if b["acao"] == "bloquear" else "Monitor off"
    if t == "chamar":
        return f"Chama {b['tecla']} (pág. {b['pagina']})"
    if t == "ir_pagina":
        return f"Ir p/ pág. {b['numero']}"
    if t == "aviso":
        return {"whatsapp": "Avisar WhatsApp", "bloco_notas": "Bloco de Notas"}.get(b.get("canal", "popup"), "Aviso")
    return "?"


def descrever_fluxo(fluxo: list[dict]) -> str:
    if not fluxo:
        return "Sem função"
    if len(fluxo) == 1:
        return descrever_bloco(fluxo[0])
    texto = f"{len(fluxo)} etapas: " + " → ".join(rotulo_bloco(b) for b in fluxo)
    return texto if len(texto) <= 160 else texto[:159] + "…"


def titulo_curto(tecla: dict, limite: int = 24) -> str:
    """Nome resumido do que a tecla faz: o nome dado pelo usuário ou um resumo automático."""
    fluxo = tecla["fluxo"]
    if tecla["nome"]:
        titulo = tecla["nome"]
    elif not fluxo:
        titulo = "Livre"
    elif len(fluxo) == 1:
        titulo = rotulo_bloco(fluxo[0])
    else:
        titulo = f"{len(fluxo)} etapas"
    return titulo if len(titulo) <= limite else titulo[: limite - 1] + "…"


def _fluxo_da_acao_antiga(acao) -> list[dict]:
    """Converte o formato da versão 1 (uma ação por tecla) para fluxo."""
    if not isinstance(acao, dict):
        return []
    tipo = acao.get("tipo")
    if tipo == "macro":
        bloco = {"tipo": "atalho", "teclas": acao.get("teclas")}
    elif tipo == "clique":
        bloco = dict(acao)
    elif tipo == "script":
        bloco = {"tipo": "abrir", "caminho": acao.get("caminho"), "argumentos": ""}
    else:
        return []
    return validar_fluxo([bloco])


def _tecla_padrao() -> dict:
    return {"nome": "", "imagem": None, "fluxo": []}


def _tecla_valida(item) -> dict:
    if not isinstance(item, dict):
        raise ErroConfig("Tecla inválida.")
    nome = str(item.get("nome") or "").strip()[:40]
    imagem = item.get("imagem")
    if imagem is not None and not (isinstance(imagem, str) and NOME_IMAGEM_RE.match(imagem)):
        imagem = None
    fluxo = validar_fluxo(item["fluxo"]) if "fluxo" in item else _fluxo_da_acao_antiga(item.get("acao"))
    return {"nome": nome, "imagem": imagem, "fluxo": fluxo}


def _extensao_da_imagem(dados: bytes) -> str | None:
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if dados.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    return None


# ---------------------------------------------------------------- configuração

def _limpar_nome_pagina(nome) -> str:
    if not isinstance(nome, str) or any(ord(c) < 32 for c in nome):
        raise ErroConfig("Nome de página inválido.")
    nome = " ".join(nome.split())
    if len(nome) > MAX_NOME_PAGINA:
        raise ErroConfig(f"O nome da página pode ter até {MAX_NOME_PAGINA} letras.")
    return nome


class Config:
    def __init__(self, pasta: str | Path | None = None):
        self.pasta = Path(pasta) if pasta else pasta_dados()
        self.pasta_imagens = self.pasta / "imagens"
        self.pasta_imagens.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.pasta / "config.json"
        self._lock = threading.RLock()
        self.versao = 1
        self._dados = self._carregar()

    # -- leitura / gravação
    @staticmethod
    def _padrao() -> dict:
        return {"pagina_atual": 1, "opcoes": dict(OPCOES_PADRAO), "paginas": {}, "variaveis": {},
                "nomes_paginas": {}, "paginas_criadas": []}

    def _carregar(self) -> dict:
        if not self.arquivo.exists():
            return self._padrao()
        try:
            return self._normalizar(json.loads(self.arquivo.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            try:  # guarda o arquivo estragado em vez de perder tudo em silêncio
                self.arquivo.replace(self.pasta / "config.corrompido.json")
            except OSError:
                pass
            return self._padrao()

    def _normalizar(self, bruto) -> dict:
        if not isinstance(bruto, dict):
            raise ErroConfig("Arquivo de configuração inválido.")
        dados = self._padrao()
        pag = bruto.get("pagina_atual")
        if isinstance(pag, int) and not isinstance(pag, bool) and 1 <= pag <= LIMITE_PAGINA:
            dados["pagina_atual"] = pag
        opcoes = bruto.get("opcoes")
        if isinstance(opcoes, dict):
            for chave, padrao in OPCOES_PADRAO.items():
                valor = opcoes.get(chave, padrao)
                if chave in LIMITES_INT:
                    minimo, maximo = LIMITES_INT[chave]
                    ok = isinstance(valor, int) and not isinstance(valor, bool) and minimo <= valor <= maximo
                else:
                    ok = isinstance(valor, bool)
                dados["opcoes"][chave] = valor if ok else padrao
        variaveis = bruto.get("variaveis")
        if isinstance(variaveis, dict):
            for nome, valor in variaveis.items():
                if (isinstance(nome, str) and NOME_VARIAVEL_RE.match(nome) and isinstance(valor, int)
                        and not isinstance(valor, bool) and abs(valor) <= LIMITE_VARIAVEL):
                    dados["variaveis"][nome] = valor
        nomes = bruto.get("nomes_paginas")
        if isinstance(nomes, dict):
            for numero, nome in nomes.items():
                if (isinstance(numero, str) and numero.isdigit() and 1 <= int(numero) <= LIMITE_PAGINA
                        and isinstance(nome, str) and nome.strip()):
                    dados["nomes_paginas"][str(int(numero))] = _limpar_nome_pagina(nome)
        criadas = bruto.get("paginas_criadas")
        if isinstance(criadas, list):
            dados["paginas_criadas"] = sorted({n for n in criadas if isinstance(n, int) and not isinstance(n, bool)
                                               and 1 <= n <= LIMITE_PAGINA})
        paginas = bruto.get("paginas")
        if isinstance(paginas, dict):
            for numero, teclas in paginas.items():
                if not (isinstance(numero, str) and numero.isdigit() and 1 <= int(numero) <= LIMITE_PAGINA):
                    continue
                if not isinstance(teclas, dict):
                    continue
                limpas = {}
                for tecla, item in teclas.items():
                    if tecla in TECLAS:
                        try:
                            nova = _tecla_valida(item)
                        except ErroConfig:
                            continue
                        if nova != _tecla_padrao():
                            limpas[tecla] = nova
                if limpas:
                    dados["paginas"][str(int(numero))] = limpas
        return dados

    def _salvar(self) -> None:
        self.versao += 1
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._dados, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.arquivo)

    # -- páginas
    @property
    def pagina_atual(self) -> int:
        with self._lock:
            return self._dados["pagina_atual"]

    def ir_para(self, pagina: int) -> int:
        if not isinstance(pagina, int) or isinstance(pagina, bool):
            raise ErroConfig("Número de página inválido.")
        pagina = max(1, min(pagina, LIMITE_PAGINA))
        with self._lock:
            if pagina != self._dados["pagina_atual"]:
                self._dados["pagina_atual"] = pagina
                self._salvar()
            return pagina

    def paginas_configuradas(self) -> list[int]:
        with self._lock:
            return sorted(int(n) for n in self._dados["paginas"])

    # -- nomes e lista de páginas
    def nome_pagina(self, pagina: int) -> str:
        with self._lock:
            return self._dados["nomes_paginas"].get(str(pagina), "")

    def todas_paginas(self) -> list[int]:
        """Páginas que "existem": com teclas, com nome, criadas pelo botão, a 1 e a atual."""
        with self._lock:
            d = self._dados
            return sorted({1, d["pagina_atual"], *map(int, d["paginas"]), *map(int, d["nomes_paginas"]), *d["paginas_criadas"]})

    def lista_paginas(self) -> list[dict]:
        with self._lock:
            return [{"numero": n, "nome": self.nome_pagina(n), "teclas": len(self._dados["paginas"].get(str(n), {}))}
                    for n in self.todas_paginas()]

    def renomear_pagina(self, pagina, nome) -> str:
        if not isinstance(pagina, int) or isinstance(pagina, bool) or not 1 <= pagina <= LIMITE_PAGINA:
            raise ErroConfig("Número de página inválido.")
        nome = _limpar_nome_pagina(nome if nome is not None else "")
        with self._lock:
            if nome:
                self._dados["nomes_paginas"][str(pagina)] = nome
            else:
                self._dados["nomes_paginas"].pop(str(pagina), None)
            self._salvar()
            return nome

    def criar_pagina(self) -> int:
        """Cria a próxima página (o maior número que existe + 1) e vai para ela."""
        with self._lock:
            novo = self.todas_paginas()[-1] + 1
            if novo > LIMITE_PAGINA:
                raise ErroConfig("Limite de páginas atingido.")
            self._dados["paginas_criadas"] = sorted({*self._dados["paginas_criadas"], novo})
            self._dados["pagina_atual"] = novo
            self._salvar()
            return novo

    def remover_pagina(self, pagina) -> None:
        """Tira da lista uma página sem teclas (a 1 e a atual não saem)."""
        if not isinstance(pagina, int) or isinstance(pagina, bool) or pagina < 1:
            raise ErroConfig("Número de página inválido.")
        with self._lock:
            if pagina == 1:
                raise ErroConfig("A página 1 não pode ser removida.")
            if pagina == self._dados["pagina_atual"]:
                raise ErroConfig("Vá para outra página antes de remover esta.")
            if self._dados["paginas"].get(str(pagina)):
                raise ErroConfig("Essa página ainda tem teclas programadas. Limpe as teclas primeiro.")
            self._dados["nomes_paginas"].pop(str(pagina), None)
            self._dados["paginas_criadas"] = [n for n in self._dados["paginas_criadas"] if n != pagina]
            self._salvar()

    # -- teclas
    def tecla(self, pagina: int, tecla: str) -> dict:
        with self._lock:
            achada = self._dados["paginas"].get(str(pagina), {}).get(tecla)
            return copy.deepcopy(achada) if achada else _tecla_padrao()

    def teclas_da_pagina(self, pagina: int) -> dict:
        return {t: self.tecla(pagina, t) for t in TECLAS}

    def info_tecla(self, pagina: int, tecla: str) -> dict:
        t = self.tecla(pagina, tecla)
        return {"pagina_nome": self.nome_pagina(pagina), "nome": t["nome"], "imagem": t["imagem"], "titulo": titulo_curto(t),
                "descricao": descrever_fluxo(t["fluxo"]), "etapas": len(t["fluxo"])}

    def itens_previa(self, pagina: int) -> list[dict]:
        """Dados da prévia grande: para cada tecla, título curto e caminho da imagem."""
        itens = []
        for numero in TECLAS:
            t = self.tecla(pagina, numero)
            caminho = self.caminho_imagem(t["imagem"]) if t["imagem"] else None
            itens.append({"tecla": numero, "titulo": titulo_curto(t),
                          "imagem": str(caminho) if caminho else None, "vazio": not t["fluxo"]})
        return itens

    def definir_tecla(self, pagina, tecla, nome, imagem, fluxo) -> dict:
        if not isinstance(pagina, int) or isinstance(pagina, bool) or not 1 <= pagina <= LIMITE_PAGINA:
            raise ErroConfig("Número de página inválido.")
        if tecla not in TECLAS:
            raise ErroConfig("Tecla inválida.")
        if imagem is not None:
            if not (isinstance(imagem, str) and NOME_IMAGEM_RE.match(imagem)
                    and (self.pasta_imagens / imagem).is_file()):
                raise ErroConfig("Imagem inválida.")
        novo = {"nome": str(nome or "").strip()[:40], "imagem": imagem, "fluxo": validar_fluxo(fluxo)}
        with self._lock:
            ciclo = self._achar_ciclo(pagina, tecla, novo["fluxo"])
            if ciclo:
                raise ErroConfig("Ciclo de chamadas: " + " → ".join(f"pág. {p} tecla {t}" for p, t in ciclo))
            antigo = self.tecla(pagina, tecla)
            chave = str(pagina)
            if novo == _tecla_padrao():
                teclas = self._dados["paginas"].get(chave, {})
                teclas.pop(tecla, None)
                if not teclas:
                    self._dados["paginas"].pop(chave, None)
            else:
                self._dados["paginas"].setdefault(chave, {})[tecla] = novo
            self._salvar()
            if antigo["imagem"] and antigo["imagem"] != imagem:
                self._apagar_se_orfa(antigo["imagem"])
            return copy.deepcopy(novo)

    def limpar_tecla(self, pagina: int, tecla: str) -> None:
        self.definir_tecla(pagina, tecla, "", None, [])

    def _achar_ciclo(self, pagina: int, tecla: str, fluxo_novo: list[dict]):
        """Procura A chama B chama A... Devolve o caminho do ciclo ou None."""
        def fluxo_de(no):
            if no == (pagina, tecla):
                return fluxo_novo
            return self._dados["paginas"].get(str(no[0]), {}).get(no[1], {}).get("fluxo", [])

        seguros: set = set()

        def visita(no, caminho):
            for bloco in fluxo_de(no):
                if bloco["tipo"] != "chamar":
                    continue
                alvo = (bloco["pagina"], bloco["tecla"])
                if alvo in caminho:
                    return caminho[caminho.index(alvo):] + [alvo]
                if alvo in seguros:
                    continue
                achou = visita(alvo, caminho + [alvo])
                if achou:
                    return achou
            seguros.add(no)
            return None

        return visita((pagina, tecla), [(pagina, tecla)])

    # -- variáveis (contadores)
    def variaveis(self) -> dict:
        with self._lock:
            return dict(self._dados["variaveis"])

    def aplicar_variavel(self, nome: str, operacao: str, valor: int) -> int:
        with self._lock:
            atual = self._dados["variaveis"].get(nome, 0)
            if operacao == "somar":
                novo = atual + valor
            elif operacao == "definir":
                novo = valor
            else:
                novo = 0
            novo = max(-LIMITE_VARIAVEL, min(LIMITE_VARIAVEL, novo))
            if novo != atual or nome not in self._dados["variaveis"]:
                self._dados["variaveis"][nome] = novo
                self._salvar()
            return novo

    # -- opções
    def opcoes(self) -> dict:
        with self._lock:
            return dict(self._dados["opcoes"])

    def definir_opcoes(self, parcial: dict) -> dict:
        if not isinstance(parcial, dict):
            raise ErroConfig("Opções inválidas.")
        with self._lock:
            for chave, valor in parcial.items():
                if chave == "porta" or chave not in OPCOES_PADRAO:
                    continue  # a porta só muda editando o arquivo
                if chave in LIMITES_INT:
                    minimo, maximo = LIMITES_INT[chave]
                    _inteiro(valor, minimo, maximo, f"Valor de {chave} fora do limite ({minimo} a {maximo}).")
                elif not isinstance(valor, bool):
                    raise ErroConfig(f"Valor inválido para {chave}.")
                self._dados["opcoes"][chave] = valor
            self._salvar()
            return dict(self._dados["opcoes"])

    # -- imagens
    def salvar_imagem(self, dados: bytes) -> str:
        ext = _extensao_da_imagem(dados)
        if ext is None:
            raise ErroConfig("Use uma imagem PNG, JPG, GIF ou WEBP.")
        nome = f"{uuid.uuid4().hex}.{ext}"
        (self.pasta_imagens / nome).write_bytes(dados)
        return nome

    def caminho_imagem(self, nome: str) -> Path | None:
        if not NOME_IMAGEM_RE.match(nome or ""):
            return None
        caminho = self.pasta_imagens / nome
        return caminho if caminho.is_file() else None

    def _imagem_em_uso(self, nome: str) -> bool:
        return any(t["imagem"] == nome for teclas in self._dados["paginas"].values() for t in teclas.values())

    def _apagar_se_orfa(self, nome: str) -> None:
        if not self._imagem_em_uso(nome):
            try:
                (self.pasta_imagens / nome).unlink()
            except OSError:
                pass

    def limpar_imagens_orfas(self) -> None:
        with self._lock:
            for arq in self.pasta_imagens.iterdir():
                if NOME_IMAGEM_RE.match(arq.name):
                    self._apagar_se_orfa(arq.name)

    # -- visão para o painel
    def snapshot(self) -> dict:
        with self._lock:
            pagina = self._dados["pagina_atual"]
            teclas = self.teclas_da_pagina(pagina)
            for t in teclas.values():
                t["descricao"] = descrever_fluxo(t["fluxo"])
                t["titulo"] = titulo_curto(t)
                t["etapas"] = len(t["fluxo"])
                for b in t["fluxo"]:
                    b["descricao"] = descrever_bloco(b)
            return {
                "versao": self.versao,
                "pagina": pagina,
                "pagina_nome": self.nome_pagina(pagina),
                "lista_paginas": self.lista_paginas(),
                "teclas": teclas,
                "opcoes": self.opcoes(),
                "variaveis": self.variaveis(),
                "paginas_configuradas": self.paginas_configuradas(),
            }
