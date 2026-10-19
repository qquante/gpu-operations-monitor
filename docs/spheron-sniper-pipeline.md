# Spheron Sniper Pipeline Runbook

This document records the current Spheron RTXPRO6000 sniper behavior and the operational checks used during the live run.

## What Was Implemented

- API create loop for Spheron RTXPRO6000 spot deployments.
- Pipeline control by deployment id.
- Worker naming from the Spheron short id, for example `spheron-6a1a43b2`.
- Up to `SPHERON_PIPELINE_MAX_ACTIVE=10` managed non-terminal deployments.
- Parallel SSH/miner bootstrap with `SPHERON_SSH_PARALLEL=10`.
- Retryable SSH failures, so early `Connection refused` does not permanently abandon an id.
- Non-interactive SSH with `BatchMode=yes`, so locked SSH keys fail quickly instead of blocking workers.
- UI scraping of `https://app.spheron.ai/instances` as an operational source of truth.
- Credit balance scraping from the Spheron navbar.
- Low-credit Windows beep alert below 5 credits.
- State tracking in `data/spheron_sniper_state.json`.
- Sanitized terminal/failed detail capture from the Spheron deployment API when available.

## Current Target

Default RTXPRO6000 preset:

```text
GPU: RTXPRO6000_PCIE
Provider: spheron-es
Region: US Central 1
Type: SPOT
Offer: US Central 1::gpu-rtx6000::1gpu-24vcpu-218gb::spot
Max price: $1.40/hr
Worker format: spheron-<short_id>
```

H100 SXM5 preset:

```text
GPU: H100_SXM5
Provider: spheron-es
Region: EU North 1
Type: SPOT
Offer: EU North 1::gpu-h100-sxm::1gpu-16vcpu-200gb::spot
OS: Ubuntu 24.04 (CUDA 13)
Volume: computefilesystem-e00zsm2mbcksqvmywg
Max price: $1.80/hr
```

H100 SXM5 x8 preset:

```text
GPU: H100_SXM5
GPU count: 8
Provider: spheron-es
Region: EU North 1
Type: SPOT
Offer: EU North 1::gpu-h100-sxm::8gpu-128vcpu-1600gb::spot
OS: Ubuntu 24.04 (CUDA 13)
Volume: computefilesystem-e00zsm2mbcksqvmywg
Max price: $14.00/hr
```

## Main Flow

1. Open Chrome with the Spheron sniper profile.
2. Capture the logged-in Spheron authorization header in memory.
3. Sync deployments through `/api/deployments`.
4. Scrape `/instances` and parse visible cards.
5. Create new deployments while stock exists and managed active count is below 10.
6. For every managed card/API record with `Running` and `ssh ubuntu@IP`, schedule SSH bootstrap.
7. SSH installs Docker if needed, validates NVIDIA Docker, pulls Akoya miner, and starts `pearl-akoya`.
8. Verify the worker on Akoya by worker name.
9. Record `ssh_status`, `pool_status`, hashrate, failures, and UI metadata in state.

## UI Scraping Semantics

The Spheron UI card is treated as an operational source:

```text
ID: 6a1a43b2
Running
SSH Connection
ssh ubuntu@204.12.162.254
Available in 17m
```

Meaning:

- `Running` plus `SSH Connection ssh ubuntu@...` means the sniper should try SSH now.
- `Available in 17m` is stored as metadata. It is not a delay before SSH.
- `Deploying` means keep waiting for SSH/IP.
- `Failed` or `Terminated` means mark the id terminal and stop trying SSH.

The same page text is used to read the balance line, such as:

```text
$ 15.56 credits
```

If credits fall below 5, the sniper triggers a Windows beep alert:

```text
8 beeps
888 Hz
888 ms each
```

The alert is latched so it does not repeat every scrape while the balance remains below 5. It resets when the balance returns to 5 or more.

## Status Meaning

```text
ssh_status=pending
```

The deployment is known but SSH has not started yet.

```text
ssh_status=running
bootstrap_status=bootstrapping
pool_status=akoya_waiting
```

The SSH/miner worker is currently running or waiting for Akoya verification.

```text
ssh_status=succeeded
bootstrap_status=completed
```

The bootstrap command completed and the miner container was started on the VM.

```text
pool_status=mining_online
pool_hashrate_ths > 0
```

Akoya confirmed the worker is online and hashing.

```text
pool_status=not_seen
```

SSH bootstrap completed, but the Akoya API check did not see that worker inside the verification window. If the Akoya dashboard shows the worker online with non-zero hashrate, mining is working and the verifier simply missed it.

```text
status=failed or status=terminated-provider
```

Spheron ended the deployment. The sniper should not keep trying that id.

## How To Run

In CMD, make sure the Windows OpenSSH agent is running:

```bat
sc config ssh-agent start= auto
net start ssh-agent
```

Then unlock the key:

```bat
ssh-add %USERPROFILE%\.ssh\id_ed25519
```

Start the sniper:

```bat
python scripts\spheron_sniper.py --watch
```

Start the H100 SXM5 preset:

```bat
set SPHERON_PIPELINE_MAX_ACTIVE=1
python scripts\spheron_sniper.py --target h100-sxm5 --watch
```

Start the H100 SXM5 x1/x8 sequence:

```bat
set SPHERON_PIPELINE_MAX_ACTIVE=1
python scripts\spheron_sniper.py --target h100-sxm5-all --watch
```

The sequence order is:

```text
h100-sxm5-1x attempt
wait 10s
h100-sxm5-8x attempt
wait 20s
repeat
```

If the process exits with a Playwright/Chrome close error, restart the same command. State is persisted locally, so already-created ids are not lost.

## How To Know If It Worked

The terminal should show scheduling:

```text
Scheduled SSH/miner pipeline: 6a1a43b2... worker=spheron-6a1a43b2 ip=204.12.162.254 attempt=1
```

With the latest code it also prints:

```text
SSH bootstrap completed: 6a1a43b2... worker=spheron-6a1a43b2 ip=204.12.162.254; verifying Akoya.
Akoya verify: 6a1a43b2... worker=spheron-6a1a43b2 pool=mining_online hash=219.62 TH/s
```

Akoya dashboard check:

```text
spheron-6a1a43b2 online 219.62
spheron-6a1a43e7 online 324.46
```

`online` plus non-zero hashrate means the VM is mining.

## Useful State Check

From the repo root:

```powershell
$s = Get-Content data\spheron_sniper_state.json -Raw | ConvertFrom-Json
$s.deployments.PSObject.Properties |
  Where-Object { $_.Value.created_by -in @('spheron_sniper','manual_bootstrap') } |
  ForEach-Object {
    [pscustomobject]@{
      id=$_.Value.short_id
      status=$_.Value.status
      ip=$_.Value.ip_address
      worker=$_.Value.worker
      phase=$_.Value.phase
      ssh=$_.Value.ssh_status
      pool=$_.Value.pool_status
      hash=$_.Value.pool_hashrate_ths
      attempts=$_.Value.ssh_attempts
      error=$_.Value.last_error
    }
  } | Format-Table -AutoSize
```

## Live Run Notes

The observed run behaved as expected:

- The sniper scraped 9 visible cards from `/instances`.
- It created deployments until managed capacity reached `10/10`.
- It scheduled SSH/miner pipelines for ids as soon as the UI/API exposed SSH IPs.
- Akoya showed `spheron-6a1a43b2` and `spheron-6a1a43e7` online with non-zero hashrate, confirming those miners were running.
- The final `BrowserContext.close: Connection closed while reading from the driver` means the Chrome/Playwright connection closed and the watcher process stopped. Restart `--watch` to continue supervising and bootstrapping remaining ids.

## Known Gaps

- The Akoya API verifier may return `not_seen` even when the dashboard already shows a worker online. The dashboard remains the stronger confirmation if it shows `online` and non-zero hashrate.
- The sniper does not auto-destroy failed, idle, or unprofitable Spheron instances yet.
- The scraper only sees cards currently rendered by the Spheron page. If the UI paginates or hides items behind `Load More`, those hidden cards may require API detail or future scroll/load-more handling.

## Spheron Cooldown

Spheron can return:

```text
HTTP 429 Deployment attempts paused
retryAfter: 900
```

This is not a generic request-limit response. It means recent deployment attempts failed in a row, so Spheron pauses new deployment creation for about 15 minutes. The sniper stores `cooldown_until` and skips offer/create calls during that window. Existing SSH workers already known in state may continue.
