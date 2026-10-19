# Pearlhash - pesquisa bruta para dashboard

Pesquisa feita em 2026-05-28 para entender como o pool Pearlhash deve entrar nas regras do dashboard de lucratividade Pearl.

## URLs visitadas

- https://pearlhash.xyz/
- https://pearlhash.xyz/api-docs
- https://pearlhash.xyz/api/stats
- https://pearlhash.xyz/api/chain-info
- https://pearlhash.xyz/api/pool-wallet-txs?page=1

## O que o site comunica

- Nome: Pearlhash.
- Posicionamento: "A pool for the finite revolution".
- Pool para mineração Pearl com miner próprio.
- O site diz que Pearl é PoUW e que cada bloco minerado é uma multiplicação de matriz verificável.
- O site fala em "0% fee until the new release".
- O site tem fluxo direto para mineração:
  - baixar `pearl-miner-v7`;
  - configurar endereço PRL;
  - rodar apontando para endpoint stratum.
- Payout mínimo mostrado no FAQ: 1 PRL.
- Rewards são distribuídos automaticamente no fim de cada epoch quando saldo passa de 1 PRL.
- O site tem lookup por endereço para ver hashrate, workers e histórico de pagamentos.

## Miner e endpoints de mineração

Miner:

```bash
curl https://pearlhash.xyz/downloads/pearl-miner-v7 -o pearl-miner && chmod +x pearl-miner
```

Comando gerado pelo site, sem wallet preenchida:

```bash
./pearl-miner --host 84.32.220.219:9000 --user <address>
```

Endpoints encontrados nos assets do site:

- EU / US: `84.32.220.219:9000`
- Asia: `129.226.55.135:9000`

## APIs públicas confirmadas

### `GET /api/stats`

URL:

```text
https://pearlhash.xyz/api/stats
```

Resposta observada:

```json
{
  "hashrate": 5105489455788381000,
  "total_accounts": 4837,
  "total_workers": 25161
}
```

Campos úteis:

- `hashrate`: hashrate do pool em H/s.
- `total_accounts`: contas/wallets vistas pelo pool.
- `total_workers`: workers online.

Uso no dashboard:

- Comparar share de pool contra rede.
- Mostrar saúde/tamanho do pool.
- Detectar queda brusca de workers/hashrate.

### `GET /api/chain-info`

URL:

```text
https://pearlhash.xyz/api/chain-info
```

Resposta observada:

```json
{
  "blocks": 62812,
  "difficulty": 7615496.00044329,
  "networkhashps": 19846762786627523000,
  "chain": "mainnet",
  "supply": 184990421.2679,
  "avg_block_time_s": 110.83
}
```

Campos úteis:

- `networkhashps`: hashrate da rede em H/s.
- `difficulty`: dificuldade da rede.
- `avg_block_time_s`: tempo médio de bloco.
- `blocks`: altura.
- `supply`: supply.

Uso no dashboard:

- Fonte alternativa para rede Pearl.
- Comparar contra `lordofpearls.xyz/api/public`.
- Se divergir muito, marcar dados de rede como risco.

### `GET /api/pool-wallet-txs?page=1`

URL:

```text
https://pearlhash.xyz/api/pool-wallet-txs?page=1
```

Resposta observada: JSON grande com carteira do pool, saldo, recebidos, enviados e transações.

Campos de topo observados:

- `page`
- `totalPages`
- `itemsOnPage`
- `address`
- `balance`
- `totalReceived`
- `totalSent`
- `unconfirmedBalance`
- `unconfirmedTxs`
- `txs`
- `transactions[]`

Campos úteis de `transactions[]`:

- `txid`
- `blockHeight`
- `blockTime`
- `confirmations`
- `value`
- `fees`

Uso no dashboard:

- Auditar atividade real da carteira do pool.
- Mostrar últimos blocos/rewards e maturidade.
- Ver se pool está recebendo rewards recentemente.

## Link de API quebrado

O menu do site tem link `API` apontando para:

```text
https://pearlhash.xyz/api-docs
```

Resultado observado: página `404 This page could not be found`.

Implica para dashboard:

- Não depender de documentação formal do Pearlhash por enquanto.
- Usar endpoints descobertos nos assets e validar periodicamente.
- Marcar integração Pearlhash como "API descoberta / não documentada".

## Dados operacionais

- Fee atual declarada visualmente: 0% até nova release.
- Payout mínimo: 1 PRL.
- Pool tem miner próprio, não Akoya nem AlphaPool.
- Site não mostrou tabela de hashrate por GPU.
- Site não deixou claro se há dev fee no miner.
- Site não deixou claro esquema exato de payout além de "epoch".

## Relação com GPUs

Dados confirmados no site:

- O site fala genericamente em "your GPUs".
- Não encontrei tabela pública de GPUs suportadas/hashrates.
- Não encontrei instrução clara de CUDA/driver mínimo.
- Não encontrei matriz de difficulty por GPU.

Para dashboard:

- Pearlhash não deve ser pool default para cálculo por GPU até termos hashrate real por GPU ou teste próprio.
- Pode entrar como opção manual ou referência de rede/pool.
- Se for usado para estimativa, aplicar hashrate conservador do nosso banco e fee 0%, mas marcar como "sem benchmark por GPU confirmado".

## Campos que um monitor futuro poderia publicar

Key proposta: `monitor:pearlhash`

Campos:

- `pool_hashrate_ths`
- `total_workers`
- `total_accounts`
- `network_hashrate_ths`
- `network_difficulty`
- `avg_block_time_s`
- `best_block_height`
- `pool_wallet_balance_prl`
- `pool_total_received_prl`
- `pool_total_sent_prl`
- `recent_rewards[]`
- `fee_percent`
- `min_payout_prl`
- `api_docs_available`

## Riscos e incertezas

- API docs visível no menu retorna 404.
- Fee "0%" pode mudar com a "new release".
- Miner próprio pode ter performance diferente de Akoya/AlphaPool.
- Sem tabela oficial de hashrate por GPU, não usar como base automática para alugar GPU.
- Endpoints de mineração são IPs diretos; isso pode mudar.

## Regras para dashboard

- Não escolher Pearlhash automaticamente para GPU sem benchmark próprio.
- Se mostrar Pearlhash, exibir como "pool alternativo / pesquisa".
- Usar Pearlhash como fonte secundária de rede e atividade de pool.
- Revalidar fee antes de calcular lucro com Pearlhash.
