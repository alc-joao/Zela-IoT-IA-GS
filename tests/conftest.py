"""Isola credenciais e impede acesso acidental a modelos/provedores."""

import pytest

from app.services import generativa, visao


@pytest.fixture(autouse=True)
def isolar_ia(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(visao, "_recursos", None)

    def proibido(*args, **kwargs):
        raise AssertionError("Dependência externa deve ser substituída por stub no teste.")

    monkeypatch.setattr(visao, "_carregar_modelo", proibido)
    monkeypatch.setattr(generativa, "_gerar_json", proibido)
