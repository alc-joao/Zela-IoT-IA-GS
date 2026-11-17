"""Contratos da análise assistida por IA e dos escores visuais."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class Prioridade(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class Categoria(str, Enum):
    BURACO = "buraco_no_asfalto"
    LIXO = "entulho_ou_lixo"
    CALCADA = "calcada_danificada"
    ILUMINACAO = "iluminacao_visivelmente_danificada"
    SEM_PROBLEMA = "sem_problema_evidente"
    INCONCLUSIVA = "inconclusiva"


class EscoreVisual(BaseModel):
    categoria: Categoria
    escore_relativo: float = Field(ge=0, le=1, allow_inf_nan=False)


class ResultadoVisual(BaseModel):
    modelo: str = "openai/clip-vit-base-patch32"
    escores: list[EscoreVisual] = Field(min_length=5, max_length=5)
    inconclusivo: bool
    observacao: str = "Escores relativos às descrições candidatas; não são probabilidades calibradas."


class AnaliseGerada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    categoria: Categoria
    descricao: str = Field(min_length=1, max_length=2000)
    prioridade: Prioridade | None = Field(description="Sugestão; nula se inconclusiva ou sem problema evidente.")
    justificativa: str = Field(min_length=1, max_length=2000)
    revisao_humana: StrictBool
    analise_inconclusiva: StrictBool


class RespostaAnalise(AnaliseGerada):
    visao_computacional: ResultadoVisual
    aviso: Literal["Prioridade sugerida por IA; não representa decisão oficial."] = (
        "Prioridade sugerida por IA; não representa decisão oficial."
    )
