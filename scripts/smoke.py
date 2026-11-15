"""Teste de fumaça: chama a API que já está rodando e imprime resultados e latências.

    python scripts/smoke.py                      # http://127.0.0.1:8000
    python scripts/smoke.py --url http://host:8000
    API_KEY=... python scripts/smoke.py          # se a API exigir chave

Os textos abaixo são inventados para o teste; não são dados de clientes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _client import DEFAULT_URL, EXAMPLE_IMAGES, check_health, example_image, make_client  # noqa: E402

AVALIACOES = [
    ("fácil, positiva", "Entrega rápida, produto de ótima qualidade e preço justo. Recomendo."),
    ("fácil, negativa", "Ainda não recebi meu pedido e o prazo já venceu faz dez dias. Ninguém responde."),
    ("mista", "O produto é bom, mas a entrega atrasou uma semana."),
    ("sem relação com comida", "Pedi um carregador e veio um cabo que não serve no meu celular. Quero trocar."),
    ("muito curta", "Bom"),
]


def timed(call):
    t0 = time.perf_counter()
    r = call()
    return r, (time.perf_counter() - t0) * 1000


def show(titulo: str, r, ms: float) -> bool:
    print(f"\n[{titulo}] HTTP {r.status_code} em {ms:.0f} ms")
    try:
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    except ValueError:
        print(r.text)
    return r.status_code == 200


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--url", default=DEFAULT_URL)
    args = p.parse_args()

    client = make_client(args.url)
    health = check_health(client)
    print(f"API em {args.url}: {health['status']} | {health['ambiente'].get('cpu')}")

    ok = True
    invalidos = 0

    print("\n===== POST /v1/review/extract =====")
    for rotulo, texto in AVALIACOES:
        r, ms = timed(lambda: client.post("/v1/review/extract", json={"texto": texto}))
        print(f"\ntexto: {texto}")
        ok &= show(rotulo, r, ms)
        if r.status_code == 200 and not r.json()["valido"]:
            invalidos += 1

    print("\n===== POST /v1/food/classify =====")
    imagens = {nome: example_image(nome) for nome in EXAMPLE_IMAGES}
    for nome, dados in imagens.items():
        r, ms = timed(lambda: client.post("/v1/food/classify", files={"imagem": (nome, dados, "image/jpeg")}))
        ok &= show(nome, r, ms)

    print("\n===== POST /v1/feedback/analyze =====")
    nome, dados = next(iter(imagens.items()))
    texto = "A marmita chegou fria e faltou o feijão. Quero meu dinheiro de volta."
    r, ms = timed(
        lambda: client.post(
            "/v1/feedback/analyze", data={"texto": texto}, files={"imagem": (nome, dados, "image/jpeg")}
        )
    )
    print(f"\ntexto: {texto}")
    ok &= show(f"texto + {nome}", r, ms)

    print("\n===== resumo =====")
    print(f"respostas HTTP 200 em todas as chamadas: {'sim' if ok else 'NÃO'}")
    print(f"saídas do extrator que não eram JSON válido: {invalidos} de {len(AVALIACOES)}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
