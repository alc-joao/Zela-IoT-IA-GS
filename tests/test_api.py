"""Testes do contrato HTTP e das validações de fotografias."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import imagens


@pytest.fixture
def cliente():
    with TestClient(app) as cliente:
        yield cliente


def criar_imagem(formato: str = "PNG") -> bytes:
    with BytesIO() as buffer:
        with Image.new("RGB", (8, 8), color="green") as imagem:
            imagem.save(buffer, format=formato)
        return buffer.getvalue()


def test_health(cliente):
    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "servico": "zela-analise-urbana"}


def test_ausencia_de_fotografia(cliente):
    resposta = cliente.post("/analisar")

    assert resposta.status_code == 422


@pytest.mark.parametrize("mime", ["text/plain", "application/pdf", "image/gif"])
def test_mime_nao_permitido(cliente, mime):
    resposta = cliente.post(
        "/analisar", files={"fotografia": ("arquivo", b"conteudo", mime)}
    )

    assert resposta.status_code == 415


@pytest.mark.parametrize("conteudo", [b"", b"isto nao e uma imagem"])
def test_conteudo_invalido(cliente, conteudo):
    resposta = cliente.post(
        "/analisar", files={"fotografia": ("foto.png", conteudo, "image/png")}
    )

    assert resposta.status_code == 400


def test_mime_diferente_do_formato_real(cliente):
    resposta = cliente.post(
        "/analisar",
        files={"fotografia": ("foto.jpg", criar_imagem("PNG"), "image/jpeg")},
    )

    assert resposta.status_code == 415


def test_imagem_corrompida(cliente):
    # Remove o fim de um JPEG que ainda pode ter seu cabeçalho reconhecido.
    conteudo = criar_imagem("JPEG")[:-2]
    resposta = cliente.post(
        "/analisar", files={"fotografia": ("foto.jpg", conteudo, "image/jpeg")}
    )

    assert resposta.status_code == 400


def test_limite_de_bytes(cliente, monkeypatch):
    conteudo = criar_imagem()
    monkeypatch.setattr(imagens, "LIMITE_IMAGEM_BYTES", len(conteudo) - 1)
    resposta = cliente.post(
        "/analisar", files={"fotografia": ("foto.png", conteudo, "image/png")}
    )

    assert resposta.status_code == 413


def test_tamanho_exatamente_no_limite(cliente, monkeypatch):
    conteudo = criar_imagem()
    monkeypatch.setattr(imagens, "LIMITE_IMAGEM_BYTES", len(conteudo))
    resposta = cliente.post(
        "/analisar", files={"fotografia": ("foto.png", conteudo, "image/png")}
    )

    assert resposta.status_code == 503


def test_limite_de_pixels(cliente, monkeypatch):
    monkeypatch.setattr(imagens, "LIMITE_PIXELS", 32)
    resposta = cliente.post(
        "/analisar", files={"fotografia": ("foto.png", criar_imagem(), "image/png")}
    )

    assert resposta.status_code == 413


@pytest.mark.parametrize("limite_pillow", [20, 40])
def test_protecao_de_descompressao(cliente, monkeypatch, limite_pillow):
    conteudo = criar_imagem()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", limite_pillow)
    resposta = cliente.post(
        "/analisar", files={"fotografia": ("foto.png", conteudo, "image/png")}
    )

    assert resposta.status_code == 413


@pytest.mark.parametrize(
    ("formato", "mime"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_imagem_valida_sem_ia_configurada(cliente, formato, mime):
    resposta = cliente.post(
        "/analisar", files={"fotografia": ("foto", criar_imagem(formato), mime)}
    )

    assert resposta.status_code == 503
    assert resposta.json() == {
        "detail": "O serviço de análise ainda não está configurado. Nenhuma classificação foi gerada."
    }
