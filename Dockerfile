FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/cache/huggingface

WORKDIR /srv

# torch e torchvision vêm do índice de wheels só de CPU do PyTorch: a imagem fica
# bem menor do que com o pacote padrão do PyPI, que traz as bibliotecas CUDA.
# As versões são lidas do requirements.txt para existir um lugar só para mudar.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        $(grep -E '^(torch|torchvision)==' requirements.txt) \
    && pip install -r requirements.txt

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /cache/huggingface \
    && chown -R app:app /cache

COPY app ./app

USER app
EXPOSE 8000

# start-period longo: na primeira subida os modelos (cerca de 1,1 GB) são baixados.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# Um único worker: cada worker carregaria uma cópia dos modelos na RAM.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
