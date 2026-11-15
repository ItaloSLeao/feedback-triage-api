"""Teste de integração com os modelos reais. Fica fora da execução padrão.

    pytest -m slow

Baixa cerca de 1,1 GB do Hugging Face Hub na primeira vez e usa uns 2 GB de RAM.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import image_bytes

pytestmark = pytest.mark.slow

AVALIACOES = [
    "Produto chegou antes do prazo e muito bem embalado. Recomendo a loja.",
    "Comprei duas unidades e só veio uma. Já mandei três e-mails e ninguém responde.",
    "Ainda não recebi meu pedido e o prazo já venceu faz dez dias.",
]


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(settings=Settings.from_env())) as c:
        assert c.get("/health").json()["modelos"] == {"extrator": True, "classificador": True}
        yield c


@pytest.mark.parametrize("texto", AVALIACOES)
def test_extrator_real_devolve_json_valido(client, texto):
    r = client.post("/v1/review/extract", json={"texto": texto})
    assert r.status_code == 200
    body = r.json()
    assert body["valido"] is True, f"saída inválida: {body['saida_bruta']!r}"
    assert body["sentimento"] in {"positivo", "neutro", "negativo"}
    assert set(body["aspectos"]) == {"entrega", "produto", "atendimento", "preco"}
    assert isinstance(body["requer_acao"], bool)


def test_classificador_real_responde_no_formato_esperado(client):
    # Imagem de cor única: não importa a classe, só o formato da resposta.
    r = client.post("/v1/food/classify", files={"imagem": ("x.png", image_bytes("PNG", (224, 224)), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert len(body["top3"]) == 3
    assert 0.0 <= body["confianca"] <= 1.0
    assert body["rejeitado"] is (body["classe"] is None)
