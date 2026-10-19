# Akoya Pool - pesquisa bruta para dashboard

Pesquisa feita em 2026-05-28 para entender como Akoya deve entrar nas regras do dashboard de lucratividade Pearl.

## URLs visitadas

- https://akoyapool.com/
- https://akoyapool.com/stats
- https://akoyapool.com/start
- https://akoyapool.com/faq
- https://akoyapool.com/blocks
- https://akoyapool.com/payouts
- https://akoyapool.com/api/v1/pool/stats
- https://akoyapool.com/api/v1/pool/info
- https://akoyapool.com/api/v1/pool/blocks
- https://akoyapool.com/api/v1/pool/payout_history
- https://akoyapool.com/api/v1/pool/hardware_mix
- https://akoyapool.com/api/v1/pool/top_miners
- https://akoyapool.com/api/v1/pool/luck
- https://akoyapool.com/api/v1/pool/tip
- https://akoyapool.com/api/v1/pool/status
- https://akoyapool.com/api/v1/pool/hashrate_history

## O que o site comunica

- Akoya Pool V2 está live.
- Pool pseudônimo para Pearl.
- Não afiliado à Pearl Research Labs.
- Infra V2: share security mais forte, single-connection miners, persistent sessions.
- Kernels dedicados para 5090 / 4090.
- A página principal fala em:
  - 5090 por volta de 250 TH/s;
  - 4090 por volta de 190 TH/s;
  - 4090 na tabela: 195 TH/s;
  - H100/H200: 600-610 TH/s.
- Pool usa kernel próprio que cabe em ~2 GB de VRAM.
- Site afirma suporte a RTX 3060 -> RTX 6000 Pro, H100, H200, A100.
- Payout: PPLNS-N e Solo.
- Pool fee: 5%.
- Min payout: 10 PRL.
- Payout sweep: a cada 15 minutos.
- Maturity: cerca de 100 confirmações / ~5h23m na página de payouts.

## Miner e setup

Docker recomendado:

```bash
docker run -d --gpus all --restart=unless-stopped --name akoya-miner \
  -e AKOYA_POOL_WALLET=YOUR_PEARL_ADDRESS \
  -e AKOYA_POOL_WORKER=YOUR_WORKER_NAME \
  registry.akoyapool.com/akoya-miner:latest
```

O site também oferece script:

```text
https://get.akoyapool.com/install.sh
```

Para cloud, o site menciona Vast.ai e RunPod.

## Fee, payout e payout method

Dados confirmados:

- Pool fee: 5%.
- Min payout: 10 PRL.
- Sweep: 15 minutos.
- Maturity: cerca de 100 confirmações.
- Payout method: PPLNS-N, Solo.
- TX fee coberta pelo pool segundo página de payouts.
- Se saldo abaixo de 10 PRL, ele acumula; o FAQ diz que saldo nunca expira e não há inactivity fee.

Implica para dashboard:

- Operações pequenas podem demorar para receber payout.
- Lucro esperado pode ser positivo, mas cashflow fica travado abaixo de 10 PRL.
- Dashboard deve mostrar "dias até payout mínimo" para nossa operação.

## Hashrates oficiais Akoya

Dados visuais:

| GPU | Hashrate Akoya oficial/visual | Observações |
| --- | ---: | --- |
| H100 / H200 | 600-610 TH/s | tabela vs reference miner |
| RTX 5090 | 250 TH/s | status fala "around 250" |
| RTX 4090 | 195 TH/s | tabela; status fala "around 190" |
| H200 reference comparison | 580 TH/s vs 245 TH/s | card "2.4x H200" |

FAQ:

- Afirma que usa ~2 GB VRAM.
- Diz que qualquer coisa da "GTX 30-series forward" funciona. Provavelmente quer dizer RTX 30-series/Ampere para frente; registrar como texto bruto do site, mas não usar literalmente GTX.

## Divergências contra AlphaPool e guia

| GPU | Akoya oficial | AlphaPool oficial | Banco/guia conservador | Regra dashboard |
| --- | ---: | ---: | ---: | --- |
| RTX 4090 | 190-195 | 245-255 | 195 | usar 195 para Akoya |
| RTX 5090 | ~250 | 350-360 | 310 | se Akoya, usar 250; se AlphaPool, usar 310 conservador |
| H100 | 600-610 | 610-620 | 594 logs | usar 594 conservador |
| H200 | 600-610 | sem tabela final, citado | 635 estimado | usar conservador/testado; evitar otimismo |

Decisão já tomada:

- Dashboard usa menor valor confiável por padrão.
- Não misturar hashrate de um pool com fee/kernel de outro.

## APIs públicas confirmadas

Base:

```text
https://akoyapool.com/api/v1
```

### `GET /pool/stats`

URL:

```text
https://akoyapool.com/api/v1/pool/stats
```

Resposta observada:

```json
{
  "data": {
    "pool_name": "Akoya",
    "connected_miners": 2184,
    "total_hashrate": 1.0943032402236992e18,
    "blocks_found24_h": 33,
    "total_blocks_found": 472,
    "current_block_height": 62813,
    "pool_fee_percent": 5,
    "min_payout_prl": 10,
    "expected_block_time_seconds": 194,
    "target_blocks_per_day": 445,
    "network_hashrate": 1.9846762786627523e19,
    "active_workers": 2184,
    "registered_miners": 2285,
    "total_paid24_h": 76313.63629467,
    "total_paid7_d": 527099.25966276,
    "total_paid_all_time": 1195899.35190117,
    "avg_time_to_block_seconds": 1734.645,
    "last_block_found_at": 1779974384,
    "pool_share_of_network": 0.05513761876375253
  },
  "server_time": 1779975311
}
```

Uso no dashboard:

- Pool hashrate.
- Network hash.
- Pool share.
- Fee e min payout.
- Blocks 24h.
- Avg time to block.
- Total paid.

### `GET /pool/info`

URL:

```text
https://akoyapool.com/api/v1/pool/info
```

Campos observados:

- `network_name`
- `network_chain_id`
- `pool_name`
- `pool_version`
- `pearld_node_version`
- `payout_interval_seconds`
- `expected_block_time_seconds`
- `target_blocks_per_day`
- `min_payout_prl`
- `pool_fee_percent`
- `block_reward_prl`
- `explorer_url_template`

Uso no dashboard:

- Configuração operacional estável.
- Mostrar payout interval, fee e min payout.

### `GET /pool/blocks`

URL:

```text
https://akoyapool.com/api/v1/pool/blocks
```

Campos observados em `data[]`:

- `block_height`
- `block_hash`
- `found_by`
- `found_at`
- `reward`
- `status`
- `is_confirmed`
- `is_mature`
- `is_orphan`
- `confirmations`
- `confirmations_remaining`
- `estimated_seconds_to_mature`
- `paid_out`

Uso no dashboard:

- Maturity de blocos.
- Blocos órfãos.
- ETA até reward maturar.

### `GET /pool/payout_history`

URL:

```text
https://akoyapool.com/api/v1/pool/payout_history
```

Campos observados:

- `wallet_address`
- `payout_date`
- `amount`
- `fee_amount`
- `fee_percent`
- `tx_id`
- `status`
- `created_at`
- `confirmed_at`

Uso no dashboard:

- Auditar pagamentos.
- Conferir fee real.
- Ver atraso/estado broadcast/confirmed.

### `GET /pool/hardware_mix`

URL:

```text
https://akoyapool.com/api/v1/pool/hardware_mix
```

Resposta observada:

```json
{
  "data": {
    "cards": [
      {"gpu_card": "NVIDIA H100 80GB HBM3", "count": 684},
      {"gpu_card": "NVIDIA GeForce RTX 4090", "count": 443},
      {"gpu_card": "NVIDIA GeForce RTX 5090", "count": 247},
      {"gpu_card": "NVIDIA H200", "count": 155},
      {"gpu_card": "NVIDIA GeForce RTX 4070 Ti SUPER", "count": 122},
      {"gpu_card": "NVIDIA GeForce RTX 3070 Laptop GPU", "count": 57},
      {"gpu_card": "NVIDIA L4", "count": 53},
      {"gpu_card": "NVIDIA L40S", "count": 48},
      {"gpu_card": "NVIDIA GeForce RTX 5070 Ti", "count": 41},
      {"gpu_card": "NVIDIA GeForce RTX 5080", "count": 30}
    ],
    "total_active_workers": 2197
  }
}
```

Uso no dashboard:

- Entender quais GPUs realmente estão sendo usadas.
- Atualizar aliases de GPU.
- Identificar laptop GPUs no pool, mas não automaticamente considerar lucrativas.

### `GET /pool/top_miners`

URL:

```text
https://akoyapool.com/api/v1/pool/top_miners
```

Campos observados:

- `rank`
- `wallet_address`
- `hashrate`
- `hashrate_formatted`
- `worker_count`
- `pool_share_percent`
- `earned24_h`
- `registered_at`

Uso no dashboard:

- Ranking público.
- Concentração do pool.
- Comparar nossa wallet se aparecer.

### `GET /pool/luck`

URL:

```text
https://akoyapool.com/api/v1/pool/luck
```

Campos observados:

- `luck24_h`
- `luck7_d`
- `blocks_found24_h`
- `blocks_found7_d`
- `expected_blocks24_h`
- `expected_blocks7_d`
- `avg_time_to_block_seconds`
- `last_block_found_at`

Uso no dashboard:

- Mostrar risco de variação de payout por luck.
- Alertar se lucro calculado por expectativa diverge do payout real recente.

### `GET /pool/status`

URL:

```text
https://akoyapool.com/api/v1/pool/status
```

Campos observados:

- `pearld_reachable`
- `last_payout_sweep_at`
- `last_payout_sweep_count`
- `last_payout_sweep_amount_prl`

Uso no dashboard:

- Saúde operacional do pool.
- Ver se payout sweep está rodando.

### `GET /pool/hashrate_history`

URL:

```text
https://akoyapool.com/api/v1/pool/hashrate_history
```

Campos observados:

- `data.samples[]`
- `timestamp`
- `hash_rate`

Uso no dashboard:

- Sparkline de saúde do pool.
- Detectar queda/aumento.

### `GET /pool/tip`

URL:

```text
https://akoyapool.com/api/v1/pool/tip
```

Campos observados:

- `height`
- `hash`
- `ts`

Uso no dashboard:

- Confirmar sync/altura recente.

### `GET /pool/endpoints`

URL testada:

```text
https://akoyapool.com/api/v1/pool/endpoints
```

Resultado observado: 404.

Notas:

- O bundle do frontend referencia `/pool/endpoints`, mas a API retornou 404 na pesquisa.
- Não depender desse endpoint.

## Monitor existente no projeto

Já existe:

```text
monitor:akoya
```

Ele usa:

```text
https://akoyapool.com/api/v1/miners/{wallet}
```

Dados publicados pelo monitor atual:

- online/offline
- workers
- total hashrate
- pending balance
- total paid
- shares/stales
- maturing blocks
- workers por nome/GPU

Gap:

- Monitor atual é da nossa wallet.
- Para dashboard completo, talvez no futuro também valha consumir endpoints globais `/pool/*`.
- Por enquanto o plano é documentar, não criar novo monitor.

## Campos que um monitor futuro poderia publicar

Key proposta: `monitor:akoya_pool`

Campos:

- `pool_hashrate_ths`
- `network_hashrate_ths`
- `pool_share_pct`
- `blocks_24h`
- `expected_blocks_24h`
- `luck_24h_pct`
- `luck_7d_pct`
- `fee_percent`
- `min_payout_prl`
- `payout_interval_seconds`
- `last_payout_sweep_at`
- `last_payout_sweep_amount_prl`
- `pearld_reachable`
- `hardware_mix[]`
- `recent_blocks[]`
- `hashrate_history[]`

## Riscos e incertezas

- O site diz "GTX 30-series forward"; interpretar como RTX/Ampere para frente, não GTX literal.
- Hashrate de 5090 no Akoya é menor que AlphaPool oficial.
- H100/H200 estimado 600-610, mas nosso log real tem ~594 TH/s; usar conservador.
- Min payout 10 PRL pode travar cashflow em operação pequena.
- PPLNS/luck pode fazer payout real divergir do lucro esperado no curto prazo.

## Regras para dashboard

- Akoya é pool default para RTX 40xx e abaixo, conforme guia atual.
- H100/H200 podem usar Akoya com hashrate conservador.
- RTX 50xx não deve usar Akoya como default se AlphaPool for melhor e já estiver decidido assim.
- Para a nossa operação, `monitor:akoya` é fonte primária de workers e saldo.
- Dashboard deve mostrar:
  - pending PRL;
  - dias/horas até min payout;
  - maturing blocks;
  - stale rate;
  - worker offline;
  - hashrate real vs esperado por GPU.
