# Workflows n8n

Este diretório contém o workflow de automação do n8n para triagem de feedback:

- `triagem-feedback.workflow.json`: fluxo completo de ingestão via webhook, chamada à API de análise, normalização, resposta imediata ao chamador e roteamento por prioridade (com alertas no Telegram).

## Credenciais e Parâmetros

O arquivo JSON **não contém credenciais nem segredos**:

- As credenciais de Telegram não estão exportadas no arquivo. Ao importar o workflow no n8n, configure a credencial de conta do bot do Telegram (`Telegram bot`).
- O identificador de chat do Telegram está preenchido como o marcador **`SEU_CHAT_ID`** nos nós de notificação (*Alerta: prioridade alta*, *Revisao manual (saida invalida)* e *Alerta: API falhou*). Substitua pelo seu ID de chat ou canal do Telegram após a importação.
- Se a API exigir autenticação (`API_KEY` configurada no ambiente), configure uma credencial de *Header Auth* (`X-API-Key`) no n8n e altere a opção *Authentication* nos dois nós de chamada HTTP (*API analisa*) de `None` para `Header Auth`.

Para instruções completas de como subir os contêineres, importar o fluxo e testar com curl, consulte a seção [Automação com n8n](../README.md#automação-com-n8n) no README principal.
