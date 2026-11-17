"""Contrato reservado para resultados reais da futura integração de IA."""

from enum import Enum

from pydantic import BaseModel, Field


class Prioridade(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class RespostaAnalise(BaseModel):
    categoria: str = Field(min_length=1, description="Categoria do problema urbano.")
    descricao: str = Field(min_length=1, description="Descrição do problema observado.")
    prioridade: Prioridade
    justificativa: str = Field(
        min_length=1, description="Justificativa da prioridade atribuída."
    )
    revisao_humana: bool = Field(
        description="Indica se o resultado requer revisão humana."
    )
