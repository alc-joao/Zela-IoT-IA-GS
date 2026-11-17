"""Política determinística: nenhuma narrativa livre é tratada como evidência."""

from app.schemas.analise import AnaliseGerada, Categoria, Prioridade, ResultadoVisual

DESCRICOES = {
    Categoria.BURACO: "Pode haver um buraco no asfalto; é necessária verificação humana.",
    Categoria.LIXO: "Pode haver entulho ou lixo; é necessária verificação humana.",
    Categoria.CALCADA: "Pode haver dano na calçada; é necessária verificação humana.",
    Categoria.ILUMINACAO: "Pode haver dano físico na iluminação; é necessária verificação humana.",
    Categoria.SEM_PROBLEMA: "Pode não haver problema evidente entre as categorias avaliadas; é necessária verificação humana.",
    Categoria.INCONCLUSIVA: "A classificação visual é inconclusiva; é necessária revisão humana.",
}


def prioridade_sugerida(categoria: Categoria) -> Prioridade | None:
    if categoria in (Categoria.INCONCLUSIVA, Categoria.SEM_PROBLEMA):
        return None
    # Triagem neutra para as quatro categorias; não estima gravidade pela foto.
    return Prioridade.MEDIA


def analise_inconclusiva() -> AnaliseGerada:
    return AnaliseGerada(
        categoria=Categoria.INCONCLUSIVA,
        descricao=DESCRICOES[Categoria.INCONCLUSIVA], prioridade=None,
        justificativa="Evidência insuficiente ou divergente entre as etapas; é necessária revisão humana.",
        revisao_humana=True, analise_inconclusiva=True,
    )


def aplicar_regras(gerada: AnaliseGerada, visual: ResultadoVisual) -> AnaliseGerada:
    categoria = max(visual.escores, key=lambda item: item.escore_relativo).categoria
    if (visual.inconclusivo or gerada.analise_inconclusiva or
            gerada.categoria == Categoria.INCONCLUSIVA or gerada.categoria != categoria):
        return analise_inconclusiva()

    descricao = DESCRICOES[categoria]
    # Lista fechada em vez de blacklist: até um texto plausível pode inventar fatos.
    descartada = gerada.descricao != descricao
    if categoria == Categoria.SEM_PROBLEMA:
        justificativa = (
            "A categoria CLIP sugere ausência de problema evidente; isso não comprova ausência de defeitos. "
            "Revisão humana obrigatória."
        )
    else:
        justificativa = (
            "Prioridade média sugerida apenas para triagem da categoria CLIP; "
            "gravidade e risco não foram determinados. Revisão humana obrigatória."
        )
    if descartada:
        justificativa = "Texto gerado descartado por não corresponder à descrição permitida. " + justificativa
    return AnaliseGerada(
        categoria=categoria, descricao=descricao, prioridade=prioridade_sugerida(categoria),
        justificativa=justificativa, revisao_humana=True, analise_inconclusiva=False,
    )
