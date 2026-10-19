# 🐚 PEARL (PRL) MINING — GUIA COMPLETO OPERACIONAL
> Última atualização: 28 mai 2026 | Mantido por operação ativa

---

## 📋 ÍNDICE
1. [O que é Pearl e como funciona](#1-o-que-é-pearl-e-como-funciona)
2. [Dados de rede — como ler e atualizar](#2-dados-de-rede)
3. [Fórmulas de cálculo](#3-fórmulas-de-cálculo)
4. [Hashrates reais por GPU](#4-hashrates-reais-por-gpu)
5. [Pools disponíveis](#5-pools-disponíveis)
6. [Plataformas de aluguel](#6-plataformas-de-aluguel)
7. [Clore.ai — guia completo](#7-cloreaі--guia-completo)
8. [TensorDock — guia completo](#8-tensordock--guia-completo)
9. [RunPod — guia completo](#9-runpod--guia-completo)
10. [Vast.ai — guia completo](#10-vastai--guia-completo)
11. [Comandos Docker por pool](#11-comandos-docker-por-pool)
12. [Análise de lucratividade por GPU](#12-análise-de-lucratividade-por-gpu)
13. [GPUs que NÃO funcionam](#13-gpus-que-não-funcionam)
14. [Onde vender PRL](#14-onde-vender-prl)
15. [Carteiras e workers](#15-carteiras-e-workers)
16. [Checklist diário](#16-checklist-diário)
17. [Histórico de operação](#17-histórico-de-operação)

---

## 1. O QUE É PEARL E COMO FUNCIONA

Pearl usa **Proof-of-Useful-Work (PoUW)** — ao invés de SHA-256, as GPUs executam inferência LLM (Large Language Model). O algoritmo chama-se **TMAD (Tensor Matrix Algorithm Division)**.

- **Pools customizados** (Akoya, AlphaPool) criaram kernels próprios que funcionam em GPUs consumer (RTX 30/40/50xx)
- O **miner oficial** da Pearl Research Labs exige H100/H200 (Hopper SM90)
- **Akoya e AlphaPool** suportam desde RTX 3060 até H200, incluindo Blackwell

### Arquitetura do miner oficial (NÃO usamos):
```
pearld (nó completo) → vLLM server → pearl-gateway (minera)
```

### O que usamos:
```
Docker container (Akoya ou AlphaPool) → conecta direto ao pool → minera
```

---

## 2. DADOS DE REDE

### Onde buscar dados atualizados:
| Site | O que mostra |
|------|-------------|
| lordofpearls.xyz | Network hashrate, blocos/dia, tempo médio, top miners |
| lordofpearls.xyz/pools | Comparativo de todos os pools |
| akoyapool.com | Dashboard Akoya, hashrate por worker |
| pearl.alphapool.tech | Dashboard AlphaPool, hashrate por worker |
| pearl-otc.com | Preço de mercado PRL/USDC |

### Evolução da rede (histórico):
| Data | Hashrate | Blocos/dia | Recompensa/bloco |
|------|----------|------------|-----------------|
| Mai/2026 início | ~517 PH/s | ~19 (Akoya) | 2.845 PRL |
| Mai/2026 meio | 7,165 EH/s | 337 | 2.845 PRL |
| Mai/2026 fim | 13,59 EH/s | 729 | 2.845 PRL |
| 28 Mai/2026 | **20,94 EH/s** | **826** | **2.686 PRL** |

> ⚠️ A rede cresce rapidamente. Sempre recalcule com dados do dia.

### Como ler os dados:
```
Network hashrate: 20,94 EH/s = 20.940.000 TH/s
Blocos/dia: ~826 (calculado por: 86400s / avg_block_time)
Recompensa: 2.686 PRL/bloco (cai com halvings)
```

---

## 3. FÓRMULAS DE CÁLCULO

### Fórmula principal:
```
PRL/dia = (seu_hash_TH / network_hash_TH) × blocos_dia × recompensa_bloco × (1 - taxa_pool)
```

### Receita em USD:
```
USD/dia = PRL/dia × preço_PRL
```

### Receita por TH (fórmula rápida):
```
$/TH/dia = (blocos_dia × recompensa × (1 - taxa) × preço_PRL) / network_hash_TH
```

### Exemplos calculados (28 Mai 2026):
```
Rede: 20.940.000 TH/s | 826 blocos/dia | 2.686 PRL | Taxa Akoya 5% | PRL $1.14

$/TH/dia = (826 × 2.686 × 0.95 × 1.14) / 20.940.000
         = (826 × 2.686 = 2.218.636 × 0.95 = 2.107.704 × 1.14 = 2.402.782) / 20.940.000
         = $0.1147/TH/dia

Com AlphaPool (taxa 6%):
$/TH/dia = (826 × 2.686 × 0.94 × 1.14) / 20.940.000
         = $0.1134/TH/dia
```

### Tabela de receita por TH em diferentes cenários:
| PRL Price | Rede 13.59 EH/s | Rede 20.94 EH/s | Rede 30 EH/s |
|-----------|-----------------|-----------------|--------------|
| $0.44 | $0.0638/TH/dia | $0.0414/TH/dia | $0.0289/TH/dia |
| $1.00 | $0.1451/TH/dia | $0.0941/TH/dia | $0.0657/TH/dia |
| $1.14 | $0.1654/TH/dia | $0.1147/TH/dia | $0.0749/TH/dia |
| $1.50 | $0.2177/TH/dia | $0.1411/TH/dia | $0.0986/TH/dia |

> Todos os valores com taxa Akoya 5%, arredondados.

---

## 4. HASHRATES REAIS POR GPU

### ✅ Confirmados por dashboard oficial (Akoya ou AlphaPool):

| GPU | TH/s | Kernel | Fonte | Tier Difficulty |
|-----|------|--------|-------|-----------------|
| RTX 3060 Ti | 40-50 TH/s | AlphaPool | Medido | 131.072 |
| RTX 3070 | 50-60 TH/s | AlphaPool | Medido | 131.072 |
| RTX 3080 | ~85 TH/s | Akoya/Alpha | Medido | 262.144 |
| RTX 3090 | 90 TH/s | AlphaPool | Medido | 262.144 |
| RTX 4090 | **195 TH/s** (Akoya) / 150-160 (Alpha) | Akoya | **Oficial** | 524.288 |
| RTX 5070 Ti | 110-130 TH/s | AlphaPool | Medido | ~524.288 |
| RTX 5080 | 165-170 TH/s | AlphaPool | Medido | 524.288 |
| RTX 5090 | **300-320 TH/s** (Alpha) / 250 (Akoya) | AlphaPool | **Oficial** | 1.048.576 |
| H100 SXM/PCIe | **594-615 TH/s** | Akoya | **Confirmado logs** | 1.048.576 |
| H200 | ~635 TH/s | Akoya/Alpha | Estimado | 1.048.576 |
| RTX A4000 | ~70-75 TH/s | Akoya | Estimado (tier 262k) | 262.144 |
| CMP 90HX | **~0.035 TH/s** | Nenhum | **Confirmado — INÚTIL** | N/A |

### ⚠️ Notas críticas:
- **RTX 4090**: use Akoya kernel (195 TH/s) — melhor que AlphaPool (150-160)
- **RTX 5090**: use AlphaPool kernel (300-320) — melhor que Akoya (250)
- **CMP 90HX**: PCIe 1.0 x4 = 0,25 GB/s banda → gargalo total → não minera Pearl
- **RTX A4000**: Ampere, suportado pelo Akoya. Hash estimado, não confirmado em logs

### Regra de ouro para escolher kernel:
```
RTX 40xx e abaixo → Akoya (kernel mais eficiente)
RTX 50xx → AlphaPool (kernel Blackwell otimizado)
H100/H200 → Akoya (confirmado 594 TH/s nos logs)
```

---

## 5. POOLS DISPONÍVEIS

| Pool | Taxa | Scheme | Min Payout | Hashrate (Mai/26) | Blocos 24h | Suporte GPU |
|------|------|--------|------------|-------------------|------------|-------------|
| **PearlHash** | 3% | — | 1 PRL | 4.85 EH/s | 182 | RTX 30/40/50, H100 |
| **AlphaMine** | 5% + 1% dev | PPLNS | 1 PRL | 3.64 EH/s | 137 | Volta→Blackwell + CMP 70/90HX |
| **Akoya Pool** | 5% | PPLNS | **10 PRL** | 1.18 EH/s | 31 | RTX 3060→H200 |
| MinePRL | 4.4% | PPLNS | Sem mínimo | 14 PH/s | 0 | H100/H200 apenas |

### Comparativo para escolha:
```
Maior pool / menores variações de payout: PearlHash (3% taxa)
Melhor para CMP/GPUs antigas: AlphaMine
Melhor kernel consumer: Akoya
Menor payout mínimo: AlphaMine (1 PRL) ou MinePRL (sem mínimo)
```

### ⚠️ Akoya tem mínimo de 10 PRL para payout
Com 1× RTX 3080 (~$9,75 receita/dia a $1.14), leva ~2-3 dias para atingir o mínimo.

---

## 6. PLATAFORMAS DE ALUGUEL

### Comparativo geral:
| Plataforma | Tipo | Billing | Docker | CUDA Controle | Preço relativo |
|------------|------|---------|--------|---------------|----------------|
| **Clore.ai** | P2P marketplace | Por dia | Sim (imagem direta) | Depende do host | ⭐ Mais barato |
| **TensorDock** | VPS dedicada | Por segundo | Manual (SSH) | Controle total | ⭐⭐ Barato |
| **RunPod** | Container cloud | Por hora | Sim (template) | Limitado | ⭐⭐⭐ Médio |
| **Vast.ai** | P2P marketplace | Por hora | Sim (docker options) | Depende do host | ⭐⭐ Barato |

---

## 7. CLORE.AI — GUIA COMPLETO

### URL: clore.ai

### Como alugar:
1. Marketplace → filtrar por GPU desejada
2. Selecionar imagem:
   - **Akoya**: `registry.akoyapool.com/akoya-miner:latest`
   - **AlphaPool**: `alphaminetech/pearl-miner`
3. Configurar variáveis de ambiente
4. Confirmar e pagar

### Variáveis para Akoya (RTX 30/40xx, H100):
```
AKOYA_POOL_WALLET = prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc
AKOYA_POOL_WORKER = [nome do worker, ex: clore01]
```

### Variáveis para AlphaPool (RTX 50xx, ou fallback):
```
PEARL_ADDRESS    = prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc
PEARL_WORKER     = [nome do worker]
PEARL_POOL_HOST  = eu1.alphapool.tech
PEARL_POOL_PORT  = 5566
PEARL_DIFFICULTY = 1048576   (RTX 5090/H100)
                   524288    (RTX 4090/5080)
                   262144    (RTX 3080/3090/A4000)
                   131072    (RTX 3060/3070)
```

### Filtros recomendados no Clore.ai:
```
CUDA version: 12.9+
PCIe version: 2.0+ (evitar PCIe 1.0 x1 para placas acima de RTX 3080)
Min reliability: 90%+
```

### Servidores históricos operados:
| Server | GPU | Qtd | Custo/dia | Status | Worker |
|--------|-----|-----|-----------|--------|--------|
| #17163 Belarus | RTX 3080 OC | 7× | $17,85 | ✅ Principal | h0st1 |
| #94782 Russia | CMP 90HX | 6× | $6,27 | ❌ Cancelado | cmp03 |
| #102084 Alemanha | CMP 90HX | 6× | $6,27 | ❌ Cancelado | cmp02 |
| #103579 Alemanha | CMP 90HX | 6× | $6,27 | ❌ Cancelado | cmp01 |
| #101531 China | RTX 3080 20GB | 1× | $3,15 | Testado | clore02 |
| #79417 Russia | RTX A4000 | 2× | $8,40 | Recomendado | — |
| #104315 Japan | RTX 3090 | 4× | $21,00 | Recomendado | — |

### ⚠️ PCIe e bandwidth — regra crítica:
```
Pearl TMAD transfere matrizes grandes entre CPU RAM e GPU VRAM via PCIe.

PCIe 1.0 x4  = 0.25 GB/s  → GARGALO TOTAL (CMP 90HX = inútil)
PCIe 2.0 x1  = 0.5 GB/s   → Limitante mas funciona (RTX 3080 no Clore)
PCIe 3.0 x8  = 8 GB/s     → Bom
PCIe 4.0 x16 = 32 GB/s    → Ótimo
PCIe 5.0 x16 = 64 GB/s    → Máximo

Hashrate pode ser reduzido em setups com PCIe lento.
```

---

## 8. TENSORDOCK — GUIA COMPLETO

### URL: dashboard.tensordock.com

### GPUs disponíveis e preços (Mai/2026):
| GPU | VRAM | Preço/hr | Disponibilidade | Melhor para |
|-----|------|----------|-----------------|-------------|
| RTX A4000 | 16GB | $0.080 | 5 units | ✅ Melhor custo-benefício |
| RTX 3090 | 24GB | $0.200 | 6 units | ✅ Bom |
| Tesla V100 16GB | 16GB | $0.190 | 7 units | ⚠️ Hash baixo |
| Tesla V100 32GB | 32GB | $0.290 | 16 units | ⚠️ Testado |
| RTX 4090 | 24GB | $0.377 | 4 units | ✅ Ótimo hash |
| RTX 5000 ADA | 32GB | $0.550 | 1 unit | ⚠️ Desconhecido |
| RTX 5090 | 32GB | $0.580 | 8 units | ✅ Alto hash |
| A100 SXM4 | 80GB | $0.850 | 2 units | ❌ Prejuízo |

### Como fazer deploy no TensorDock:
```
1. tensordock.com/deploy → selecionar GPU
2. GPU: quantidade desejada
3. CPU: 2 cores por GPU mínimo (4 para 1 GPU, 8 para 4+ GPUs)
4. RAM: 4 GB por GPU mínimo (16 GB para 1-2 GPU)
5. Storage: 100 GB
6. OS: Ubuntu 22.04 LTS + NVIDIA 570 (Open)  ← OBRIGATÓRIO para RTX 50xx
      Ubuntu 24 ML Everything                ← Para RTX 40xx e abaixo
7. Dedicated IP: DESATIVAR (custo extra desnecessário)
8. SSH Key: selecionar chave salva
```

### Após deploy — setup completo (SSH):
```bash
# 1. Verificar CUDA (deve ser 12.9+)
nvidia-smi

# 2. Instalar NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker

# 3. Aguardar apt (pode levar 5-10 min na 1ª vez)
while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do sleep 5; done

# 4. Instalar Docker (se não tiver)
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER

# 5. Rodar miner (Akoya - para RTX 40xx e abaixo)
sudo docker run -d --gpus all --restart=unless-stopped --name akoya-miner \
  -e AKOYA_POOL_WALLET=prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc \
  -e AKOYA_POOL_WORKER=tensor01 \
  registry.akoyapool.com/akoya-miner:latest

# Para RTX 5090 — AlphaPool
sudo docker run -d --gpus all --restart=unless-stopped --name alpha-miner \
  -e PEARL_ADDRESS=prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc \
  -e PEARL_WORKER=tensor01 \
  -e PEARL_POOL_HOST=eu1.alphapool.tech \
  -e PEARL_POOL_PORT=5566 \
  -e PEARL_DIFFICULTY=1048576 \
  alphaminetech/pearl-miner

# 6. Ver logs
sudo docker logs akoya-miner -f

# 7. Confirmar hashrate (deve aparecer em ~2 min)
# Buscar: tmads/s=XXX TH/s e gpuUtilPct=99-100
```

### SSH Key (Windows):
```powershell
# Chave existente (usar esta):
cat ~/.ssh/id_ed25519.pub
# ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMArP82LpPfrSLUjNyYIHxYba19oHNHuEGMF3AxU5a3d qquantebuild@gmail.com

# Conectar:
ssh -p PORTA user@IP -i ~/.ssh/id_ed25519

# Se der erro de host key:
ssh-keygen -R "[IP]:PORTA"
```

### Problemas comuns TensorDock:
| Problema | Causa | Solução |
|----------|-------|---------|
| `CUDA 12.7` nos logs | Driver antigo | Usar Ubuntu 24 ML Everything ou Ubuntu 22.04 + NVIDIA 570 |
| `cuda>=12.9 required` | Mesmo acima | Atualizar driver ou recriar VM |
| `dpkg lock` | apt rodando | `while sudo fuser /var/lib/dpkg/lock-frontend; do sleep 5; done` |
| `docker not found` | Docker não instalado | `curl -fsSL https://get.docker.com \| sudo bash` |
| `no GPU vendor found` | Container toolkit não instalado | Instalar nvidia-container-toolkit |

---

## 9. RUNPOD — GUIA COMPLETO

### URL: runpod.io

### GPUs disponíveis e preços (Secure Cloud, Mai/2026):
| GPU | VRAM | Preço/hr | Disponibilidade | Lucro/dia (PRL $1.14) |
|-----|------|----------|-----------------|----------------------|
| H100 SXM | 80GB | $3.29 | HIGH (8 max) | -$10 a +$15 (depende rede) |
| H100 NVL | 94GB | $3.19 | Low (5 max) | Similar H100 SXM |
| H200 SXM | 141GB | $4.39 | Medium | ❌ Prejuízo |
| RTX 5090 | 32GB | $0.99 | Low (1 max) | +$11-25 |
| RTX A5000 | 24GB | $0.27 | Low (raramente) | +$5-8 |
| A100 SXM | 80GB | $1.49 | Low | ❌ Prejuízo (hash baixo) |
| B200 | 180GB | $5.89 | Low | ❌ Muito caro |

### Como criar Pod no RunPod:
```
1. runpod.io → Pods → Deploy
2. Secure Cloud (mais estável)
3. Selecionar GPU
4. Pod Template: Custom (digitar imagem)
5. Container Image: registry.akoyapool.com/akoya-miner:latest
6. Container Disk: 20 GB
7. Volume Disk: 0 (não precisa)
8. Environment Variables:
   AKOYA_POOL_WALLET = prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc
   AKOYA_POOL_WORKER = runpod01
9. HTTP Port: 8080 (obrigatório pelo sistema, mas não usado)
10. Deploy
```

### H100 SXM — configuração confirmada (logs reais):
```
Container Image: registry.akoyapool.com/akoya-miner:latest
AKOYA_POOL_WALLET: prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc
AKOYA_POOL_WORKER: runpod01

Resultado real confirmado:
tmads/s=594.63 TH/s
gpuUtilPct=100
gpuPowerW=689W
shares accepted=True
```

### Verificar se está minerando:
```bash
# Via Web Terminal (no dashboard RunPod → Connect → Web Terminal)
env | grep AKOYA   # confirma carteira e worker
```

### Problema CUDA no RunPod:
```
Erro: cuda>=12.9, please update your driver
Solução: Ao criar o Pod, filtrar por CUDA Version mínima 12.9
  → Additional filters → Min Cuda Version → 12.9
```

---

## 10. VAST.AI — GUIA COMPLETO

### URL: vast.ai

### Como configurar instância para mineração:
```
1. cloud.vast.ai → Search (ou usar template salvo)
2. Configurar filtros:
   - Min CUDA Version: 12.9
   - PCIe Bandwidth: mínimo 10 GB/s
   - On-Demand (não interruptível)
3. Template/Image: registry.akoyapool.com/akoya-miner:latest
4. Container Size: 16 GB
5. Docker Options (campo extra):
   -e AKOYA_POOL_WALLET=prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc -e AKOYA_POOL_WORKER=vast01
6. Deploy
```

### Preços encontrados no marketplace (Mai/2026):
| GPU | País | $/hr | Custo/dia | Hash | Lucro/dia |
|-----|------|------|-----------|------|-----------|
| H100 NVL | 🇺🇸 Colorado | $2.003 | $48 | 615 TH/s | +$22 |
| RTX 4090 | 🇷🇴 Romênia | $1.122 | $26,93 | 195 TH/s | +$3,69 |
| RTX 3090 | 🇨🇦 Quebec | $0.341 | $8,18 | 90 TH/s | +$5,95 |
| RTX A6000 | 🇨🇦 Quebec | $0.432 | $10,37 | ~90 TH/s | +$3,76 |
| RTX 3090 | 🇧🇷 (mínimo) | $0.12 | $2,88 | 90 TH/s | +$11 |
| RTX 3080 | (mínimo) | $0.07 | $1,68 | 85 TH/s | +$11,69 |

> ⚠️ Preços mínimos ($0.07, $0.12) são interruptíveis. Para mineração use On-Demand.

---

## 11. COMANDOS DOCKER POR POOL

### Akoya Pool (melhor para RTX 30/40xx e H100):
```bash
# Deploy básico
sudo docker run -d \
  --gpus all \
  --restart=unless-stopped \
  --name akoya-miner \
  -e AKOYA_POOL_WALLET=prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc \
  -e AKOYA_POOL_WORKER=NOME_DO_WORKER \
  registry.akoyapool.com/akoya-miner:latest

# Ver logs
sudo docker logs akoya-miner -f

# Ver logs últimas 100 linhas
sudo docker logs akoya-miner --tail 100

# Reiniciar
sudo docker restart akoya-miner

# Parar
sudo docker stop akoya-miner

# Remover (para recriar)
sudo docker rm -f akoya-miner

# Ver métricas ao vivo
sudo docker logs akoya-miner 2>&1 | grep -i "tmads\|gpuUtil\|accepted\|share"
```

### AlphaPool / AlphaMine (melhor para RTX 50xx):
```bash
# Deploy RTX 5090 / H100
sudo docker run -d \
  --gpus all \
  --restart=unless-stopped \
  --name alpha-miner \
  -e PEARL_ADDRESS=prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc \
  -e PEARL_WORKER=NOME_DO_WORKER \
  -e PEARL_POOL_HOST=eu1.alphapool.tech \
  -e PEARL_POOL_PORT=5566 \
  -e PEARL_DIFFICULTY=1048576 \
  alphaminetech/pearl-miner

# Ver logs
sudo docker logs alpha-miner -f
```

### Tabela de difficulty por GPU:
| GPU | Difficulty |
|-----|------------|
| GTX 1080 Ti / V100 / CMP 100-210 | 4.096 |
| RTX 2070 / 2080 | 16.384 |
| RTX 3060 Ti / 3070 | 131.072 |
| RTX 3080 / 3090 / CMP 70HX/90HX | 262.144 |
| A100 / datacenter Ampere | 131.072 |
| RTX 4070 / 4080 | 262.144 |
| RTX 4090 / 5080 | 524.288 |
| RTX 5090 / H100 / H200 / B100 | 1.048.576 |

### Verificação rápida de saúde do miner:
```bash
# Linha saudável no Akoya (aparece a cada ~5 segundos):
# tmads/s=195.xx TH/s gpuUtilPct=99-100 accepted=True

# Linha saudável no AlphaPool:
# connected host=eu1.alphapool.tech
# share submitted job=...
# workspace_ready

# Sinal de problema:
# CUDA driver call failed (cuInit): 804  → driver antigo
# unsupported GPU                        → GPU não suportada
# connection_lost (reconecta sozinho)    → normal, não é problema
```

---

## 12. ANÁLISE DE LUCRATIVIDADE POR GPU

### Método de avaliação (sempre atualizar com dados do dia):
```
1. Pegar network_hash de lordofpearls.xyz/stats
2. Calcular: $/TH/dia = (blocos_dia × reward × (1-fee) × prl_price) / network_hash_TH
3. Multiplicar pelo TH/s da GPU
4. Subtrair custo de aluguel
```

### Tabela de lucratividade — PRL $1.14, Rede 20.94 EH/s (28/mai/2026):
| GPU | TH/s | Receita/dia | Custo break-even | Plataformas rentáveis |
|-----|------|-------------|-----------------|----------------------|
| RTX 3080 | 85 | $9,75 | < $9,75/dia | Clore <$9/dia |
| RTX 3090 | 90 | $10,32 | < $10,32/dia | Clore #104315, TensorDock $0.20 |
| RTX 4090 | 195 | $22,37 | < $22,37/dia | TensorDock $0.38, RunPod $0.34 |
| RTX 5090 | 310 | $35,56 | < $35,56/dia | TensorDock $0.58, RunPod $0.99 |
| RTX A4000 | ~72 | $8,26 | < $8,26/dia | Clore $8.40 ≈ break-even |
| H100 | 594 | $68,13 | < $68,13/dia | RunPod $3.29 = -$10 (prejuízo!) |

> ⚠️ H100 no RunPod ($3.29/hr = $78.96/dia) dá PREJUÍZO com rede em 20.94 EH/s e PRL $1.14!
> H100 só é lucrativo se: PRL > $1.30 OU rede < 15 EH/s OU custo < $2.84/hr

### Fórmula do break-even para H100:
```
Custo máximo por hora = (594 TH/s × $/TH/dia) / 24h
= (594 × 0.1147) / 24
= $68.13 / 24
= $2.84/hr

Conclusão: qualquer H100 acima de $2.84/hr dá prejuízo hoje.
```

---

## 13. GPUs QUE NÃO FUNCIONAM

### ❌ CMP 90HX — CONFIRMADO INÚTIL para Pearl:
```
Problema: PCIe 1.0 x4 = 0.25 GB/s de bandwidth
Resultado: ~0.035 TH/s por GPU (confirmado no dashboard AlphaPool)
18 × CMP 90HX = 4 TH/s total (menos que 1/20 de uma RTX 3080)
Custo para 3 servidores: $18.81/dia
Receita: $0.63/dia
Prejuízo: -$18.18/dia

Lição: PCIe bandwidth é crítico para Pearl. Nunca alugar PCIe 1.0 x4.
```

### ❌ GPUs sem tensor cores (Pascal e anteriores):
- GTX 10xx série — sem tensor cores → não suportado
- GTX 745, GTX 980, etc — não funciona

### ❌ GPUs Turing (RTX 20xx) — AINDA NÃO SUPORTADAS:
```
AlphaPool oficial: "Turing (RTX 20-series, T4, CMP 30/40/50HX) — kernels pending"
Akoya: não suporta explicitamente RTX 20xx
```

### ⚠️ A100 — baixo hash para o preço:
```
A100 é datacenter Ampere, difficulty tier = 131.072 (mesmo que RTX 3070)
Hash estimado: ~50 TH/s (mesma tier que RTX 3070 de 50-60 TH/s)
A $1.49/hr (RunPod) = $35.76/dia → receita $5.74/dia → PREJUÍZO ENORME
```

---

## 14. ONDE VENDER PRL

### Comparativo de plataformas OTC (Mai/2026):
| Plataforma | Taxa | KYC | Liquidação | Min | Bot/Link |
|------------|------|-----|------------|-----|---------|
| **Lord of Pearls OTC** | **1.8%** | ❌ Não | Instantânea | — | t.me/LOPOTCBOT |
| BlackPearlMarket | — | ❌ Não | Rápida (ledger) | — | t.me/BlackPearlMkt |
| Pearl OTC | 2% | ❌ Não | ~20 min (on-chain) | — | — |

### Recomendação: Lord of Pearls OTC
```
- Taxa mais baixa (1.8%)
- Liquidação instantânea off-chain
- 2FA nas retiradas
- Bid atual: $1.00-1.02 (verificar antes de vender)
- Máximo por trade: 10.000 PRL (evitar slippage)
- Para grandes volumes: dividir em múltiplos trades
```

### Evolução do preço (histórico observado):
| Data | Preço PRL |
|------|-----------|
| Mai/2026 início | ~$0.30-0.44 |
| Mai/2026 pico intraday | $1.40 |
| 25 Mai/2026 | $0.44-0.45 |
| 28 Mai/2026 manhã | $1.085 |
| 28 Mai/2026 tarde | $1.14-1.30 |

> ⚠️ Alta volatilidade. Vender regularmente (não acumular demais).

---

## 15. CARTEIRAS E WORKERS

### Carteiras ativas:
| Carteira | Uso atual | Pool |
|----------|-----------|------|
| `prl1putmd804p9xwjt0lceygj883e55cywul9jhsc8m0wu7926uc8j9qqntkksr` | Antiga (RTX 3080 #17163) | Akoya |
| `prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc` | **Principal atual** | Akoya + AlphaPool |

> ✅ Usar sempre: `prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc`

### Workers ativos / nomenclatura sugerida:
```
h0st1    → Clore #17163 (7× RTX 3080)
cmp01-03 → Cancelados (CMP 90HX)
tensor02 → TensorDock Tallinn
runpod01 → RunPod H100 SXM
clore05+ → Próximos servidores Clore
vast01   → Vast.ai
```

### Verificar saldo e hashrate:
```
Akoya: akoyapool.com → cole a carteira principal
AlphaPool: pearl.alphapool.tech → cole a carteira principal
```

---

## 16. CHECKLIST DIÁRIO

### Manhã (verificar):
- [ ] Preço PRL em lordofpearls.xyz
- [ ] Network hashrate atual
- [ ] Calcular $/TH/dia atualizado
- [ ] Dashboard Akoya — todos workers com hashrate
- [ ] Clore.ai My Orders — verificar servidores ativos
- [ ] RunPod Pods — verificar pods ativos

### Análise de rentabilidade:
```bash
# Fórmula rápida no terminal (substitua os valores):
NETWORK_HASH=20940000   # TH/s
BLOCKS_DAY=826
REWARD=2686
POOL_FEE=0.05
PRL_PRICE=1.14

RATE=$(python3 -c "print(f'${BLOCKS_DAY*REWARD*(1-POOL_FEE)*PRL_PRICE/NETWORK_HASH:.4f}/TH/dia')")
echo "Receita atual: $RATE"
```

### Se PRL cair abaixo de $0.80:
- [ ] Cancelar servidores com custo > $15/dia
- [ ] Manter apenas servidores com custo < $8/dia
- [ ] Considerar vender PRL acumulado

### Se PRL subir acima de $1.50:
- [ ] Alugar máximo de RTX 3090 e RTX 4090 baratos
- [ ] Verificar H100 no RunPod (pode virar lucrativo)
- [ ] Vender PRL acumulado gradualmente

---

## 17. HISTÓRICO DE OPERAÇÃO

### Timeline de descobertas:
```
Sessão 1: Setup inicial, descoberta do Akoya Pool, primeira mineração RTX 3080
Sessão 2: Erro com CMP 90HX no Akoya (suporte inexistente)
Sessão 3: Descoberta que CMP 90HX funciona no AlphaPool mas hash = 0.035 TH/s
          Confirmação que CMP é inútil para Pearl (PCIe 1.0 x4)
Sessão 4: Rede cresce de 7 EH/s para 13.59 EH/s
          PRL sobe de $0.44 para $1.085
          Hashrates reais obtidos do AlphaPool Get Started
Sessão 5: Deploy H100 SXM no RunPod → 594 TH/s confirmado nos logs
          Rede atinge 20.94 EH/s — H100 vira prejudicial a $3.29/hr
          PRL atinge $1.14-1.30 no OTC
```

### Erros cometidos e lições:
| Erro | Lição |
|------|-------|
| Alugar CMP 90HX sem testar | Sempre testar 1 unidade por 1 dia primeiro |
| Usar imagem Akoya para CMP (não suportado) | Verificar suporte na documentação do pool |
| TensorDock com Ubuntu 24.04 LTS base | Usar Ubuntu 24 ML Everything ou +NVIDIA 570 |
| 5× GPUs com 4 CPU cores | Mínimo 2 cores por GPU, 4 cores por 2 GPUs |
| H100 sem calcular break-even | Sempre calcular custo máximo por hora |

---

## APÊNDICE — LINKS ÚTEIS

| Recurso | URL |
|---------|-----|
| Dados de rede Pearl | lordofpearls.xyz |
| Dashboard Akoya | akoyapool.com |
| Dashboard AlphaPool | pearl.alphapool.tech |
| Pools comparativo | lordofpearls.xyz/pools |
| OTC Trading | t.me/LOPOTCBOT |
| Clore.ai marketplace | clore.ai |
| TensorDock deploy | dashboard.tensordock.com/deploy |
| RunPod | runpod.io |
| Vast.ai | cloud.vast.ai |

---

*Guia baseado em operação real — Maio 2026*
*Atualizar os dados de rede e preço PRL diariamente antes de qualquer decisão*
