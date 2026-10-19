# Spheron Sniper

Local Windows sniper for Spheron RTXPRO6000 spot deployments.

The script uses a logged-in Chrome profile because official Spheron API key generation is locked for this account. It captures the temporary `Authorization: Bearer ...` header from live Spheron browser requests in memory, calls the same JSON API used by the web app, waits for the VM IP, then bootstraps Akoya over SSH.

It does not save tokens, cookies, or browser storage in repo files.

## Install

From the repo root:

```powershell
python -m pip install -r scripts\spheron_sniper_requirements.txt
python -m playwright install chromium
```

The script prefers installed Google Chrome. The Playwright Chromium install is a fallback.

## Required Configuration

The defaults match the current RTXPRO6000 target:

```text
SPHERON_TARGET_GPU_TYPE=RTXPRO6000_PCIE
SPHERON_TARGET_GPU_COUNT=1
SPHERON_TARGET_PROVIDER=spheron-es
SPHERON_TARGET_OFFER_ID=US Central 1::gpu-rtx6000::1gpu-24vcpu-218gb::spot
SPHERON_TARGET_REGION=US Central 1
SPHERON_TARGET_OS=Ubuntu 24.04 (CUDA 13)
SPHERON_TARGET_INSTANCE_TYPE=SPOT
SPHERON_MAX_PRICE_USD_HR=1.40
SPHERON_MAX_ACTIVE_TARGET=0
SPHERON_USER_ID=6a198661e8c930baae60fd54
SPHERON_TEAM_ID=6a198661e8c930baae60fd57
SPHERON_SSH_KEY_ID=6a1a1af578fd1c6d26fa449c
SPHERON_VOLUME_IDS=computefilesystem-u00bc4zakxx6rax8qf
SPHERON_SSH_PRIVATE_KEY_PATH=C:\Users\PC\.ssh\id_ed25519
SPHERON_WORKER_PREFIX=spheron
SPHERON_WORKER_START=6
SPHERON_WORKER_USE_DEPLOYMENT_ID=true
SPHERON_PIPELINE_MAX_ACTIVE=10
SPHERON_CREATE_BATCH_PER_TICK=1
SPHERON_SSH_PARALLEL=10
SPHERON_SSH_RETRY_SECONDS=30
SPHERON_SSH_CONNECT_TIMEOUT_SECONDS=12
SPHERON_UI_SCRAPE_ENABLED=true
SPHERON_LOW_CREDITS_THRESHOLD=5
SPHERON_LOW_CREDITS_BEEP_ENABLED=true
SPHERON_LOW_CREDITS_BEEP_COUNT=8
SPHERON_LOW_CREDITS_BEEP_FREQUENCY=888
SPHERON_LOW_CREDITS_BEEP_DURATION_MS=888
SPHERON_AKOYA_VERIFY_SECONDS=300
SPHERON_AKOYA_VERIFY_INTERVAL_SECONDS=15
```

`AKOYA_WALLET` must exist in `.env`; the script loads the repo `.env` automatically.

## First Login

The sniper uses a dedicated Chrome profile:

```text
%LOCALAPPDATA%\SpheronSniper\ChromeProfile
```

On first run, Chrome opens. Log in to Spheron in that window. The script waits until it sees authenticated Spheron API traffic.

## Commands

Local checks, no browser:

```powershell
python scripts\spheron_sniper.py --self-test
```

Inspect current target and state:

```powershell
python scripts\spheron_sniper.py --list
```

Dry-run one pass. This does not create a deployment or SSH:

```powershell
python scripts\spheron_sniper.py --once --dry-run
```

Create one deployment if available and record it for the pipeline:

```powershell
python scripts\spheron_sniper.py --once
```

Keep watching:

```powershell
python scripts\spheron_sniper.py --watch
```

Use the H100 SXM5 spot preset from the captured Spheron payload:

```powershell
python scripts\spheron_sniper.py --target h100-sxm5 --watch
```

Try both H100 SXM5 offers in a fixed loop: x1, wait 10s, x8, wait 20s, repeat:

```bat
set SPHERON_PIPELINE_MAX_ACTIVE=1
python scripts\spheron_sniper.py --target h100-sxm5-all --watch
```

The sequence uses:

```text
h100-sxm5-1x: EU North 1::gpu-h100-sxm::1gpu-16vcpu-200gb::spot, gpuCount=1, maxPrice=$1.80/h
h100-sxm5-8x: EU North 1::gpu-h100-sxm::8gpu-128vcpu-1600gb::spot, gpuCount=8, maxPrice=$14.00/h
```

For a single H100 attempt, set the pipeline cap before starting:

```bat
set SPHERON_PIPELINE_MAX_ACTIVE=1
python scripts\spheron_sniper.py --target h100-sxm5 --watch
```

`--watch` is the normal production mode. It keeps creating target deployments while stock exists and the managed pipeline has fewer than `SPHERON_PIPELINE_MAX_ACTIVE` non-terminal deployments. SSH/miner bootstrap runs in parallel, up to `SPHERON_SSH_PARALLEL` workers.

By default it also scrapes `https://app.spheron.ai/instances` as the operational view. The scraper reads the visible cards, matches `ID: 6a1a3fdc` to the local full deployment id, captures `Running`/`Deploying`/`Failed`/`Terminated`, `ssh ubuntu@IP`, and `Available in 20m`, then feeds that into the same state pipeline.

The same scrape reads the navbar balance, for example `$ 15.56 credits`. If the balance drops below `SPHERON_LOW_CREDITS_THRESHOLD`, Windows beeps `SPHERON_LOW_CREDITS_BEEP_COUNT` times at `SPHERON_LOW_CREDITS_BEEP_FREQUENCY` Hz for `SPHERON_LOW_CREDITS_BEEP_DURATION_MS` ms each. The alert fires once per low-balance episode and resets after credits return to the threshold or above.

For parallel SSH, unlock the private key in Windows OpenSSH agent before starting `--watch`:

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

The sniper uses non-interactive SSH (`BatchMode=yes`). If Spheron reports an IP before port 22 is truly ready, the attempt is recorded as `ssh_failed` and retried every `SPHERON_SSH_RETRY_SECONDS` while the deployment remains running.

If Spheron returns `HTTP 429 Deployment attempts paused`, the sniper respects the API `retryAfter` value, usually 900 seconds. During this cooldown it skips offer/create requests instead of hammering the deployment endpoint.

Bootstrap an already-created Spheron deployment:

```powershell
python scripts\spheron_sniper.py --bootstrap-existing 6a1a2f9d90f6e1a5dcd5775d
```

The short id shown in the Spheron UI also works:

```powershell
python scripts\spheron_sniper.py --bootstrap-existing 6a1a3867
```

Available target presets:

```text
rtxpro6000
h100-sxm5
h100-sxm5-1x
h100-sxm5-8x
h100-sxm5-all
```

## Behavior

The script only creates when all of these are true:

- matching RTXPRO6000 offer is available;
- provider is `spheron-es`;
- region is `US Central 1`;
- instance type is `SPOT`;
- offer id matches exactly;
- price is `<= $1.40/h`;
- active matching target deployments are below `SPHERON_MAX_ACTIVE_TARGET`.
  `0` means unlimited, so existing target deployments do not block new creates.

After create, `--watch` keeps scanning instead of blocking on that one VM. Each managed deployment moves through pipeline phases:

```text
deploying -> running_ip_ready -> ssh_running -> miner_started -> mining_online
```

Failures are recorded as `failed`, `terminated`, `ssh_failed`, `not_seen`, or `connected_no_hash`.

When the UI shows `Running` plus `SSH Connection ssh ubuntu@...`, the sniper treats the deployment as SSH-ready even if the API is behind. `Available in 20m` is stored as UI metadata; it is not treated as a delay before SSH.

During bootstrap the terminal prints two useful milestones per id:

```text
SSH bootstrap completed: 6a1a43b2... worker=spheron-6a1a43b2 ip=204.12.162.254; verifying Akoya.
Akoya verify: 6a1a43b2... worker=spheron-6a1a43b2 pool=mining_online hash=219.62 TH/s
```

In state, `ssh_status=succeeded` means the miner container was started on the VM. `pool_status=mining_online` plus non-zero `pool_hashrate_ths` means Akoya has confirmed it is hashing.

Then it runs on the VM:

```bash
sudo docker pull registry.akoyapool.com/akoya-miner:latest
sudo docker rm -f pearl-akoya || true
sudo docker run -d --name pearl-akoya --restart unless-stopped --gpus all \
  -e AKOYA_POOL_WALLET="$AKOYA_WALLET" \
  -e AKOYA_POOL_WORKER="$WORKER" \
  registry.akoyapool.com/akoya-miner:latest
```

If Docker is missing, it installs Docker first. If NVIDIA Docker runtime fails, the bootstrap is marked failed.

## State

State is stored in:

```text
data/spheron_sniper_state.json
```

It stores worker counters, deployment ids, IPs, prices, SSH/bootstrap/pool status, Akoya hashrate, and sanitized errors. It does not store browser tokens or cookies.

By default, new workers are named from the Spheron deployment id:

```text
spheron-6a1a3a17
```

That makes the Akoya worker name line up with the short id shown in the Spheron UI. After SSH bootstrap, the sniper waits up to `SPHERON_AKOYA_VERIFY_SECONDS` for that worker to appear in Akoya and report hashrate.

## Current Limitations

- v1 does not auto-destroy bad or unprofitable instances.
- v1 always sends the configured volume id. If Spheron rejects the volume, it does not retry without it.
- If SSH auth fails, unlock the key in Windows OpenSSH agent and leave `--watch` running; failed SSH attempts retry.
- If Spheron changes the web auth flow, the script may fail to capture the temporary token until the official API key is available.
