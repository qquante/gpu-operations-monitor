# AlphaPool / AlphaMine Pearl - pesquisa bruta para dashboard

Pesquisa feita em 2026-05-28 para entender como AlphaPool deve entrar nas regras do dashboard de lucratividade Pearl.

## URLs visitadas

- https://pearl.alphapool.tech/
- https://pearl.alphapool.tech/#dashboard
- https://pearl.alphapool.tech/#blocks
- https://pearl.alphapool.tech/#miners
- https://pearl.alphapool.tech/#setup
- https://pearl.alphapool.tech/#faq
- https://pearl.alphapool.tech/api/stats
- https://pearl.alphapool.tech/api/charts
- https://pearl.alphapool.tech/api/blocks?limit=5
- https://pearl.alphapool.tech/api/miners?limit=5

## O que o site comunica

- Nome visual: AlphaPool Pearl.
- Operado pela AlphaPool / AlphaMine.
- Não afiliado à Pearl Research Labs.
- Proposta: miner rápido para Pearl em qualquer NVIDIA com tensor cores.
- O site afirma suporte a:
  - Volta: V100, CMP 100-210;
  - Ampere: RTX 30, A100;
  - Ada: RTX 40, L4, L40;
  - Blackwell: RTX 50, B100, B200;
  - Hopper: H100, H200.
- Declara que o `alpha-miner` supera referência e kernels concorrentes em hashrate por watt.
- Declara H100/Hopper optimization live no `alpha-miner v1.6`.

## Fee, payout e payout method

Dados visuais:

- Pool fee: 5%.
- Miner client dev fee: 1%.
- Para cálculo econômico real, custo efetivo recomendado: 6%.
- Payout method: time-weighted PPLNS.
- Half-life PPLNS: 65 minutos.
- Share conta 100% quando fresh, 50% depois de 65 min, 25% depois de 2h10.
- Min payout: 0.5 PRL.
- Payouts a cada 6h no rodapé.
- Solo mode disponível com 5% fee.

Implica para dashboard:

- `fee_percent_pool = 5`.
- `fee_percent_effective = 6` quando usando `alpha-miner`.
- Payout mínimo baixo; bom para operação menor.
- PPLNS com decay favorece mineração contínua. Dashboard deve alertar que liga/desliga curto pode distorcer payout real.

## Stratum endpoints

Dados visuais:

```text
STANDARD: us2.alphapool.tech:5566
SOLO:     us2.alphapool.tech:5567
```

Notas:

- Standard: PPLNS, 5% fee, auto-difficulty.
- Solo: 5% fee, winner takes whole block reward.
- High-diff aparece como "soon", usando mesmo host/porta no texto.

Login:

```text
<your_PRL_address>.<rig_label>
```

Password:

```text
x
```

Static diff:

```text
x;d=4096
```

## Hashrates oficiais por GPU

Tabela extraída visualmente do site:

| GPU | Hashrate oficial AlphaPool | Observações |
| --- | ---: | --- |
| RTX 3060 Ti | 40-50 TH/s | Ampere SM_86 |
| RTX 3070 | 50-60 TH/s | Ampere, 8 GB |
| RTX 3090 | 100-110 TH/s | Ampere, 24 GB |
| RTX 5070 Ti | 110-130 TH/s | Blackwell SM_120, alpha-miner v1.6 |
| RTX 4090 | 245-255 TH/s | Ada SM_89 |
| RTX 5080 | 175-185 TH/s | Blackwell SM_120, alpha-miner v1.6 |
| RTX 5090 | 350-360 TH/s | Blackwell, 32 GB, alpha-miner v1.6 |
| H100 | 610-620 TH/s | Hopper SM_90, alpha-miner v1.6 |

O site diz que mais placas serão adicionadas conforme dados entram:

- RTX 3080
- RTX 4070
- RTX 4080
- A100
- A4000
- L4
- L40
- H200
- B100
- B200
- V100
- RTX 5060 Ti
- RTX 5070
- RTX 5070 Ti

## Divergências contra o guia e banco atual

O `PEARL_MINING_COMPLETE_GUIDE.md` e `shared/gpu_hashrates.py` têm valores mais conservadores para algumas GPUs.

Exemplos importantes:

| GPU | Guia/banco atual | AlphaPool oficial | Regra dashboard |
| --- | ---: | ---: | --- |
| RTX 3090 | 90 TH/s | 100-110 TH/s | usar 90 por padrão conservador |
| RTX 4090 | 195 TH/s Akoya | 245-255 TH/s AlphaPool | não misturar; Akoya 195 para Akoya, AlphaPool só se escolhido/testado |
| RTX 5080 | 167 TH/s | 175-185 TH/s | usar 167 por padrão conservador |
| RTX 5090 | 310 TH/s | 350-360 TH/s | usar 310 por padrão conservador |
| H100 | 594 TH/s logs Akoya | 610-620 TH/s AlphaPool | usar 594 por padrão conservador |

Decisão já tomada:

- Dashboard usa o menor valor confiável por padrão.
- Valores oficiais otimistas podem aparecer como teto/observação, não como base de decisão automática.

## APIs públicas confirmadas

### `GET /api/stats`

URL:

```text
https://pearl.alphapool.tech/api/stats
```

Resposta observada contém:

- `chain.best_hash`
- `chain.chain`
- `chain.difficulty`
- `chain.height`
- `coins[]`
- `feePercent`
- `pool.blocks24h`
- `pool.hashrate`
- `pool.hashrate1h`
- `pool.miners24h`
- `pool.payouts24h`
- `pool.ttfLabel`
- `pool.workers`
- `recentBlocks[]`
- `stratum.host`
- `stratum.standardPort`
- `stratum.soloPort`
- `stratum.soloFeePercent`
- `updatedAt`

Valores observados:

```json
{
  "feePercent": 5,
  "pool": {
    "blocks24h": 134,
    "hashrate": "3.74 EH/s",
    "hashrate1h": "3.74 EH/s",
    "miners24h": 2808,
    "workers": 26203
  },
  "stratum": {
    "host": "us2.alphapool.tech",
    "standardPort": 5566,
    "soloPort": 5567,
    "soloFeePercent": 5
  }
}
```

Uso no dashboard:

- Pool hashrate.
- Blocks found 24h.
- Workers/miners.
- Fee.
- Network height/difficulty/reward.
- Recent blocks.
- Stratum endpoint.

### `GET /api/charts`

URL:

```text
https://pearl.alphapool.tech/api/charts
```

Resposta observada:

- `hashrateSeries[]` com `t` e `hashrateRaw`.
- Há séries históricas de hashrate e possivelmente blocos.

Uso no dashboard:

- Sparkline de pool health.
- Detectar queda/aumento brusco do pool.

### `GET /api/blocks?limit=5`

URL:

```text
https://pearl.alphapool.tech/api/blocks?limit=5
```

Campos observados:

- `height`
- `hash`
- `found_ts`
- `reward_grain`
- `is_solo`
- `confirmed`
- `orphaned`
- `paid_out`
- `found_by_miner_addr`

Uso no dashboard:

- Blocos recentes.
- Confirmado/imature/orphaned.
- Payout não deve ser assumido antes de maturidade.

### `GET /api/miners?limit=5`

URL:

```text
https://pearl.alphapool.tech/api/miners?limit=5
```

Campos observados:

- `address`
- `workers`
- `hashrate_1h`
- `shares_24h`
- `last_share_ts`
- `rank`

Uso no dashboard:

- Ranking público de miners.
- Ver concentração de pool.
- Comparar nossa wallet se monitor futuro for criado.

### `GET /api/miner/{wallet}`

Endpoint encontrado nos assets:

```text
https://pearl.alphapool.tech/api/miner/{wallet}
```

Ainda não testado com wallet principal nesta pesquisa.

Uso provável:

- Dashboard por carteira.
- Workers e hashrate próprios no AlphaPool.

## Dados operacionais observados

Na visita, o site mostrou aproximadamente:

- Pool hashrate: 3.74 EH/s.
- Network hashrate: 19.85 EH/s.
- Active miners 24h: 2,808.
- Workers: 26,203.
- Blocks found 24h: 134.
- Block reward: ~2,686 PRL.
- Difficulty: ~7,615,496.
- Block time visual: ~3 min 14 sec.

Esses números são temporais e devem ser coletados por API se virarem monitor.

## Campos que um monitor futuro poderia publicar

Key proposta: `monitor:alphapool`

Campos:

- `pool_hashrate_ths`
- `pool_hashrate_1h_ths`
- `network_hashrate_ths`
- `network_difficulty`
- `best_block_height`
- `reward_per_block_prl`
- `fee_percent_pool`
- `fee_percent_effective`
- `min_payout_prl`
- `workers`
- `miners_24h`
- `blocks_24h`
- `payouts_24h_prl`
- `stratum_host`
- `stratum_standard_port`
- `stratum_solo_port`
- `recent_blocks[]`
- `hashrate_series[]`
- `my_wallet` quando configurada

## Riscos e incertezas

- Site oficial é otimista em relação a alguns hashrates. Dashboard deve usar valor conservador por padrão.
- Fee efetiva é pool fee 5% + miner dev fee 1% se usar `alpha-miner`.
- PPLNS com half-life: payout real pode demorar a convergir depois de ligar/desligar.
- H100/H200 podem ser melhores no AlphaPool segundo site, mas temos logs próprios no Akoya; usar menor confiável.
- Endpoint high-diff aparece como "soon"; não assumir pronto.

## Regras para dashboard

- Usar AlphaPool como pool preferencial para RTX 50xx se nosso banco conservar isso.
- Calcular com fee efetiva 6% quando a estratégia usar `alpha-miner`.
- Mostrar hashrate oficial AlphaPool como faixa, mas decisão automática usa valor conservador.
- Para RTX 4090, não trocar automaticamente de Akoya para AlphaPool só porque o site promete mais; exigir teste/flag.
- Alertar para PPLNS decay se a operação for curta.
