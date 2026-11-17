"""Configurações locais, sem dependência de um provedor de IA."""

import os

NOME_SERVICO = "zela-analise-urbana"


def _limite_imagem_bytes() -> int:
    try:
        limite_mb = int(os.getenv("MAX_IMAGE_SIZE_MB", "5"))
    except ValueError as erro:
        raise ValueError("MAX_IMAGE_SIZE_MB deve ser um inteiro positivo.") from erro

    if limite_mb <= 0:
        raise ValueError("MAX_IMAGE_SIZE_MB deve ser um inteiro positivo.")

    return limite_mb * 1024 * 1024


LIMITE_IMAGEM_BYTES = _limite_imagem_bytes()
