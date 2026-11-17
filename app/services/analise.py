"""Coordenação da visão e geração, com abstenção conservadora."""

from io import BytesIO

from PIL import Image, ImageOps

from app.schemas.analise import Categoria, RespostaAnalise
from app.services import generativa, visao


def analisar_fotografia(conteudo: bytes) -> RespostaAnalise:
    # Falha antes de carregar CLIP se a chave estiver ausente.
    generativa.verificar_configuracao()
    with Image.open(BytesIO(conteudo)) as original:
        with ImageOps.exif_transpose(original) as orientada:
            with orientada.convert("RGB") as imagem:
                imagem.thumbnail((1600, 1600))
                visual = visao.classificar(imagem)
                with BytesIO() as buffer:
                    # Sem EXIF; as duas etapas veem os mesmos pixels.
                    imagem.info.clear()
                    imagem.save(buffer, format="PNG")
                    gerada = generativa.gerar_analise(buffer.getvalue(), visual)

    dados = gerada.model_dump()
    dados["revisao_humana"] = True
    if (visual.inconclusivo or gerada.analise_inconclusiva or
            gerada.categoria == Categoria.INCONCLUSIVA or
            gerada.categoria != visual.escores[0].categoria):
        dados.update(
            categoria=Categoria.INCONCLUSIVA, analise_inconclusiva=True,
            prioridade=None,
            descricao="A imagem e os resultados visuais não permitem uma conclusão confiável.",
            justificativa="Evidência insuficiente ou divergente entre as etapas; é necessária revisão humana.",
        )
    elif gerada.categoria == Categoria.SEM_PROBLEMA:
        dados["prioridade"] = None
    return RespostaAnalise(**dados, visao_computacional=visual)
