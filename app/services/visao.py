"""CLIP zero-shot em CPU, carregado apenas na primeira análise."""

from threading import Lock

from PIL import Image

from app.schemas.analise import Categoria, EscoreVisual, ResultadoVisual
from app.services.erros import ErroAnalise

MODELO_CLIP = "openai/clip-vit-base-patch32"
CANDIDATAS = (
    (Categoria.BURACO, "a photo of a pothole in an asphalt road"),
    (Categoria.LIXO, "a photo of garbage or construction debris dumped on a street"),
    (Categoria.CALCADA, "a photo of a broken or damaged sidewalk"),
    (Categoria.ILUMINACAO, "a photo of a visibly broken street light fixture or damaged light pole"),
    (Categoria.SEM_PROBLEMA, "a photo of an urban street with no evident maintenance problem"),
)
_recursos = None
_trava = Lock()


def _carregar_modelo():
    # Imports e downloads somente em uma requisição válida e configurada.
    import torch
    from transformers import CLIPModel, CLIPProcessor

    processador = CLIPProcessor.from_pretrained(MODELO_CLIP)
    modelo = CLIPModel.from_pretrained(MODELO_CLIP)
    modelo.eval()
    return torch, processador, modelo


def classificar(imagem: Image.Image) -> ResultadoVisual:
    global _recursos
    try:
        # Serializa carga e inferência para limitar picos de memória.
        with _trava:
            if _recursos is None:
                _recursos = _carregar_modelo()
            torch, processador, modelo = _recursos
            entradas = processador(
                text=[texto for _, texto in CANDIDATAS], images=imagem,
                return_tensors="pt", padding=True,
            )
            with torch.inference_mode():
                valores = modelo(**entradas).logits_per_image.softmax(dim=-1)[0].tolist()
        escores = sorted(
            [EscoreVisual(categoria=cat, escore_relativo=valor)
             for (cat, _), valor in zip(CANDIDATAS, valores, strict=True)],
            key=lambda item: item.escore_relativo, reverse=True,
        )
        # Heurísticas de abstenção; não medem confiança calibrada.
        inconclusivo = (escores[0].escore_relativo < 0.40 or
                        escores[0].escore_relativo - escores[1].escore_relativo < 0.10)
        return ResultadoVisual(escores=escores, inconclusivo=inconclusivo)
    except Exception:
        raise ErroAnalise(503, "Modelo de visão computacional indisponível.") from None
