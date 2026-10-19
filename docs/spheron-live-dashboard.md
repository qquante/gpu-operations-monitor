# Spheron Live Dashboard

Dashboard local: http://localhost:8091/

Ele controla o sniper por `data/spheron_control_config.json`. O sniper recarrega esse arquivo a cada tick, entao nao precisa reiniciar para mudar limite, pausa, preco ou delay.

## Fluxo

1. Rode o sniper no terminal:

```powershell
python scripts\spheron_sniper.py --target h100-sxm5-1x --watch
```

2. Abra o dashboard:

```text
http://localhost:8091/
```

3. Ajuste ao vivo:

- `Criacao`: pausa ou retoma novos creates.
- `GPUs online alvo`: default 10, conta workers Spheron H100 x1 online no Akoya com hash > 0.
- `IDs ativos maximo`: default 20, conta deployments Spheron alvo ainda nao terminais.
- `SSH paralelo`: limite de bootstraps simultaneos.
- `Delay loop`: intervalo do `--watch`.
- `Preco max`: cap de create para H100 x1.

## Dados

- Spheron: `data/spheron_sniper_state.json`
- Config viva: `data/spheron_control_config.json`
- Hashrate Akoya: Redis `monitor:akoya`, vindo do container `monitor-akoya`
- Custos por worker: `data/fixed_worker_costs.json`
- Uso total Spheron: capturado do card/API como `total_usage_usd`
- Ganho por worker: `data/spheron_earnings_history.json`, estimado pelo hashrate Akoya vezes a taxa atual em `monitor:pearl`

O join e feito por worker name: `spheron-<short_id>`.

O custo/hora do dashboard prioriza o preco vindo do Spheron. O custo fixo local fica apenas como fallback quando o Spheron ainda nao informou preco.
