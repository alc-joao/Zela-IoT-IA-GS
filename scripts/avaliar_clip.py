"""Avaliação local do CLIP: python -m scripts.avaliar_clip --help."""

import argparse
import csv
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import warnings

# Permite também `python scripts/avaliar_clip.py ...`, a partir de qualquer pasta.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.datastructures import Headers

from app.schemas.analise import Categoria
from app.services import imagens, visao
from app.services.erros import ErroAnalise

CAMPOS = (
    "linha", "caminho", "categoria_esperada", "categoria_prevista", "categoria_top1",
    "maior_escore_relativo", "abstencao", "acerto", "status", "erro",
)


def _classificar_arquivo(caminho: Path):
    with caminho.open("rb") as arquivo:
        conteudo = arquivo.read(imagens.LIMITE_IMAGEM_BYTES + 1)
    if len(conteudo) > imagens.LIMITE_IMAGEM_BYTES:
        raise HTTPException(413, "Arquivo acima do limite de bytes da API.")

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(conteudo)) as cabecalho:
            mime = Image.MIME.get(cabecalho.format, "application/octet-stream")
        with BytesIO(conteudo) as arquivo:
            imagens.validar_fotografia(UploadFile(
                file=arquivo, headers=Headers({"content-type": mime})
            ))
        with Image.open(BytesIO(conteudo)) as original:
            with ImageOps.exif_transpose(original) as orientada:
                with orientada.convert("RGB") as imagem:
                    # Mesmo pré-processamento da API, sem a etapa Gemini.
                    imagem.thumbnail((1600, 1600))
                    imagem.info.clear()
                    return visao.classificar(imagem)


def _avaliar_linha(linha: dict, numero: int, base: Path) -> dict:
    resultado = dict.fromkeys(CAMPOS, "")
    resultado.update(linha=numero, caminho=(linha.get("caminho") or "").strip(),
                     categoria_esperada=(linha.get("categoria") or "").strip())
    if None in linha or not resultado["caminho"] or linha.get("categoria") is None:
        resultado.update(status="linha_invalida", erro="Campos ausentes ou quantidade de colunas inválida.")
        return resultado
    try:
        esperada = Categoria(resultado["categoria_esperada"])
    except ValueError:
        resultado.update(status="categoria_invalida", erro="Categoria não definida no projeto.")
        return resultado

    caminho = base / resultado["caminho"]
    try:
        visual = _classificar_arquivo(caminho)
    except FileNotFoundError:
        resultado.update(status="arquivo_ausente", erro="Arquivo não encontrado.")
    except (PermissionError, IsADirectoryError):
        resultado.update(status="erro_leitura", erro="Não foi possível ler o arquivo como fotografia.")
    except HTTPException as erro:
        resultado.update(status="imagem_invalida", erro=str(erro.detail))
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        resultado.update(status="imagem_invalida", erro="Imagem inválida, corrompida ou com dimensões excessivas.")
    except ErroAnalise:
        resultado.update(status="falha_modelo", erro="CLIP indisponível; confira dependências e pesos no cache offline.")
    else:
        maior = max(visual.escores, key=lambda item: item.escore_relativo)
        prevista = Categoria.INCONCLUSIVA if visual.inconclusivo else maior.categoria
        resultado.update(
            status="valido", categoria_prevista=prevista.value,
            categoria_top1=maior.categoria.value, maior_escore_relativo=maior.escore_relativo,
            abstencao=visual.inconclusivo, acerto=prevista == esperada,
        )
    return resultado


def _metricas(resultados: list[dict], minimo: int) -> dict:
    validos = [item for item in resultados if item["status"] == "valido"]

    def contar(casos):
        total = len(casos)
        acertos = sum(item["acerto"] for item in casos)
        inconclusivas = sum(item["abstencao"] for item in casos)
        return dict(casos_validos=total, acertos=acertos, inconclusivas=inconclusivas,
                    acuracia_simples=acertos / total if total else None,
                    percentual_inconclusivas=100 * inconclusivas / total if total else None)

    resumo = contar(validos)
    resumo.update(total_linhas=len(resultados), casos_invalidos=len(resultados) - len(validos),
                  minimo_por_categoria=minimo, por_categoria={})
    for categoria in Categoria:
        casos = [item for item in validos if item["categoria_esperada"] == categoria.value]
        medidas = contar(casos)
        medidas["exemplos_suficientes"] = len(casos) >= minimo
        if len(casos) < minimo:
            medidas["acuracia_simples"] = None
            medidas["percentual_inconclusivas"] = None
        resumo["por_categoria"][categoria.value] = medidas
    resumo["modelo"] = visao.MODELO_CLIP
    resumo["candidatas"] = {categoria.value: texto for categoria, texto in visao.CANDIDATAS}
    resumo["observacao"] = "Escores relativos, não probabilidades calibradas. Nenhum Gemini utilizado."
    return resumo


def avaliar_csv(entrada: Path, saida: Path, minimo_por_categoria: int = 5) -> dict:
    """Lê fotos reais e chama exclusivamente o serviço CLIP existente."""
    if minimo_por_categoria < 1:
        raise ValueError("O mínimo por categoria deve ser positivo.")
    # Não permite download de pesos/configurações. Deve existir cache local.
    # O serviço importa Transformers/Hugging Face somente durante a inferência.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    entrada, saida = Path(entrada), Path(saida)
    if saida.exists():
        raise ValueError("A saída já existe; escolha outro nome para preservar os arquivos.")
    with entrada.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        if (not leitor.fieldnames or not {"caminho", "categoria"}.issubset(leitor.fieldnames)
                or len(set(leitor.fieldnames)) != len(leitor.fieldnames)):
            raise ValueError("O CSV deve ter cabeçalhos únicos e incluir caminho,categoria (separados por vírgula).")
        resultados = [_avaliar_linha(linha, leitor.line_num, entrada.resolve().parent)
                      for linha in leitor]
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("x", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        escritor.writeheader()
        escritor.writerows(resultados)
    return _metricas(resultados, minimo_por_categoria)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia fotos reais com CLIP offline, sem Gemini.")
    parser.add_argument("entrada", type=Path, help="CSV UTF-8 com caminho,categoria.")
    parser.add_argument("--saida", required=True, type=Path, help="CSV de resultados; não pode existir.")
    parser.add_argument("--resumo", type=Path, help="JSON de métricas; padrão: <saida>.resumo.json.")
    parser.add_argument("--min-exemplos-por-categoria", type=int, default=5)
    args = parser.parse_args(argv)
    resumo_path = args.resumo or args.saida.with_suffix(".resumo.json")
    try:
        if resumo_path.exists() or resumo_path.resolve() in {args.entrada.resolve(), args.saida.resolve()}:
            raise ValueError("O resumo deve ser um novo arquivo, diferente da entrada e da saída.")
        resumo = avaliar_csv(args.entrada, args.saida, args.min_exemplos_por_categoria)
        resumo_path.parent.mkdir(parents=True, exist_ok=True)
        with resumo_path.open("x", encoding="utf-8") as arquivo:
            json.dump(resumo, arquivo, ensure_ascii=False, indent=2, allow_nan=False)
            arquivo.write("\n")
    except (OSError, ValueError, csv.Error) as erro:
        print(f"Erro na avaliação: {erro}", file=sys.stderr)
        return 2
    print(json.dumps(resumo, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if resumo["casos_validos"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
