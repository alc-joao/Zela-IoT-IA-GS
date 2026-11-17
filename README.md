# Zela — Zeladoria Colaborativa com IA

Projeto IoT/IA para a Global Solution 2026/2 da FIAP. Este microsserviço apoia a
identificação de problemas urbanos em fotografias e sugere prioridades sujeitas
à revisão humana. Ele usa visão computacional real e geração multimodal,
sem resultados simulados em produção.

## Arquitetura

Cliente → FastAPI → validação → CLIP zero-shot → Gemini multimodal → validação
Pydantic → regras de abstenção → JSON.

- `app/main.py`: aplicação, `/health`, `/analisar` e documentação OpenAPI.
- `app/config.py`: nome do serviço e limite de upload.
- `app/schemas/analise.py`: categorias, escores visuais e contratos JSON.
- `app/services/imagens.py`: MIME, bytes, dimensões e integridade.
- `app/services/visao.py`: CLIP, carga sob demanda e reutilização por processo.
- `app/services/generativa.py`: SDK oficial google-genai, prompt e validação.
- `app/services/analise.py`: normalização da foto e coordenação das etapas.
- `app/services/erros.py`: erros públicos sem detalhes internos.
- `tests/test_api.py`: validações HTTP originais.
- `tests/test_ia.py` e `tests/conftest.py`: integração e falhas com stubs isolados.
- `data/examples/` e `docs/`: diretórios existentes, preservados.

A API não armazena fotografias permanentemente. O framework pode usar arquivos
multipart temporários. Após validação, a foto tem orientação EXIF aplicada,
é convertida em RGB, reduzida a no máximo 1600 × 1600 mantendo a proporção e
reencodificada sem metadados. CLIP e Gemini recebem esses mesmos pixels.
**A imagem normalizada é enviada ao Google Gemini**, junto dos escores CLIP.

## Modelos e interpretação

O modelo `openai/clip-vit-base-patch32` é utilizado via Transformers e PyTorch em
CPU. Ele compara a imagem com estas descrições em inglês:

| Categoria retornada | Descrição candidata |
| --- | --- |
| `buraco_no_asfalto` | a photo of a pothole in an asphalt road |
| `entulho_ou_lixo` | a photo of garbage or construction debris dumped on a street |
| `calcada_danificada` | a photo of a broken or damaged sidewalk |
| `iluminacao_visivelmente_danificada` | a photo of a visibly broken street light fixture or damaged light pole |
| `sem_problema_evidente` | a photo of an urban street with no evident maintenance problem |

O softmax dos logits produz **escores relativos às candidatas**, não probabilidades
calibradas de um problema existir. Mudar as descrições muda os escores. CLIP sempre
compara essas cinco opções; não é um detector validado de todos os problemas urbanos.

Há abstenção conservadora se o maior escore for menor que 0,40 ou a diferença para
o segundo for menor que 0,10. São heurísticas iniciais, sem calibração em dados
locais. Também há abstenção se Gemini indicar incerteza ou discordar da categoria
mais bem pontuada pelo CLIP. A resposta usa `categoria=inconclusiva`,
`analise_inconclusiva=true`, `prioridade=null` e `revisao_humana=true`.
Uma descrição neutra substitui conclusões conflitantes nesses casos.

Gemini considera a imagem e os escores para gerar descrição objetiva, justificativa
e sugestão de prioridade. Usa JSON estruturado com schema Pydantic, validado também
localmente. O modelo padrão configurável é `gemini-3.8-flash`, documentado com entrada
de imagem e saída estruturada. A disponibilidade depende da conta e do provedor.

Todas as respostas exigem revisão humana nesta versão. A prioridade **não é decisão
oficial**; é `baixa`, `media`, `alta` ou `null` quando inconclusiva ou sem problema
evidente. Os nomes dos cinco campos originais foram preservados; `categoria` agora
é enumerada e `prioridade` admite `null` para evitar atribuições sem fundamento.

Uma fotografia não prova que uma luminária está apagada: a candidata de iluminação
trata apenas de danos físicos visíveis. O prompt proíbe inventar localização,
dimensões, risco confirmado ou pessoas envolvidas e manda ignorar instruções
escritas na imagem. Pydantic valida estrutura e tipos; não comprova a veracidade
das afirmações. Os modelos podem errar, inclusive em fotos fora do domínio ou com
baixa qualidade; a abstenção não garante detectar todos esses casos. Não houve
avaliação de acurácia com uma base de fotografias urbanas nesta etapa.

## Requisitos e execução local

Python 3.10 ou superior, pip e recursos de memória/disco compatíveis com PyTorch e
CLIP. Não é necessária GPU. A instalação inclui bibliotecas grandes; execute-a
quando desejar preparar o ambiente:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edite `.env`: preencha `GEMINI_API_KEY` com sua chave do Google AI Studio e escolha
um `GEMINI_MODEL` compatível com imagem e saída estruturada. Nunca versione a chave.
O arquivo não é carregado automaticamente; em Bash/Zsh, exporte-o antes de iniciar:

```bash
set -a
source .env
set +a
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

| Variável | Configuração |
| --- | --- |
| `GEMINI_API_KEY` | Obrigatória para análise; sem valor no exemplo. |
| `GEMINI_MODEL` | Padrão `gemini-3.8-flash`; deve estar disponível para sua conta. |
| `MAX_IMAGE_SIZE_MB` | Inteiro positivo; padrão 5 MiB (5.242.880 bytes). |
| `HF_HOME` | Opcional; diretório de cache gerenciado pelo Hugging Face. |

CLIP só é carregado na primeira análise válida com chave configurada. Essa
requisição poderá baixar pesos/configurações do Hugging Face se não estiverem em
cache; poderá demorar e requerer internet. Importar a API, consultar `/health`,
gerar OpenAPI e coletar/executar os testes não baixa pesos. Depois da carga, o
modelo é reutilizado, com inferência serializada por processo. Cada worker teria
sua própria cópia; comece com um processo. Falhas de carga retornam 503 e permitem
nova tentativa numa próxima requisição. Não há fallback simulado.

O Gemini tem timeout HTTP de 30 segundos e uma tentativa por análise. Esse timeout
não limita a carga inicial do CLIP nem o tempo total da requisição. As chamadas
externas estão sujeitas às cotas e condições da conta Google.

Swagger: http://127.0.0.1:8000/docs · ReDoc: http://127.0.0.1:8000/redoc

## Endpoints

`GET /health` retorna HTTP 200:

```json
{"status": "ok", "servico": "zela-analise-urbana"}
```

É uma checagem de execução da API, sem carregar modelos nem consultar o provedor.

`POST /analisar` recebe multipart/form-data no campo obrigatório `fotografia`:

```bash
curl -i http://127.0.0.1:8000/analisar -F 'fotografia=@/caminho/foto.jpg;type=image/jpeg'
```

Aceita JPEG, PNG e WebP com MIME compatível com o conteúdo real. Rejeita arquivos
vazios, falsos, corrompidos, acima do limite em bytes ou de 25 milhões de pixels.
O limite de bytes é aplicado depois do parsing multipart; em implantação, o gateway
também precisa limitar o corpo da requisição. Para arquivos animados, somente o
primeiro quadro é analisado.

| HTTP | Situação |
| --- | --- |
| 200 | Análise estruturada, que pode ser inconclusiva. |
| 400 | Conteúdo vazio, inválido ou corrompido. |
| 413 | Limite de bytes ou pixels excedido. |
| 415 | MIME não permitido ou divergente do formato real. |
| 422 | Campo ausente ou requisição incompatível. |
| 502 | Gemini retornou resposta incompleta, bloqueada ou inválida pelo schema. |
| 503 | Chave/modelo não configurado, falha do CLIP ou provedor indisponível, inclusive cota/autenticação. |
| 504 | Timeout do Gemini. |

Erros retornam `{"detail": "mensagem pública"}`, sem chave nem exceções internas.
O contrato HTTP 200 está documentado em OpenAPI e contém `categoria`, `descricao`,
`prioridade`, `justificativa`, `revisao_humana`, `analise_inconclusiva`,
`visao_computacional` (modelo, cinco escores, indicação de abstenção e observação)
e `aviso` sobre prioridade sugerida. Os escores são ordenados do maior ao menor.

## Testes

```bash
source .venv/bin/activate
python -m pytest -q
```

Os testes usam imagens pequenas em memória e substituem dependências externas por
stubs: não precisam de chave, internet, Transformers, PyTorch nem SDK Google para
rodar com as dependências HTTP/Pillow/Pydantic de teste já instaladas. As fixtures
removem credenciais do ambiente e bloqueiam os pontos de chamada externa por padrão.
Stubs nunca participam da execução de produção.

Cobertura: validações HTTP, sucesso integrado, imagem/escores enviados ao Gemini,
modelo configurável, ausência de chave, resposta malformada ou bloqueada,
timeout/indisponibilidade sem vazamento, abstenção, prioridade não oficial, carga
CLIP sob demanda e reutilização, além de importação/OpenAPI sem bibliotecas pesadas.
São testes de comportamento com stubs, não uma validação de qualidade dos modelos
nem uma chamada real aos provedores.

## Avaliação real do CLIP

O protocolo para avaliar fotografias reais com CLIP, sem Gemini nem downloads,
está em [docs/avaliacao.md](docs/avaliacao.md). Com pesos já no cache local e um
manifesto real preparado pela equipe:

```bash
python -m scripts.avaliar_clip data/avaliacao/entrada.csv --saida data/avaliacao/resultados.csv
```

O comando produz CSV por fotografia e resumo JSON; nenhum resultado real foi
gerado nesta etapa.

## Referências oficiais

- [CLIP no Transformers](https://huggingface.co/docs/transformers/model_doc/clip)
- [Modelo CLIP utilizado](https://huggingface.co/openai/clip-vit-base-patch32)
- [SDK oficial google-genai: multimodalidade, schema e configuração HTTP](https://googleapis.github.io/python-genai/)
- [Gemini 3.8 Flash: modalidades e saída estruturada](https://aistudio.google.com/docs/models/gemini-3.8-flash)
