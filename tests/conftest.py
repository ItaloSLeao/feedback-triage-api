"""Dublês dos dois modelos e fixtures. Nada aqui importa torch nem baixa modelos."""

from __future__ import annotations

import io
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app


def review_json(sentimento="negativo", requer_acao=True, problema="produto não chegou") -> str:
    return json.dumps(
        {
            "sentimento": sentimento,
            "aspectos": {"entrega": "negativo", "produto": None, "atendimento": None, "preco": None},
            "problema_principal": problema,
            "requer_acao": requer_acao,
        },
        ensure_ascii=False,
    )


class FakeExtractor:
    """Devolve sempre a mesma saída crua e registra chamadas e concorrência."""

    def __init__(self, raw: str | None = None, delay: float = 0.0):
        self.raw = review_json() if raw is None else raw
        self.delay = delay
        self.calls: list[str] = []
        self.max_concurrent = 0
        self._running = 0
        self._lock = threading.Lock()

    def generate(self, text: str) -> str:
        with self._lock:
            self._running += 1
            self.max_concurrent = max(self.max_concurrent, self._running)
        try:
            time.sleep(self.delay)
            self.calls.append(text)
            return self.raw
        finally:
            with self._lock:
                self._running -= 1


class FakeClassifier:
    def __init__(self, rejeitado: bool = False):
        self.rejeitado = rejeitado
        self.calls = 0

    def predict(self, image) -> dict:
        assert isinstance(image, Image.Image)
        self.calls += 1
        top3 = [
            {"classe": "arroz", "confianca": 0.2 if self.rejeitado else 0.9},
            {"classe": "feijão", "confianca": 0.06},
            {"classe": "farofa", "confianca": 0.04},
        ]
        return {
            "classe": None if self.rejeitado else "arroz",
            "confianca": top3[0]["confianca"],
            "top3": top3,
            "rejeitado": self.rejeitado,
        }


def image_bytes(fmt: str = "JPEG", size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def make_client():
    """Cria um TestClient com dublês; o lifespan roda, mas nenhum modelo real é carregado."""
    clients = []

    def _make(extractor="default", classifier="default", **settings_kwargs) -> TestClient:
        app = create_app(
            settings=Settings(**settings_kwargs),
            extractor=FakeExtractor() if extractor == "default" else extractor,
            classifier=FakeClassifier() if classifier == "default" else classifier,
            load_models=False,
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()
