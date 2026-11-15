"""Prompt, montagem das mensagens e validação da saída do extrator.

Origem: copiado de src/common.py do repositório pt-review-extractor
(https://github.com/ItaloSLeao/pt-review-extractor, commit 531d55b).
Só o que a inferência usa foi trazido: ASPECTS, SENTIMENTS, ASPECT_VALUES,
SYSTEM_PROMPT, build_messages, parse_output e is_valid.

NÃO edite o SYSTEM_PROMPT nem build_messages aqui: o modelo foi treinado com
exatamente este texto, e qualquer diferença piora a taxa de JSON válido. Se o
prompt mudar no repositório de origem (e o modelo for retreinado), copie de novo.
"""

import json
import re

ASPECTS = ["entrega", "produto", "atendimento", "preco"]
SENTIMENTS = ["positivo", "neutro", "negativo"]
ASPECT_VALUES = ["positivo", "negativo", None]

SYSTEM_PROMPT = """Você extrai informações estruturadas de avaliações de clientes em português.
Responda APENAS com um objeto JSON válido, sem texto adicional, no formato:
{
  "sentimento": "positivo" | "neutro" | "negativo",
  "aspectos": {
    "entrega": "positivo" | "negativo" | null,
    "produto": "positivo" | "negativo" | null,
    "atendimento": "positivo" | "negativo" | null,
    "preco": "positivo" | "negativo" | null
  },
  "problema_principal": string curta (até 10 palavras) | null,
  "requer_acao": true | false
}
Regras:
- Use null para aspectos não mencionados.
- "entrega" cobre prazo, atraso, rastreio e não recebimento.
- "problema_principal" é null quando não há reclamação.
- "requer_acao" é true quando a empresa precisa agir (produto não recebido, defeito, item errado, pedido de contato)."""


def build_messages(text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Avaliação: {text.strip()}"},
    ]


def parse_output(raw: str) -> dict | None:
    """Extrai e valida o JSON. Retorna None se inválido."""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if is_valid(obj) else None


def is_valid(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    if obj.get("sentimento") not in SENTIMENTS:
        return False
    asp = obj.get("aspectos")
    if not isinstance(asp, dict) or set(asp) != set(ASPECTS):
        return False
    if any(asp[a] not in ASPECT_VALUES for a in ASPECTS):
        return False
    if not isinstance(obj.get("requer_acao"), bool):
        return False
    pp = obj.get("problema_principal")
    return pp is None or isinstance(pp, str)
