# Scout, Vast, RunPod e TensorDock - contexto operacional

Data: 2026-05-28

## Objetivo

O dashboard deve decidir onde alugar GPU para minerar Pearl com lucro real, nao apenas lucro teorico.

O fluxo ideal e:

- buscar oportunidades em marketplaces;
- calcular receita esperada por pool;
- alugar apenas dentro dos limites configurados;
- testar mineracao real por janela minima;
- medir hash real, custo real e lucro/h;
- manter apenas o que passou;
- destruir e registrar historico do que falhou;
- evitar repetir host/maquina ruim.

## Estado atual do Scout

Rota atual:

- `/scout`

APIs atuais:

- `GET /api/scout/state`
- `POST /api/scout/settings`
- `POST /api/scout/start/{ask_id}`
- `POST /api/scout/stop/{test_id}`
- `POST /api/scout/destroy/{test_id}`
- `POST /api/scout/pause`
- `POST /api/scout/resume`
- `POST /api/scout/reset`

Configuracao operacional atual verificada apos reset:

- `enabled`: false
- `active_tests`: 0
- `history`: 0
- `max_parallel_tests`: 10
- `starts_per_tick`: 1
- `test_seconds`: 1800
- `worker_timeout_seconds`: 900
- `offline_timeout_seconds`: 480
- `min_profit_usd_hr`: 0.20
- `min_hash_ratio`: 0.45
- `max_price_usd_hr`: 3.00
- `pool_order`: `["akoya", "alphamine"]`

## Mudancas ja feitas

### Reset limpo

Foi criado o endpoint `POST /api/scout/reset`.

Ele:

- pausa o Scout;
- limpa testes ativos do Scout;
- limpa historico duravel em `data/scout_history.json`;
- arquiva acoes antigas de Scout;
- remove blacklist criada pelo Scout;
- preserva settings;
- garante timeout sem worker de no minimo 15 min.

Tambem foi adicionado o botao `Reset limpo` na tela `/scout`.

Observacao: no primeiro reset, algumas instancias antigas ainda foram reencontradas pela sincronizacao Vast. Elas foram destruidas manualmente depois. Para robustez futura, o reset tambem deve destruir acoes que tenham `scout_test_id` mesmo quando o teste ja sumiu do estado.

### Timeout sem miner

Regra atual:

- se o worker/miner nao aparece em 15 min, o Scout pode destruir/ignorar;
- isso nao deve tentar trocar pool automaticamente em cima de instancia quebrada;
- erros fatais de Docker/CDI/GPU ainda podem destruir antes dos 15 min.

Antes, status transitorio como `offline`, `unknown` ou `exited` podia matar teste cedo demais. Isso foi ajustado para nao ser fatal sozinho.

### Paralelismo e isolamento

Regra atual:

- o Scout respeita `max_parallel_tests`;
- o valor desejado atual e 10 testes paralelos;
- o motor inicia no maximo `starts_per_tick` por ciclo para evitar rate limit;
- hoje `starts_per_tick = 1`, entao ele preenche os 10 aos poucos;
- ha filtro para evitar testar em paralelo a mesma combinacao de `machine_id`, `host_id` e GPU.

Ponto importante:

- se a oferta nao trouxer `machine_id` ou `host_id`, o isolamento fica mais fraco;
- para RunPod/TensorDock, precisamos definir identificadores equivalentes de host/datacenter/maquina.

### Custo e decisao

Regra atual:

- entrada Scout so aceita oferta ate `max_price_usd_hr`;
- atualmente o limite e `$3.00/h`;
- manter apenas se lucro real estimado for `>= $0.20/h`;
- destruir se lucro real ficar abaixo;
- destruir se hash real ficar abaixo de 45% do esperado;
- medir com `live_ths` suavizado, nao com `1h`/`24h` para maquina nova.

## Problemas conhecidos

### A/B entre pools in-place

Foi implementado o modo `pool_switch_mode = in_place_ab`.

Fluxo atual:

- aluga a instancia uma vez;
- mede o primeiro pool por 30 min;
- salva o resultado em `prior_results`;
- troca o container na mesma instancia Vast com `PUT /api/v0/instances/update_template/{instance_id}/`;
- executa `PUT /api/v0/instances/recycle/{instance_id}/`;
- preserva `ask_id`, `instance_id`, `host_id`, `machine_id` e custo/h;
- aguarda worker do novo pool por ate 15 min;
- mede o segundo pool por 30 min quando o worker aparece;
- escolhe o pool com maior lucro real, desde que `profit_usd_hr >= 0.20` e `hash_ratio >= 45%`;
- se o melhor pool nao estiver ativo, troca de volta in-place;
- se nenhum pool passa, destroi.

Detalhe importante aprendido em producao:

- `recycle` sozinho recria o container sem perder a GPU, mas usa a config atual;
- para trocar de pool antes do `recycle`, a Vast exige `update_template`;
- `update_template` precisa receber `image` como string, nao apenas `template_hash_id`;
- defaults usados:
  - Akoya: `registry.akoyapool.com/akoya-miner:latest`;
  - AlphaMine: `alphaminetech/pearl-miner:latest`;
- estes valores podem ser sobrescritos por `VAST_AKOYA_IMAGE` e `VAST_ALPHAMINE_IMAGE`.

Estado verificado:

- o teste `38264203` manteve o mesmo `instance_id = 38285368`;
- apos `update_template + recycle`, a Vast passou a mostrar `success, running alphaminetech/pearl-miner:latest`;
- o Scout passou a aguardar o worker AlphaMine, sem tentar realugar a ask.

### Rate limit

Abrir muitas instancias de uma vez gerou `429 Too Many Requests` na Vast.

Regra segura:

- manter `starts_per_tick = 1` ou pequeno;
- preencher ate 10 paralelos gradualmente;
- backoff quando qualquer marketplace responder 429.

### Historico antigo

O historico Scout foi limpo. Acoes antigas de Vast que nao eram Scout podem continuar em estado local e nao devem ser confundidas com testes novos.

## RunPod - informacoes trazidas

O console da RunPod usa GraphQL em:

- `https://api.runpod.io/graphql`

Operacao observada:

- `SecureGpuTypes`

Query observada:

```graphql
query SecureGpuTypes($lowestPriceInput: GpuLowestPriceInput, $gpuTypesInput: GpuTypeFilter) {
  gpuTypes(input: $gpuTypesInput) {
    lowestPrice(input: $lowestPriceInput) {
      minimumBidPrice
      uninterruptablePrice
      minVcpu
      minMemory
      stockStatus
      compliance
      maxUnreservedGpuCount
      availableGpuCounts
      gpuTypeDatacenters {
        dataCenterId
        availability
        supportNetworkVolumes
      }
    }
    id
    displayName
    memoryInGb
    securePrice
    communityPrice
    oneMonthPrice
    oneWeekPrice
    threeMonthPrice
    sixMonthPrice
    oneYearPrice
    secureSpotPrice
  }
}
```

IDs de GPU observados:

- `NVIDIA GeForce RTX 3090`
- `NVIDIA GeForce RTX 4090`
- `NVIDIA GeForce RTX 5090`
- `NVIDIA RTX A4000`
- `NVIDIA RTX A4500`
- `NVIDIA RTX A5000`
- `NVIDIA RTX A6000`
- `NVIDIA RTX 2000 Ada Generation`
- `NVIDIA RTX 4000 Ada Generation`
- `NVIDIA RTX 6000 Ada Generation`
- `NVIDIA RTX PRO 4000 Blackwell`
- `NVIDIA RTX PRO 4500 Blackwell`
- `NVIDIA RTX PRO 6000 Blackwell Server Edition`
- `NVIDIA RTX PRO 6000 Blackwell Workstation Edition`
- `NVIDIA L4`
- `NVIDIA L40`
- `NVIDIA L40S`
- `NVIDIA A40`
- `NVIDIA A100 80GB PCIe`
- `NVIDIA A100-SXM4-80GB`
- `NVIDIA H100 PCIe`
- `NVIDIA H100 80GB HBM3`
- `NVIDIA H100 NVL`
- `NVIDIA H200`
- `NVIDIA H200 NVL`
- `NVIDIA B200`
- `NVIDIA B300 SXM6 AC`
- `AMD Instinct MI300X OAM`

Nota de seguranca:

- nao salvar Bearer token do browser no repo;
- usar token de API oficial quando existir;
- se Bearer de sessao foi exposto em chat/log, relogar/rotacionar.

## TensorDock

Docs informadas:

- `https://dashboard.tensordock.com/api/docs`
- `https://dashboard.tensordock.com/api/docs/instance-creation`

Ainda precisa investigar a API antes de implementar.

## Modelo de integracao desejado

Criar uma camada comum de provider:

```text
MarketplaceProvider
  list_offers()
  create_instance(offer, pool_strategy, worker_name)
  destroy_instance(instance_id)
  get_instance_status(instance_id)
```

Cada provider deve retornar uma oportunidade normalizada:

```text
provider
offer_id
instance_id
gpu
gpu_count
price_usd_hr
price_usd_day
region
datacenter_id
host_id
machine_id
available
interruptible
expected_ths_akoya
expected_ths_alphamine
recommended_pool
risk_flags
```

Assim o Scout nao precisa saber se veio de Vast, RunPod, TensorDock ou Clore.

## Logica certa para RunPod/TensorDock

1. Buscar ofertas e precos.
2. Normalizar GPU para o mesmo nome usado no dashboard.
3. Calcular expected TH/s por pool.
4. Filtrar:
   - NVIDIA apenas;
   - GPU suportada pelo miner;
   - preco/h <= limite Scout;
   - capacidade disponivel;
   - regiao/datacenter com risco aceitavel.
5. Entrar na tabela `Decisao agora` junto com Vast/Clore.
6. Se Scout automatico estiver ativo, testar seguindo a mesma regra:
   - 30 min por pool;
   - 15 min max sem worker;
   - max paralelos configuravel;
   - custo acumulado visivel;
   - historico por provider/host/maquina/GPU/pool.

## Proximas tarefas sugeridas

1. Investigar APIs oficiais RunPod e TensorDock.
2. Criar provider `runpod` somente leitura primeiro.
3. Mostrar RunPod em `Decisao agora`, sem aluguel automatico.
4. Adicionar credenciais via `.env`, nunca no codigo.
5. Implementar criacao/destruicao RunPod.
6. Integrar RunPod no Scout.
7. Repetir para TensorDock.
8. Fortalecer reset para destruir acoes orfas com `scout_test_id`.
9. Corrigir A/B para trocar pool na mesma instancia quando provider permitir.

## Correcao Scout 2026-05-28

Problema encontrado: o Scout finalizava o primeiro pool com `destroy=True` e depois tentava recriar a mesma `ask_id` no segundo pool. Na Vast, isso perde a posse da GPU e muitas vezes a ask some, gerando `next_pool_unavailable`.

Regra corrigida no backend:

- `SCOUT_POOL_SWITCH_MODE=single_pool` e o padrao seguro.
- Ao terminar os 30 min do primeiro pool, o Scout decide `keep` ou `destroy` pela regra real de lucro/hash.
- Ele nao destroi uma VPS lucrativa apenas para tentar AlphaMine.
- O modo antigo destrutivo fica disponivel somente com `SCOUT_POOL_SWITCH_MODE=recreate`.
- Troca Akoya/AlphaMine sem perder a GPU deve ser implementada depois como modo in-place, usando template/imagem propria ou update/reboot Vast testado em maquina barata.

Estado operacional recomendado:

- deixar Scout pausado antes de alterar fluxo;
- preservar testes vivos;
- retomar auto somente depois de confirmar `pool_switch_mode=single_pool`;
- testar qualquer troca de imagem em uma instancia barata antes de permitir no worker automatico.
