# Monitor GPU — Status do Projeto

## Visão Geral

Sistema de monitoramento de lucratividade para mineração Pearl (PRL).
Cada monitor roda em container Docker isolado, publica dados no Redis a cada 5s.
O dashboard (ainda por fazer) vai consumir todos os Redis keys e exibir uma tabela de decisão.

---

## Arquitetura

```
docker-compose
├── gpu-redis            ← Redis 7 (message bus central)
├── monitor-pearl        ← Rede Pearl (preço PRL, hashrate, blocos/dia)
├── monitor-akoya        ← Sua operação no Akoya Pool (workers, hashrate, saldo)
├── monitor-clore        ← Clore.ai marketplace
├── monitor-vastai       ← Vast.ai marketplace
├── monitor-runpod       ← (pendente) RunPod marketplace
├── monitor-tensordock   ← (pendente) TensorDock marketplace
└── dashboard            ← (pendente) FastAPI + WebSocket + HTML
```

Cada monitor herda `shared/base_monitor.py`:
- Polling loop com intervalo preciso (poll_interval - elapsed)
- Publica JSON no Redis key com TTL de 30s (expira sozinho se o monitor morrer)
- Também faz `PUBLISH` no canal Redis para o dashboard via WebSocket
- Exponential backoff em erros: 1s → 2s → 4s → ... → 60s máx

A pasta `shared/` é montada como volume read-only em todos os containers (`/app/shared`).

---

## Redis Keys

| Key               | Fonte           | TTL |
|-------------------|-----------------|-----|
| `monitor:pearl`   | lordofpearls.xyz | 30s |
| `monitor:akoya`   | akoyapool.com    | 30s |
| `monitor:clore`   | clore.ai         | 30s |
| `monitor:vastai`  | cloud.vast.ai    | 30s |
| `monitor:runpod`  | api.runpod.io    | 30s |
| `monitor:tensordock` | marketplace.tensordock.com | 30s |

---

## O que está pronto e funcionando

### ✅ shared/base_monitor.py
Classe base abstrata. Todos os monitors herdam isso.
Campos de config: `redis_host`, `redis_port`, `poll_interval`, `redis_key`.

### ✅ shared/gpu_hashrates.py
Banco de dados de GPUs suportadas pela Pearl (TMAD algorithm):
- RTX 30xx: 3060Ti (45 TH/s), 3070 (55), 3080 (85), 3090 (90)
- RTX 40xx: 4070 (100), 4070Ti (125), 4080 (155), 4090 (195 — kernel Akoya)
- RTX 50xx: 5070Ti (120), 5080 (167), 5090 (310 — kernel AlphaPool)
- Workstation: A4000 (72), A5000 (80), A6000 (90)
- Datacenter: H100 SXM (594 — confirmado nos logs), H100 PCIe (594), H100 NVL (610), H200 (635)
- Low-value: A100 SXM/PCIe (~50 TH/s, caro demais)
- Blacklist: CMP 90HX/70HX (PCIe 1.0 = inútil), RTX 20xx (Turing sem kernel)

Regra de kernel: RTX 40xx e abaixo → Akoya. RTX 50xx → AlphaPool. H100/H200 → Akoya.

Funções: `normalize_gpu_name()`, `get_gpu()`, `is_supported()`.
`POOL_FEES`: pearlhash=3%, alphamine=6%, akoya=5%, mineprl=4.4%.

### ✅ Monitor Pearl — `monitor:pearl`
**API:** `GET https://lordofpearls.xyz/api/public` (pública, sem auth)
**Intervalo:** 5s
**Container:** `monitor-pearl` — Running ✅

Dados publicados:
- `network_hashrate_ths` / `network_hashrate_ehs`
- `avg_block_time_s`, `blocks_per_day`
- `reward_per_block` — do bloco mais recente confirmado
- `prl_price_usd`, `price_source`
- `difficulty`, `best_block_height`
- `mempool_size`, `peer_count`
- `supply`, `supply_pct`, `supply_max`
- `usd_per_th_per_day` — dict por pool (pearlhash/alphamine/akoya/mineprl)
- `usd_per_th_per_hour` — idem
- `leaderboard_24h_total_blocks`, `leaderboard_24h_unique_miners`

Fórmula de receita:
```
$/TH/dia = (blocos_por_dia × recompensa × (1 - taxa) × preço_prl) / hashrate_rede_TH
```

### ✅ Monitor Akoya Pool — `monitor:akoya`
**API:** `GET https://akoyapool.com/api/v1/miners/{wallet}` (pública, sem auth)
**Intervalo:** 5s
**Container:** `monitor-akoya` — Running ✅
**Wallet:** configurada via env var `AKOYA_WALLET`

Dados publicados:
- `is_online`, `worker_count`, `online_worker_count`
- `total_hashrate_ths`, `total_hashrate_formatted`
- `pending_balance_prl`, `total_paid_prl`
- `total_shares24h`, `accepted_shares24h`, `stale_shares24h`, `stale_rate24h_pct`
- `maturing_blocks`, `next_maturity_eta_s`
- `workers[]` — por worker:
  - `worker_name`, `gpu_card`, `gpu_card_normalized` (usando `normalize_gpu_name`)
  - `gpu_count`, `hashrate_ths`, `is_connected`
  - `shares1h`, `stale_shares1h`

Workers ativos no momento:
| Worker     | GPU                    | Hashrate    | Status      |
|------------|------------------------|-------------|-------------|
| runpod01   | H100 80GB (HBM3)       | 596.48 TH/s | Online ✅   |
| x4.3090    | RTX 3090               | 0 (offline) | Offline ❌  |
| clore02    | RTX 3080 ×18           | 0 (offline) | Offline ❌  |

---

## O que falta fazer

### ✅ Monitor 3 — Clore.ai
**API:** `https://clore.ai/webapi/marketplace/servers` (pública)
**Redis key:** `monitor:clore`
**Intervalo:** 5s
**Container:** `monitor-clore` — Running ✅

Dados publicados:
- `total_servers`, `available_count`, `supported_count`, `available_supported_count`
- `servers[]` — por servidor suportado:
  - `server_id`, `gpu_model_raw`, `gpu_model_normalized`, `gpu_count`, `gpu_vram_gb`
  - `price_usd_hr`, `price_usd_day`, `spot_price_usd_hr`, `price_btc_hr`, `price_clore_hr`
  - `rented`, `reliability`, `rating_avg`, `rating_cnt`, `country`
  - `net_up_mbps`, `net_down_mbps`, `cuda_version`, `ram_gb`, `disk_speed_mbps`, `cpu`, `mrl_min`

Observações:
- Filtra somente GPUs suportadas pela Pearl via `GPU_DATABASE`.
- Ignora GPUs laptop/mobile por baixa lucratividade.
- Parser defensivo contra campos numéricos `null` e formatos variáveis de `gpu_array`.

### ✅ Monitor 4 — Vast.ai
**API:** `POST https://console.vast.ai/api/v0/bundles/` (Search Offers)
**Redis key:** `monitor:vastai`
**Intervalo:** 5s
**Container:** `monitor-vastai` — Running ✅

Filtros da busca:
- `type=ondemand`
- `gpu_arch=nvidia`
- `rentable=true`, `rented=false`
- `cuda_max_good >= 12.9`
- `pcie_bw >= 8.0`

Filtro local adicional:
- PCIe lanes `gpu_lanes >= 8` quando o campo existe.

Dados publicados:
- `total_offers`, `available_count`, `supported_count`, `available_supported_count`, `usable_supported_count`
- `filters`, `unsupported_gpu_counts`
- `offers[]` — por oferta suportada:
  - `offer_id`, `bundle_id`, `host_id`, `machine_id`
  - `gpu_model_raw`, `gpu_model_normalized`, `gpu_count`, `gpu_vram_gb`
  - `price_usd_hr`, `price_usd_day`
  - `rentable`, `rented`, `is_bid`, `on_demand_available`, `meets_guidelines`
  - `cuda_max_good`, `pcie_lanes`, `pcie_bw_gbps`
  - `country`, `net_up_mbps`, `net_down_mbps`, `disk_space_gb`, `disk_bw_mbps`, `cpu`, `cpu_cores`, `ram_gb`, `reliability`

### ⬜ Monitor 5 — RunPod
**API:** GraphQL em `https://api.runpod.io/graphql` (pública para listagem)
**Redis key:** `monitor:runpod`
Query: `gpuTypes` com campos `id`, `displayName`, `memoryInGb`, `communityPrice`, `securePrice`.

### ⬜ Monitor 6 — TensorDock
**API:** `https://marketplace.tensordock.com/api/v0/client/deploy/hostnodes/` (pública)
**Redis key:** `monitor:tensordock`
Dados a coletar: GPU specs, preço/hr, disponibilidade por hostnode.

### ⬜ Dashboard
**Stack:** FastAPI + WebSocket + HTML/JS puro (sem framework)
**Porta:** 8080
**Container:** `dashboard`

Features planejadas:
- Tabela de lucratividade por GPU: preço aluguel vs receita esperada
- Semáforo verde/amarelo/vermelho por GPU/plataforma
- Seção "Minha Operação" com dados do Akoya (workers, saldo, hashrate)
- Auto-refresh via WebSocket (sem polling do browser)
- Dados: `preço/hr`, `preço/dia`, `lucro/hr`, `lucro/dia`, `qtd disponível`

---

## Estrutura de Arquivos

```
monitor-gpu/
├── docker-compose.yml
├── .env
├── STATUS.md                    ← este arquivo
├── shared/
│   ├── __init__.py
│   ├── base_monitor.py          ✅
│   └── gpu_hashrates.py         ✅
└── monitors/
    ├── pearl/
    │   ├── Dockerfile           ✅
    │   ├── requirements.txt     ✅
    │   └── monitor.py           ✅
    ├── akoya/
        ├── Dockerfile           ✅
        ├── requirements.txt     ✅
        └── monitor.py           ✅
    ├── clore/
        ├── Dockerfile           ✅
        ├── requirements.txt     ✅
        └── monitor.py           ✅
    └── vastai/
        ├── Dockerfile           ✅
        ├── requirements.txt     ✅
        └── monitor.py           ✅
```

---

## Progresso

| # | Componente        | Status      |
|---|-------------------|-------------|
| 1 | Estrutura base    | ✅ Pronto   |
| 2 | GPU hashrates DB  | ✅ Pronto   |
| 3 | Base monitor      | ✅ Pronto   |
| 4 | Monitor Pearl     | ✅ Running  |
| 5 | Monitor Akoya     | ✅ Running  |
| 6 | Monitor Clore.ai  | ✅ Running  |
| 7 | Monitor Vast.ai   | ✅ Running  |
| 8 | Monitor RunPod    | ⬜ Pendente |
| 9 | Monitor TensorDock| ⬜ Pendente |
| 10| Dashboard         | ⬜ Pendente |
