"""API FastAPI que serve o extrator de avaliações e o classificador de alimentos.

Rodar localmente:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import schemas
from app.config import Settings
from app.extractor import to_result
from app.priority import compute_priority
from app.runtime import configure_threads, environment_info
from app.validation import clean_text, read_image

logger = logging.getLogger("api")

ERROS = {
    401: {"model": schemas.ErroOut, "description": "X-API-Key ausente ou incorreta"},
    422: {"model": schemas.ErroOut, "description": "Entrada inválida"},
    503: {"model": schemas.ErroOut, "description": "Modelo não carregado"},
}
ERROS_IMAGEM = {
    **ERROS,
    413: {"model": schemas.ErroOut, "description": "Imagem acima do limite de tamanho"},
    415: {"model": schemas.ErroOut, "description": "Formato de imagem não suportado"},
}


def _ms_since(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _load_models(app: FastAPI) -> None:
    """Carrega os modelos que não foram injetados. Falha de carga não derruba a API:
    o /health mostra qual modelo faltou e as rotas dele respondem 503."""
    settings: Settings = app.state.settings
    configure_threads(settings.torch_num_threads)

    if app.state.extractor is None:
        try:
            from app.extractor import Extractor

            t0 = time.perf_counter()
            app.state.extractor = Extractor(settings.extractor_model, settings.device, settings.max_new_tokens)
            logger.info("extrator carregado modelo=%s tempo_ms=%.0f", settings.extractor_model, _ms_since(t0))
        except Exception:
            logger.exception("falha ao carregar o extrator modelo=%s", settings.extractor_model)

    if app.state.classifier is None:
        try:
            from app.classifier import Classifier

            t0 = time.perf_counter()
            app.state.classifier = Classifier(
                settings.classifier_model, settings.device, settings.classifier_threshold
            )
            logger.info(
                "classificador carregado modelo=%s limiar=%.4f tempo_ms=%.0f",
                settings.classifier_model,
                app.state.classifier.threshold,
                _ms_since(t0),
            )
        except Exception:
            logger.exception("falha ao carregar o classificador modelo=%s", settings.classifier_model)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uma geração por vez: o semáforo é criado aqui para pertencer ao loop do servidor.
    app.state.generation_semaphore = asyncio.Semaphore(1)
    if app.state.load_models:
        _load_models(app)
    app.state.environment = environment_info()
    yield
    app.state.extractor = None
    app.state.classifier = None


async def require_api_key(request: Request) -> None:
    expected = request.app.state.settings.api_key
    if not expected:
        return
    received = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(received.encode(), expected.encode()):
        raise HTTPException(401, "Cabeçalho X-API-Key ausente ou incorreto.")


def _note(request: Request, **fields) -> None:
    """Acrescenta campos (só tamanhos e resultados, nunca conteúdo) ao log da requisição."""
    request.state.log_fields.update(fields)


async def _extract(request: Request, texto: str) -> dict:
    extractor = request.app.state.extractor
    if extractor is None:
        raise HTTPException(503, "O extrator não está carregado. Consulte /health e os logs do servidor.")
    async with request.app.state.generation_semaphore:
        raw = await run_in_threadpool(extractor.generate, texto)
    result = to_result(raw)
    _note(request, texto_chars=len(texto), saida_chars=len(raw), valido=result["valido"])
    return result


async def _classify(request: Request, upload: UploadFile) -> dict:
    classifier = request.app.state.classifier
    if classifier is None:
        raise HTTPException(503, "O classificador não está carregado. Consulte /health e os logs do servidor.")
    image, size = await read_image(upload, request.app.state.settings.max_image_bytes)
    result = await run_in_threadpool(classifier.predict, image)
    _note(request, imagem_bytes=size, rejeitado=result["rejeitado"])
    return result


router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@router.post("/review/extract", response_model=schemas.ReviewOutTimed, responses=ERROS)
async def review_extract(body: schemas.ReviewIn, request: Request):
    t0 = time.perf_counter()
    texto = clean_text(body.texto, request.app.state.settings.max_text_chars)
    result = await _extract(request, texto)
    return {**result, "latencia_ms": _ms_since(t0)}


@router.post("/food/classify", response_model=schemas.FoodOut, responses=ERROS_IMAGEM)
async def food_classify(request: Request, imagem: UploadFile = File(...)):
    t0 = time.perf_counter()
    result = await _classify(request, imagem)
    return {**result, "latencia_ms": _ms_since(t0)}


@router.post("/feedback/analyze", response_model=schemas.FeedbackOut, responses=ERROS_IMAGEM)
async def feedback_analyze(
    request: Request,
    texto: str = Form(...),
    imagem: UploadFile | None = File(None),
):
    t0 = time.perf_counter()
    texto = clean_text(texto, request.app.state.settings.max_text_chars)
    if request.app.state.extractor is None:
        raise HTTPException(503, "O extrator não está carregado. Consulte /health e os logs do servidor.")

    # A imagem é validada e classificada antes da geração: se ela for inválida,
    # o cliente recebe o erro sem esperar os segundos do extrator.
    prato = None
    if imagem is not None:
        classificacao = await _classify(request, imagem)
        if not classificacao["rejeitado"]:
            prato = {"classe": classificacao["classe"], "confianca": classificacao["confianca"]}

    analise = await _extract(request, texto)
    prioridade = compute_priority(analise)
    _note(request, prioridade=prioridade)
    return {"analise_texto": analise, "prato": prato, "prioridade": prioridade, "latencia_ms": _ms_since(t0)}


def _validation_message(exc: RequestValidationError) -> str:
    # Só o campo e o motivo. O valor recebido não entra na resposta.
    parts = []
    for err in exc.errors():
        campo = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "header"))
        if err["type"] == "missing":
            motivo = "campo obrigatório ausente"
        elif err["type"] in ("json_invalid", "model_attributes_type", "dict_type"):
            motivo = "o corpo precisa ser um objeto JSON válido"
        elif err["type"] == "string_type":
            motivo = "precisa ser um texto"
        else:
            motivo = err["msg"]
        parts.append(f"{campo}: {motivo}" if campo else motivo)
    return "; ".join(parts) or "Entrada inválida."


def create_app(
    settings: Settings | None = None,
    extractor=None,
    classifier=None,
    load_models: bool = True,
) -> FastAPI:
    """Monta a aplicação. Os testes passam dublês em extractor/classifier e
    load_models=False para não carregar (nem baixar) os modelos reais."""
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    app = FastAPI(
        title="API de análise de feedback",
        description="Extração estruturada de avaliações em PT-BR e classificação de alimentos, em CPU.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.extractor = extractor
    app.state.classifier = classifier
    app.state.load_models = load_models
    app.state.environment = {}

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.log_fields = {}
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Nunca logar corpo, texto ou imagem: só id, rota, status, latência e tamanhos.
            extras = "".join(f" {k}={v}" for k, v in request.state.log_fields.items())
            logger.info(
                "id=%s metodo=%s rota=%s status=%d latencia_ms=%.1f req_bytes=%s%s",
                request_id,
                request.method,
                request.url.path,
                status,
                _ms_since(t0),
                request.headers.get("content-length", "-"),
                extras,
            )

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": _validation_message(exc)})

    @app.get("/health", response_model=schemas.HealthOut, responses={503: {"model": schemas.HealthOut}})
    async def health(request: Request):
        state = request.app.state
        modelos = {"extrator": state.extractor is not None, "classificador": state.classifier is not None}
        ok = all(modelos.values())
        body = {"status": "ok" if ok else "degradado", "modelos": modelos, "ambiente": state.environment}
        return JSONResponse(status_code=200 if ok else 503, content=body)

    app.include_router(router)
    return app


app = create_app()
