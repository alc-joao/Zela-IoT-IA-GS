"""Stubs existem apenas nos testes; nenhuma rede ou peso de modelo é necessário."""

from contextlib import nullcontext
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.main import app
from app.schemas.analise import Categoria, EscoreVisual, ResultadoVisual
from app.services import generativa, visao
from app.services.erros import ErroAnalise

_GERAR_JSON_REAL = generativa._gerar_json


def visual(valores=(0.8, 0.05, 0.05, 0.05, 0.05), inconclusivo=False):
    return ResultadoVisual(
        escores=sorted(
            [EscoreVisual(categoria=cat, escore_relativo=valor)
             for (cat, _), valor in zip(visao.CANDIDATAS, valores, strict=True)],
            key=lambda item: item.escore_relativo, reverse=True,
        ), inconclusivo=inconclusivo,
    )


def dados_gerados(**alteracoes):
    dados = dict(categoria=Categoria.BURACO.value,
                 descricao="Há uma irregularidade visível no asfalto.",
                 prioridade="media", justificativa="Possível necessidade de manutenção visual.",
                 revisao_humana=False, analise_inconclusiva=False)
    dados.update(alteracoes)
    return dados


def enviar():
    with BytesIO() as buffer:
        with Image.new("RGB", (8, 8), "green") as imagem:
            imagem.save(buffer, format="PNG")
        with TestClient(app) as cliente:
            return cliente.post("/analisar", files={
                "fotografia": ("foto.png", buffer.getvalue(), "image/png")
            })


@pytest.fixture
def configurar(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-apenas-do-teste")
    monkeypatch.setattr(visao, "classificar", lambda imagem: visual())
    monkeypatch.setattr(generativa, "_gerar_json", lambda *args: json.dumps(dados_gerados()))


def test_integracao_imagem_escores_e_modelo(monkeypatch, configurar):
    monkeypatch.setenv("GEMINI_MODEL", "modelo-configurado-no-teste")

    def gerar(chave, modelo, imagem, resultado):
        assert chave == "chave-apenas-do-teste"
        assert modelo == "modelo-configurado-no-teste"
        with Image.open(BytesIO(imagem)) as foto:
            assert foto.format == "PNG"
            assert foto.size == (8, 8)
        assert resultado.escores[0].categoria == Categoria.BURACO
        return json.dumps(dados_gerados())

    monkeypatch.setattr(generativa, "_gerar_json", gerar)
    resposta = enviar()
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["categoria"] == "buraco_no_asfalto"
    assert dados["prioridade"] == "media"
    assert dados["revisao_humana"] is True
    assert dados["analise_inconclusiva"] is False
    assert len(dados["visao_computacional"]["escores"]) == 5
    assert "não representa decisão oficial" in dados["aviso"]


@pytest.mark.parametrize("motivo", ["clip", "gemini", "divergencia", "categoria"])
def test_abstencao(monkeypatch, configurar, motivo):
    if motivo == "clip":
        monkeypatch.setattr(visao, "classificar", lambda imagem: visual(inconclusivo=True))
    alteracoes = {
        "gemini": {"analise_inconclusiva": True},
        "divergencia": {"categoria": Categoria.LIXO.value},
        "categoria": {"categoria": Categoria.INCONCLUSIVA.value},
    }.get(motivo, {})
    monkeypatch.setattr(generativa, "_gerar_json", lambda *a: json.dumps(dados_gerados(**alteracoes)))
    resposta = enviar()
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["categoria"] == "inconclusiva"
    assert dados["analise_inconclusiva"] is True
    assert dados["revisao_humana"] is True
    assert dados["prioridade"] is None


def test_sem_problema_nao_recebe_prioridade(monkeypatch, configurar):
    monkeypatch.setattr(visao, "classificar", lambda imagem: visual((.05, .05, .05, .05, .8)))
    monkeypatch.setattr(generativa, "_gerar_json", lambda *a: json.dumps(
        dados_gerados(categoria=Categoria.SEM_PROBLEMA.value)))
    resposta = enviar()
    assert resposta.status_code == 200
    assert resposta.json()["prioridade"] is None
    assert resposta.json()["revisao_humana"] is True


def test_normalizacao_remove_metadados_e_preserva_pixels_entre_etapas(monkeypatch, configurar):
    pixels_clip = []

    def classificar(imagem):
        assert imagem.size == (1600, 9)
        pixels_clip.append(imagem.tobytes())
        return visual()

    def gerar(chave, modelo, imagem, resultado):
        with Image.open(BytesIO(imagem)) as foto:
            assert not foto.getexif()
            assert not foto.info
            assert foto.tobytes() == pixels_clip[0]
        return json.dumps(dados_gerados())

    monkeypatch.setattr(visao, "classificar", classificar)
    monkeypatch.setattr(generativa, "_gerar_json", gerar)
    with BytesIO() as buffer:
        with Image.new("RGB", (1700, 10), "green") as imagem:
            exif = Image.Exif()
            exif[0x010E] = "metadado que nao deve ser enviado"
            imagem.save(buffer, format="PNG", exif=exif)
        with TestClient(app) as cliente:
            resposta = cliente.post("/analisar", files={
                "fotografia": ("foto.png", buffer.getvalue(), "image/png")})
    assert resposta.status_code == 200


def test_sem_chave_nao_chama_clip(monkeypatch):
    chamadas = []
    monkeypatch.setattr(visao, "classificar", lambda imagem: chamadas.append(imagem))
    assert enviar().status_code == 503
    assert chamadas == []


def test_falha_modelo_sem_expor_detalhes(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-secreta-teste")

    def falhar():
        raise RuntimeError("chave-secreta-teste erro interno")

    monkeypatch.setattr(visao, "_carregar_modelo", falhar)
    resposta = enviar()
    assert resposta.status_code == 503
    assert "chave-secreta" not in resposta.text


@pytest.mark.parametrize("texto", ["", "não é JSON", "{}", json.dumps(dados_gerados(prioridade="urgente")),
    json.dumps(dados_gerados(revisao_humana="false")),
    json.dumps(dados_gerados(descricao="  ")), json.dumps(dados_gerados(extra="inesperado"))])
def test_json_invalido(monkeypatch, configurar, texto):
    monkeypatch.setattr(generativa, "_gerar_json", lambda *a: texto)
    resposta = enviar()
    assert resposta.status_code == 502
    if texto:
        assert texto not in resposta.text


@pytest.mark.parametrize("erro,codigo", [
    (RuntimeError("segredo-provedor"), 503), (TimeoutError("segredo-provedor"), 504),
    (ErroAnalise(502, "O provedor não retornou uma análise completa."), 502),
])
def test_falhas_provedor(monkeypatch, configurar, erro, codigo):
    def falhar(*a):
        raise erro

    monkeypatch.setattr(generativa, "_gerar_json", falhar)
    resposta = enviar()
    assert resposta.status_code == codigo
    assert "segredo-provedor" not in resposta.text


def test_modelo_vazio(monkeypatch, configurar):
    monkeypatch.setenv("GEMINI_MODEL", " ")
    assert enviar().status_code == 503


@pytest.mark.parametrize("valores,inconclusivo", [
    ([.8, .05, .05, .05, .05], False), ([.2] * 5, True),
    ([.38, .2, .2, .12, .1], True), ([.45, .4, .05, .05, .05], True),
])
def test_clip_lazy_reutilizado(monkeypatch, valores, inconclusivo):
    cargas = []

    class Logits:
        def softmax(self, dim):
            assert dim == -1
            return self

        def __getitem__(self, indice):
            return self

        def tolist(self):
            return valores

    def processador(**kwargs):
        assert kwargs["text"] == [texto for _, texto in visao.CANDIDATAS]
        return {}

    def carregar():
        cargas.append(True)
        return (SimpleNamespace(inference_mode=nullcontext), processador,
                lambda **kw: SimpleNamespace(logits_per_image=Logits()))

    monkeypatch.setattr(visao, "_carregar_modelo", carregar)
    assert cargas == []
    with Image.new("RGB", (8, 8)) as imagem:
        for _ in range(2):
            resultado = visao.classificar(imagem)
            assert resultado.inconclusivo is inconclusivo
            assert resultado.escores[0].categoria == Categoria.BURACO
    assert len(cargas) == 1


def test_importacao_e_openapi_sem_dependencias_pesadas():
    codigo = '''
import builtins
original = builtins.__import__
def importar(nome, *args, **kwargs):
    if nome.split('.')[0] in {'torch', 'transformers', 'google'}:
        raise AssertionError('Import pesado: ' + nome)
    return original(nome, *args, **kwargs)
builtins.__import__ = importar
from app.main import app
schema = app.openapi()
assert 'RespostaAnalise' in schema['components']['schemas']
assert '504' in schema['paths']['/analisar']['post']['responses']
'''
    subprocess.run([sys.executable, "-c", codigo], check=True,
                   cwd=Path(__file__).resolve().parents[1], capture_output=True)


@pytest.mark.parametrize("termino", ["STOP", "MAX_TOKENS", "SAFETY"])
def test_sdk_recebe_imagem_e_schema(monkeypatch, termino):
    # Exercita o adaptador SDK real, substituindo somente o SDK externo.
    gerar_json = _GERAR_JSON_REAL
    chamadas = []

    def generate_content(**kwargs):
        chamadas.append(kwargs)
        return SimpleNamespace(text=json.dumps(dados_gerados()), candidates=[
            SimpleNamespace(finish_reason=SimpleNamespace(value=termino))])

    class Cliente:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "chave-teste"
            self.models = SimpleNamespace(generate_content=generate_content)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    google = ModuleType("google")
    sdk = ModuleType("google.genai")
    sdk.Client = Cliente
    sdk.types = SimpleNamespace(
        HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw,
        GenerateContentConfig=lambda **kw: kw,
        Part=SimpleNamespace(from_bytes=lambda **kw: kw),
    )
    google.genai = sdk
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", sdk)
    if termino == "STOP":
        assert gerar_json("chave-teste", "modelo-teste", b"pixels", visual())
    else:
        with pytest.raises(ErroAnalise) as erro:
            gerar_json("chave-teste", "modelo-teste", b"pixels", visual())
        assert erro.value.status_code == 502
    assert chamadas[0]["model"] == "modelo-teste"
    assert chamadas[0]["contents"][0] == {"data": b"pixels", "mime_type": "image/png"}
    assert chamadas[0]["config"]["response_mime_type"] == "application/json"
    assert chamadas[0]["config"]["response_schema"] is generativa.AnaliseGerada
