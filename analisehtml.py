"""Descobre o que dá para clicar ou preencher num HTML colado pelo usuário.

Fluxo: `analisar(html)` lê o HTML (sem executar nada), lista os botões, links, campos e listas e propõe um
seletor CSS para cada um (preferindo id, data-testid, name, aria-label... e só no fim o "caminho" por posição).
Se houver navegador, `fotografar` mostra a página com cada elemento numerado, como ele aparece de verdade.
"""
from __future__ import annotations

import base64
import io
import re
from html.parser import HTMLParser

LIMITE_ELEMENTOS = 150
VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
IGNORAR_CONTEUDO = {"script", "style", "template", "noscript"}
ATRIBUTOS_DE_TESTE = ("data-testid", "data-test-id", "data-test", "data-cy", "data-qa")
TIPOS_CLIQUE = {"button", "submit", "reset", "image", "checkbox", "radio"}
ROTULO_INPUT = {"text": "Campo de texto", "password": "Campo de senha", "email": "Campo de e-mail", "search": "Campo de pesquisa",
                "tel": "Campo de telefone", "url": "Campo de endereço", "number": "Campo numérico", "date": "Campo de data",
                "time": "Campo de hora", "datetime-local": "Campo de data e hora", "file": "Escolher arquivo",
                "checkbox": "Caixa de marcar", "radio": "Botão de opção", "submit": "Botão enviar", "button": "Botão",
                "reset": "Botão limpar", "image": "Botão de imagem", "color": "Seletor de cor", "range": "Barra deslizante"}
ROLES_CLIQUE = {"button", "link", "tab", "menuitem", "checkbox", "switch", "option", "radio", "menuitemcheckbox"}
ROLES_PREENCHER = {"textbox", "searchbox", "combobox"}


class _No:
    __slots__ = ("tag", "attrs", "pai", "filhos", "partes", "oculto")

    def __init__(self, tag: str, attrs: dict, pai):
        self.tag, self.attrs, self.pai = tag, attrs, pai
        self.filhos: list = []
        self.partes: list[str] = []
        self.oculto = False

    def texto(self) -> str:
        pedaco = " ".join(self.partes)
        for f in self.filhos:
            pedaco += " " + f.texto()
        return re.sub(r"\s+", " ", pedaco).strip()


class _Leitor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = _No("#raiz", {}, None)
        self.atual = self.raiz
        self.todos: list[_No] = []
        self._ignorando = 0

    def handle_starttag(self, tag, attrs):
        if self._ignorando:
            if tag not in VAZIOS:
                self._ignorando += tag in IGNORAR_CONTEUDO
            return
        dic = {k.lower(): (v if v is not None else "") for k, v in attrs}
        pai = self.atual
        if tag == "tr" and pai.tag == "table":            # o navegador cria o <tbody> sozinho
            tb = _No("tbody", {}, pai)
            pai.filhos.append(tb)
            self.todos.append(tb)
            pai = tb
        no = _No(tag, dic, pai)
        estilo = dic.get("style", "").replace(" ", "").lower()
        no.oculto = (pai.oculto or "hidden" in dic or dic.get("type", "").lower() == "hidden"
                     or "display:none" in estilo or "visibility:hidden" in estilo)
        pai.filhos.append(no)
        self.todos.append(no)
        if tag in IGNORAR_CONTEUDO:
            self._ignorando = 1
            self.atual = no
        elif tag not in VAZIOS:
            self.atual = no

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VAZIOS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self._ignorando:
            if tag in IGNORAR_CONTEUDO:
                self._ignorando -= 1
                if not self._ignorando and self.atual.tag == tag:
                    self.atual = self.atual.pai or self.raiz
            return
        n = self.atual
        while n is not None and n.tag != tag:
            n = n.pai
        if n is not None and n is not self.raiz:
            self.atual = n.pai or self.raiz

    def handle_data(self, data):
        if not self._ignorando and self.atual is not self.raiz:
            self.atual.partes.append(data)


def _css(valor: str) -> str:
    return "'" + valor.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _ident_ok(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][\w-]*", s))


def _parece_gerado(s: str) -> bool:
    """ids/classes que mudam a cada carregamento (hash, números longos)."""
    return len(s) > 32 or len(re.findall(r"\d", s)) >= 4 or bool(re.search(r"[0-9a-f]{8,}", s)) \
        or bool(re.fullmatch(r"[a-z]{1,3}[A-Z0-9_-]{4,}", s)) or s.startswith(("css-", "sc-", "jsx-", "ember", ":r"))


def _classes(no: _No) -> list[str]:
    return [c for c in no.attrs.get("class", "").split() if _ident_ok(c) and not _parece_gerado(c)]


def _candidatos(no: _No) -> list[tuple[str, callable]]:
    """Seletores do mais estável para o menos, cada um com a regra que o testa nos outros elementos."""
    t, a, saida = no.tag, no.attrs, []

    def eq(chave, valor):
        return lambda n: n.attrs.get(chave) == valor

    def com_tag(f):
        return lambda n: n.tag == t and f(n)

    ident = a.get("id", "")
    if ident and _ident_ok(ident) and not _parece_gerado(ident):
        saida.append((f"#{ident}", eq("id", ident)))
    for k in ATRIBUTOS_DE_TESTE:
        if a.get(k):
            saida.append((f"[{k}={_css(a[k])}]", eq(k, a[k])))
    if a.get("name") and t in {"input", "select", "textarea", "button", "form"}:
        saida.append((f"{t}[name={_css(a['name'])}]", com_tag(eq("name", a["name"]))))
    if a.get("aria-label"):
        saida.append((f"{t}[aria-label={_css(a['aria-label'])}]", com_tag(eq("aria-label", a["aria-label"]))))
    if a.get("placeholder"):
        saida.append((f"{t}[placeholder={_css(a['placeholder'])}]", com_tag(eq("placeholder", a["placeholder"]))))
    if a.get("title") and len(a["title"]) < 60:
        saida.append((f"{t}[title={_css(a['title'])}]", com_tag(eq("title", a["title"]))))
    if t == "a" and a.get("href") and len(a["href"]) < 100 and not a["href"].startswith("javascript"):
        saida.append((f"a[href={_css(a['href'])}]", com_tag(eq("href", a["href"]))))
    if t == "input" and a.get("type") and a.get("value"):
        saida.append((f"input[type={_css(a['type'])}][value={_css(a['value'])}]",
                      com_tag(lambda n, tp=a["type"], v=a["value"]: n.attrs.get("type") == tp and n.attrs.get("value") == v)))
    cls = _classes(no)
    if cls:
        todas = "." + ".".join(cls)
        saida.append((t + todas, com_tag(lambda n, c=cls: set(c) <= set(n.attrs.get("class", "").split()))))
        if len(cls) > 1:
            for c in cls:
                saida.append((f"{t}.{c}", com_tag(lambda n, c=c: c in n.attrs.get("class", "").split())))
    if a.get("type") and t == "input":
        saida.append((f"input[type={_css(a['type'])}]", com_tag(eq("type", a["type"]))))
    return saida


def _caminho(no: _No, unicos_por_id) -> str:
    partes = []
    n = no
    while n is not None and n is not n_raiz(no):
        if n.tag in ("html", "body", "head"):
            n = n.pai
            continue
        irmaos = [x for x in (n.pai.filhos if n.pai else []) if x.tag == n.tag]
        pos = irmaos.index(n) + 1
        partes.append(n.tag + (f":nth-of-type({pos})" if len(irmaos) > 1 else ""))
        ident = n.attrs.get("id", "")
        if ident and _ident_ok(ident) and not _parece_gerado(ident) and unicos_por_id(ident):
            partes[-1] = f"#{ident}"
            return " > ".join(reversed(partes))
        n = n.pai
    return "body > " + " > ".join(reversed(partes))


def n_raiz(no: _No) -> _No:
    while no.pai is not None:
        no = no.pai
    return no


def _rotulo(no: _No, etiquetas: dict | None = None) -> tuple[str, str]:
    """(tipo de ação, descrição para a pessoa)"""
    t, a = no.tag, no.attrs
    tipo_in = a.get("type", "text").lower() if t == "input" else ""
    papel = a.get("role", "").lower()
    if t == "input":
        acao = "clicar" if tipo_in in TIPOS_CLIQUE else "preencher"
        base = ROTULO_INPUT.get(tipo_in, "Campo de texto")
    elif t == "textarea":
        acao, base = "preencher", "Área de texto"
    elif t == "select":
        acao, base = "preencher", "Lista de opções"
    elif t == "button" or papel == "button":
        acao, base = "clicar", "Botão"
    elif t == "a":
        acao, base = "clicar", "Link"
    elif t == "summary":
        acao, base = "clicar", "Item que abre/fecha"
    elif a.get("contenteditable", "").lower() in ("", "true") and "contenteditable" in a or papel in ROLES_PREENCHER:
        acao, base = "preencher", "Campo editável"
    else:
        acao, base = "clicar", {"tab": "Aba", "menuitem": "Item de menu", "checkbox": "Caixa de marcar", "switch": "Interruptor",
                                "link": "Link", "option": "Opção", "radio": "Botão de opção"}.get(papel, "Elemento clicável")
    nome = "" if t in ("select", "textarea", "input") else no.texto()
    if t in ("select", "textarea", "input") and tipo_in not in ("submit", "button", "reset", "image"):
        nome = (etiquetas or {}).get(a.get("id", "")) or ""
        p = no.pai
        while not nome and p is not None and p.tag != "#raiz":
            if p.tag == "label":
                nome = p.texto()
            p = p.pai
    if not nome or tipo_in in ("submit", "button", "reset"):
        nome = nome or a.get("value", "")
    nome = nome or a.get("aria-label", "") or a.get("title", "") or a.get("placeholder", "") or a.get("alt", "")
    if not nome:
        for f in no.filhos:                       # ícone dentro do botão: usa o alt/aria-label dele
            nome = f.attrs.get("alt") or f.attrs.get("aria-label") or f.attrs.get("title") or ""
            if nome:
                break
    nome = nome or a.get("name", "") or a.get("id", "")
    nome = re.sub(r"\s+", " ", nome).strip()
    if len(nome) > 60:
        nome = nome[:57] + "…"
    return acao, base + (f" “{nome}”" if nome else " (sem texto)")


def _interativo(no: _No) -> bool:
    t, a = no.tag, no.attrs
    if no.oculto:
        return False
    if t in ("button", "select", "textarea", "summary"):
        return True
    if t == "input":
        return a.get("type", "text").lower() != "hidden"
    if t == "a":
        return "href" in a or "onclick" in a or a.get("role") is not None
    papel = a.get("role", "").lower()
    return (papel in ROLES_CLIQUE or papel in ROLES_PREENCHER or "onclick" in a
            or ("contenteditable" in a and a["contenteditable"].lower() in ("", "true")))


def analisar(html: str) -> dict:
    """{"elementos": [{"n", "tag", "acao", "rotulo", "seletor", "alternativas", "unico"}], "total", "cortado"}"""
    leitor = _Leitor()
    leitor.feed(html)
    leitor.close()
    todos = [n for n in leitor.todos if n.tag not in IGNORAR_CONTEUDO]
    ids = {}
    for n in todos:
        if n.attrs.get("id"):
            ids[n.attrs["id"]] = ids.get(n.attrs["id"], 0) + 1
    etiquetas = {n.attrs["for"]: n.texto() for n in todos if n.tag == "label" and n.attrs.get("for") and n.texto()}
    achados = [n for n in todos if _interativo(n)]
    elementos = []
    for n in achados[:LIMITE_ELEMENTOS]:
        acao, rotulo = _rotulo(n, etiquetas)
        unicos = [css for css, regra in _candidatos(n) if sum(1 for x in todos if regra(x)) == 1]
        if unicos:
            seletor, alternativas = unicos[0], unicos[1:4]
        else:                       # nada estável identifica só este: usa o caminho pela posição na página
            seletor, alternativas = _caminho(n, lambda i: ids.get(i) == 1), []
        elementos.append({"n": len(elementos) + 1, "tag": n.tag, "acao": acao, "rotulo": rotulo, "seletor": seletor,
                          "alternativas": alternativas, "por_posicao": not unicos})
    return {"elementos": elementos, "total": len(achados), "cortado": len(achados) > LIMITE_ELEMENTOS}


# ---------------------------------------------------------------- limpeza antes de mostrar no navegador
_BLOCOS_PERIGOSOS = re.compile(r"<\s*(script|iframe|object|embed|applet|noscript)\b.*?<\s*/\s*\1\s*>", re.I | re.S)
_SOLTAS = re.compile(r"<\s*/?\s*(script|iframe|object|embed|applet|base)\b[^>]*>", re.I)
_EVENTOS = re.compile(r"""\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_META_REFRESH = re.compile(r"<\s*meta\b[^>]*http-equiv\s*=\s*[\"']?refresh[^>]*>", re.I)
_JS_URL = re.compile(r"""(href|src|action|formaction|xlink:href)\s*=\s*("\s*javascript:[^"]*"|'\s*javascript:[^']*')""", re.I)


def higienizar(html: str) -> str:
    """Tira scripts, iframes, eventos e redirecionamentos: a página só é *desenhada*, nunca executada."""
    html = _BLOCOS_PERIGOSOS.sub("", html)
    html = _SOLTAS.sub("", html)
    html = _META_REFRESH.sub("", html)
    html = _JS_URL.sub(r'\1="#"', html)
    return _EVENTOS.sub("", html)


def marcar_imagem(png: bytes, itens: list[dict], largura_max: int = 1100) -> str:
    """Desenha um quadro numerado em volta de cada elemento e devolve a imagem como data URL."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(png)).convert("RGB")
    fonte = None
    for nome in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            fonte = ImageFont.truetype(nome, 15)
            break
        except OSError:
            continue
    fonte = fonte or ImageFont.load_default()
    d = ImageDraw.Draw(img, "RGBA")
    cores = ((4, 211, 97), (255, 138, 0), (64, 156, 255), (255, 64, 129))
    for it in itens:
        r = it.get("rect")
        if not r or r["w"] < 1 or r["h"] < 1 or r["y"] > img.height:
            continue
        cor = cores[(it["n"] - 1) % len(cores)]
        d.rectangle([r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]], outline=cor + (255,), width=3, fill=cor + (40,))
        rotulo = str(it["n"])
        caixa = d.textbbox((0, 0), rotulo, font=fonte)
        lw, lh = caixa[2] - caixa[0] + 10, caixa[3] - caixa[1] + 8
        x0, y0 = max(0, r["x"]), max(0, r["y"] - lh)
        d.rectangle([x0, y0, x0 + lw, y0 + lh], fill=cor + (255,))
        d.text((x0 + 5, y0 + 2), rotulo, fill=(0, 0, 0, 255), font=fonte)
    fundo = max((it["rect"]["y"] + it["rect"]["h"] for it in itens if it.get("rect") and it["rect"].get("w")), default=0)
    if 0 < fundo + 60 < img.height:                    # página curta: corta o branco de baixo
        img = img.crop((0, 0, img.width, max(120, int(fundo) + 60)))
    if img.width > largura_max:
        img = img.resize((largura_max, round(img.height * largura_max / img.width)))
    saida = io.BytesIO()
    img.save(saida, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(saida.getvalue()).decode()
