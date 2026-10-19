# Vast.ai template AlphaMine

Este documento registra o template necessario para minerar Pearl na AlphaMine/AlphaPool pela Vast.ai.

## Imagem Docker

```text
alphaminetech/pearl-miner
```

Use a tag fixa se a `latest` falhar:

```text
alphaminetech/pearl-miner:1.5.0
```

## Env vars do template

```text
PEARL_ADDRESS=prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc
PEARL_WORKER=vast-{ASK_ID}
PEARL_POOL_HOST=us2.alphapool.tech
PEARL_POOL_PORT=5566
PEARL_DIFFICULTY=65536
```

O dashboard sobrescreve `PEARL_WORKER` para `vast-{ask_id}` quando aluga pela API.

## Docker equivalente

```bash
docker run -d --restart=unless-stopped --gpus all \
  --name pearl-miner \
  -e PEARL_ADDRESS=prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc \
  -e PEARL_WORKER=vast-ASK_ID \
  -e PEARL_POOL_HOST=us2.alphapool.tech \
  -e PEARL_POOL_PORT=5566 \
  -e PEARL_DIFFICULTY=65536 \
  alphaminetech/pearl-miner
```

## Dificuldade estatica recomendada

O dashboard escolhe automaticamente quando `ALPHAMINE_DIFFICULTY` fica vazio:

| GPU | Difficulty |
| --- | ---: |
| RTX 3060 Ti / 3070 / A100 | 131072 |
| RTX 3080 / 3090 / 4070 / 4080 | 262144 |
| RTX 4090 / 5080 | 524288 |
| RTX 5090 / H100 / H200 / B100 | 1048576 |
| fallback | 65536 |

## Configuracao local do dashboard

Depois de criar o template na Vast, copie o hash do template e configure:

```text
VAST_ALPHAMINE_TEMPLATE_HASH_ID=<hash_do_template_alphamine>
ALPHAMINE_WALLET=prl1puna9a3e854p30s8hcxk4u2sm754xj2x3yx5vpe4exq49d2vk72sq9fkmnc
ALPHAMINE_POOL_HOST=us2.alphapool.tech
ALPHAMINE_POOL_PORT=5566
ALPHAMINE_DIFFICULTY=
```

`ALPHAMINE_DIFFICULTY` vazio deixa o dashboard escolher por GPU. Se quiser travar tudo em uma dificuldade, preencha esse campo.

## Monitor

Novo container:

```text
monitor-alphamine
```

Redis key:

```text
monitor:alphamine
```

API usada:

```text
https://pearl.alphapool.tech/api/miner/{wallet}
```

O dashboard agora junta Akoya e AlphaMine em `Minha Operacao - Pools`.
