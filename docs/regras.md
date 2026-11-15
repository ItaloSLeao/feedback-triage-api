# Regras

## Prioridade do feedback

O endpoint `POST /v1/feedback/analyze` devolve um campo `prioridade`, calculado só a partir da análise do texto. A implementação está em `app/priority.py`.

| Saída do extrator | Sentimento negativo? | `requer_acao`? | Prioridade |
|---|---|---|---|
| válida | sim | sim | `alta` |
| válida | sim | não | `media` |
| válida | não | sim | `media` |
| válida | não | não | `baixa` |
| inválida | n/d | n/d | `indeterminada` |

Em palavras: `alta` quando o sentimento é negativo **e** o modelo marcou que a empresa precisa agir; `media` quando só uma das duas coisas acontece; `baixa` quando nenhuma; `indeterminada` quando a saída do extrator não era um JSON válido e, portanto, não há o que avaliar.

Observações:

- "Sentimento negativo" é o campo `sentimento` geral. Um aspecto negativo isolado (por exemplo `entrega: negativo` com sentimento geral `neutro`) não conta.
- `neutro` e `positivo` são tratados do mesmo jeito.
- `indeterminada` não é o mesmo que `baixa`. Um feedback que o modelo não conseguiu analisar pode ser grave; quem consome a API deve mandá-lo para revisão humana ou tentar de novo, não descartá-lo.
- A imagem não entra na regra. O prato identificado é informação de contexto.

A regra é propositalmente simples. Ela usa dois campos previstos por um modelo pequeno, que erra. Veja em [decisoes.md](decisoes.md) por que ela fica na API e como o n8n pode substituí-la.

## Campo `prato`

`prato` é `{"classe", "confianca"}` quando uma imagem foi enviada e o classificador a aceitou. É `null` em dois casos: nenhuma imagem enviada, ou imagem rejeitada por baixa confiança. Para distinguir os dois, ou para ver o top-3 de uma imagem rejeitada, chame `POST /v1/food/classify` com a mesma imagem.

Imagem inválida (corrompida, formato não aceito, grande demais) não vira `prato: null`: a requisição inteira é recusada com o erro correspondente, antes de gastar tempo com a geração do texto.

## Validação de entrada

Texto (`texto`):

- obrigatório;
- espaços no início e no fim são removidos antes de contar;
- não pode ficar vazio depois disso;
- no máximo 2000 caracteres (`MAX_TEXT_CHARS`).

Imagem (`imagem`):

- no máximo 5 MB (`MAX_IMAGE_BYTES`); acima disso, 413;
- precisa abrir com Pillow e ser decodificada por inteiro; arquivo que não é imagem, corrompido, truncado ou vazio dá 422;
- o formato detectado pelo Pillow precisa ser JPEG, PNG ou WEBP; outro formato (GIF, BMP etc.) dá 415, mesmo que o `Content-Type` diga outra coisa;
- no máximo 40 megapixels depois de decodificada, para evitar que um arquivo pequeno ocupe gigabytes de memória.

## Rejeição do classificador

O limiar vem do arquivo `limiar.json` publicado no repositório do modelo no Hub. Ele foi calibrado no conjunto de validação do projeto de origem, como o quantil 0,05 da confiança dos acertos. Se a maior probabilidade ficar abaixo dele, a resposta vem com `classe: null` e `rejeitado: true`. `CLASSIFIER_THRESHOLD` sobrescreve o valor.

## O que vai para o log

Por requisição: id, método, rota, status, latência, tamanho do corpo e, conforme a rota, número de caracteres do texto, tamanho da saída do modelo, tamanho da imagem em bytes, se a saída foi válida, se a imagem foi rejeitada e a prioridade. O texto da avaliação, a saída do modelo e a imagem não são logados.
