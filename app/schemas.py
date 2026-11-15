"""Modelos Pydantic de entrada e saída."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Sentimento = Literal["positivo", "neutro", "negativo"]
SentimentoAspecto = Literal["positivo", "negativo"]
Prioridade = Literal["alta", "media", "baixa", "indeterminada"]


class ReviewIn(BaseModel):
    # Tamanho e conteúdo são validados em app.validation.clean_text, que é a
    # mesma função usada pelo campo de formulário do /v1/feedback/analyze.
    texto: str


class Aspectos(BaseModel):
    entrega: SentimentoAspecto | None
    produto: SentimentoAspecto | None
    atendimento: SentimentoAspecto | None
    preco: SentimentoAspecto | None


class ReviewOut(BaseModel):
    valido: bool
    sentimento: Sentimento | None
    aspectos: Aspectos | None
    problema_principal: str | None
    requer_acao: bool | None
    # Preenchido só quando valido é false: o texto cru que o modelo gerou.
    saida_bruta: str | None


class ReviewOutTimed(ReviewOut):
    latencia_ms: float


class ClasseConfianca(BaseModel):
    classe: str
    confianca: float


class FoodOut(BaseModel):
    classe: str | None
    confianca: float
    top3: list[ClasseConfianca]
    rejeitado: bool
    latencia_ms: float


class FeedbackOut(BaseModel):
    analise_texto: ReviewOut
    prato: ClasseConfianca | None
    prioridade: Prioridade
    latencia_ms: float


class ModelosCarregados(BaseModel):
    extrator: bool
    classificador: bool


class HealthOut(BaseModel):
    status: Literal["ok", "degradado"]
    modelos: ModelosCarregados
    ambiente: dict


class ErroOut(BaseModel):
    detail: str
