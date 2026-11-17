"""Fotos artificiais pequenas apenas para testar o script, nunca como evidência real."""

import csv
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

from app.schemas.analise import Categoria, EscoreVisual, ResultadoVisual
from app.services import visao
from app.services.erros import ErroAnalise
from scripts.avaliar_clip import avaliar_csv, main


def criar_foto(caminho: Path, identificador=1):
    with Image.new("RGB", (8, 6), (identificador, 0, 0)) as imagem:
        imagem.save(caminho, format="PNG")


def criar_csv(caminho: Path, linhas):
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["caminho", "categoria"])
        escritor.writerows(linhas)


def resultado(categoria=Categoria.BURACO, inconclusivo=False):
    return ResultadoVisual(
        escores=[EscoreVisual(categoria=cat, escore_relativo=.8 if cat == categoria else .05)
                 for cat, _ in visao.CANDIDATAS],
        inconclusivo=inconclusivo,
    )


def ler_saida(caminho):
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def test_resultados_metricas_e_abstencao(tmp_path, monkeypatch):
    entrada, saida = tmp_path / "entrada.csv", tmp_path / "saida.csv"
    categorias = [Categoria.BURACO, Categoria.CALCADA, Categoria.BURACO,
                  Categoria.INCONCLUSIVA, Categoria.SEM_PROBLEMA]
    for indice in range(1, 6):
        criar_foto(tmp_path / f"foto{indice}.png", indice)
    criar_csv(entrada, [(f"foto{i}.png", cat.value) for i, cat in enumerate(categorias, 1)])
    chamadas = []

    def inferir(imagem):
        assert imagem.mode == "RGB"
        indice = imagem.getpixel((0, 0))[0]
        chamadas.append(indice)
        if indice == 5:
            return resultado(Categoria.SEM_PROBLEMA)
        return resultado(inconclusivo=indice in (3, 4))

    monkeypatch.setattr(visao, "classificar", inferir)
    resumo = avaliar_csv(entrada, saida, minimo_por_categoria=2)
    assert chamadas == [1, 2, 3, 4, 5]
    assert resumo["casos_validos"] == 5
    assert resumo["casos_invalidos"] == 0
    assert resumo["acuracia_simples"] == pytest.approx(.6)
    assert resumo["percentual_inconclusivas"] == 40
    assert resumo["por_categoria"][Categoria.BURACO.value]["acuracia_simples"] == .5
    assert resumo["por_categoria"][Categoria.CALCADA.value]["acuracia_simples"] is None
    linhas = ler_saida(saida)
    assert linhas[0]["acerto"] == "True"
    assert linhas[1]["acerto"] == "False"
    assert linhas[2]["categoria_prevista"] == "inconclusiva"
    assert linhas[2]["categoria_top1"] == Categoria.BURACO.value
    assert linhas[2]["abstencao"] == "True"
    assert float(linhas[2]["maior_escore_relativo"]) == .8
    assert linhas[3]["acerto"] == "True"
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_lote_continua_apos_arquivos_invalidos(tmp_path, monkeypatch):
    criar_foto(tmp_path / "valida.png")
    (tmp_path / "corrompida.png").write_bytes(b"nao e imagem")
    with Image.new("RGB", (8, 6)) as imagem:
        imagem.save(tmp_path / "nao_aceita.gif", format="GIF")
    entrada, saida = tmp_path / "entrada.csv", tmp_path / "saida.csv"
    criar_csv(entrada, [("ausente.png", "buraco_no_asfalto"),
                        ("corrompida.png", "buraco_no_asfalto"),
                        ("nao_aceita.gif", "buraco_no_asfalto"),
                        ("valida.png", "categoria_inexistente"),
                        ("", "buraco_no_asfalto"),
                        ("valida.png", "buraco_no_asfalto")])
    chamadas = []

    def inferir(imagem):
        chamadas.append(True)
        return resultado()

    monkeypatch.setattr(visao, "classificar", inferir)
    resumo = avaliar_csv(entrada, saida)
    assert len(chamadas) == 1
    assert resumo["casos_validos"] == 1
    assert resumo["casos_invalidos"] == 5
    assert resumo["acuracia_simples"] == 1
    linhas = ler_saida(saida)
    assert [linha["status"] for linha in linhas] == [
        "arquivo_ausente", "imagem_invalida", "imagem_invalida",
        "categoria_invalida", "linha_invalida", "valido"]
    assert linhas[0]["acerto"] == ""
    assert linhas[0]["abstencao"] == ""
    assert linhas[0]["erro"]


def test_falha_modelo_nao_entra_na_acuracia_e_lote_continua(tmp_path, monkeypatch):
    criar_foto(tmp_path / "foto.png")
    entrada, saida = tmp_path / "entrada.csv", tmp_path / "saida.csv"
    criar_csv(entrada, [("foto.png", "buraco_no_asfalto")] * 2)
    chamadas = []

    def inferir(imagem):
        chamadas.append(True)
        if len(chamadas) == 1:
            raise ErroAnalise(503, "Detalhe interno que não deve aparecer no relatório")
        return resultado()

    monkeypatch.setattr(visao, "classificar", inferir)
    resumo = avaliar_csv(entrada, saida)
    assert resumo["casos_validos"] == 1
    assert resumo["casos_invalidos"] == 1
    assert ler_saida(saida)[0]["status"] == "falha_modelo"
    assert "Detalhe interno" not in saida.read_text()


@pytest.mark.parametrize("linhas", [[], [("ausente.png", "buraco_no_asfalto")]])
def test_sem_casos_validos_nao_inventa_metricas(tmp_path, linhas):
    entrada, saida = tmp_path / "entrada.csv", tmp_path / "saida.csv"
    criar_csv(entrada, linhas)
    assert main([str(entrada), "--saida", str(saida)]) == 1
    resumo = json.loads(saida.with_suffix(".resumo.json").read_text())
    assert resumo["casos_validos"] == 0
    assert resumo["acuracia_simples"] is None
    assert resumo["percentual_inconclusivas"] is None
    assert all(item["acuracia_simples"] is None for item in resumo["por_categoria"].values())


def test_cli_grava_metricas_sem_precisar_gemini(tmp_path, monkeypatch):
    criar_foto(tmp_path / "foto.png")
    entrada, saida, resumo = (tmp_path / nome for nome in ("entrada.csv", "saida.csv", "metricas.json"))
    criar_csv(entrada, [("foto.png", "buraco_no_asfalto")])
    monkeypatch.setattr(visao, "classificar", lambda imagem: resultado())
    assert main([str(entrada), "--saida", str(saida), "--resumo", str(resumo)]) == 0
    assert json.loads(resumo.read_text())["casos_validos"] == 1


@pytest.mark.parametrize("conteudo", ["foto,rotulo\n", "caminho,categoria,categoria\n"])
def test_cabecalho_invalido(tmp_path, conteudo):
    entrada, saida = tmp_path / "entrada.csv", tmp_path / "saida.csv"
    entrada.write_text(conteudo)
    assert main([str(entrada), "--saida", str(saida)]) == 2
    assert not saida.exists()


def test_preserva_saida_existente(tmp_path):
    entrada, saida = tmp_path / "entrada.csv", tmp_path / "saida.csv"
    criar_csv(entrada, [])
    saida.write_text("conteudo anterior")
    assert main([str(entrada), "--saida", str(saida)]) == 2
    assert saida.read_text() == "conteudo anterior"


def test_ajuda_nao_importa_modelos_nem_gemini():
    codigo = '''
import builtins
original = builtins.__import__
def importar(nome, *args, **kwargs):
    if nome.split('.')[0] in {'torch', 'transformers', 'google', 'huggingface_hub'} or 'generativa' in nome:
        raise AssertionError('Import externo não permitido: ' + nome)
    return original(nome, *args, **kwargs)
builtins.__import__ = importar
from scripts.avaliar_clip import main
main(['--help'])
'''
    subprocess.run([sys.executable, "-c", codigo], check=True,
                   cwd=Path(__file__).resolve().parents[1], capture_output=True)
