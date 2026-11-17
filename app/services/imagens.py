"""Validação de uploads sem persistir fotografias em disco."""

from io import BytesIO
import warnings

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.config import LIMITE_IMAGEM_BYTES

FORMATOS_POR_MIME = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
# Limita também o tamanho descompactado, independentemente dos bytes do upload.
LIMITE_PIXELS = 25_000_000


def validar_fotografia(fotografia: UploadFile) -> bytes:
    """Confere MIME, tamanho, formato real, integridade e decodificação."""
    formato_esperado = FORMATOS_POR_MIME.get(fotografia.content_type or "")
    if formato_esperado is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Tipo MIME não permitido. Envie uma imagem JPEG, PNG ou WebP.",
        )

    # Lê no máximo o limite mais um byte para detectar excesso sem ler tudo.
    conteudo = fotografia.file.read(LIMITE_IMAGEM_BYTES + 1)
    if len(conteudo) > LIMITE_IMAGEM_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"A fotografia excede o limite de {LIMITE_IMAGEM_BYTES} bytes.",
        )
    if not conteudo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O arquivo de imagem está vazio.",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(conteudo)) as imagem:
                if imagem.format != formato_esperado:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="O tipo MIME informado não corresponde ao formato da imagem.",
                    )
                if imagem.width * imagem.height > LIMITE_PIXELS:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"A fotografia excede o limite de {LIMITE_PIXELS} pixels.",
                    )
                imagem.verify()

            # verify() confere a estrutura; load() também detecta pixels truncados.
            with Image.open(BytesIO(conteudo)) as imagem:
                imagem.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as erro:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="A fotografia excede o limite seguro de dimensões.",
        ) from erro
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as erro:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O arquivo não contém uma imagem válida ou está corrompido.",
        ) from erro
    return conteudo
