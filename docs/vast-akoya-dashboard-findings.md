# Vast/Akoya Dashboard Findings

Data da investigacao: 2026-05-28

## Resumo

O dashboard compara dados de duas fontes diferentes:

- Vast.ai: informa a instancia alugada, o `Instance ID`, o preco e `num_gpus`.
- Akoya Pool: informa o worker de mineracao, hashrate real e `gpu_count` reportado pelo pool.

Esses campos nao significam a mesma coisa. Em algumas instancias a Vast mostra `2x`, mas o Akoya reporta `gpu_count=1` e o hashrate parece de uma GPU so.

## Estado observado

Instancias ativas na Vast:

| Vast Instance ID | Worker | GPU Vast | GPUs Vast | Estado |
| --- | --- | --- | ---: | --- |
| 38261330 | vast-38109728 | RTX 4070S | 2 | running |
| 38261655 | vast-38109733 | RTX 4070S | 2 | running |
| 38263626 | vast-38237772 | RTX 4090 | 2 | running |
| 38264475 | vast-38259515 | RTX 4090 | 1 | loading |
| 38264482 | vast-37204580 | RTX 3090 | 1 | created |

Workers observados no Akoya:

| Worker | GPU Akoya | GPUs Akoya | Hashrate |
| --- | --- | ---: | ---: |
| vast-38109728 | RTX 4070 | 1 | ~70 TH/s |
| vast-38109733 | RTX 4070 | 1 | ~62 TH/s |
| vast-38237772 | RTX 4090 | 1 | ~184 TH/s |

## Causa da confusao

No bloco `Controle Vast`, o dashboard usa `dashboard:vast:actions`, sincronizado com a API de instancias da Vast. Ali a contagem correta para alugueis vem de `num_gpus`.

No bloco `Minha Operacao - Akoya`, o dashboard usa `monitor:akoya.workers[]`. Esse payload vem da API do Akoya e traz `gpu_count=1` para os workers acima, mesmo quando a instancia da Vast tem `num_gpus=2`.

Portanto:

- `Vast x2` significa duas GPUs alugadas naquela instancia.
- `Akoya x1` significa uma GPU reportada/minerando para aquele worker no pool.

## Instance ID

Ha tres IDs diferentes envolvidos:

| Campo | Fonte | Exemplo | Significado |
| --- | --- | --- | --- |
| `ask_id` | Vast marketplace | 38237772 | ID da oferta/ask alugada |
| `instance_id` | Vast instances | 38263626 | ID real da instancia na Vast |
| `instance_id` | Akoya API | UUID | ID interno do pool, nao e ID da Vast |

O dashboard deve evitar chamar o UUID do Akoya de instancia Vast. Quando o worker for `vast-*`, a instancia Vast correta deve vir do registro de acoes/sincronizacao da Vast.

## Preco das instancias novas

Para instancias ainda em `created/loading`, a API da Vast pode retornar dois precos:

- `instance.totalHour`: preco parcial temporario, muitas vezes so disco, igual ao que a UI mostra enquanto a GPU ainda nao iniciou.
- `dph_total` / `search.totalHour`: preco cheio esperado da oferta.

Exemplos observados:

| Instance ID | UI temporaria | Preco cheio API |
| --- | ---: | ---: |
| 38264475 | ~$0.003/h | ~$0.6963/h |
| 38264482 | ~$0.002/h | ~$0.2022/h |

Para custo conservador, o dashboard deve usar o preco cheio (`dph_total` / `search.totalHour`). Para explicar divergencia visual, pode exibir status `loading/created`.

## Mudanca aplicada no dashboard

O bloco `Minha Operacao - Akoya` agora:

- mostra a coluna `Instancia Vast` quando houver associacao por worker;
- ignora acoes Vast arquivadas nessa coluna para nao confundir workers antigos/offline com instancias atuais;
- mostra `GPU Akoya xN / Placas xM` quando as contagens divergem;
- marca risco `qtd placas` quando a quantidade do pool e diferente da quantidade de placas da instancia Vast;
- marca risco `hash baixo p/ placas` quando o hashrate real parece baixo para a quantidade de placas alugada.

O bloco `Decisao agora` nao bloqueia mais ofertas verdes apenas porque ja existem instancias ativas. O painel continua mostrando quantas instancias existem em `Controle Vast`, mas deixa a decisao de novo aluguel para o operador.

## Interpretacao operacional

Se uma instancia aparece como `Vast x2` e `Akoya x1`, existem duas possibilidades principais:

- o miner esta usando apenas uma GPU da instancia;
- o pool esta agregando/reportando de forma incompleta.

Quando o hashrate bate com uma unica GPU, a primeira hipotese fica mais forte. Exemplo: uma RTX 4090 `x2` com ~184 TH/s parece uma so 4090 minerando, nao duas.

## Proximos pontos a investigar

- Conferir logs dentro da instancia Vast para ver quantas GPUs o miner detecta.
- Verificar se o template Akoya/miner limita GPU visivel, device index ou CUDA_VISIBLE_DEVICES.
- Verificar se `gpu_frac` na Vast indica particionamento/isolamento que afeta o miner.
- Ajustar o painel para mostrar preco temporario e preco cheio em colunas separadas, se isso continuar confundindo.

## Blacklist operacional

Erro observado:

```text
failed to inject CDI devices: unresolvable CDI devices ... gpu=1, gpu=2, gpu=3: unknown
```

Esse erro acontece antes do miner iniciar. A falha esta no runtime do host Vast/CDI/NVIDIA Container Toolkit, nao no Akoya em si. Como renter, o caminho operacional mais seguro e destruir essa instancia e evitar alugar o mesmo host/maquina novamente.

Fluxo implementado no dashboard:

1. Em `Controle Vast`, clicar `Blacklist` na linha ativa.
2. O navegador pede confirmacao.
3. O dashboard chama `DELETE https://console.vast.ai/api/v0/instances/{instance_id}/`.
4. Se a Vast aceitar, a acao local vira `archived`.
5. O host/maquina/GPU entra em `data/vast_blacklist.json`.
6. Ofertas futuras com o mesmo `machine_id`, ou mesmo `host_id + gpu`, deixam de aparecer em `Decisao agora`.

O botao `Arquivar` continua sendo apenas local. Ele nao destroi a instancia na Vast.

Arquivo persistente:

```text
data/vast_blacklist.json
```

O volume `./data:/app/data` foi adicionado ao dashboard para preservar a blacklist entre rebuilds/restarts do container.
