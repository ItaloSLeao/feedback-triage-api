"""Classificador de alimentos: imagem -> uma entre 20 classes, com rejeição.

Origem: adaptado de src/predict.py do repositório ml-image-classifier
(https://github.com/ItaloSLeao/ml-image-classifier, commit 9427523). Foram
mantidos o pré-processamento (AutoImageProcessor do próprio modelo, imagem em
RGB), o top-3 e a rejeição por limiar lido de limiar.json. Mudou só o que a API
precisa: dispositivo/precisão configuráveis e inference_mode.

Abaixo do limiar a resposta vem com classe None e rejeitado True. O limiar mede
baixa confiança; ele não é um detector de "isto não é comida".
"""

from __future__ import annotations

import json
from pathlib import Path

THRESHOLD_FILE = "limiar.json"


def load_threshold(model_id: str) -> float:
    local = Path(model_id) / THRESHOLD_FILE
    if local.exists():
        path = local
    elif Path(model_id).exists():
        raise FileNotFoundError(f"{local} não existe na pasta do modelo")
    else:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(model_id, THRESHOLD_FILE)
    return float(json.loads(Path(path).read_text(encoding="utf-8"))["limiar"])


class Classifier:
    def __init__(self, model_id: str, device: str = "auto", threshold: float | None = None):
        import torch
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        from app.runtime import pick_device

        self._torch = torch
        self.model_id = model_id
        self.device, self.dtype = pick_device(device)
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = (
            AutoModelForImageClassification.from_pretrained(model_id, dtype=self.dtype).to(self.device).eval()
        )
        self.threshold = load_threshold(model_id) if threshold is None else threshold

    def predict(self, image) -> dict:
        """Classifica uma PIL.Image (bloqueante; chame fora do loop de eventos)."""
        pixels = self.processor(image.convert("RGB"), return_tensors="pt")["pixel_values"]
        pixels = pixels.to(self.device, dtype=self.dtype)
        with self._torch.inference_mode():
            probs = self.model(pixel_values=pixels).logits[0].float().softmax(-1).cpu()
        conf, ids = probs.topk(min(3, len(probs)))
        id2label = self.model.config.id2label
        top3 = [{"classe": id2label[int(i)], "confianca": float(c)} for c, i in zip(conf, ids)]
        rejected = top3[0]["confianca"] < self.threshold
        return {
            "classe": None if rejected else top3[0]["classe"],
            "confianca": top3[0]["confianca"],
            "top3": top3,
            "rejeitado": rejected,
        }
