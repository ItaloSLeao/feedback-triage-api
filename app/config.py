"""Configuração lida de variáveis de ambiente (ver .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _float_or_none(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    api_key: str | None = None
    extractor_model: str = "aitalo/qwen2.5-0.5b-avaliacoes-ptbr"
    classifier_model: str = "aitalo/convnext-tiny-comida-brasileira"
    max_new_tokens: int = 200
    # None = usa o valor do generation_config.json do modelo (1.1), como na avaliação.
    repetition_penalty: float | None = None
    torch_num_threads: int = 0  # 0 = padrão do PyTorch
    device: str = "auto"  # auto | cpu | cuda
    classifier_threshold: float | None = None  # None = limiar.json do repositório do modelo
    max_text_chars: int = 2000
    max_image_bytes: int = 5 * 1024 * 1024
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            api_key=os.environ.get("API_KEY", "").strip() or None,
            extractor_model=os.environ.get("EXTRACTOR_MODEL", "").strip() or d.extractor_model,
            classifier_model=os.environ.get("CLASSIFIER_MODEL", "").strip() or d.classifier_model,
            max_new_tokens=_int("MAX_NEW_TOKENS", d.max_new_tokens),
            repetition_penalty=_float_or_none("REPETITION_PENALTY"),
            torch_num_threads=_int("TORCH_NUM_THREADS", d.torch_num_threads),
            device=os.environ.get("DEVICE", "").strip().lower() or d.device,
            classifier_threshold=_float_or_none("CLASSIFIER_THRESHOLD"),
            max_text_chars=_int("MAX_TEXT_CHARS", d.max_text_chars),
            max_image_bytes=_int("MAX_IMAGE_BYTES", d.max_image_bytes),
            log_level=os.environ.get("LOG_LEVEL", "").strip().upper() or d.log_level,
        )
