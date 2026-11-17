# Avaliação real da Visão Computacional — Zela

Global Solution 2026/2 da FIAP. Este protocolo avalia exclusivamente o CLIP
`openai/clip-vit-base-patch32` reutilizando `app.services.visao.classificar`.
Não avalia a geração textual, a prioridade nem a integração Gemini.

**Situação: avaliação exploratória real executada em 17/11/2026**, com 3
fotografias válidas e 3 acertos, sem abstenções ou arquivos inválidos. Os resultados
estão no [CSV](../data/avaliacao/resultados.csv) e no
[resumo JSON](../data/avaliacao/resultados.resumo.json). A amostra é pequena e
**não comprova acurácia geral**. O teste real da API com Ollama está registrado
separadamente ao final deste documento.

Os **89 testes automatizados aprovados** usam stubs nos pontos de acesso a modelos
e provedores e não compõem essa avaliação real. As tabelas de coleta abaixo
distinguem o que já foi observado das condições ainda pendentes.

## Preparar o conjunto

1. Obter fotografias reais, com autorização/licença verificável, e verificar sua
   privacidade antes de armazená-las. Usar identificadores neutros nos arquivos.
2. Selecionar cenas distintas, sem duplicatas, recortes da mesma foto ou várias
   fotos quase idênticas contadas como evidências independentes.
3. Rotular antes de ver as previsões. Registrar o responsável pela anotação e
   revisar divergências com outra pessoa, quando possível. Não escolher o rótulo
   apenas pelo nome da foto ou pela descrição do site de origem.
4. Para fotos com múltiplos problemas sem um alvo visual dominante, enquadramento
   insuficiente ou conteúdo não discernível, usar `inconclusiva`. Não atribuir um
   defeito a uma foto escura apenas porque sua fonte menciona um problema.
5. Separar um conjunto de desenvolvimento de outro de avaliação final. Se mudar
   candidatas ou limiares após inspecionar resultados, registrar a alteração e
   usar fotos ainda não utilizadas para a avaliação final.
6. Guardar as fotos em `data/avaliacao/fotos/`, pasta já ignorada pelo Git por
   motivos de distribuição e privacidade. O repositório inclui manifesto e
   relatórios, mas não distribui essas fotografias. **Terceiros devem fornecer
   imagens próprias** para repetir o protocolo; um clone não contém as fotos
   referidas no manifesto original. Registrar as origens e autorizações das
   novas imagens e preparar um novo manifesto em `data/avaliacao/`.

As categorias aceitas são as de `app.schemas.analise.Categoria`:

| Rótulo no CSV | Critério observável para anotação |
| --- | --- |
| `buraco_no_asfalto` | Cavidade ou ruptura visível no pavimento asfáltico. |
| `entulho_ou_lixo` | Resíduos ou entulho visíveis no espaço urbano. |
| `calcada_danificada` | Dano físico visível na superfície da calçada. |
| `iluminacao_visivelmente_danificada` | Dano físico visível em luminária/poste; não inferir que a lâmpada está apagada. |
| `sem_problema_evidente` | Cena urbana discernível sem problema evidente entre os alvos; não garante ausência de defeitos. |
| `inconclusiva` | Evidência insuficiente, ambígua ou sem alvo dominante para escolher um dos cinco rótulos. |

`inconclusiva` é um rótulo de abstenção, não uma sexta candidata do CLIP.

## CSV de entrada

Criar um CSV UTF-8, delimitado por vírgula, com este cabeçalho:

```csv
caminho,categoria
```

O [manifesto da primeira avaliação](../data/avaliacao/entrada.csv) contém três
registros com caminhos sob `fotos/`. Para uma nova amostra, criar, por exemplo,
`data/avaliacao/entrada-repeticao.csv`, com os caminhos das imagens próprias e
seus rótulos, preservando o manifesto e as evidências originais.

Acrescentar somente linhas referentes a fotos reais que a equipe efetivamente
obteve e anotou. `caminho` pode ser absoluto ou relativo **à pasta do CSV**, não à
pasta do terminal. Valores de `categoria` devem corresponder exatamente à tabela.
Para caminhos contendo vírgulas, usar aspas conforme o formato CSV. BOM UTF-8 é
aceito. Cabeçalhos duplicados ou ausência das duas colunas impedem a execução.

Colunas extras como `condicao`, `fonte`, `autor`, `licenca`, `url_licenca` e
`alteracoes` podem ser mantidas no manifesto; o script ignora essas colunas nas
métricas. Guardar esse CSV com os relatórios para relacionar as condições às linhas
avaliadas. Não colocar nomes pessoais, coordenadas ou endereços nos caminhos.

## Executar sem downloads nem provedores generativos

Pré-requisitos: ambiente virtual já preparado com as dependências do projeto e
pesos/processador CLIP **já presentes no cache local** do Hugging Face.
`GEMINI_API_KEY` e servidor Ollama não são necessários. Não há instalação ou
download automático feito por este protocolo. Se o cache estiver ausente,
registrar a pendência e preparar o modelo separadamente antes da avaliação.

Após preparar as fotos próprias e um novo manifesto real em
`data/avaliacao/entrada-repeticao.csv`, executar na raiz do projeto:

```bash
source .venv/bin/activate
python -m scripts.avaliar_clip data/avaliacao/entrada-repeticao.csv --saida data/avaliacao/resultados-repeticao.csv
```

O sufixo `-repeticao` evita sobrescrever os relatórios existentes da primeira
avaliação; escolha outros nomes a cada execução. Os novos arquivos de entrada e
fotos devem ser preparados por quem repete o protocolo. Também funciona
`python scripts/avaliar_clip.py ...`. Para consultar argumentos sem carregar modelos:

```bash
python -m scripts.avaliar_clip --help
```

O script força `HF_HUB_OFFLINE=1` e `TRANSFORMERS_OFFLINE=1` antes da primeira
inferência. Não chama Ollama nem Gemini, não possui modo simulado e sempre usa
`visao.classificar` na execução real. CLIP mantém sua carga sob demanda
e reutilização no processo. Se necessário, apontar `HF_HOME` para um cache local
existente antes de iniciar; o avaliador não popula esse cache.

São produzidos:

- O CSV solicitado, com uma linha por registro de entrada, inclusive os inválidos.
- Um JSON de métricas no mesmo diretório, com sufixo `.resumo.json`, além do resumo
  no terminal. `--resumo caminho.json` permite escolher outro arquivo.

As saídas devem ser novas: o script não sobrescreve arquivos existentes.
`--min-exemplos-por-categoria 5` é o padrão. Esse mínimo serve para apresentação
exploratória e **não** estabelece suficiência estatística ou confiabilidade.
Códigos de saída: `0` se houver ao menos um caso válido, mesmo com erros em outras
linhas; `1` se não houver casos válidos; `2` para erro na configuração/CSV/saída.
Um código `0` não comprova qualidade do classificador nem integridade de todo o lote.

## Processamento e critérios

O script verifica arquivos e reutiliza a validação de imagens do projeto: JPEG,
PNG ou WebP, limite em bytes da API (padrão 5 MiB), integridade, decodificação e
teto de 25 milhões de pixels. Como não há upload multipart, o MIME é obtido do
formato real detectado pelo Pillow. Arquivos ausentes, corrompidos, formatos não
aceitos e categorias inválidas são registrados, sem interromper o restante.

A orientação EXIF é aplicada, a foto é convertida em RGB e reduzida a no máximo
1600 × 1600 mantendo a proporção, como na etapa visual da API. Somente o primeiro
quadro de arquivos animados é analisado. O processador CLIP aplica então seu
pré-processamento próprio. A inferência, as candidatas em inglês e a regra de
abstenção vêm do serviço existente; o script não implementa outro modelo.

A regra atual abstém quando o maior escore é menor que 0,40 ou a diferença entre
os dois maiores é menor que 0,10. São heurísticas sem calibração em dados locais.
O softmax produz **escores relativos às candidatas, não probabilidades calibradas**.
Um escore de 0,80 não comprova 80% de chance de existir um problema.

## CSV de saída e métricas

| Campo | Significado |
| --- | --- |
| `linha`, `caminho` | Linha física do CSV (ao fim do registro, para campos multilinha) e caminho informado. |
| `categoria_esperada` | Rótulo de referência anotado pela equipe. |
| `categoria_top1` | Categoria de maior escore entre as cinco candidatas. |
| `categoria_prevista` | `inconclusiva` se houve abstenção; caso contrário, `categoria_top1`. |
| `maior_escore_relativo` | Maior escore CLIP, sem interpretação probabilística. |
| `abstencao` | `True` ou `False`, conforme a regra do serviço. |
| `acerto` | `True` para igualdade entre categoria prevista e esperada; `False` para erro. |
| `status`, `erro` | `valido` ou diagnóstico por linha, sem detalhes internos do modelo. |

Em linhas inválidas ou com falha de inferência, previsão/escore/abstenção/acerto
ficam vazios: falha operacional não é uma classificação errada nem uma abstenção.

Definições do resumo:

- **Casos válidos (N):** imagem aceita, categoria reconhecida e inferência concluída.
- **Acurácia simples:** acertos / N, na escala 0–1. A comparação usa a decisão após
  abstenção: abster em foto de classe conhecida conta como erro; se o rótulo humano
  for `inconclusiva`, abster conta como acerto. Não é acurácia top-1 bruta do CLIP.
- **Percentual inconclusivo:** 100 × abstenções / N, independentemente de estarem corretas.
- **Por categoria:** agrupamento pelo rótulo esperado, com contagens sempre visíveis.
  Acurácia e percentual ficam `null` abaixo do mínimo configurado.
- **N = 0:** acurácia e percentual ficam `null`, nunca zero nem sucesso presumido.

Fotos inválidas e falhas de modelo ficam fora dos denominadores, mas suas
quantidades e linhas devem ser apresentadas junto das métricas. O JSON registra
modelo e candidatas. Guardar versão do código, versões das dependências e revisão
do modelo/cache no registro da execução para permitir comparação posterior.

## Matriz de casos a coletar e testar

| Grupo | Critério de observação | Registro real |
| --- | --- | --- |
| Cada uma das cinco classes | Exemplos distintos, alvo legível e rótulo revisado. | Um acerto em buraco, um em lixo/entulho e um em calçada; faltam exemplos e as demais classes. |
| Escuras/subexpostas | Verificar se ainda há evidência; usar `inconclusiva` quando não houver. | Pendente na avaliação real |
| Ambíguas/múltiplos problemas | Sem alvo dominante, esperar encaminhamento à revisão humana. | Pendente na avaliação real |
| Sem problema evidente | Cenas urbanas diversas; observar falsos positivos. | Pendente na avaliação real |
| Iluminação | Dano físico visível; foto escura ou poste diurno não prova lâmpada apagada. | Pendente na avaliação real |
| Fora do domínio | Foto não urbana ou enquadramento insuficiente; analisar abstenções e erros. | Pendente na avaliação real |
| Arquivo ausente/corrompido/vazio | Registrar erro e continuar o lote, sem inferência válida. | Pendente na avaliação real |
| Rótulo inválido/formato não aceito | Registrar diagnóstico; não incluir em acurácia. | Pendente na avaliação real |

Grupos de condição não são novas categorias do modelo. Para resultados por
condição (escura, ambígua etc.), revisar as linhas usando o manifesto original;
o resumo automático agrupa apenas por categoria esperada.

## Registro da avaliação real

| Item | Valor real |
| --- | --- |
| Data e responsáveis | 17/11/2026; responsáveis a preencher. |
| Versão do código e dependências | A preencher com as versões da execução registrada. |
| Revisão/cache CLIP e equipamento | Modelo `openai/clip-vit-base-patch32`; revisão/cache e equipamento a preencher. |
| Manifesto, origens e licenças | [entrada.csv](../data/avaliacao/entrada.csv); origens e autorizações/licenças a documentar. |
| Quantidade por classe e condição | 1 buraco, 1 lixo/entulho, 1 calçada; condições detalhadas a documentar. |
| Regras de anotação e revisão | Rótulos prévios conforme registro; responsáveis e eventual revisão a documentar. |
| Arquivos CSV/JSON produzidos | [resultados.csv](../data/avaliacao/resultados.csv) e [resultados.resumo.json](../data/avaliacao/resultados.resumo.json). |
| Casos válidos / inválidos / falhas de modelo | 3 / 0 / 0. |
| Acurácia simples e inconclusivas (%) | 3/3 (100% apenas nesta amostra); 0%. |
| Resultados por categoria e tamanho de cada grupo | 1 acerto em cada uma das 3 classes observadas; métricas por categoria `null` por insuficiência de exemplos (mínimo configurado: 5). |
| Erros observados, divergências e limitações | Nenhum erro de classificação observado nos 3 casos; amostra pequena, incompleta e sem validação de acurácia geral. |

Não preencher essa tabela com os resultados dos testes automatizados.

## Fontes, licença e privacidade

Pode-se obter fotos reais no Wikimedia Commons, verificando **a página de cada
arquivo**, autoria e condições de reutilização; estar acessível na internet não
é prova de licença. Registrar URL de origem, licença/link, autoria e alterações
no manifesto. As exigências variam entre arquivos. Ver a
[orientação oficial de reutilização do Commons](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia).

Preferir arquivos com permissões claras e cumprir atribuição e demais condições.
Licenças Creative Commons têm requisitos diferentes, incluindo restrições a
adaptações em algumas modalidades. Conferir a licença específica antes de recortar,
anonimizar ou publicar; ver o [guia oficial de licenças CC](https://creativecommons.org/cc-licenses/).
Fotos próprias também podem ser usadas com origem e autorização registradas.

Selecionar fotos sem rostos, placas, números de imóveis, pessoas identificáveis ou
localização sensível; se necessário, obter uma versão sanitizada permitida pela
licença ou escolher outra imagem. Remover metadados sensíveis **antes de guardar
ou compartilhar o conjunto**. O pré-processamento do script não apaga o EXIF dos
originais no disco. Não inferir coordenadas nem registrar endereço exato. Manter
as fotos locais, na pasta ignorada `data/avaliacao/fotos/`; revisar privacidade e
licença antes de distribuir qualquer imagem ou novo relatório. Os relatórios
CSV/JSON da primeira execução estão versionados, mas as fotografias não. Sua
ausência no clone é intencional por motivos de distribuição e privacidade, e
exige que terceiros preparem imagens próprias para uma nova avaliação.

O modelo é zero-shot e não foi treinado especificamente para zeladoria local.
As escolhas de candidatas, iluminação, enquadramento, distribuição de classes,
pequeno tamanho da amostra e possíveis vieses influenciam o resultado. Acurácia
global pode esconder erros em classes raras. Uma foto não estabelece dimensões,
risco confirmado ou funcionamento elétrico. A avaliação não valida decisão oficial.

Referências técnicas primárias:

- [Model card do CLIP e limitações](https://huggingface.co/openai/clip-vit-base-patch32).
- [CLIP no Transformers](https://huggingface.co/docs/transformers/model_doc/clip).
- Serviço local: `app/services/visao.py`, fonte das candidatas e da abstenção.

## Testes automatizados do avaliador

```bash
source .venv/bin/activate
python -m pytest -q tests/test_avaliar_clip.py
```

São arquivos temporários pequenos, sem fotos reais. Somente a inferência CLIP é
substituída nos testes do script; leitura, validação, CSV e métricas executam de
verdade. A infraestrutura existente bloqueia pontos de acesso externo por padrão.
Não há argumento para ativar stubs na avaliação real.

## Primeira avaliação real — 17/11/2026

**Modelo:** openai/clip-vit-base-patch32

**Metodologia:** classificação zero-shot com fotografias urbanas rotuladas
previamente, comparando a categoria prevista **após a regra de abstenção** com a
categoria esperada. Como não houve abstenção nesses três casos, a categoria
prevista coincidiu com a categoria top-1 em todas as linhas.

### Resultados observados

| Categoria esperada | Resultado |
|---|---|
| Buraco no asfalto | Acerto |
| Entulho ou lixo | Acerto |
| Calçada danificada | Acerto |

- Casos válidos: 3
- Acertos: 3
- Acurácia simples da amostra: 100%
- Análises inconclusivas: 0
- Arquivos inválidos nesta execução: 0

### Limitações

A amostra é pequena e não representa a precisão geral do modelo. Não houve quantidade suficiente de exemplos para métricas por categoria.

Não foram avaliados nesta execução casos de imagens corrompidas, fotos escuras, enchentes ou ausência de problemas evidentes.

Os escores CLIP são relativos às descrições candidatas, não probabilidades calibradas. As previsões precisam de revisão humana.

As fotografias estão armazenadas localmente em `data/avaliacao/fotos/`, ignorada
pelo Git por motivos de distribuição e privacidade. Sua origem e autorização de
uso ainda devem ser documentadas. Terceiros devem usar imagens próprias e um
novo manifesto para repetir o protocolo; não é possível repetir exatamente o
mesmo conjunto apenas com o conteúdo versionado.

### Evidências

- [data/avaliacao/entrada.csv](../data/avaliacao/entrada.csv)
- [data/avaliacao/resultados.csv](../data/avaliacao/resultados.csv)
- [data/avaliacao/resultados.resumo.json](../data/avaliacao/resultados.resumo.json)

A avaliação utilizou o modelo CLIP real, sem Ollama nem Gemini. Não avaliou a
qualidade de geração textual ou o funcionamento externo desses provedores.

## Teste ponta a ponta com Ollama — 17/11/2026

- Imagem real: `data/avaliacao/fotos/buraco_na_rua-831589.jpg`
- Classificação CLIP: `buraco_no_asfalto`
- Resposta da API: `POST /analisar` retornou HTTP 200
- Provedor: Ollama local, modelo `qwen2.5:1.5b`
- Verificação local registrada: nenhum modelo carregado antes; Qwen confirmado carregado após a requisição real
- Saída estruturada validada, com revisão humana obrigatória
- Descrição final padronizada pela camada de segurança
- Arquivo: [docs/evidencias/analise-buraco.json](evidencias/analise-buraco.json)

Somente o CLIP analisa a fotografia no fluxo local. O Qwen é um LLM textual:
recebe a categoria e os escores relativos do CLIP, com a indicação de abstenção e
instruções, e produz saída estruturada para confirmação/abstenção. Ele não recebe
nem inspeciona a imagem. Pydantic valida a estrutura; depois, as regras de
segurança podem abster, fixam prioridade e justificativa e usam uma descrição
padronizada. Uma descrição livre diferente é descartada.

O JSON versionado contém o corpo final da resposta, não a saída bruta do Ollama.
A frase “Pode haver um buraco no asfalto; é necessária verificação humana.” é
definida pela camada de segurança e não deve ser apresentada como texto gerado
pelo Qwen. O teste confirma o acionamento local do modelo generativo, mas não
comprova aproveitamento de sua redação livre nem qualidade geral da classificação.

## Situação do Gemini

Gemini foi preservado como alternativa multimodal selecionada por
`IA_PROVIDER=gemini`, sem fallback automático. Nessa opção, ele recebe a fotografia
normalizada e os escores do CLIP, e sua resposta passa por Pydantic e pelas mesmas
regras de segurança. **Chamadas reais da API Gemini não foram validadas com
sucesso.** A cobertura automatizada com stubs não substitui essa validação externa.

### Origem das fotografias de avaliação

As cinco fotografias utilizadas nos testes foram obtidas
na internet, e não produzidas pela equipe.

As URLs originais, os autores e as licenças não foram
registrados. Portanto, não há autorização de
redistribuição comprovada.

As imagens foram utilizadas somente na avaliação local
e permanecem excluídas do repositório pelo .gitignore.

Para reproduzir os experimentos, recomenda-se utilizar
fotografias próprias ou com licença de uso adequada.
