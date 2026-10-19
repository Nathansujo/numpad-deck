"""Avisos do fluxo: onde e de que tamanho o pop-up aparece, envio de mensagem pela Evolution API
(WhatsApp) e geração do TXT com a saída de um comando/script para abrir no Bloco de Notas.

Nada aqui depende do Windows (os testes rodam em qualquer sistema)."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

# tamanho do pop-up como fração da área útil da tela (largura, altura)
TAMANHOS = {"pequeno": (0.20, 0.10), "medio": (0.30, 0.17), "grande": (0.46, 0.32)}
MARGEM = 0.02          # distância da borda, como fração do menor lado
LARGURA_MIN, ALTURA_MIN = 260, 90


class ErroAviso(Exception):
    """Falha ao avisar (aparece como aviso de erro para o usuário)."""


# ---------------------------------------------------------------- geometria do pop-up
def calcular_retangulo(area_util, tamanho: str, posicao: str, area: dict | None = None, tela_virtual=None):
    """Devolve (x, y, largura, altura) em pixels.

    area_util: (x, y, largura, altura) da área de trabalho do monitor principal (sem a barra de tarefas).
    area: retângulo desenhado (frações 0 a 1 da tela virtual) quando posicao == "personalizado".
    """
    ux, uy, uw, uh = area_util
    if posicao == "personalizado":
        if not area:
            raise ErroAviso("Aviso sem área desenhada.")
        tx, ty, tw, th = tela_virtual or area_util
        return (round(tx + area["x"] * tw), round(ty + area["y"] * th),
                max(160, round(area["l"] * tw)), max(60, round(area["a"] * th)))
    fl, fa = TAMANHOS[tamanho]
    largura = min(uw, max(LARGURA_MIN, round(fl * uw)))
    altura = min(uh, max(ALTURA_MIN, round(fa * uh)))
    m = round(MARGEM * min(uw, uh))
    esq, dir_, meio_x = ux + m, ux + uw - largura - m, ux + (uw - largura) // 2
    topo, base, meio_y = uy + m, uy + uh - altura - m, uy + (uh - altura) // 2
    pontos = {"centro": (meio_x, meio_y), "topo": (meio_x, topo), "baixo": (meio_x, base),
              "topo_esq": (esq, topo), "topo_dir": (dir_, topo), "baixo_esq": (esq, base), "baixo_dir": (dir_, base)}
    x, y = pontos[posicao]
    return x, y, largura, altura


# ---------------------------------------------------------------- segredos (chave da Evolution API)
class Segredos:
    """Guarda a URL, a instância e a chave da Evolution API num arquivo À PARTE (segredos.json).
    A chave nunca é devolvida ao painel: ele só sabe se ela existe."""

    def __init__(self, pasta: Path):
        self.arquivo = Path(pasta) / "segredos.json"

    def _ler(self) -> dict:
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def publico(self) -> dict:
        d = self._ler()
        return {"evolution_url": d.get("evolution_url", ""), "evolution_instancia": d.get("evolution_instancia", ""),
                "evolution_chave_definida": bool(d.get("evolution_chave"))}

    def salvar(self, url: str, instancia: str, chave: str | None = None, limpar_chave: bool = False) -> None:
        url = (url or "").strip().rstrip("/")
        instancia = (instancia or "").strip()
        if url and not re.match(r"^https?://[^\s/]+", url):
            raise ErroAviso("O endereço da Evolution API deve começar com http:// ou https://")
        if len(url) > 300 or len(instancia) > 100 or (chave is not None and len(chave) > 300):
            raise ErroAviso("Valor muito longo.")
        if any(c in instancia for c in "/?#\\ ") or any(ord(c) < 32 for c in url + instancia + (chave or "")):
            raise ErroAviso("Nome da instância ou chave com caracteres inválidos.")
        d = self._ler()
        d["evolution_url"], d["evolution_instancia"] = url, instancia
        if limpar_chave:
            d.pop("evolution_chave", None)
        elif chave:
            d["evolution_chave"] = chave
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.arquivo)

    def evolution(self) -> tuple[str, str, str]:
        d = self._ler()
        url, inst, chave = d.get("evolution_url", ""), d.get("evolution_instancia", ""), d.get("evolution_chave", "")
        if not (url and inst and chave):
            raise ErroAviso("Configure a Evolution API em Opções (endereço, instância e chave).")
        return url, inst, chave


# ---------------------------------------------------------------- WhatsApp por link (wa.me) + Enter
LIMITE_ZAP = {"link": 1200, "evolution": 3800}   # o link wa.me aceita pouco texto; a API aceita bem mais


def ler_texto_para_whatsapp(arquivo, modo: str = "link") -> str:
    """Conteúdo do TXT pronto para virar mensagem (corta se passar do limite do modo de envio)."""
    bruto = Path(arquivo).read_bytes()
    for codec in ("utf-8-sig", "cp1252"):
        try:
            texto = bruto.decode(codec)
            break
        except UnicodeDecodeError:
            continue
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not texto:
        return "(sem conteúdo)"
    limite = LIMITE_ZAP.get(modo, 1200)
    if len(texto) > limite:
        texto = texto[:limite].rstrip() + "\n… (texto cortado; o arquivo completo ficou no computador)"
    return texto


def link_whatsapp(numero: str, texto: str) -> str:
    """https://wa.me/<número>?text=<mensagem codificada>: abre a conversa com a mensagem já digitada."""
    return f"https://wa.me/{numero}?text={urllib.parse.quote(texto, safe='')}"


# ---------------------------------------------------------------- WhatsApp (Evolution API)
def _post_json(url: str, chave: str, corpo: dict, timeout: float):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), method="POST", headers={
        "Content-Type": "application/json", "apikey": chave, "User-Agent": "NumpadDeck"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def enviar_whatsapp(url_base: str, instancia: str, chave: str, numero: str, texto: str, timeout: float = 15) -> None:
    """Manda uma mensagem de texto pela Evolution API (POST /message/sendText/{instância})."""
    endpoint = f"{url_base.rstrip('/')}/message/sendText/{urllib.parse.quote(instancia, safe='')}"
    corpos = ({"number": numero, "text": texto},                                   # Evolution v2
              {"number": numero, "textMessage": {"text": texto}})                 # Evolution v1
    for i, corpo in enumerate(corpos):
        try:
            _post_json(endpoint, chave, corpo, timeout)
            return
        except urllib.error.HTTPError as e:
            if e.code == 400 and i == 0:
                continue   # formato antigo da API: tenta o outro
            detalhe = ""
            try:
                detalhe = e.read().decode("utf-8", "replace")[:140]
            except Exception:
                pass
            dica = " (confira a chave e o nome da instância)" if e.code in (401, 403, 404) else ""
            raise ErroAviso(f"A Evolution API respondeu {e.code}{dica}: {detalhe}".strip(": ")) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErroAviso(f"Não consegui falar com a Evolution API: {getattr(e, 'reason', e)}") from None


# ---------------------------------------------------------------- Bloco de Notas
def _codificacao_oem() -> str:
    if sys.platform == "win32":
        try:
            import ctypes

            return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        except Exception:
            pass
    return "utf-8"


def resolver_arquivo(bloco: dict, base_padrao: Path, pasta_script: Path | None = None) -> Path:
    """Onde fica o TXT: caminho completo, ou nome dentro da pasta informada, ou (saída de script) na pasta
    do script, ou na pasta de saídas do programa."""
    nome = bloco.get("arquivo", "").strip()
    pasta = bloco.get("pasta", "").strip()
    if not nome:
        return Path(base_padrao) / f"saida_{datetime.now():%Y%m%d_%H%M%S}.txt"
    caminho = Path(nome)
    if caminho.is_absolute():
        return caminho
    if pasta:
        return Path(pasta) / caminho
    return (pasta_script or Path(base_padrao)) / caminho


def interpretador_com_console(interpretador: str) -> str:
    """pythonw.exe não tem tela para o print escrever: para capturar a saída usamos o python.exe vizinho."""
    caminho = Path(interpretador)
    if caminho.name.lower() == "pythonw.exe" and caminho.with_name("python.exe").exists():
        return str(caminho.with_name("python.exe"))
    return interpretador


def _montar_comando(bloco: dict, interpretador: str):
    shell, comando = bloco["shell"], bloco["comando"]
    if shell == "python":
        partes = [p.strip('"') for p in shlex.split(comando, posix=False)]
        script = Path(partes[0])
        if not script.is_file():
            raise ErroAviso(f"Script não encontrado: {script}")
        return [interpretador_com_console(interpretador), str(script), *partes[1:]], script.parent, "utf-8"
    if shell == "powershell":
        import shutil

        exe = shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            raise ErroAviso("PowerShell não encontrado.")
        return [exe, "-NoProfile", "-NonInteractive", "-Command", comando], None, _codificacao_oem()
    return ["cmd", "/c", comando], None, _codificacao_oem()


def gerar_txt_da_saida(bloco: dict, base_padrao: Path, interpretador: str) -> Path:
    """Roda o comando/script, guarda o que ele escreveu na tela num TXT e devolve o caminho do arquivo."""
    args, cwd, codificacao = _montar_comando(bloco, interpretador)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        r = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=bloco["limite"], creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except subprocess.TimeoutExpired:
        raise ErroAviso(f"O comando passou de {bloco['limite']} segundos e foi interrompido.") from None
    saida = r.stdout.decode(codificacao, "replace").strip("\r\n")
    erros = r.stderr.decode(codificacao, "replace").strip("\r\n")
    linhas = [f"Saída de: {bloco['comando']}", f"{datetime.now():%d/%m/%Y %H:%M:%S}", "-" * 40, saida or "(sem saída)"]
    if erros:
        linhas += ["", "--- mensagens de erro ---", erros]
    if r.returncode != 0:
        linhas += ["", f"(o comando terminou com código de erro {r.returncode})"]
    destino = resolver_arquivo(bloco, base_padrao, cwd)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8-sig")   # com BOM: o Bloco de Notas acerta os acentos
    return destino
