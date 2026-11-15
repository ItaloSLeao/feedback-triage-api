"""Testes das funções puras: regra de prioridade e validação da saída do extrator."""

from __future__ import annotations

import pytest

from app.extractor import to_result
from app.priority import compute_priority
from app.review_common import SYSTEM_PROMPT, build_messages, parse_output
from tests.conftest import review_json


@pytest.mark.parametrize(
    "analise,esperada",
    [
        ({"valido": True, "sentimento": "negativo", "requer_acao": True}, "alta"),
        ({"valido": True, "sentimento": "negativo", "requer_acao": False}, "media"),
        ({"valido": True, "sentimento": "positivo", "requer_acao": True}, "media"),
        ({"valido": True, "sentimento": "neutro", "requer_acao": False}, "baixa"),
        ({"valido": False, "sentimento": None, "requer_acao": None}, "indeterminada"),
        ({}, "indeterminada"),
    ],
)
def test_compute_priority(analise, esperada):
    assert compute_priority(analise) == esperada


def test_build_messages_usa_o_prompt_do_treino():
    msgs = build_messages("  Chegou quebrado.  ")
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert msgs[1] == {"role": "user", "content": "Avaliação: Chegou quebrado."}


def test_parse_output_aceita_json_com_texto_em_volta():
    assert parse_output("Claro:\n" + review_json() + "\nfim")["sentimento"] == "negativo"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "[]",
        '{"sentimento": "negativo"}',
        review_json().replace('"negativo", "aspectos"', '"pessimo", "aspectos"'),
        review_json().replace("true", '"sim"'),
        review_json().replace('"preco": null', '"sabor": null'),
    ],
)
def test_parse_output_rejeita_fora_do_esquema(raw):
    assert parse_output(raw) is None


def test_to_result_guarda_a_saida_bruta_so_quando_invalida():
    ok = to_result(review_json())
    assert ok["valido"] is True and ok["saida_bruta"] is None
    ruim = to_result("{quebrado")
    assert ruim["valido"] is False and ruim["saida_bruta"] == "{quebrado"
