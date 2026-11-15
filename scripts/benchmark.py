"""Mede a latência p50/p95 dos endpoints de extração e de classificação.

    python scripts/benchmark.py              # 20 chamadas por endpoint
    python scripts/benchmark.py --n 50

Faz 1 chamada de aquecimento (descartada) e depois N chamadas em sequência para
cada endpoint, medindo o tempo visto pelo cliente (inclui o HTTP local). Grava
results/latencia.json, com a CPU e as versões informadas pelo /health da API, e
atualiza a tabela de latência do README a partir desse arquivo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _client import DEFAULT_URL, EXAMPLE_IMAGES, check_health, example_image, make_client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
README_BLOCK = re.compile(r"(<!-- latencia:inicio -->\n).*?(<!-- latencia:fim -->)", re.DOTALL)

# Textos inventados, de tamanhos variados: o tempo de geração depende
# principalmente do tamanho da saída, e ela muda pouco entre avaliações.
TEXTOS = [
    "Entrega rápida, produto de ótima qualidade e preço justo. Recomendo.",
    "Ainda não recebi meu pedido e o prazo já venceu faz dez dias. Ninguém responde.",
    "Chegou quebrado e ninguém me atende.",
    "Bom",
    "Pedi um carregador e veio um cabo que não serve no meu celular. Tentei falar com a loja pelo chat "
    "duas vezes e não tive resposta. Quero trocar ou receber o dinheiro de volta.",
]


def percentile(values: list[float], q: float) -> float:
    """Percentil com interpolação linear (mesma definição padrão do numpy)."""
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def measure(call, n: int) -> dict:
    call(0)  # aquecimento
    tempos = []
    for i in range(n):
        t0 = time.perf_counter()
        r = call(i)
        tempos.append((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            sys.exit(f"Chamada {i + 1} falhou com HTTP {r.status_code}: {r.text[:200]}")
        print(f"  {i + 1:>3}/{n}  {tempos[-1]:8.0f} ms", flush=True)
    return {
        "n": n,
        "p50_ms": round(percentile(tempos, 0.50), 1),
        "p95_ms": round(percentile(tempos, 0.95), 1),
        "media_ms": round(sum(tempos) / n, 1),
        "min_ms": round(min(tempos), 1),
        "max_ms": round(max(tempos), 1),
    }


def readme_table(result: dict) -> str:
    amb = result["ambiente"]
    v = amb["versoes"]
    linhas = [
        "| Endpoint | Chamadas | p50 (ms) | p95 (ms) |",
        "|---|---|---|---|",
    ]
    for rota, m in result["endpoints"].items():
        linhas.append(f"| `POST {rota}` | {m['n']} | {m['p50_ms']:.0f} | {m['p95_ms']:.0f} |")
    linhas += [
        "",
        f"Medido em {result['data'][:10]} com `scripts/benchmark.py`. CPU: {amb['cpu']} "
        f"({amb['nucleos_logicos']} núcleos lógicos, {amb['threads_torch']} threads no PyTorch). "
        f"Python {v['python']}, torch {v['torch']}, transformers {v['transformers']}, pillow {v['pillow']}.",
    ]
    return "\n".join(linhas) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--n", type=int, default=20, help="chamadas por endpoint (padrão: 20)")
    p.add_argument("--out", default=str(ROOT / "results" / "latencia.json"))
    p.add_argument("--no-readme", action="store_true", help="não atualizar a tabela do README")
    args = p.parse_args()

    client = make_client(args.url)
    health = check_health(client)
    imagem = example_image(EXAMPLE_IMAGES[0])

    endpoints = {}
    print("POST /v1/review/extract")
    endpoints["/v1/review/extract"] = measure(
        lambda i: client.post("/v1/review/extract", json={"texto": TEXTOS[i % len(TEXTOS)]}), args.n
    )
    print("POST /v1/food/classify")
    endpoints["/v1/food/classify"] = measure(
        lambda i: client.post("/v1/food/classify", files={"imagem": (EXAMPLE_IMAGES[0], imagem, "image/jpeg")}),
        args.n,
    )

    result = {
        "data": datetime.now().astimezone().isoformat(timespec="seconds"),
        "metodo": "1 chamada de aquecimento descartada; chamadas em sequência; tempo medido no cliente",
        "ambiente": health["ambiente"],
        "endpoints": endpoints,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nGravado em {out}\n")
    print(readme_table(result))

    if not args.no_readme:
        readme = ROOT / "README.md"
        texto = readme.read_text(encoding="utf-8")
        novo, trocas = README_BLOCK.subn(lambda m: m.group(1) + readme_table(result) + m.group(2), texto)
        if trocas:
            readme.write_text(novo, encoding="utf-8")
            print("Tabela de latência do README atualizada.")
        else:
            print("Não achei os marcadores de latência no README; tabela não atualizada.")


if __name__ == "__main__":
    main()
