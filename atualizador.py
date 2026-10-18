"""Atualização automática pelo GitHub Releases: ao abrir, vê se existe uma versão mais nova do
NumpadDeck.exe, baixa, confere, troca o arquivo e o programa reinicia.

Como trocar um .exe em uso: o Windows deixa RENOMEAR um programa que está rodando (só não deixa apagar
ou sobrescrever). Então: NumpadDeck.exe -> NumpadDeck.antigo.exe, NumpadDeck.novo.exe -> NumpadDeck.exe.
Nada aqui depende do Windows (os testes rodam em qualquer sistema).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

REPO = "Nathansujo/numpad-deck"
NOME_ASSET = "NumpadDeck.exe"
LIMITE_BYTES = 300 * 1024 * 1024
_UA = {"User-Agent": "NumpadDeck-Atualizador"}


class ErroAtualizacao(Exception):
    """Não deu para consultar, baixar ou instalar (aparece como aviso, o programa segue na versão atual)."""


def versao_tupla(tag) -> tuple | None:
    """'v1.2.3' -> (1, 2, 3). Qualquer outra coisa ('dev', 'main') -> None."""
    m = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", (tag or "").strip())
    return tuple(int(x or 0) for x in m.groups()) if m else None


def consultar_ultima(repo: str = REPO, api_base: str = "https://api.github.com", timeout: float = 6) -> dict | None:
    """Última release publicada: {"tag", "url", "tamanho", "sha256"}; None se não houver release com o .exe."""
    req = urllib.request.Request(f"{api_base}/repos/{repo}/releases/latest",
                                 headers={**_UA, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise ErroAtualizacao(f"O GitHub respondeu {e.code} ao procurar atualização.") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ErroAtualizacao(f"Sem conexão com o GitHub ({getattr(e, 'reason', e)}).") from None
    if not isinstance(dados, dict):
        return None
    for ativo in dados.get("assets") or []:
        if isinstance(ativo, dict) and ativo.get("name") == NOME_ASSET and isinstance(ativo.get("browser_download_url"), str):
            digest = ativo.get("digest") if isinstance(ativo.get("digest"), str) else ""
            return {"tag": str(dados.get("tag_name", "")), "url": ativo["browser_download_url"],
                    "tamanho": ativo.get("size") if isinstance(ativo.get("size"), int) else None,
                    "sha256": digest[7:].lower() if digest.startswith("sha256:") else ""}
    return None


class _SoHttps(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("redirecionamento para endereço não seguro")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def baixar(info: dict, destino: Path, repo: str = REPO, timeout: float = 60, exigir_https: bool = True) -> Path:
    """Baixa o .exe para `destino`, conferindo origem, tamanho, assinatura 'MZ' e SHA-256 (quando o GitHub informa)."""
    if exigir_https and not info["url"].startswith(f"https://github.com/{repo}/releases/download/"):
        raise ErroAtualizacao("Endereço de download fora do repositório oficial: atualização recusada.")
    abridor = urllib.request.build_opener(_SoHttps) if exigir_https else urllib.request.build_opener()
    tmp = destino.with_name(destino.name + ".parte")
    h, total = hashlib.sha256(), 0
    try:
        with abridor.open(urllib.request.Request(info["url"], headers=_UA), timeout=timeout) as r, open(tmp, "wb") as f:
            while True:
                bloco = r.read(65536)
                if not bloco:
                    break
                total += len(bloco)
                if total > LIMITE_BYTES:
                    raise ErroAtualizacao("Arquivo grande demais: atualização recusada.")
                f.write(bloco)
                h.update(bloco)
        if info.get("tamanho") is not None and total != info["tamanho"]:
            raise ErroAtualizacao("Download incompleto (tamanho diferente do anunciado).")
        with open(tmp, "rb") as f:
            if f.read(2) != b"MZ":
                raise ErroAtualizacao("O arquivo baixado não é um programa do Windows: atualização recusada.")
        if info.get("sha256") and h.hexdigest() != info["sha256"]:
            raise ErroAtualizacao("O arquivo baixado não confere com o SHA-256 da release: atualização recusada.")
        os.replace(tmp, destino)
        return destino
    except (urllib.error.URLError, OSError) as e:
        raise ErroAtualizacao(f"Não consegui baixar a atualização ({getattr(e, 'reason', e)}).") from None
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _nome(exe: Path, sufixo: str) -> Path:
    return exe.with_name(f"{exe.stem}.{sufixo}{exe.suffix}")


def trocar(exe: Path, novo: Path) -> None:
    """Põe `novo` no lugar de `exe` (que pode estar rodando), guardando o anterior como .antigo."""
    antigo = _nome(exe, "antigo")
    try:
        if antigo.exists():
            antigo.unlink()
        os.replace(exe, antigo)
    except OSError as e:
        raise ErroAtualizacao(f"Não consegui substituir o programa (pasta protegida?): {e}") from None
    try:
        os.replace(novo, exe)
    except OSError as e:
        os.replace(antigo, exe)    # desfaz: o programa antigo continua no lugar
        raise ErroAtualizacao(f"Não consegui instalar a atualização: {e}") from None


def limpar_restos(exe: Path) -> None:
    for sufixo in ("antigo", "novo"):
        for arq in (_nome(exe, sufixo), _nome(exe, sufixo).with_name(_nome(exe, sufixo).name + ".parte")):
            try:
                arq.unlink()
            except OSError:
                pass


def verificar_e_atualizar(versao_atual: str, exe: Path, repo: str = REPO, api_base: str = "https://api.github.com",
                          exigir_https: bool = True, ao_baixar=None) -> dict:
    """{"status": "dev" | "atual" | "atualizado", "tag": ...}. Levanta ErroAtualizacao se algo falhar."""
    atual = versao_tupla(versao_atual)
    if atual is None:
        return {"status": "dev", "tag": versao_atual}
    info = consultar_ultima(repo, api_base)
    nova = versao_tupla(info["tag"]) if info else None
    if info is None or nova is None or nova <= atual:
        return {"status": "atual", "tag": versao_atual}
    if ao_baixar:
        ao_baixar(info["tag"])
    novo = baixar(info, _nome(exe, "novo"), repo, exigir_https=exigir_https)
    try:
        trocar(exe, novo)
    finally:
        try:
            novo.unlink()
        except OSError:
            pass
    return {"status": "atualizado", "tag": info["tag"]}
