"""Utilidades comuns ao smoke e ao benchmark: cliente HTTP e imagens de exemplo."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx2

DEFAULT_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")

# Imagens de exemplo publicadas junto do classificador no Hub (recortes do
# conjunto "Brazilian food images", CC BY 4.0). São baixadas para .cache/, que
# não é versionada.
EXAMPLES_BASE = "https://huggingface.co/aitalo/convnext-tiny-comida-brasileira/resolve/main/exemplos"
EXAMPLE_IMAGES = ["rice0003.jpg", "fries0001.jpg"]
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "exemplos"


def make_client(url: str) -> httpx2.Client:
    headers = {}
    if os.environ.get("API_KEY"):
        headers["X-API-Key"] = os.environ["API_KEY"]
    # Timeout longo: uma geração em CPU leva segundos e as requisições fazem fila.
    return httpx2.Client(base_url=url, headers=headers, timeout=300.0)


def check_health(client: httpx2.Client) -> dict:
    try:
        r = client.get("/health")
    except httpx2.HTTPError as exc:
        sys.exit(f"Não consegui falar com a API em {client.base_url}: {exc}\nEla está rodando?")
    body = r.json()
    if r.status_code != 200:
        sys.exit(f"A API respondeu, mas não está pronta: {body}")
    return body


def example_image(name: str) -> bytes:
    path = CACHE_DIR / name
    if not path.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        r = httpx2.get(f"{EXAMPLES_BASE}/{name}", follow_redirects=True, timeout=60.0)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path.read_bytes()
