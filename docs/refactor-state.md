# Refactor State

Atualizado: 2026-05-29

## Estado Operacional Seguro

- Scout automatico pausado durante a modularizacao.
- Testes ativos do Scout observados em `0` antes desta etapa.
- Fila operacional do Scout observada em `0` antes desta etapa.
- GPUs/miners e monitores seguem rodando; as mudancas feitas ate aqui reiniciam apenas o servico `gpu-dashboard`.
- Config importante preservada: allowlist `H100 SXM`, teto Scout observado em `$2.40/h`, janela de teste `15 min`.

## Partes Concluidas

1. `dashboard/state_store.py`
   - Extraidos helpers genericos de JSON, Redis JSON e leitura bruta dos monitores.
   - `dashboard/app.py` manteve wrappers com os nomes antigos.

2. `scripts/check_dashboard_contracts.py`
   - Smoke test local para `/api/state`, `/api/scout/state` e `/api/results/state`.
   - Ajuda a confirmar que o dashboard continua servindo os contratos principais depois de cada etapa.

3. `dashboard/vast_service.py`
   - Extraidos helpers Vast: templates, wallets, payloads, aceitar ask, destruir instancia, trocar pool e reciclar instancia.
   - `dashboard/app.py` manteve wrappers com os nomes antigos.

4. `dashboard/scout_settings.py`
   - Extraidos defaults/settings do Scout, allowlist de GPU e bloqueio por allowlist.
   - `dashboard/app.py` manteve wrappers com os nomes antigos.

5. `dashboard/scout_history.py`
   - Extraidos historico Scout, machine key, comparacao de hardware e indice de maquinas.
   - `dashboard/app.py` manteve wrappers com os nomes antigos.

## Ultima Verificacao

- `python -m py_compile dashboard\app.py dashboard\state_store.py dashboard\vast_service.py dashboard\scout_settings.py dashboard\scout_history.py scripts\check_dashboard_contracts.py`
- `python scripts\check_dashboard_contracts.py`
- `docker compose build dashboard`
- `docker compose run --rm --no-deps dashboard python -c "import app, scout_settings; print(app.app.title); print(scout_settings.settings({})['allowed_gpu_models'])"`
- `docker compose up -d dashboard`
- `python scripts\check_dashboard_contracts.py`
- `docker logs --tail 80 gpu-dashboard`

Resultado: dashboard subiu sem erro visivel nos logs, contratos HTTP passaram, Scout segue pausado (`enabled=false`), testes ativos `0`, allowlist `H100 SXM`.

Checkpoint da parte 5: apos extrair `scout_history.py`, o dashboard foi rebuildado e reiniciado. Resultado observado: Scout `enabled=false`, `active=0`, fila operacional `queued/renting/rented=0`, radar bloqueado apenas como observabilidade, allowlist `H100 SXM`, teto `$2.40/h`.

Checkpoint Akoya Miner 2.1: preparado endpoint manual `POST /api/vast/actions/{ask_id}/update-akoya` e botao `Atualizar Akoya` na Operacao Pools. A acao atualiza o template Vast da instancia para a imagem Akoya configurada e chama recycle. Nao executa atualizacao em massa.

Checkpoint comparativo Akoya: adicionado registro de hash antes da atualizacao e secao `Atualizacoes Akoya` no dashboard para comparar hash antigo vs hash atual por instancia.

## Regra De Trabalho

- Fazer uma parte por vez.
- Ler o codigo antes de mexer.
- Manter wrappers enquanto o app grande ainda depende dos nomes antigos.
- Verificar sintaxe, contratos HTTP e import dentro do container antes de considerar a etapa pronta.
- Nao religar o Scout automatico sem pedido explicito.
