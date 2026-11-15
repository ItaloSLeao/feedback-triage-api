"""Regra de prioridade do feedback (documentada em docs/regras.md)."""

from __future__ import annotations


def compute_priority(analise: dict) -> str:
    """alta, media, baixa ou indeterminada, a partir do resultado do extrator."""
    if not analise.get("valido"):
        return "indeterminada"
    negativo = analise.get("sentimento") == "negativo"
    requer_acao = analise.get("requer_acao") is True
    if negativo and requer_acao:
        return "alta"
    if negativo or requer_acao:
        return "media"
    return "baixa"
