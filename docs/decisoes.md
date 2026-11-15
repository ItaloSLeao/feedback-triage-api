# Decisões de projeto

Registro curto do porquê de cada escolha, incluindo o que ficou de fora.

## Por que FastAPI

Os modelos são em Python (PyTorch e transformers), então servir no mesmo processo evita uma camada a mais. Dentro do Python, o FastAPI resolve o que esta API precisa sem código extra:

- validação e serialização com Pydantic, que também documentam o contrato;
- OpenAPI e Swagger gerados a partir do código, o que facilita configurar as chamadas no n8n;
- upload multipart e rotas assíncronas, que permitem manter o `/health` respondendo enquanto um modelo trabalha em outra thread.

Servidores de inferência dedicados (TorchServe, Triton, vLLM) fariam sentido com GPU, lote e muito tráfego. Para dois modelos pequenos em CPU, em uma máquina só, seriam mais peças para manter sem ganho correspondente.

## Por que carregar os modelos na inicialização

Carregar os dois modelos leva alguns segundos e ocupa alguns GB de RAM. Fazer isso uma vez, no `lifespan`, tem três efeitos:

- nenhuma requisição paga o custo de carga; a latência fica previsível;
- o problema aparece cedo: se um modelo não carrega (sem rede, sem memória, nome errado), isso fica visível no log e no `/health` logo na subida, e não na primeira chamada de um cliente;
- o `HEALTHCHECK` do Docker passa a significar "pronto para atender", não apenas "processo vivo".

Uma falha de carga não derruba o processo. O `/health` responde 503 dizendo qual modelo faltou, e as rotas daquele modelo respondem 503. Assim, se só o extrator falhar, a classificação continua disponível, e o diagnóstico pode ser feito com a API no ar.

O servidor roda com um único worker. Cada worker do uvicorn é um processo com a própria cópia dos modelos; dois workers dobrariam o uso de RAM.

## Por que uma geração por vez

A geração do extrator usa todos os núcleos que o PyTorch tiver disponíveis. Duas gerações ao mesmo tempo disputam os mesmos núcleos: nenhuma termina mais rápido, as duas ficam mais lentas e cada uma aloca a própria memória de trabalho. Em uma máquina com pouca RAM, isso pode levar o sistema a usar swap ou a matar o processo.

Por isso há um semáforo de tamanho 1 em volta da geração. As requisições concorrentes esperam na fila, de forma assíncrona, sem ocupar threads. A chamada do modelo em si roda com `run_in_threadpool`, fora do loop de eventos, para o servidor continuar aceitando conexões e respondendo ao `/health`.

O custo é a fila: sob carga, o tempo de espera cresce linearmente. Não implementei limite de fila nem resposta 429, porque o consumidor previsto (um fluxo no n8n) pode controlar a própria concorrência. Se a API fosse exposta a clientes que eu não controlo, esse seria o primeiro item a acrescentar.

O classificador não passa pelo semáforo. Ele é rápido e leve, e pode rodar enquanto uma geração está em andamento.

## Por que a regra de prioridade é simples e fica na API

A regra (em [regras.md](regras.md)) combina dois campos: sentimento negativo e `requer_acao`.

Ela é simples porque os dados de entrada não sustentam mais do que isso. Os dois campos vêm de um modelo de 0,5 bilhão de parâmetros, que erra em parte dos casos. Uma regra com pesos, pontuações ou muitos ramos daria aparência de precisão a algo que depende de previsões incertas. Uma regra que cabe em uma tabela pode ser conferida por qualquer pessoa olhando a resposta.

Ela fica na API para que exista um padrão testado e documentado. Qualquer cliente, mesmo um `curl`, recebe a mesma prioridade para a mesma análise, e a regra tem testes automatizados.

Ela não prende ninguém. A resposta traz também `analise_texto` completo e `prato`. O n8n pode ignorar `prioridade` e calcular a própria com esses campos, por exemplo: subir a prioridade quando `aspectos.entrega` for negativo, tratar `indeterminada` com uma segunda tentativa, ou considerar o prato identificado. Regra de negócio que muda com frequência fica melhor no orquestrador, onde alterar não exige publicar a API de novo.

## Saída inválida do extrator responde 200

Quando o modelo gera algo fora do esquema, a API responde 200 com `valido: false` e o texto cru em `saida_bruta`. A requisição foi atendida; o que falhou foi a qualidade da resposta do modelo, e isso é informação útil para quem consome. Um 500 esconderia o motivo e convidaria a repetir a chamada às cegas, o que não adianta: a decodificação é gulosa, então a mesma entrada produz a mesma saída.

A API não tenta consertar o JSON (por exemplo, completar chaves que faltaram). Um conserto silencioso mudaria o comportamento medido do modelo sem que isso aparecesse em lugar nenhum.

## Mesma configuração de geração da avaliação

O extrator gera exatamente como no `src/evaluate.py` do projeto de origem: mesmo prompt de sistema, chat template do tokenizer, decodificação gulosa, `max_new_tokens=200`, e os demais parâmetros vindos do `generation_config.json` do modelo, que inclui `repetition_penalty=1.1`. Assim a taxa de JSON válido medida lá continua valendo como referência aqui.

Durante os testes vi um caso em que essa penalidade parece ter feito o modelo omitir chaves com valor `null` repetido. Deixei a variável `REPETITION_PENALTY` para permitir o experimento, mas não mudei o padrão: um exemplo não é uma medição, e mudar o padrão exige reavaliar no conjunto de teste.

## Precisão numérica

Os pesos do extrator estão publicados em fp16. Na CPU eles são convertidos para float32, porque operações em meia precisão na CPU são lentas e mal suportadas. O fp16 só é usado quando há CUDA.

## Códigos de erro para imagem

Arquivo corrompido ou que não é imagem responde 422. Tamanho acima do limite responde 413 e formato não aceito responde 415, que são os códigos HTTP específicos para esses casos e permitem que o cliente trate cada um sem ler a mensagem.

## O `/health` não exige chave

O `HEALTHCHECK` do Docker e qualquer monitor precisam consultá-lo sem credencial. Ele expõe apenas o estado dos modelos, o nome da CPU e versões de bibliotecas.

## Dependências

`torch`, `torchvision`, `transformers`, `huggingface_hub`, `pillow` e `numpy` estão nas mesmas versões do repositório do classificador, onde aquele modelo foi testado em CPU. O extrator foi publicado com transformers 5.20.2 e carrega sem problemas na 5.23.0 (conferido pelo teste de integração).

O código da API importa o PyTorch só dentro das funções que carregam os modelos. Com isso os testes rápidos rodam com dublês sem precisar do PyTorch instalado.

## O que ficou de fora

- Orquestração com n8n: é a próxima fase, em outro lugar.
- Limite de fila, limite de requisições por cliente e métricas no formato Prometheus.
- Inferência em lote.
- Quantização do extrator para reduzir RAM e latência. Mudaria as saídas do modelo e exigiria reavaliar.
