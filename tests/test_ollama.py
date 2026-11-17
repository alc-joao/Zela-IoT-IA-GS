"""HTTP Ollama substituído por transporte local; sem servidor ou inferência real."""

from io import BytesIO
import json

from fastapi.testclient import TestClient
import httpx
from PIL import Image
import pytest

from app.main import app
from app.schemas.analise import AnaliseGerada, Categoria, EscoreVisual, ResultadoVisual
from app.services import generativa, ollama, visao
from app.services.seguranca import DESCRICOES


def visual(categoria=Categoria.BURACO, inconclusivo=False):
    return ResultadoVisual(
        escores=[EscoreVisual(categoria=cat, escore_relativo=.8 if cat == categoria else .05)
                 for cat, _ in visao.CANDIDATAS], inconclusivo=inconclusivo,
    )


def dados(categoria=Categoria.BURACO, **alteracoes):
    categoria = Categoria(categoria)
    conteudo = dict(categoria=categoria.value, descricao=DESCRICOES[categoria],
                    prioridade="media", justificativa="Sugestão baseada na categoria CLIP.",
                    revisao_humana=True, analise_inconclusiva=False)
    conteudo.update(alteracoes)
    return conteudo


def envelope(conteudo=None):
    return dict(done=True, done_reason="stop", message={
        "role": "assistant", "content": json.dumps(conteudo if conteudo is not None else dados())})


def enviar(conteudo=None, mime="image/png"):
    if conteudo is None:
        with BytesIO() as buffer:
            with Image.new("RGB", (8, 8)) as imagem:
                imagem.save(buffer, format="PNG")
            conteudo = buffer.getvalue()
    with TestClient(app) as cliente:
        return cliente.post("/analisar", files={"fotografia": ("foto.png", conteudo, mime)})


def transporte(monkeypatch, handler):
    monkeypatch.setattr(ollama, "_criar_cliente", lambda timeout: httpx.Client(
        transport=httpx.MockTransport(handler), timeout=timeout, trust_env=False))


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv("IA_PROVIDER", "ollama")
    monkeypatch.setattr(visao, "classificar", lambda imagem: visual())


def test_sucesso_padrao_sem_chave_imagem_ou_gemini(monkeypatch, local):
    monkeypatch.delenv("IA_PROVIDER")
    chamadas = []

    def responder(request):
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        assert request.method == "POST"
        payload = json.loads(request.content)
        chamadas.append(payload)
        assert payload["model"] == "qwen2.5:1.5b"
        assert payload["stream"] is False
        assert payload["options"]["temperature"] == 0
        assert payload["format"] == AnaliseGerada.model_json_schema()
        assert all("images" not in mensagem for mensagem in payload["messages"])
        recebido = json.loads(payload["messages"][1]["content"])
        assert set(recebido) == {"categoria_clip", "escores_relativos", "inconclusivo"}
        assert recebido["categoria_clip"] == Categoria.BURACO.value
        assert len(recebido["escores_relativos"]) == 5
        assert "foto.png" not in request.content.decode()
        return httpx.Response(200, json=envelope())

    transporte(monkeypatch, responder)
    resposta = enviar()
    assert resposta.status_code == 200
    assert len(chamadas) == 1
    assert resposta.json()["descricao"] == DESCRICOES[Categoria.BURACO]
    assert resposta.json()["prioridade"] == "media"
    assert resposta.json()["revisao_humana"] is True
    assert resposta.json()["analise_inconclusiva"] is False


def test_modelo_url_e_timeout_configuraveis(monkeypatch, local):
    monkeypatch.setenv("OLLAMA_MODEL", "modelo-do-teste")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11435/")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "2.5")

    def responder(request):
        assert str(request.url) == "http://localhost:11435/api/chat"
        assert request.extensions["timeout"]["read"] == 2.5
        assert json.loads(request.content)["model"] == "modelo-do-teste"
        return httpx.Response(200, json=envelope())

    transporte(monkeypatch, responder)
    assert enviar().status_code == 200


@pytest.mark.parametrize("status,esperado,trecho", [
    (404, 503, "Modelo Ollama não encontrado"),
    (503, 503, "Ollama local indisponível"),
    (400, 502, "Ollama rejeitou"),
])
def test_erros_http(monkeypatch, local, status, esperado, trecho):
    transporte(monkeypatch, lambda request: httpx.Response(status, json={"error": "detalhe-interno-secreto"}))
    resposta = enviar()
    assert resposta.status_code == esperado
    assert trecho in resposta.json()["detail"]
    assert "detalhe-interno" not in resposta.text


@pytest.mark.parametrize("erro,codigo", [(httpx.ConnectError, 503), (httpx.ReadTimeout, 504)])
def test_conexao_e_timeout(monkeypatch, local, erro, codigo):
    def falhar(request):
        raise erro("detalhe-interno-secreto", request=request)

    transporte(monkeypatch, falhar)
    resposta = enviar()
    assert resposta.status_code == codigo
    assert "detalhe-interno" not in resposta.text


@pytest.mark.parametrize("conteudo", [
    None, {}, {"done": False, "message": {"role": "assistant", "content": "{}"}},
    {"done": True, "done_reason": "length", "message": {"role": "assistant", "content": "{}"}},
    {"done": True, "message": {"role": "assistant", "content": "nao e JSON"}},
    envelope(dados(revisao_humana="false")), envelope(dados(prioridade="urgente")),
    envelope(dados(descricao=" ")), envelope(dados(campo_extra="objeto")),
])
def test_json_e_schema_invalidos(monkeypatch, local, conteudo):
    transporte(monkeypatch, lambda request: httpx.Response(200, json=conteudo))
    assert enviar().status_code == 502


def test_json_http_malformado(monkeypatch, local):
    transporte(monkeypatch, lambda request: httpx.Response(200, content=b"nao e JSON"))
    assert enviar().status_code == 502


def test_objeto_alucinado_descartado_e_prioridade_nao_aceita(monkeypatch, local):
    conteudo = dados(descricao="Há uma TV de 50 polegadas na Rua Exemplo com duas pessoas.",
                     justificativa="A TV pode explodir e causar acidente confirmado.",
                     prioridade="alta", revisao_humana=False)
    transporte(monkeypatch, lambda request: httpx.Response(200, json=envelope(conteudo)))
    resposta = enviar()
    assert resposta.status_code == 200
    segura = resposta.json()
    assert segura["descricao"] == DESCRICOES[Categoria.BURACO]
    assert segura["prioridade"] == "media"
    assert segura["revisao_humana"] is True
    assert "Texto gerado descartado" in segura["justificativa"]
    for detalhe in ("TV", "50", "Rua Exemplo", "pessoas", "explodir"):
        assert detalhe not in resposta.text


@pytest.mark.parametrize("categoria", [cat for cat, _ in visao.CANDIDATAS])
def test_prioridade_deterministica_e_justificativa_sem_fatos_livres(monkeypatch, local, categoria):
    monkeypatch.setattr(visao, "classificar", lambda imagem: visual(categoria))
    transporte(monkeypatch, lambda request: httpx.Response(200, json=envelope(dados(
        categoria, prioridade="alta", justificativa="Existe uma TV perigosa no local."))))
    resposta = enviar()
    assert resposta.status_code == 200
    assert resposta.json()["prioridade"] == (None if categoria == Categoria.SEM_PROBLEMA else "media")
    assert "TV" not in resposta.text


def test_clip_inconclusivo_nao_chama_ollama(monkeypatch, local):
    monkeypatch.setattr(visao, "classificar", lambda imagem: visual(inconclusivo=True))

    def proibido(*args):
        pytest.fail("Ollama não deve ser chamado se CLIP abstém.")

    monkeypatch.setattr(ollama, "gerar_analise", proibido)
    resposta = enviar()
    assert resposta.status_code == 200
    assert resposta.json()["categoria"] == "inconclusiva"
    assert resposta.json()["prioridade"] is None
    assert resposta.json()["revisao_humana"] is True


@pytest.mark.parametrize("alteracao", [{"categoria": Categoria.LIXO.value}, {"analise_inconclusiva": True}])
def test_llm_divergente_ou_inseguro_abstem(monkeypatch, local, alteracao):
    transporte(monkeypatch, lambda request: httpx.Response(200, json=envelope(dados(**alteracao))))
    resposta = enviar()
    assert resposta.status_code == 200
    assert resposta.json()["analise_inconclusiva"] is True
    assert resposta.json()["prioridade"] is None


def test_selecao_gemini_independente_sem_ollama(monkeypatch, local):
    monkeypatch.setenv("IA_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "chave-do-teste")
    chamadas = []

    def gerar(chave, modelo, imagem, resultado):
        chamadas.append(True)
        assert imagem.startswith(b"\x89PNG")
        return json.dumps(dados(prioridade="alta", descricao="Uma TV inexistente."))

    monkeypatch.setattr(generativa, "_gerar_json", gerar)
    resposta = enviar()
    assert resposta.status_code == 200
    assert chamadas == [True]
    assert resposta.json()["prioridade"] == "media"
    assert "TV" not in resposta.text


@pytest.mark.parametrize("nome,valor", [
    ("IA_PROVIDER", "desconhecido"), ("OLLAMA_TIMEOUT_SECONDS", "nan"),
    ("OLLAMA_TIMEOUT_SECONDS", "0"), ("OLLAMA_MODEL", " "),
    ("OLLAMA_BASE_URL", "https://exemplo.com"),
    ("OLLAMA_BASE_URL", "http://usuario:senha@localhost:11434"),
])
def test_configuracao_invalida(monkeypatch, local, nome, valor):
    monkeypatch.setenv(nome, valor)
    assert enviar().status_code == 503


def test_imagem_invalida_nao_aciona_ollama(local):
    assert enviar(b"imagem falsa").status_code == 400
