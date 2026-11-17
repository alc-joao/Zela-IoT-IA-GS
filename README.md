# Zela — Zeladoria Colaborativa com IA

Projeto para a Global Solution 2026/2 da FIAP. O Zela pretende apoiar a identificação
e a priorização de problemas urbanos a partir de fotografias enviadas pela comunidade,
com justificativas e indicação de revisão humana.

Esta etapa prepara um microsserviço Python com FastAPI. A integração de IA ainda
não foi implementada: fotografias válidas recebem **HTTP 503**, sem classificações
simuladas. Nenhum provedor ou modelo foi escolhido.

## Arquitetura prevista

Fluxo atual: cliente → API FastAPI → validação da fotografia → resposta 503.
O próximo passo será conectar a validação a um serviço de análise real, responsável
por produzir uma resposta estruturada e sinalizar quando houver necessidade de
revisão humana. A API não persiste as fotografias; o processamento multipart pode
usar arquivos temporários, gerenciados e fechados pelo framework.

```text
app/
├── __init__.py
├── config.py             # Nome do serviço e limite de upload
├── main.py               # Aplicação e rotas HTTP
├── schemas/
│   ├── __init__.py
│   └── analise.py        # Contrato da futura resposta de IA
└── services/
    ├── __init__.py
    └── imagens.py        # MIME, bytes, formato real e integridade
data/
└── examples/             # Diretório existente, reservado para exemplos
docs/                     # Diretório existente, reservado para documentação
tests/
└── test_api.py
.env.example
.gitignore
requirements.txt
README.md
```

## Requisitos

- Python 3.10 ou superior e `pip`.
- FastAPI, Uvicorn, python-multipart, Pillow e Pydantic.
- pytest e httpx para testes.

Não há dependências de IA nem modelos para baixar nesta etapa.

## Execução local

Execute os comandos na raiz deste repositório, em um terminal Bash ou Zsh:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

A configuração é opcional. Sem variáveis de ambiente, cada fotografia tem limite
de **5 MiB (5.242.880 bytes)**. Para personalizar o limite, copie e edite o exemplo:

```bash
cp .env.example .env
# Edite MAX_IMAGE_SIZE_MB em .env, se necessário.
set -a
source .env
set +a
```

`MAX_IMAGE_SIZE_MB` deve ser um inteiro positivo. A aplicação lê o ambiente do
processo na inicialização; o arquivo `.env` não é carregado automaticamente.
O exemplo não contém segredos e não pressupõe um provedor de IA.

Inicie a API:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Endpoints

### `GET /health`

Retorna HTTP 200 e informa que a API está em execução. Esse endpoint não indica
disponibilidade da futura integração de IA.

```json
{"status": "ok", "servico": "zela-analise-urbana"}
```

```bash
curl http://127.0.0.1:8000/health
```

### `POST /analisar`

Recebe `multipart/form-data` com o campo obrigatório **`fotografia`**. São aceitos
JPEG (`image/jpeg`), PNG (`image/png`) e WebP (`image/webp`). O conteúdo precisa ser
uma imagem íntegra, decodificável e compatível com o MIME declarado; a extensão do
nome do arquivo não é usada como prova do formato.

Além do limite em bytes, há um teto de **25 milhões de pixels** para limitar a
memória usada na decodificação. A leitura de validação é limitada a um byte além
do máximo permitido. Esse limite é aplicado após o processamento multipart; na
implantação, o gateway também deverá limitar o tamanho do corpo da requisição.

```bash
curl -i -X POST http://127.0.0.1:8000/analisar \
  -F 'fotografia=@/caminho/foto.jpg;type=image/jpeg'
```

| HTTP | Situação |
| --- | --- |
| 400 | Arquivo vazio, conteúdo inválido ou imagem corrompida. |
| 413 | Fotografia acima do limite de bytes ou de pixels. |
| 415 | MIME não permitido ou incompatível com o formato real. |
| 422 | Campo `fotografia` ausente ou requisição incompatível com o contrato. |
| 503 | Fotografia válida, mas serviço de análise ainda não configurado. |

Resposta atual para uma imagem válida:

```json
{
  "detail": "O serviço de análise ainda não está configurado. Nenhuma classificação foi gerada."
}
```

O schema `RespostaAnalise` reserva o contrato futuro de sucesso com os campos
obrigatórios `categoria`, `descricao`, `prioridade` (`baixa`, `media` ou `alta`),
`justificativa` e `revisao_humana` (booleano). A documentação OpenAPI apresenta
esse contrato, mas a API ainda não retorna resultados de análise com HTTP 200.

## Testes

Com o ambiente virtual ativado e as dependências instaladas:

```bash
python -m pytest -q
```

Os testes verificam a saúde da API, ausência de arquivo, MIME não permitido ou
divergente, conteúdo vazio ou falso, imagem corrompida, limites de bytes e pixels,
proteção contra descompressão excessiva e resposta 503 para imagens válidas em
todos os formatos aceitos. As pequenas imagens usadas nos testes são geradas em
memória, sem rede, credenciais ou resultados fictícios de IA.
