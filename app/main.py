"""Ponto de entrada HTTP do microsserviço Zela."""

from fastapi import FastAPI, File, HTTPException, UploadFile, status

from app.config import NOME_SERVICO
from app.schemas.analise import RespostaAnalise
from app.services.imagens import validar_fotografia

app = FastAPI(
    title="Zela — Análise de Fotografias Urbanas",
    version="0.1.0",
    description="Base do serviço de zeladoria colaborativa com IA. Integração de IA pendente.",
)


@app.get("/health", summary="Verifica se a API está em execução")
def health() -> dict[str, str]:
    return {"status": "ok", "servico": NOME_SERVICO}


@app.post(
    "/analisar",
    response_model=RespostaAnalise,
    summary="Recebe e valida uma fotografia de problema urbano",
    description="Após validar a fotografia, retorna 503 enquanto a IA não estiver implementada.",
    responses={
        400: {"description": "Arquivo vazio, inválido ou corrompido."},
        413: {"description": "Limite de bytes ou de pixels excedido."},
        415: {"description": "Tipo MIME não permitido ou incompatível com a imagem."},
        503: {"description": "Serviço de análise ainda não configurado."},
    },
)
def analisar(
    fotografia: UploadFile = File(description="Fotografia em JPEG, PNG ou WebP."),
) -> RespostaAnalise:
    # A rota síncrona executa a leitura e a decodificação fora do event loop.
    validar_fotografia(fotografia)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="O serviço de análise ainda não está configurado. Nenhuma classificação foi gerada.",
    )
