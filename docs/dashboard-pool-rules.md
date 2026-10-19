# Regras de pools para o dashboard Pearl

Documento de consolidação para o futuro dashboard. Baseado em:

- `PEARL_MINING_COMPLETE_GUIDE.md`
- `docs/pools/pearlhash.md`
- `docs/pools/alphapool.md`
- `docs/pools/akoya.md`
- Monitores atuais: `monitor:pearl`, `monitor:akoya`, `monitor:clore`, `monitor:vastai`

## Decisão central do dashboard

O dashboard deve responder em poucos segundos:

```text
Devo alugar, manter, cancelar ou investigar cada GPU/servidor agora?
```

Não é primeiro uma landing page nem painel bonito. É uma tela operacional de decisão.

## Régua de decisão

Campos calculados por oferta/servidor:

- `receita_usd_dia`
- `custo_usd_dia`
- `lucro_usd_dia`
- `roi_pct_dia`
- `pool_recomendado`
- `hashrate_ths_usado`
- `hashrate_source`
- `risk_flags[]`
- `decision`

Fórmulas:

```text
receita_usd_dia = gpu_hashrate_ths * usd_per_th_per_day(pool)
custo_usd_dia = price_usd_hr * 24
lucro_usd_dia = receita_usd_dia - custo_usd_dia
roi_pct_dia = lucro_usd_dia / custo_usd_dia * 100
```

Semáforo:

- Verde: `lucro_usd_dia >= 3` e `roi_pct_dia >= 20`.
- Amarelo: lucro positivo, mas abaixo de verde.
- Vermelho: lucro menor ou igual a zero.
- Alerta: lucro positivo com risco técnico alto ou dados fracos.
- Cinza: dados insuficientes, GPU desconhecida ou pool sem benchmark confiável.

## Princípio conservador

Quando houver divergência entre:

- guia antigo;
- site oficial do pool;
- benchmark próprio;
- banco `shared/gpu_hashrates.py`;
- marketplace;

o dashboard usa o menor valor confiável por padrão.

O valor otimista pode aparecer como cenário/teto, mas não decide aluguel automaticamente.

## Pool/kernel por GPU

Default atual, vindo do guia:

| Classe GPU | Pool/kernel default | Fee de cálculo | Observação |
| --- | --- | ---: | --- |
| RTX 30xx | Akoya | 5% | Usar hashrate conservador do banco |
| RTX 40xx | Akoya | 5% | RTX 4090 usa 195 TH/s default |
| RTX 50xx | AlphaPool/AlphaMine | 6% | 5% pool + 1% miner dev fee |
| H100/H200 | Akoya | 5% | Usar 594 TH/s para H100 por padrão conservador |
| A100 | Akoya/Alpha possível, mas low-value | 5-6% | Marcar como alto risco/prejuízo provável |
| RTX A4000/A5000/A6000 | Akoya | 5% | Hashrate estimado, mostrar risco se margem pequena |
| V100/L4/L40/B200/RTX PRO | Não default | n/a | Só calcular se houver benchmark confiável |

Regra importante:

```text
Nunca misturar hashrate oficial de um pool com fee/kernel de outro.
```

Exemplo:

- RTX 4090 no Akoya: calcular com ~195 TH/s.
- RTX 4090 no AlphaPool: site promete 245-255 TH/s, mas dashboard só deve usar isso se estratégia/pool for explicitamente AlphaPool e ainda assim com aviso.

## Hashrate default por divergência conhecida

| GPU | Valor conservador default | Fontes/divergência |
| --- | ---: | --- |
| RTX 3060 Ti | 45 TH/s | guia/banco; AlphaPool 40-50 |
| RTX 3070 | 55 TH/s | guia/banco; AlphaPool 50-60 |
| RTX 3080 | 85 TH/s | guia/banco |
| RTX 3090 | 90 TH/s | guia/banco; AlphaPool 100-110 |
| RTX 4090 | 195 TH/s | Akoya oficial/banco; AlphaPool 245-255 |
| RTX 5070 Ti | 120 TH/s | banco; AlphaPool 110-130 |
| RTX 5080 | 167 TH/s | banco; AlphaPool 175-185 |
| RTX 5090 | 310 TH/s | banco; AlphaPool 350-360; Akoya ~250 |
| H100 | 594 TH/s | logs próprios; AlphaPool 610-620; Akoya 600-610 |
| H200 | 635 TH/s | estimado no banco; validar antes de alto gasto |
| A100 | 50 TH/s | low-value, alto risco econômico |

## Fontes de dados atuais

### `monitor:pearl`

Fonte principal de rede e preço:

- `network_hashrate_ths`
- `avg_block_time_s`
- `blocks_per_day`
- `reward_per_block`
- `prl_price_usd`
- `difficulty`
- `usd_per_th_per_day`
- `usd_per_th_per_hour`

Uso:

- Base de cálculo econômico.
- Dashboard deve recalcular lucro toda vez que esse payload muda.

### `monitor:akoya`

Fonte da nossa operação atual:

- `is_online`
- `worker_count`
- `online_worker_count`
- `total_hashrate_ths`
- `pending_balance_prl`
- `total_paid_prl`
- `accepted_shares24h`
- `stale_shares24h`
- `stale_rate24h_pct`
- `maturing_blocks`
- `workers[]`

Uso:

- Saúde dos workers.
- Receita real vs esperada.
- Alertas de worker offline, stale alto, hashrate abaixo do esperado.

### `monitor:clore`

Fonte marketplace:

- `servers[]`
- preço por hora/dia;
- GPU normalizada;
- quantidade;
- CUDA;
- país;
- rede;
- reliability;
- rented/available.

Uso:

- Oportunidades e servidores alugados/indisponíveis.
- Cuidado: Clore tem GPUs laptop e PCIe ruim; manter flags técnicas.

### `monitor:vastai`

Fonte marketplace:

- `offers[]`
- `price_usd_hr`
- `gpu_model_normalized`
- `gpu_count`
- `cuda_max_good`
- `pcie_lanes`
- `pcie_bw_gbps`
- `reliability`
- `meets_guidelines`

Uso:

- Oportunidades on-demand com CUDA >= 12.9 e PCIe >= x8/bw >= 8.
- Vast.ai já filtra para candidatos mais prontos.

## Pools documentados mas sem monitor novo agora

### Pearlhash

Usar por enquanto como:

- fonte secundária de dados de rede;
- pesquisa sobre pool alternativo;
- não calcular como pool default por GPU.

Motivos:

- Sem tabela pública de hashrate por GPU.
- API docs linkado no site retorna 404.
- Fee 0% é temporário ("until the new release").

### AlphaPool

Usar por enquanto como:

- referência de estratégia para RTX 50xx;
- fonte de hashrate oficial otimista;
- candidato a monitor futuro.

Motivos:

- Tem APIs públicas boas.
- Fee efetiva precisa incluir dev fee do miner.
- PPLNS half-life precisa entrar no risco operacional.

### Akoya global pool

Já temos monitor da nossa wallet. O monitor global `/pool/*` fica para depois.

Uso futuro:

- pool luck;
- hardware mix;
- payout sweep;
- pool status;
- hashrate history.

## Risk flags

O dashboard deve marcar risco quando:

- `cuda_version < 12.9`.
- PCIe lanes abaixo de x8 ou bandwidth abaixo de 8 GB/s em Vast.
- PCIe desconhecido em oferta cara.
- GPU laptop/mobile.
- GPU low-value: A100, V100, Turing, RTX PRO desconhecida, B200/B300 sem benchmark.
- Reliability baixa no marketplace.
- Rede up/down muito baixa.
- Preço positivo mas lucro abaixo de $3/dia.
- ROI positivo mas abaixo de 20%.
- Pool fee/dev fee incerto.
- Hashrate oficial do pool maior que nosso conservador por margem grande.
- Dados de rede divergentes entre fontes.
- Worker real no Akoya abaixo do hashrate esperado.
- Stale rate alto.
- Pending balance abaixo do payout mínimo com ETA longo.

## Dashboard views sugeridas

### 1. Decisão agora

Tabela única:

- plataforma;
- id oferta/servidor;
- GPU;
- qtd;
- pool recomendado;
- custo/dia;
- receita/dia;
- lucro/dia;
- ROI;
- decisão;
- riscos.

Ordenar por:

1. decisão verde;
2. maior lucro/dia;
3. maior ROI;
4. menor risco.

### 2. Minha operação

Dados do Akoya:

- total hash;
- workers online/offline;
- saldo pendente;
- PRL pago;
- stale rate;
- maturing blocks;
- ETA até payout mínimo;
- hashrate esperado vs real por worker.

### 3. Rede Pearl

- preço PRL;
- network hash;
- difficulty;
- blocks/day;
- reward;
- USD/TH/day por pool;
- variação vs última atualização.

### 4. Pesquisa de pools

Bloco informativo com:

- Akoya;
- AlphaPool;
- Pearlhash;
- fee;
- payout mínimo;
- payout method;
- endpoints;
- status de confiança.

## Acceptance criteria para o dashboard futuro

- Uma oferta verde deve sempre mostrar o cálculo que levou ao verde.
- Nenhuma oferta com lucro <= 0 pode aparecer verde.
- Nenhuma GPU desconhecida pode aparecer como oportunidade automática.
- Se houver divergência de hashrate, mostrar fonte e valor conservador usado.
- Se a operação atual perder worker ou stale subir, isso deve aparecer acima das oportunidades.
- Se `monitor:pearl` ficar stale/expirar, cálculos de lucro devem virar cinza.
