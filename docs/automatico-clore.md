# AUTOMATICO CLORE

Documento tecnico e operacional da implementacao do autoaluguel Clore no Pearl GPU Monitor.

Data da implementacao/documentacao: 2026-05-29.

## Objetivo

O recurso **AUTOMATICO CLORE** liga/desliga um fluxo independente para pegar oportunidades Clore boas automaticamente. Quando ligado, o sistema:

1. Observa a tabela de oportunidades ja calculada em **Decisao agora**.
2. Seleciona apenas ofertas Clore conservadoras e lucrativas.
3. Cria uma ordem Clore usando o mesmo caminho seguro do clique manual.
4. Abre um teste Scout automaticamente.
5. Registra origem, decisao e log para ficar claro que a ordem veio do automatico.
6. Deixa o Scout decidir manter ou cancelar conforme hash real, lucro real, worker e timeout.

O recurso foi feito para ser separado do auto antigo do Scout/Vast. O botao **Auto** da pagina **Testes** continua controlando o fluxo Scout/Vast existente. O botao **AUTOMATICO CLORE** fica no **Dashboard**, acima da tabela **Decisao agora**.

## Como usar

Abra o Dashboard e va ate a secao **Decisao agora**. Acima da tabela existe o grupo:

```text
Auto Clore
AUTOMATICO CLORE OFF
fila 0 | ativos 0 | cooldown 0 | min $0.20 | max $3.00/h
```

Clique em **AUTOMATICO CLORE OFF**. O navegador mostra uma confirmacao explicando os filtros. Confirmando, o botao muda para:

```text
AUTOMATICO CLORE ON
```

Quando ligado, o backend passa a enfileirar e iniciar Clore sozinho. Quando desligado, ele nao inicia novas ordens automaticas.

## Arquivos principais

### Backend

- `dashboard/app.py`
  - Guarda constantes e filtros duros.
  - Enriquece oportunidades com historico Scout.
  - Mantem `clore_auto_queue`.
  - Escolhe candidatos Clore.
  - Inicia ordem e teste Scout via `start_scout_clore_rent()`.
  - Expoe endpoints para ligar/desligar o automatico.
  - Expoe campos publicos de origem/log em `/api/state`, `/api/scout/state` e resultados.

- `dashboard/scout_settings.py`
  - Define defaults persistidos no estado Scout.
  - Adiciona `clore_auto_enabled: False`.
  - Adiciona `clore_auto_queue: {}`.

### Frontend Dashboard

- `dashboard/static/index.html`
  - Adiciona toolbar **Auto Clore** acima de **Decisao agora**.
  - Adiciona botao `id="cloreAutoToggle"`.
  - Adiciona status `id="cloreAutoStatus"`.
  - Adiciona colunas de historico na tabela de oportunidades:
    - `Ja pegou?`
    - `Pegas`
    - `TH/s real med.`

- `dashboard/static/app.js`
  - Renderiza o botao **AUTOMATICO CLORE ON/OFF**.
  - Chama `/api/scout/clore-auto/resume` e `/api/scout/clore-auto/pause`.
  - Renderiza status da fila/cooldown.
  - Renderiza historico por oferta em **Decisao agora**.
  - Permite ordenar por campos de historico.

- `dashboard/static/styles.css`
  - Reusa estilos de botoes e toolbar existentes.
  - Adiciona/usa estado `.action-button.failed` para falha de toggle.

### Frontend Scout/Results

- `dashboard/static/scout.html`
  - Adiciona coluna **Origem** em **Testes ativos**.
  - Adiciona coluna **Origem** em **RESULTADOS**.

- `dashboard/static/scout.js`
  - Renderiza `source_label`.
  - Mostra `Auto Clore / ALUGAR` quando a origem for automatica.
  - Coloca `auto_log` no `title`/hover da celula **Origem**.
  - Mostra cards fixos informando filtros duros:
    - `CUDA min 12.9+`
    - `PCIe min x8/x16`

- `dashboard/static/results.html`
  - Adiciona coluna **Origem** nos resultados.

- `dashboard/static/results.js`
  - Renderiza origem e log igual a pagina Scout.

## Estado persistido

O estado principal do Scout fica em Redis:

```text
dashboard:scout:state
```

Chaves relevantes adicionadas:

```json
{
  "clore_auto_enabled": false,
  "clore_auto_queue": {}
}
```

As acoes Clore continuam em:

```text
dashboard:clore:actions
```

Historico Scout em arquivo:

```text
data/scout_history.json
```

Historico de workers em arquivo:

```text
data/worker_history.json
```

O historico de worker ja era gravado periodicamente. A implementacao nova usa o historico Scout para responder na tabela se uma oferta ja foi pega e qual foi o hash real medio.

## Defaults e variaveis de ambiente

Arquivo: `dashboard/scout_settings.py`.

Defaults novos:

```python
"clore_auto_enabled": False
"clore_auto_queue": {}
```

Constantes relevantes em `dashboard/app.py`:

```python
CLORE_AUTO_COOLDOWN_SECONDS = 300
CLORE_AUTO_QUEUE_RETENTION_SECONDS = 1800
SCOUT_HARDWARE_BLOCK_RISKS = {
    "cuda_below_12_9",
    "cuda_unknown",
    "pcie_below_rule",
    "pcie_unknown",
}
CLORE_AUTO_BLOCK_RISKS = {
    "reliability_low",
    "network_bad",
    "price_usd_missing",
    *SCOUT_HARDWARE_BLOCK_RISKS,
}
```

Variaveis que influenciam o comportamento:

- `SCOUT_MIN_PROFIT_USD_HR`
  - Default: `0.20`.
  - Lucro minimo por hora para o automatico considerar uma oferta.

- `SCOUT_MAX_PRICE_USD_HR`
  - Default no backend: `3.00`.
  - Maximo de custo/h para entrar no Scout.

- `SCOUT_MAX_PARALLEL_TESTS`
  - Limita quantos testes Scout podem rodar ao mesmo tempo.

- `SCOUT_STARTS_PER_TICK`
  - Quantos novos testes o automatico pode iniciar por ciclo.

- `CLORE_AUTO_COOLDOWN_SECONDS`
  - Default: `300`.
  - Tempo de cooldown apos falha de tentativa automatica.

- `CLORE_AUTO_QUEUE_RETENTION_SECONDS`
  - Default: `1800`.
  - Quanto tempo manter itens nao ativos na fila interna.

## Filtros duros

O automatico foi implementado em modo conservador.

Para entrar automaticamente, a oportunidade precisa passar por todos estes filtros:

1. `platform == "clore"`.
2. Decisao visual `green`, que aparece como **ALUGAR**.
3. `rent_options[pool].state == "ready"`.
4. CUDA `12.9+`.
5. PCIe `x8` ou `x16`.
6. Sem riscos bloqueadores:
   - `cuda_below_12_9`
   - `cuda_unknown`
   - `pcie_below_rule`
   - `pcie_unknown`
   - `reliability_low`
   - `network_bad`
   - `price_usd_missing`
7. Lucro previsto/h maior ou igual ao `SCOUT_MIN_PROFIT_USD_HR`.
8. Custo/h menor ou igual ao `SCOUT_MAX_PRICE_USD_HR`.
9. Nao pode ja estar em teste ou alugado.
10. Nao pode ter historico ruim.

Historico ruim bloqueia auto:

```python
blacklist
blacklisted
destroy
destroyed
failed
no_worker
offline
order_lost
runtime_error
stopped
switch_failed_destroy
```

Tambem bloqueia quando o historico indica:

- hash real baixo contra esperado;
- lucro real abaixo do minimo;
- worker nao apareceu;
- teste anterior terminou ruim.

## Filtro de visibilidade em Decisao agora

A tabela **Decisao agora** passou a ocultar oportunidades que nao cumprem o filtro duro de hardware:

```text
CUDA 12.9+
PCIe x8/x16
```

Funcao relevante:

```python
decision_opportunity_visible()
```

Ela usa `SCOUT_HARDWARE_BLOCK_RISKS` para tirar da decisao principal ofertas com CUDA baixa/desconhecida ou PCIe baixo/desconhecido.

## Fluxo de dados

Fluxo simplificado:

```text
monitores Redis
  -> refresh_state_unlocked()
  -> compute_state()
  -> build_opportunities()
  -> enrich_opportunities_with_scout_history()
  -> maybe_autostart_clore_scout()
  -> update_clore_auto_queue_from_opportunities()
  -> start_scout_clore_rent(source="auto_clore")
  -> clore.create_order()
  -> scout["tests"][test_id]
  -> evaluate_scout_state()
  -> keep/cancel/blacklist/history
```

O ponto de entrada do ciclo e:

```python
refresh_state_unlocked()
```

Ele roda:

1. Carrega estado bruto dos monitores.
2. Sincroniza Vast.
3. Sincroniza Clore.
4. Sincroniza wallets Clore.
5. Carrega Scout.
6. Calcula oportunidades.
7. Avalia Scout ativo.
8. Recalcula oportunidades.
9. Executa watch/re-rent Clore.
10. Executa rescue Vast.
11. Executa autostart Vast se aplicavel.
12. Executa `maybe_autostart_clore_scout()`.
13. Salva Scout se algo mudou.
14. Grava historico de worker.

## Funcoes backend adicionadas/alteradas

### `load_scout_state()`

Arquivo: `dashboard/app.py`.

Garante que estados antigos recebam os campos novos:

```python
data.setdefault("clore_auto_enabled", False)
data.setdefault("clore_auto_queue", {})
```

Isso evita quebrar ambientes que ja tinham Redis salvo antes da implementacao.

### `prune_scout_runtime_state()`

Arquivo: `dashboard/app.py`.

Agora tambem limpa e limita `clore_auto_queue`.

Regras:

- Mantem `cooldown` enquanto `next_retry_at` estiver no futuro.
- Mantem `queued`, `renting`, `rented`.
- Mantem bloqueados/recentes por `CLORE_AUTO_QUEUE_RETENTION_SECONDS`.
- Corta a fila para no maximo 120 itens, priorizando:
  - `queued`;
  - lucro/h;
  - ROI;
  - ultimo visto.

### `scout_opportunity_history_summary()`

Arquivo: `dashboard/app.py`.

Resume historico de cada oportunidade usando Scout history e testes ativos.

Campos adicionados em cada oportunidade:

```text
history_seen
history_count
history_completed_count
history_active_count
history_avg_ths
history_best_ths
history_last_ths
history_last_decision
history_last_pool
history_last_at
history_best_profit_usd_hr
```

Esses campos alimentam a tabela **Decisao agora**:

- `Ja pegou?`
- `Pegas`
- `TH/s real med.`

### `enrich_opportunities_with_scout_history()`

Arquivo: `dashboard/app.py`.

Percorre todas as oportunidades e injeta o resumo de historico.

Chamado dentro de:

```python
compute_state()
```

### `clore_auto_queue()`

Arquivo: `dashboard/app.py`.

Retorna a fila interna `scout["clore_auto_queue"]`. Se ela nao existir ou nao for dict, recria `{}`.

### `clore_auto_active_server_ids()`

Arquivo: `dashboard/app.py`.

Monta um set de servidores Clore ja ocupados por:

- testes Scout ativos;
- acoes Clore em `renting`;
- acoes Clore em `rented`.

Evita duplicar aluguel/teste do mesmo server.

### `clore_auto_candidate_strategy()`

Arquivo: `dashboard/app.py`.

Escolhe a pool a partir da oportunidade:

1. Le `opportunity["pool"]`.
2. Confere se a pool existe em `clore.pool_strategies()`.
3. Confere `rent_options[pool].state == "ready"`.

Se nao estiver pronto, retorna motivo bloqueante.

### `clore_auto_history_bad_reason()`

Arquivo: `dashboard/app.py`.

Consulta historico Scout da oportunidade. Se achar decisao ruim ou resultado ruim, devolve o motivo que bloqueia o automatico.

Exemplos de motivos:

```text
historico ruim: no_worker
historico hash baixo: 12.4%
historico lucro baixo: $-0.10/h
historico ruim sem worker/hash
```

### `clore_auto_block_reason()`

Arquivo: `dashboard/app.py`.

E o filtro central do automatico Clore.

Bloqueia quando:

- nao e Clore;
- nao tem server id;
- ja esta ativo/testando;
- decisao nao e `green`;
- rent option nao esta ready;
- risco bloqueador aparece;
- lucro/h previsto esta abaixo do minimo;
- preco/h ausente;
- preco/h acima do maximo Scout;
- historico e ruim.

Quando retorna string vazia, a oferta pode entrar na fila.

### `clore_auto_priority_score()`

Arquivo: `dashboard/app.py`.

Cria score para ordenacao interna. O score favorece:

1. maior lucro/h;
2. maior ROI;
3. melhor reliability;
4. bonus pequeno quando existe historico positivo.

### `clore_auto_queue_item_from_opportunity()`

Arquivo: `dashboard/app.py`.

Transforma uma oportunidade aprovada em item da fila `clore_auto_queue`.

Campos importantes:

```text
server_id
offer_id
pool_strategy
gpu
gpu_count
price_usd_hr
expected_ths
profit_usd_hr
roi_pct
host_id
machine_id
cuda
pcie
reliability
risks
history_seen
history_count
history_avg_ths
history_best_profit_usd_hr
queue_status = queued
sniper_status = auto Clore
skip_reason = Auto Clore: decisao ALUGAR; candidato pronto
priority_score
min_profit_usd_hr
max_price_usd_hr
source = auto_clore
```

### `clore_auto_mark_cooldown()`

Arquivo: `dashboard/app.py`.

Coloca um item em cooldown apos falha.

Campos atualizados:

```text
queue_status = cooldown
sniper_status = cooldown
skip_reason = Auto Clore falhou: ...; retry em N min
last_retry_error
last_retry_at
next_retry_at
retry_attempts
updated_at
```

Falhas comuns:

- server sumiu do marketplace;
- server ficou rented antes do Scout;
- sem saldo/moeda aceita;
- erro API Clore;
- preco mudou;
- revalidacao spot offline/nao publica.

### `update_clore_auto_queue_from_opportunities()`

Arquivo: `dashboard/app.py`.

Atualiza a fila automatica a partir das oportunidades atuais.

Para cada oportunidade Clore:

1. Ignora se nao tem id.
2. Respeita cooldown ativo.
3. Calcula estrategia.
4. Calcula motivo de bloqueio.
5. Se bloqueada e estava `queued`/`renting`, muda para `blocked`.
6. Se aprovada, cria/atualiza item `queued`.
7. Se item sumiu do marketplace e estava `queued`/`renting`, entra em cooldown.

### `maybe_autostart_clore_scout()`

Arquivo: `dashboard/app.py`.

Motor principal do automatico.

Fluxo:

1. Se `clore_auto_enabled` for falso, retorna sem fazer nada.
2. Atualiza fila com `update_clore_auto_queue_from_opportunities()`.
3. Conta testes ativos.
4. Calcula slots livres pelo `max_parallel_tests`.
5. Ordena itens `queued` por:
   - lucro/h desc;
   - ROI desc;
   - reliability desc;
   - melhor lucro historico desc;
   - primeiro visto asc.
6. Respeita `starts_per_tick`.
7. Revalida oportunidade atual.
8. Marca item como `renting`.
9. Chama `start_scout_clore_rent(..., source="auto_clore")`.
10. Se der erro, marca cooldown.
11. Se criar teste, marca `rented` e salva `test_id`/`order_id`.

### `start_scout_clore_rent()`

Arquivo: `dashboard/app.py`.

Essa funcao ja era o caminho seguro para aluguel Clore manual e passou a receber:

```python
source: str = "manual_clore"
```

Quando chamada pelo automatico, recebe:

```python
source="auto_clore"
```

Ela faz as revalidacoes oficiais antes de criar a ordem:

1. Pool Clore valida.
2. Oportunidade existe no estado atual.
3. Rent option pronto.
4. Hardware passa `scout_hardware_block_reason()`.
5. Decisao permitida.
6. Nao existe acao ativa para o mesmo server.
7. Configuracao Clore existe.
8. Server ainda existe no marketplace oficial.
9. Server nao esta rented.
10. Existe wallet/moeda elegivel com saldo/config.
11. Preco USD existe.
12. Se `green`, preco/h nao passa do teto.
13. Spot marketplace ainda existe.
14. Server esta online.
15. Server esta publico.

Depois:

1. Cria `clore_actions[server_id]` em `renting`.
2. Tenta criar ordem com as moedas elegiveis.
3. Sincroniza ordem Clore.
4. Cria `scout["tests"][test_id]` com status `testing`.
5. Salva action e Scout state.

Campos adicionados para log/origem:

```text
source
source_label
auto_decision
auto_decision_label
auto_log
```

Quando automatico:

```text
source = auto_clore
source_label = Auto Clore
auto_decision = green
auto_decision_label = ALUGAR
auto_log = Auto Clore: decisao ALUGAR; lucro prev $X/h; custo $Y/h; pool Akoya
```

Quando manual:

```text
source = manual_clore
source_label = Scout manual Clore
auto_decision = ""
auto_log = ""
```

### `public_scout_test()` e `public_scout_history()`

Arquivo: `dashboard/app.py`.

Passam os campos de origem/log para a API:

```text
source
source_label
auto_decision
auto_decision_label
auto_log
```

Isso permite que as paginas **Testes** e **Results** mostrem claramente se algo foi manual ou automatico.

### `api_scout_state()`

Arquivo: `dashboard/app.py`.

Inclui no retorno:

```json
{
  "clore_auto_enabled": true,
  "summary": {
    "clore_auto_enabled": true,
    "clore_auto": {
      "queued": 0,
      "renting": 0,
      "rented": 0,
      "lost": 0,
      "blocked": 0,
      "cooldown": 0
    }
  }
}
```

### Endpoints do toggle

Arquivo: `dashboard/app.py`.

```http
POST /api/scout/clore-auto/pause
POST /api/scout/clore-auto/resume
```

`pause`:

```python
scout["clore_auto_enabled"] = False
```

`resume`:

```python
scout["clore_auto_enabled"] = True
asyncio.create_task(scout_worker_tick())
```

O `resume` dispara um tick para o automatico reagir sem esperar muito.

## Frontend: Dashboard

### Botao

Arquivo: `dashboard/static/index.html`.

Trecho funcional:

```html
<div class="toolbar-group">
  <span>Auto Clore</span>
  <button class="action-button quiet" id="cloreAutoToggle" type="button">
    AUTOMATICO CLORE OFF
  </button>
  <small id="cloreAutoStatus">fila 0 | cooldown 0</small>
</div>
```

### Renderizacao

Arquivo: `dashboard/static/app.js`.

Funcao:

```javascript
renderCloreAuto(state)
```

Comportamento:

- Le `state.scout.clore_auto_enabled`.
- Le `state.scout.clore_auto_queue`.
- Conta `queued`, `renting`, `rented`, `cooldown`.
- Atualiza texto do botao:
  - `AUTOMATICO CLORE OFF`
  - `AUTOMATICO CLORE ON`
- Mostra resumo:
  - fila;
  - ativos;
  - cooldown;
  - lucro minimo;
  - preco maximo.
- Ao ligar, mostra `window.confirm()` explicando os filtros.
- Chama `/api/scout/clore-auto/resume`.
- Ao desligar, chama `/api/scout/clore-auto/pause`.

### Historico em Decisao agora

Arquivos:

- `dashboard/static/index.html`
- `dashboard/static/app.js`

Colunas:

```text
Ja pegou?
Pegas
TH/s real med.
```

Funcoes:

```javascript
renderHistorySeen(item)
historyTitle(item)
```

Tooltip mostra:

```text
pegas N | ativas N | media X TH/s | melhor Y TH/s | melhor lucro $Z/h | ult keep | data
```

## Frontend: Scout e Results

### Origem em Testes ativos

Arquivo: `dashboard/static/scout.js`.

Funcao:

```javascript
sourceLabel(item)
sourceDetail(item)
renderActiveRow(test)
```

Se for automatico:

```text
Auto Clore / ALUGAR
```

Tooltip:

```text
Auto Clore | Auto Clore: decisao ALUGAR; lucro prev $X/h; custo $Y/h; pool Akoya
```

Se for manual:

```text
Scout manual Clore
```

ou:

```text
Manual Clore
```

### Origem em RESULTADOS

Arquivos:

- `dashboard/static/scout.html`
- `dashboard/static/scout.js`
- `dashboard/static/results.html`
- `dashboard/static/results.js`

Mesma logica:

- `Auto Clore` indica automatico.
- `Manual Clore`/`Scout manual Clore` indica clique manual.
- `Results` indica origem do fluxo Results/Vast.

## Como saber se uma ordem foi automatica

Procure a coluna **Origem** em **Testes** ou **Results**.

Automatico:

```text
Auto Clore / ALUGAR
```

Manual:

```text
Scout manual Clore
Manual Clore
```

Logs automaticos esperados:

```text
Auto Clore: decisao ALUGAR; lucro prev $2.64/h; custo $4.63/h; pool AlphaMine
Auto Clore medindo Akoya
Auto Clore medindo AlphaMine
Auto Clore iniciou scout-clore-...
Auto Clore falhou: server Clore sumiu do marketplace; retry em 5 min
```

Se a tela mostrar `Scout manual Clore`, entao nao foi automatico.

## Decisoes de produto/risco

O comportamento atual e conservador:

- Auto pega apenas **ALUGAR**.
- Nao pega **MARGEM**.
- Nao pega **RISCO**.
- Nao ignora historico ruim.
- Nao tenta CUDA baixa.
- Nao tenta PCIe baixo.
- Nao tenta reliability baixa.
- Nao tenta rede ruim.
- Usa o fluxo manual ja existente para criar ordem.
- O Scout ainda e quem decide manter/cancelar no fim.

Motivo: Clore cobra por duracao e algumas ofertas baratas deram `no_worker`, `order_lost`, hash baixo ou lucro real abaixo do previsto. O automatico precisa evitar repetir esses prejuizos.

## Relacao com Scout/Vast antigo

Existem dois controles separados:

1. **Auto** na pagina **Testes**
   - Campo: `scout["enabled"]`.
   - Fluxo: `maybe_autostart_scout()`.
   - Focado no Scout/Vast/radar existente.

2. **AUTOMATICO CLORE** no **Dashboard**
   - Campo: `scout["clore_auto_enabled"]`.
   - Fluxo: `maybe_autostart_clore_scout()`.
   - Focado em Clore.

Desligar um nao desliga o outro.

## Falhas e cooldown

Quando uma tentativa automatica falha, o item entra em cooldown para evitar loop.

Exemplo de item:

```json
{
  "queue_status": "cooldown",
  "sniper_status": "cooldown",
  "skip_reason": "Auto Clore falhou: Servidor Clore ficou rented antes do Scout; retry em 5 min",
  "last_retry_error": "Servidor Clore ficou rented antes do Scout",
  "next_retry_at": 1780080000.0,
  "retry_attempts": 1
}
```

Falhas comuns:

- A oferta sumiu do marketplace.
- A oferta ficou `rented` antes do sistema criar a ordem.
- A API Clore retornou erro.
- Nenhuma moeda aceita tinha saldo/configuracao.
- O server ficou offline na revalidacao spot.
- O server nao estava publico.

## Por que usar `start_scout_clore_rent()`

O automatico nao duplica a logica de aluguel. Ele chama a mesma funcao usada pelo clique manual:

```python
start_scout_clore_rent(..., source="auto_clore")
```

Isso evita divergencia em:

- validacao de pool;
- validacao de hardware;
- validacao de marketplace;
- validacao de wallet/moeda;
- criacao de order;
- criacao de worker;
- criacao do teste Scout;
- persistencia de `clore_actions`;
- persistencia de `scout["tests"]`.

## Estados da fila Clore automatica

```text
queued
```

Candidato aprovado e pronto para iniciar.

```text
renting
```

Backend esta criando ordem/teste.

```text
rented
```

Ordem/teste foi criado e esta ativo no Scout.

```text
blocked
```

Oferta nao passa mais nos filtros.

```text
cooldown
```

Falhou recentemente; aguarda `next_retry_at`.

```text
lost
```

Reservado no contador, mas o fluxo atual normalmente usa `cooldown` quando some.

## Campos de log/origem

Campos publicos:

```text
source
source_label
auto_decision
auto_decision_label
auto_log
opportunity_decision
```

Valores:

```text
source = auto_clore
source_label = Auto Clore
auto_decision = green
auto_decision_label = ALUGAR
```

ou:

```text
source = manual_clore
source_label = Scout manual Clore
```

Esses campos aparecem em:

- `clore_actions`;
- `scout["tests"]`;
- historico Scout;
- `/api/scout/state`;
- `/api/state`;
- telas **Testes** e **Results**.

## Interacao com historico

O historico vem de:

```text
data/scout_history.json
```

O sistema cruza uma oportunidade atual com historico por:

- provider;
- id/server/ask;
- host/machine;
- GPU;
- quantidade de placas.

O historico e usado para duas coisas:

1. Mostrar na UI se ja pegamos a oferta.
2. Bloquear automatico quando o historico foi ruim.

Isso resolve o caso operacional: quando uma GPU volta ao marketplace, o dashboard pode mostrar se ela ja foi testada e quanto rendeu de TH/s real.

## Criterio de qualidade de resultado

Funcao:

```python
scout_result_quality()
```

Um resultado e bom quando:

- lucro/h >= minimo; ou
- hash ratio >= 80% e lucro fica ate $0.10/h abaixo do minimo.

Um resultado e ruim quando:

- decisao foi destroy/blacklist/failed/no_worker/offline;
- ratio abaixo do minimo;
- lucro abaixo do minimo.

Esse criterio alimenta `clore_auto_history_bad_reason()`.

## Regras de hardware

Funcao:

```python
scout_hardware_block_reason()
```

Mensagem:

```text
Filtro Scout: exige CUDA 12.9+ e PCIe x8/x16 (...)
```

Riscos usados:

```text
cuda_below_12_9
cuda_unknown
pcie_below_rule
pcie_unknown
```

Esses riscos:

- bloqueiam teste manual Clore via Scout;
- bloqueiam automatico Clore;
- removem oportunidades da tabela principal de decisao.

## Endpoints envolvidos

### Estado geral

```http
GET /api/state
```

Retorna Dashboard, oportunidades, operacao, Scout embedado e status Clore.

### Estado Scout

```http
GET /api/scout/state
```

Retorna:

- testes ativos;
- fila Scout/Vast;
- radar;
- historico;
- settings;
- `clore_auto_enabled`;
- contadores de `clore_auto_queue`.

### Toggle Clore automatico

```http
POST /api/scout/clore-auto/resume
POST /api/scout/clore-auto/pause
```

### Aluguel manual Clore

O fluxo manual continua usando os endpoints existentes de Scout manual Clore e internamente chama:

```python
start_scout_clore_rent(..., source="manual_clore")
```

## Validacao feita na implementacao

Foi validado no fechamento da implementacao:

- compilacao Python via `py_compile`;
- checagem JS via `node --check`;
- rebuild do dashboard;
- leitura dos endpoints:
  - `/api/state`;
  - `/api/scout/state`.

Tambem foi validado visualmente pelo comportamento descrito nas telas:

- botao no Dashboard;
- coluna Origem em Testes;
- coluna Origem em Results;
- filtros CUDA/PCIe visiveis na pagina Testes;
- historico em Decisao agora.

## Como investigar em producao

### Ver se automatico esta ligado

Abra Dashboard e veja:

```text
AUTOMATICO CLORE ON
```

Ou consulte `/api/scout/state` e procure:

```json
"clore_auto_enabled": true
```

### Ver fila automatica

Em `/api/scout/state`, procure:

```json
"summary": {
  "clore_auto": {
    "queued": 0,
    "renting": 0,
    "rented": 0,
    "blocked": 0,
    "cooldown": 0
  }
}
```

No Dashboard, o texto ao lado do botao mostra:

```text
fila N | ativos N | cooldown N | min $X | max $Y/h
```

### Ver se um teste e automatico

Na pagina **Testes**, coluna **Origem**:

```text
Auto Clore / ALUGAR
```

Se aparecer:

```text
Scout manual Clore
```

foi clique manual.

### Ver motivo de bloqueio

Olhe `skip_reason` do item em `clore_auto_queue` ou o texto na UI.

Exemplos:

```text
auto Clore so pega ALUGAR
risco auto: reliability_low
risco auto: cuda_below_12_9
lucro $0.10/h abaixo do minimo $0.20/h
custo $3.20/h acima do max Scout $2.40/h
historico ruim: no_worker
```

## Pontos de atencao

1. **Clore automatico nao pega MARGEM/RISCO.**
   - Isso foi intencional para evitar repetir perdas em ofertas instaveis.

2. **Reliability baixa bloqueia auto.**
   - Mesmo que a oferta pareca lucrativa no papel, historico ruim ou reliability baixa podem matar worker/hash.

3. **Historico ruim bloqueia auto.**
   - Se quiser retestar uma oferta ruim, deve ser manual.

4. **O Scout ainda pode cancelar uma oferta automatica.**
   - Auto apenas inicia o teste.
   - Quem decide manter/cancelar e a medicao real do Scout.

5. **Preco/rede/PRL mudam.**
   - Uma oferta pode entrar como ALUGAR e ficar ruim depois.
   - O Scout mede lucro real e cancela quando nao bate minimo.

6. **`Auto OFF` na pagina Testes nao e o mesmo botao.**
   - O Clore automatico fica no Dashboard como **AUTOMATICO CLORE ON/OFF**.

## Checklist de manutencao futura

Ao mexer neste recurso, verificar:

1. `dashboard/app.py`
   - `CLORE_AUTO_BLOCK_RISKS`
   - `CLORE_AUTO_BAD_HISTORY_DECISIONS`
   - `scout_hardware_block_reason()`
   - `decision_opportunity_visible()`
   - `scout_opportunity_history_summary()`
   - `clore_auto_block_reason()`
   - `maybe_autostart_clore_scout()`
   - `start_scout_clore_rent()`
   - endpoints `/api/scout/clore-auto/*`

2. `dashboard/scout_settings.py`
   - defaults de `clore_auto_enabled`;
   - defaults de `clore_auto_queue`.

3. `dashboard/static/app.js`
   - `renderCloreAuto()`;
   - `renderHistorySeen()`;
   - `historyTitle()`;
   - colunas de oportunidade.

4. `dashboard/static/scout.js`
   - `sourceLabel()`;
   - `sourceDetail()`;
   - coluna Origem em ativos/historico.

5. `dashboard/static/results.js`
   - mesma logica de origem/log.

6. `dashboard/static/index.html`
   - botao e colunas.

7. `dashboard/static/scout.html`
   - coluna Origem.

8. `dashboard/static/results.html`
   - coluna Origem.

## Melhorias futuras possiveis

Ideias ainda nao implementadas:

- Botao separado para permitir **Auto Clore MARGEM** com limite menor.
- Lista visual da `clore_auto_queue` no Dashboard.
- Filtro configuravel de reliability minima.
- Filtro configuravel de pais/rede.
- Botao para limpar cooldown de um server especifico.
- Modo reteste automatico para historico ruim muito antigo.
- Grafico de lucro real por server Clore.
- Painel de "por que nao alugou" direto na linha da oportunidade.

