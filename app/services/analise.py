"""Coordenação da visão e geração, com abstenção conservadora."""

from io import BytesIO
import os

from PIL import Image, ImageOps

from app.schemas.analise import RespostaAnalise
from app.services import generativa, ollama, visao
from app.services.erros import ErroAnalise
from app.services.seguranca import analise_inconclusiva, aplicar_regras


def analisar_fotografia(conteudo: bytes) -> RespostaAnalise:
    provedor = os.getenv("IA_PROVIDER", "ollama").strip().lower()
    if provedor == "ollama":
        ollama.verificar_configuracao()
    elif provedor == "gemini":
        generativa.verificar_configuracao()
    else:
        raise ErroAnalise(503, "IA_PROVIDER inválido; use ollama ou gemini.")
    with Image.open(BytesIO(conteudo)) as original:
        with ImageOps.exif_transpose(original) as orientada:
            with orientada.convert("RGB") as imagem:
                imagem.thumbnail((1600, 1600))
                visual = visao.classificar(imagem)
                if visual.inconclusivo:
                    return RespostaAnalise(**analise_inconclusiva().model_dump(), visao_computacional=visual)
                if provedor == "ollama":
                    gerada = ollama.gerar_analise(visual)
                else:
                    # Sem EXIF; as duas etapas veem os mesmos pixels.
                    imagem.info.clear()
                    with BytesIO() as buffer:
                        imagem.save(buffer, format="PNG")
                        gerada = generativa.gerar_analise(buffer.getvalue(), visual)

    segura = aplicar_regras(gerada, visual)
    return RespostaAnalise(**segura.model_dump(), visao_computacional=visual)
