"""Isola credenciais e impede acesso acidental a modelos/provedores."""

import pytest

from app.services import generativa, ollama, visao


@pytest.fixture(autouse=True)
def isolar_ia(monkeypatch):
    # A suíte original exercita Gemini; testes Ollama selecionam o provedor explicitamente.
    monkeypatch.setenv("IA_PROVIDER", "gemini")
    for nome in ("OLLAMA_MODEL", "OLLAMA_BASE_URL", "OLLAMA_TIMEOUT_SECONDS"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(visao, "_recursos", None)

    def proibido(*args, **kwargs):
        raise AssertionError("Dependência externa deve ser substituída por stub no teste.")

    monkeypatch.setattr(visao, "_carregar_modelo", proibido)
    monkeypatch.setattr(generativa, "_gerar_json", proibido)
    monkeypatch.setattr(ollama, "_criar_cliente", proibido)
