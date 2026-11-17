"""Ponto de entrada HTTP do microsserviço Zela."""

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.config import NOME_SERVICO
from app.schemas.analise import RespostaAnalise
from app.services.imagens import validar_fotografia
from app.services.analise import analisar_fotografia
from app.services.erros import ErroAnalise

app = FastAPI(
    title="Zela — Análise de Fotografias Urbanas",
    version="0.2.0",
    description="Análise assistida por CLIP e Gemini. Prioridades são sugestões sujeitas a revisão humana.",
)


@app.get("/health", summary="Verifica se a API está em execução")
def health() -> dict[str, str]:
    return {"status": "ok", "servico": NOME_SERVICO}


@app.post(
    "/analisar",
    response_model=RespostaAnalise,
    summary="Recebe e valida uma fotografia de problema urbano",
    description="Valida a fotografia, classifica com CLIP e estrutura a análise com Gemini.",
    responses={
        400: {"description": "Arquivo vazio, inválido ou corrompido."},
        413: {"description": "Limite de bytes ou de pixels excedido."},
        415: {"description": "Tipo MIME não permitido ou incompatível com a imagem."},
        502: {"description": "Resposta do provedor incompleta ou inválida."},
        503: {"description": "Configuração, modelo ou provedor indisponível."},
        504: {"description": "Tempo limite do provedor excedido."},
    },
)
def analisar(
    fotografia: UploadFile = File(description="Fotografia em JPEG, PNG ou WebP."),
) -> RespostaAnalise:
    # A rota síncrona executa a leitura e a decodificação fora do event loop.
    conteudo = validar_fotografia(fotografia)
    try:
        return analisar_fotografia(conteudo)
    except ErroAnalise as erro:
        raise HTTPException(status_code=erro.status_code, detail=erro.mensagem) from None
