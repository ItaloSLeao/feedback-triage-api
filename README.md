# API de análise de feedback

API em FastAPI para analisar avaliações em português e identificar alimentos em fotos. Combina dois modelos que treinei e publiquei no Hugging Face:

- [Extrator de avaliações](https://huggingface.co/aitalo/qwen2.5-0.5b-avaliacoes-ptbr): identifica sentimento, aspectos, problema principal e necessidade de ação.
- [Classificador de alimentos](https://huggingface.co/aitalo/convnext-tiny-comida-brasileira): reconhece 20 classes e rejeita previsões com baixa confiança.

A API pode ser usada diretamente ou integrada ao n8n para fazer a triagem dos feedbacks e enviar alertas ao Telegram. O projeto foi desenvolvido para execução em CPU e uso em estudo e portfólio.

## Como rodar

Você precisa de Docker com Compose. Na primeira inicialização, a API baixa cerca de 1,1 GB de modelos; reserve aproximadamente 3 GB de RAM livres.

### Apenas a API

```bash
docker compose up --build
```

A API fica em http://127.0.0.1:8000, com documentação interativa em http://127.0.0.1:8000/docs. Aguarde o carregamento dos modelos e confira:

```bash
curl http://127.0.0.1:8000/health
```

O status HTTP será `200` quando os dois modelos estiverem disponíveis e `503` se algum falhar no carregamento. O cache fica no volume `hf-cache` e é reutilizado ao recriar os contêineres.

### API com n8n

Para usar a automação e os alertas do Telegram, suba os dois serviços:

```bash
docker compose -f docker-compose.yml -f docker-compose.n8n.yml up -d --build
```

Abra o n8n em http://127.0.0.1:5678 e siga a configuração abaixo. Os workflows e as credenciais ficam salvos no volume `n8n_data`.

## Automação com n8n

O fluxo recebe o feedback por webhook, chama a API, responde ao cliente após a análise e encaminha os alertas conforme a prioridade.

**Para enviar alertas ao Telegram, use o webhook do n8n.** Chamadas diretas à API, como `POST /v1/review/extract` ou `POST /v1/feedback/analyze`, retornam a análise, mas não executam o workflow.

### 1. Importar o workflow

Na primeira abertura do n8n, crie sua conta local. No editor de workflows, use **Import from File…** e selecione [workflows/triagem-feedback.workflow.json](workflows/triagem-feedback.workflow.json).

Os dois nós **API analisa** já apontam para `http://api:8000/v1/feedback/analyze`. Mantenha esse endereço: dentro do contêiner do n8n, `localhost` se refere ao próprio n8n.

### 2. Configurar o Telegram

1. No Telegram, abra o [BotFather](https://t.me/BotFather), envie `/newbot` e siga as instruções para obter o token do bot.
2. Abra uma conversa com o bot criado e envie `/start`.
3. Para consultar o ID dessa conversa, substitua `SEU_TOKEN` e execute:

   ```bash
   curl "https://api.telegram.org/botSEU_TOKEN/getUpdates"
   ```

   Copie o valor de `message.chat.id` na resposta. Se `result` estiver vazio, envie uma nova mensagem ao bot e consulte novamente.
4. No n8n, abra um nó do Telegram, crie uma credencial **Telegram** e preencha **Access Token** com o token fornecido pelo BotFather.
5. Selecione essa credencial e substitua `SEU_CHAT_ID` pelo ID obtido nos três nós: **Alerta: prioridade alta**, **Revisao manual (saida invalida)** e **Alerta: API falhou**.

Esse passo a passo usa uma conversa privada com o bot. Veja também as referências oficiais de [credenciais do Telegram no n8n](https://docs.n8n.io/integrations/builtin/credentials/telegram/) e da [API do Telegram](https://core.telegram.org/bots/api#getupdates).

### 3. Configurar autenticação, se necessário

Por padrão, a API local não exige chave. Se você definiu `API_KEY` no `.env`, configure os dois nós **API analisa** com **Authentication → Generic Credential Type → Header Auth**. Crie e selecione uma credencial com o nome de cabeçalho `X-API-Key` e o mesmo valor definido na API.

### 4. Testar e publicar

No nó **Webhook feedback**, clique em **Listen for test event** e execute:

```bash
curl -X POST http://localhost:5678/webhook-test/feedback \
  -F "texto=Comprei duas unidades e só veio uma. Ninguém responde no SAC."
```

Confira o resultado de cada nó no editor. Para manter o fluxo disponível, publique o workflow com **Publish**; em versões anteriores do n8n, use **Active**. Depois, envie as requisições para a URL de produção:

```bash
curl -X POST http://localhost:5678/webhook/feedback \
  -F "texto=Comprei duas unidades e só veio uma. Ninguém responde no SAC."
```

Para incluir uma foto, acrescente `-F "imagem=@prato.jpg"` ao comando.

| URL | Quando usar |
|---|---|
| `/webhook-test/feedback` | Durante a escuta de teste no editor; é necessário iniciar a escuta novamente para outro teste. |
| `/webhook/feedback` | Com o workflow publicado, sem precisar manter o editor aberto. |

Após alterar o workflow, publique novamente para atualizar a execução de produção. Consulte a [documentação de publicação do n8n](https://docs.n8n.io/workflows/publish/).

### Quando uma mensagem é enviada

| Resultado | Destino |
|---|---|
| `alta`: sentimento negativo e necessidade de ação | Alerta no Telegram |
| `media`: apenas uma dessas condições | Nó **Registrar: media** |
| `baixa`: nenhuma dessas condições | Nó **Registrar: baixa** |
| `indeterminada`: saída inválida do extrator | Revisão manual no Telegram |
| Falha ou timeout da chamada à API | Resposta HTTP `502` e alerta no Telegram |

Os nós **Registrar** são pontos de extensão: não persistem dados na configuração atual. A foto fornece contexto e não altera a prioridade. Os alertas de feedback incluem até 200 caracteres do texto do cliente enviados ao Telegram.

Se a mensagem não chegar, confira a prioridade retornada, as credenciais e o **Chat ID** nos nós do Telegram. Consulte **Executions** no n8n para ver falhas; receber a resposta do webhook não garante que o envio seguinte ao Telegram tenha sido concluído.

Para acompanhar os serviços:

```bash
docker compose -f docker-compose.yml -f docker-compose.n8n.yml logs -f api n8n
```

## Uso direto da API

| Método e rota | Função |
|---|---|
| `GET /health` | Verifica o carregamento dos modelos |
| `POST /v1/review/extract` | Analisa uma avaliação em JSON |
| `POST /v1/food/classify` | Classifica uma imagem enviada como formulário |
| `POST /v1/feedback/analyze` | Analisa texto e foto opcional, com prioridade de atendimento |

**Analisar texto:**

```bash
curl -X POST http://127.0.0.1:8000/v1/review/extract \
  -H "Content-Type: application/json" \
  -d '{"texto": "Comprei duas unidades e só veio uma. Ninguém responde no SAC."}'
```

**Classificar uma foto:**

```bash
curl -X POST http://127.0.0.1:8000/v1/food/classify \
  -F "imagem=@prato.jpg"
```

**Analisar feedback com foto:**

```bash
curl -X POST http://127.0.0.1:8000/v1/feedback/analyze \
  -F "texto=A marmita chegou fria e faltou o feijão." \
  -F "imagem=@prato.jpg"
```

A imagem é opcional no último endpoint. Se `API_KEY` estiver definida, acrescente `-H "X-API-Key: SUA_CHAVE"` às chamadas `/v1/*`.

O extrator sinaliza saída inválida com `valido: false`, mantendo HTTP `200` e a geração em `saida_bruta`. O classificador sinaliza baixa confiança com `rejeitado: true` e `classe: null`. Consulte os esquemas completos em `/docs` e as [regras de prioridade e validação](docs/regras.md).

Por padrão, o texto aceita até 2000 caracteres e as imagens até 5 MB, em JPEG, PNG ou WEBP. Erros de validação retornam `422`, formato não aceito `415`, imagem acima do limite `413`, chave inválida `401` e modelo indisponível `503`. Os logs da API registram metadados e um `X-Request-ID`, sem gravar o texto das avaliações ou as imagens.

## Configuração e desenvolvimento

As variáveis disponíveis estão em [.env.example](.env.example). Para personalizar a execução, copie esse arquivo para `.env` e ajuste os valores; preserve seu `.env` caso já exista. O Compose o carrega automaticamente.

As principais opções são `API_KEY`, `TORCH_NUM_THREADS`, `DEVICE` e `CLASSIFIER_THRESHOLD`. Para reaproveitar o cache local dos modelos no Docker, defina `HF_CACHE=/home/SEU_USUARIO/.cache/huggingface` no `.env`.

Para executar sem Docker, use Python 3.12 ou superior:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 torchvision==0.29.2
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Para carregar um `.env` nessa execução, acrescente `--env-file .env` ao comando do Uvicorn.

```bash
pytest                          # testes rápidos, sem baixar modelos
pytest -m slow                  # integração com os modelos reais
python scripts/smoke.py          # verifica a API em execução
python scripts/benchmark.py      # mede latência e atualiza a tabela abaixo
```

Os scripts aceitam `--url` e leem `API_KEY` do ambiente. O benchmark grava `results/latencia.json`.

## Latência e limitações

<!-- latencia:inicio -->
| Endpoint | Chamadas | p50 (ms) | p95 (ms) |
|---|---|---|---|
| `POST /v1/review/extract` | 20 | 5903 | 7454 |
| `POST /v1/food/classify` | 20 | 66 | 74 |

Medido em 2026-11-14 com `scripts/benchmark.py`. CPU: 12th Gen Intel(R) Core(TM) i5-1235U (12 núcleos lógicos, 10 threads no PyTorch). Python 3.14.4, torch 2.15.0+cpu, transformers 5.23.0, pillow 12.1.1.
<!-- latencia:fim -->

A extração processa uma geração por vez; chamadas simultâneas aguardam em fila, sem limite de espera na API. Configure o timeout no cliente de acordo com essa condição.

O extrator foi treinado com avaliações de e-commerce do Olist. A qualidade em restaurantes e delivery não foi medida, e 4,4% das saídas no teste do projeto de origem foram inválidas. `REPETITION_PENALTY` mantém o padrão do modelo; alterá-lo exige nova avaliação.

O classificador atribui uma única classe por foto e foi treinado com recortes sobre fundo preto. Seu desempenho em fotos comuns de pratos não foi medido. A rejeição por baixa confiança não garante a detecção de imagens fora das 20 classes.

O fluxo de revisão manual (`indeterminada`) ainda não foi testado de ponta a ponta. A autenticação usa uma chave compartilhada, e a configuração fornecida é voltada a demonstração local.

## Origem e licenças

Este repositório integra os projetos [pt-review-extractor](https://github.com/ItaloSLeao/pt-review-extractor) e [ml-image-classifier](https://github.com/ItaloSLeao/ml-image-classifier). O código de prompt e validação em `app/review_common.py` veio do primeiro (commit `531d55b`); o pré-processamento e a predição em `app/classifier.py` foram adaptados do segundo (commit `9427523`).

- **Extrator:** dados derivados do *Brazilian E-Commerce Public Dataset by Olist*, sob CC BY-NC-SA 4.0, com uso não comercial.
- **Classificador:** *Brazilian food images*, sob CC BY 4.0. Atribuição: Carvalho, Marcos Alberto (2023), Mendeley Data, V2, DOI [10.17632/7n36jtcpv3.2](https://doi.org/10.17632/7n36jtcpv3.2). As imagens de exemplo dos scripts vêm desse conjunto.

As condições dos dados do extrator restringem o uso do projeto a fins não comerciais. As decisões de arquitetura estão em [docs/decisoes.md](docs/decisoes.md).
