"""Ollama local via HTTP; recebe somente dados CLIP, nunca fotografias."""

from dataclasses import dataclass
import json
import math
import os
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.schemas.analise import AnaliseGerada, ResultadoVisual
from app.services.erros import ErroAnalise
from app.services.seguranca import DESCRICOES, analise_inconclusiva, prioridade_sugerida


@dataclass(frozen=True)
class ConfiguracaoOllama:
    base_url: str
    modelo: str
    timeout: float


def verificar_configuracao() -> ConfiguracaoOllama:
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
    modelo = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b").strip()
    try:
        url = urlsplit(base)
        porta = url.port
        timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
        if (url.scheme not in ("http", "https") or url.hostname not in ("127.0.0.1", "localhost", "::1")
                or url.username is not None or url.password is not None or url.path
                or url.query or url.fragment or porta == 0 or not modelo
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError
    except ValueError:
        raise ErroAnalise(503, "Configuração Ollama inválida: confira URL local, modelo e timeout positivo.") from None
    return ConfiguracaoOllama(base, modelo, timeout)


def _criar_cliente(timeout: float) -> httpx.Client:
    # Não encaminha dados locais a proxies do ambiente nem segue redirecionamentos.
    return httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False)


def gerar_analise(visual: ResultadoVisual) -> AnaliseGerada:
    if visual.inconclusivo:
        return analise_inconclusiva()
    config = verificar_configuracao()
    categoria = max(visual.escores, key=lambda item: item.escore_relativo).categoria
    schema = AnaliseGerada.model_json_schema()
    instrucoes = (
        "Você organiza dados CLIP e NÃO recebeu nem viu a fotografia. Responda somente JSON conforme o schema. "
        "Use exclusivamente a categoria e os escores fornecidos, que são relativos, não probabilidades calibradas. "
        "Não invente localização, objetos, dimensões, pessoas, danos específicos, causas ou riscos. "
        "Não afirme funcionamento de luminárias. Não acrescente fatos à categoria CLIP. "
        "A descrição deve ser curta e condicional: copie exatamente a descrição permitida abaixo. "
        "Se houver dúvida, sinalize categoria inconclusiva, prioridade null e revisão humana. "
        "Prioridade é apenas sugestão de triagem, nunca decisão oficial. Sempre revisao_humana=true. "
        f"Descrição permitida: {DESCRICOES[categoria]} "
        f"Prioridade permitida: {json.dumps(prioridade_sugerida(categoria))}. "
        "Justifique sem acrescentar observações, usando somente a categoria CLIP. "
        "Schema JSON: " + json.dumps(schema, ensure_ascii=False)
    )
    dados = {
        "categoria_clip": categoria.value,
        "escores_relativos": [item.model_dump(mode="json") for item in visual.escores],
        "inconclusivo": visual.inconclusivo,
    }
    payload = {
        "model": config.modelo,
        "messages": [{"role": "system", "content": instrucoes},
                     {"role": "user", "content": json.dumps(dados, ensure_ascii=False)}],
        "stream": False,
        "format": schema,
        "options": {"temperature": 0, "num_predict": 512},
    }
    try:
        with _criar_cliente(config.timeout) as cliente:
            resposta = cliente.post(config.base_url + "/api/chat", json=payload)
            resposta.raise_for_status()
            envelope = resposta.json()
        if (not isinstance(envelope, dict) or envelope.get("done") is not True
                or envelope.get("done_reason", "stop") != "stop"):
            raise ValueError
        mensagem = envelope.get("message")
        if (not isinstance(mensagem, dict) or mensagem.get("role") != "assistant"
                or not isinstance(mensagem.get("content"), str)):
            raise ValueError
        return AnaliseGerada.model_validate_json(mensagem["content"], strict=True)
    except httpx.TimeoutException:
        raise ErroAnalise(504, "Tempo limite do Ollama excedido.") from None
    except httpx.HTTPStatusError as erro:
        if erro.response.status_code == 404:
            raise ErroAnalise(503, "Modelo Ollama não encontrado; confira OLLAMA_MODEL no servidor local.") from None
        if erro.response.status_code >= 500:
            raise ErroAnalise(503, "Ollama local indisponível.") from None
        raise ErroAnalise(502, "Ollama rejeitou a solicitação; confira suporte ao JSON Schema.") from None
    except httpx.RequestError:
        raise ErroAnalise(503, "Não foi possível conectar ao Ollama local.") from None
    except (ValidationError, ValueError):
        raise ErroAnalise(502, "Ollama retornou JSON inválido, incompleto ou fora do contrato esperado.") from None
