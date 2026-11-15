"""Testes rápidos da API com dublês no lugar dos modelos."""

from __future__ import annotations

import logging

import httpx2
import pytest

from app.config import Settings
from app.main import create_app
from tests.conftest import FakeClassifier, FakeExtractor, image_bytes, review_json

JPEG = ("prato.jpg", image_bytes("JPEG"), "image/jpeg")


# ---------- /health ----------


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["modelos"] == {"extrator": True, "classificador": True}


def test_health_degradado_quando_falta_modelo(make_client):
    r = make_client(classifier=None).get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degradado"
    assert r.json()["modelos"] == {"extrator": True, "classificador": False}


def test_rota_responde_503_sem_modelo(make_client):
    c = make_client(extractor=None, classifier=None)
    assert c.post("/v1/review/extract", json={"texto": "ok"}).status_code == 503
    assert c.post("/v1/food/classify", files={"imagem": JPEG}).status_code == 503
    assert c.post("/v1/feedback/analyze", data={"texto": "ok"}).status_code == 503


# ---------- /v1/review/extract ----------


def test_extract_saida_valida(client):
    r = client.post("/v1/review/extract", json={"texto": "  Não chegou.  "})
    assert r.status_code == 200
    body = r.json()
    assert body["valido"] is True
    assert body["sentimento"] == "negativo"
    assert body["aspectos"] == {"entrega": "negativo", "produto": None, "atendimento": None, "preco": None}
    assert body["requer_acao"] is True
    assert body["saida_bruta"] is None
    assert body["latencia_ms"] >= 0
    assert "X-Request-ID" in r.headers


@pytest.mark.parametrize(
    "raw",
    [
        "não sei responder",  # nenhum JSON
        '{"sentimento": "negativo", "aspectos": {',  # JSON cortado
        '{"sentimento": "furioso", "aspectos": {}, "requer_acao": true}',  # JSON fora do esquema
    ],
)
def test_extract_saida_invalida_nao_e_escondida(make_client, raw):
    r = make_client(extractor=FakeExtractor(raw)).post("/v1/review/extract", json={"texto": "qualquer"})
    assert r.status_code == 200
    body = r.json()
    assert body["valido"] is False
    assert body["saida_bruta"] == raw
    assert body["sentimento"] is None and body["aspectos"] is None and body["requer_acao"] is None


@pytest.mark.parametrize("texto", ["", "   \n\t "])
def test_extract_texto_vazio(client, texto):
    r = client.post("/v1/review/extract", json={"texto": texto})
    assert r.status_code == 422
    assert "vazio" in r.json()["detail"]


def test_extract_limite_de_2000_caracteres(make_client):
    fake = FakeExtractor()
    c = make_client(extractor=fake)
    assert c.post("/v1/review/extract", json={"texto": "a" * 2000}).status_code == 200
    r = c.post("/v1/review/extract", json={"texto": "a" * 2001})
    assert r.status_code == 422
    assert "2000" in r.json()["detail"]
    assert len(fake.calls) == 1  # o texto longo nem chegou ao modelo


@pytest.mark.parametrize("payload", [{}, {"texto": 123}, {"texto": None}])
def test_extract_corpo_invalido(client, payload):
    r = client.post("/v1/review/extract", json=payload)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and "texto" in r.json()["detail"]


def test_extract_corpo_que_nao_e_json(client):
    r = client.post("/v1/review/extract", content=b"isto nao e json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


# ---------- /v1/food/classify ----------


@pytest.mark.parametrize("fmt,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_classify_formatos_aceitos(client, fmt, mime):
    r = client.post("/v1/food/classify", files={"imagem": ("x", image_bytes(fmt), mime)})
    assert r.status_code == 200
    body = r.json()
    assert body["classe"] == "arroz" and body["rejeitado"] is False
    assert body["confianca"] == pytest.approx(0.9)
    assert [t["classe"] for t in body["top3"]] == ["arroz", "feijão", "farofa"]


def test_classify_rejeitado(make_client):
    r = make_client(classifier=FakeClassifier(rejeitado=True)).post("/v1/food/classify", files={"imagem": JPEG})
    assert r.status_code == 200
    assert r.json()["classe"] is None and r.json()["rejeitado"] is True
    assert len(r.json()["top3"]) == 3


def test_classify_arquivo_que_nao_e_imagem(make_client):
    fake = FakeClassifier()
    r = make_client(classifier=fake).post(
        "/v1/food/classify", files={"imagem": ("prato.jpg", b"isto nao e uma imagem" * 50, "image/jpeg")}
    )
    assert r.status_code == 422
    assert "corrompido" in r.json()["detail"]
    assert fake.calls == 0


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_classify_imagem_truncada(make_client, fmt):
    fake = FakeClassifier()
    data = image_bytes(fmt, size=(400, 300))
    r = make_client(classifier=fake).post(
        "/v1/food/classify", files={"imagem": ("prato", data[: len(data) // 2], "image/jpeg")}
    )
    assert r.status_code == 422
    assert "corrompido" in r.json()["detail"]
    assert fake.calls == 0


def test_classify_formato_nao_suportado(client):
    # GIF válido, mas declarado como JPEG: vale o conteúdo, não o Content-Type.
    r = client.post("/v1/food/classify", files={"imagem": ("prato.jpg", image_bytes("GIF"), "image/jpeg")})
    assert r.status_code == 415
    assert "JPEG, PNG ou WEBP" in r.json()["detail"]


def test_classify_imagem_acima_do_limite(make_client):
    c = make_client(max_image_bytes=1000)
    grande = image_bytes("PNG", size=(64, 64)) + b"\0" * 2000
    r = c.post("/v1/food/classify", files={"imagem": ("prato.png", grande, "image/png")})
    assert r.status_code == 413


def test_limite_padrao_de_imagem_e_5_mb():
    assert Settings().max_image_bytes == 5 * 1024 * 1024
    assert Settings().max_text_chars == 2000


def test_classify_arquivo_vazio_ou_ausente(client):
    assert client.post("/v1/food/classify", files={"imagem": ("prato.jpg", b"", "image/jpeg")}).status_code == 422
    r = client.post("/v1/food/classify", files={"outro": JPEG})
    assert r.status_code == 422
    assert "imagem" in r.json()["detail"]


# ---------- /v1/feedback/analyze ----------


@pytest.mark.parametrize(
    "sentimento,requer_acao,esperada",
    [
        ("negativo", True, "alta"),
        ("negativo", False, "media"),
        ("neutro", True, "media"),
        ("positivo", True, "media"),
        ("neutro", False, "baixa"),
        ("positivo", False, "baixa"),
    ],
)
def test_analyze_regra_de_prioridade(make_client, sentimento, requer_acao, esperada):
    c = make_client(extractor=FakeExtractor(review_json(sentimento, requer_acao)))
    r = c.post("/v1/feedback/analyze", data={"texto": "avaliação"})
    assert r.status_code == 200
    body = r.json()
    assert body["prioridade"] == esperada
    assert body["analise_texto"]["valido"] is True
    assert body["prato"] is None  # sem imagem
    assert body["latencia_ms"] >= 0


def test_analyze_saida_invalida_da_prioridade_indeterminada(make_client):
    c = make_client(extractor=FakeExtractor("texto solto, sem JSON"))
    r = c.post("/v1/feedback/analyze", data={"texto": "avaliação"}, files={"imagem": JPEG})
    assert r.status_code == 200
    body = r.json()
    assert body["prioridade"] == "indeterminada"
    assert body["analise_texto"]["valido"] is False
    assert body["analise_texto"]["saida_bruta"] == "texto solto, sem JSON"
    assert body["prato"] == {"classe": "arroz", "confianca": pytest.approx(0.9)}  # a imagem ainda é analisada


def test_analyze_com_imagem(client):
    r = client.post("/v1/feedback/analyze", data={"texto": "avaliação"}, files={"imagem": JPEG})
    assert r.status_code == 200
    assert r.json()["prato"] == {"classe": "arroz", "confianca": pytest.approx(0.9)}
    assert r.json()["prioridade"] == "alta"


def test_analyze_imagem_rejeitada_vira_prato_nulo(make_client):
    c = make_client(classifier=FakeClassifier(rejeitado=True))
    r = c.post("/v1/feedback/analyze", data={"texto": "avaliação"}, files={"imagem": JPEG})
    assert r.status_code == 200
    assert r.json()["prato"] is None


def test_analyze_imagem_corrompida_nao_gasta_geracao(make_client):
    fake = FakeExtractor()
    c = make_client(extractor=fake)
    r = c.post(
        "/v1/feedback/analyze",
        data={"texto": "avaliação"},
        files={"imagem": ("prato.png", b"\x89PNG\r\n\x1a\n lixo", "image/png")},
    )
    assert r.status_code == 422
    assert fake.calls == []


def test_analyze_sem_classificador_funciona_se_nao_houver_imagem(make_client):
    c = make_client(classifier=None)
    assert c.post("/v1/feedback/analyze", data={"texto": "avaliação"}).status_code == 200
    assert c.post("/v1/feedback/analyze", data={"texto": "avaliação"}, files={"imagem": JPEG}).status_code == 503


def test_analyze_valida_texto(client):
    assert client.post("/v1/feedback/analyze", data={"texto": "   "}).status_code == 422
    assert client.post("/v1/feedback/analyze", data={"texto": "a" * 2001}).status_code == 422
    r = client.post("/v1/feedback/analyze", files={"imagem": JPEG})
    assert r.status_code == 422
    assert "texto" in r.json()["detail"]


# ---------- autenticação ----------

ROTAS_V1 = [
    ("/v1/review/extract", {"json": {"texto": "ok"}}),
    ("/v1/food/classify", {"files": {"imagem": JPEG}}),
    ("/v1/feedback/analyze", {"data": {"texto": "ok"}}),
]


@pytest.mark.parametrize("rota,kwargs", ROTAS_V1)
def test_sem_api_key_configurada_a_api_fica_aberta(client, rota, kwargs):
    assert client.post(rota, **kwargs).status_code == 200


@pytest.mark.parametrize("rota,kwargs", ROTAS_V1)
def test_api_key_configurada_exige_cabecalho(make_client, rota, kwargs):
    c = make_client(api_key="segredo-de-teste")
    assert c.post(rota, **kwargs).status_code == 401
    assert c.post(rota, headers={"X-API-Key": "errada"}, **kwargs).status_code == 401
    assert c.post(rota, headers={"X-API-Key": "segredo-de-teste"}, **kwargs).status_code == 200


def test_health_nao_exige_api_key(make_client):
    assert make_client(api_key="segredo-de-teste").get("/health").status_code == 200


def test_api_key_vem_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    assert Settings.from_env().api_key == "abc"
    monkeypatch.setenv("API_KEY", "")
    assert Settings.from_env().api_key is None


# ---------- logs e concorrência ----------


def test_log_nao_contem_texto_da_avaliacao(make_client, caplog):
    segredo = "TEXTO-CONFIDENCIAL-DO-CLIENTE"
    c = make_client(extractor=FakeExtractor("SAIDA-CRUA-" + segredo))
    with caplog.at_level(logging.DEBUG):
        c.post("/v1/review/extract", json={"texto": segredo})
        c.post("/v1/feedback/analyze", data={"texto": segredo}, files={"imagem": JPEG})
        c.post("/v1/review/extract", json={"texto": segredo + "x" * 2000})  # erro de validação
    assert caplog.text, "esperava ao menos uma linha de log por requisição"
    assert segredo not in caplog.text
    linha = next(r.getMessage() for r in caplog.records if "rota=/v1/review/extract" in r.getMessage())
    for campo in ("id=", "status=200", "latencia_ms=", "texto_chars=", "req_bytes="):
        assert campo in linha


@pytest.mark.anyio
async def test_uma_geracao_por_vez():
    fake = FakeExtractor(delay=0.05)
    app = create_app(settings=Settings(), extractor=fake, classifier=FakeClassifier(), load_models=False)
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://teste") as c:
            import asyncio

            respostas = await asyncio.gather(
                *[c.post("/v1/review/extract", json={"texto": f"avaliação {i}"}) for i in range(5)]
            )
    assert [r.status_code for r in respostas] == [200] * 5
    assert len(fake.calls) == 5
    assert fake.max_concurrent == 1


@pytest.fixture
def anyio_backend():
    return "asyncio"
