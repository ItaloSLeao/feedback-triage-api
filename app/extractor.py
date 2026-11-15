"""Extrator de avaliações: texto -> JSON (sentimento, aspectos, problema, ação).

A geração segue o src/evaluate.py do repositório pt-review-extractor: mesmo
SYSTEM_PROMPT, chat template do tokenizer, decodificação gulosa e
max_new_tokens=200. Os demais parâmetros de geração (por exemplo o
repetition_penalty) vêm do generation_config.json do modelo, como na avaliação.
"""

from __future__ import annotations

from app.review_common import build_messages, parse_output


class Extractor:
    def __init__(
        self,
        model_id: str,
        device: str = "auto",
        max_new_tokens: int = 200,
        repetition_penalty: float | None = None,
    ):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from app.runtime import pick_device

        self._torch = torch
        self.model_id = model_id
        self.max_new_tokens = max_new_tokens
        # None mantém o repetition_penalty do generation_config.json do modelo.
        self.extra_generation_args = {} if repetition_penalty is None else {"repetition_penalty": repetition_penalty}
        self.device, self.dtype = pick_device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        # Os pesos no Hub estão em fp16; na CPU são convertidos para float32.
        self.model = AutoModelForCausalLM.from_pretrained(model_id, dtype=self.dtype).to(self.device).eval()

    def generate(self, text: str) -> str:
        """Devolve o texto cru gerado pelo modelo (bloqueante; chame fora do loop de eventos)."""
        tok = self.tokenizer
        prompt = tok.apply_chat_template(build_messages(text), tokenize=False, add_generation_prompt=True)
        enc = tok(prompt, return_tensors="pt").to(self.device)
        with self._torch.inference_mode():
            out = self.model.generate(
                **enc,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=tok.pad_token_id,
                **self.extra_generation_args,
            )
        return tok.decode(out[0, enc.input_ids.shape[1] :], skip_special_tokens=True)


def to_result(raw: str) -> dict:
    """Converte a saída crua no corpo da resposta. Saída inválida não é escondida."""
    obj = parse_output(raw)
    if obj is None:
        return {
            "valido": False,
            "sentimento": None,
            "aspectos": None,
            "problema_principal": None,
            "requer_acao": None,
            "saida_bruta": raw,
        }
    return {
        "valido": True,
        "sentimento": obj["sentimento"],
        "aspectos": obj["aspectos"],
        "problema_principal": obj["problema_principal"],
        "requer_acao": obj["requer_acao"],
        "saida_bruta": None,
    }
