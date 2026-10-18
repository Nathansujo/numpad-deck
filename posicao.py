"""Posição de clique relativa a uma janela: a conta que faz o ponto acompanhar o programa quando ele
muda de tamanho ou de lugar. Sem nada do Windows (testável em qualquer sistema).

rect = (esquerda, topo, largura, altura) da área útil da janela (sem a barra de título), em pixels da tela.
"""
from __future__ import annotations

ANCORAS = ("proporcional", "topo_esq", "topo_dir", "baixo_esq", "baixo_dir")
ROTULO_ANCORA = {
    "proporcional": "proporcional",
    "topo_esq": "a partir do canto superior esquerdo",
    "topo_dir": "a partir do canto superior direito",
    "baixo_esq": "a partir do canto inferior esquerdo",
    "baixo_dir": "a partir do canto inferior direito",
}


class ForaDaJanela(ValueError):
    """O ponto marcado não está dentro da área útil da janela."""


def calcular_ponto(b: dict, rect) -> tuple[int, int]:
    """Ponto da tela (x, y) que o bloco descreve, dado onde a janela está agora."""
    esq, topo, larg, alt = rect
    if larg <= 0 or alt <= 0:
        raise ValueError("A janela não tem área visível (está minimizada?).")
    ancora = b["ancora"]
    if ancora == "proporcional":
        x, y = esq + b["rx"] * (larg - 1), topo + b["ry"] * (alt - 1)
    else:
        x = esq + b["dx"] if ancora.endswith("esq") else esq + larg - 1 - b["dx"]
        y = topo + b["dy"] if ancora.startswith("topo") else topo + alt - 1 - b["dy"]
    # nunca clica fora da janela, mesmo se ela ficou menor do que o deslocamento marcado
    return round(min(max(x, esq), esq + larg - 1)), round(min(max(y, topo), topo + alt - 1))


def referencia(x: int, y: int, rect, ancora: str) -> dict:
    """Campos do bloco (rx, ry ou dx, dy) para o ponto (x, y) marcado agora na janela."""
    esq, topo, larg, alt = rect
    if not (esq <= x < esq + larg and topo <= y < topo + alt):
        raise ForaDaJanela("Clique dentro da janela, abaixo da barra de título.")
    if ancora == "proporcional":
        return {"rx": round((x - esq) / max(1, larg - 1), 4), "ry": round((y - topo) / max(1, alt - 1), 4)}
    dx = x - esq if ancora.endswith("esq") else esq + larg - 1 - x
    dy = y - topo if ancora.startswith("topo") else topo + alt - 1 - y
    return {"dx": int(dx), "dy": int(dy)}
