"""Validação das entradas. Todas as falhas viram HTTPException com mensagem clara."""

from __future__ import annotations

import io

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
# Limite de pixels depois de decodificar: um PNG pequeno em bytes pode virar
# gigabytes na memória (bomba de descompressão).
MAX_PIXELS = 40_000_000


def clean_text(texto: str, max_chars: int) -> str:
    texto = texto.strip()
    if not texto:
        raise HTTPException(422, "O campo 'texto' não pode ser vazio.")
    if len(texto) > max_chars:
        raise HTTPException(422, f"O campo 'texto' tem {len(texto)} caracteres; o máximo é {max_chars}.")
    return texto


async def read_image(upload: UploadFile, max_bytes: int) -> tuple[Image.Image, int]:
    """Lê e valida o upload. Devolve a imagem já decodificada e o tamanho em bytes."""
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"Imagem maior que o limite de {max_bytes / (1024 * 1024):.0f} MB.")
    if not data:
        raise HTTPException(422, "O campo 'imagem' veio vazio.")
    return decode_image(data), len(data)


def decode_image(data: bytes) -> Image.Image:
    # O formato é decidido pelo conteúdo do arquivo, não pelo Content-Type
    # informado pelo cliente (que pode estar errado ou ausente).
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
    except UnidentifiedImageError:
        raise HTTPException(422, "O arquivo enviado em 'imagem' não é uma imagem reconhecível ou está corrompido.")
    except Exception:
        raise HTTPException(422, "Não foi possível abrir a imagem: arquivo corrompido.")

    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(415, f"Formato de imagem não suportado ({fmt}). Envie JPEG, PNG ou WEBP.")
    if width * height > MAX_PIXELS:
        raise HTTPException(422, f"Imagem com {width}x{height} pixels; o máximo é {MAX_PIXELS // 1_000_000} megapixels.")

    try:
        image = Image.open(io.BytesIO(data))
        image.load()  # decodifica tudo agora; arquivo truncado falha aqui
    except Exception:
        raise HTTPException(422, "Não foi possível decodificar a imagem: arquivo corrompido ou truncado.")
    return image
