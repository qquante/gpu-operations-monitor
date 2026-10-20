# GPU Operations Monitor

![Language: Python](https://img.shields.io/badge/Language-Python-3776AB?style=flat-square&logo=python) ![API: FastAPI](https://img.shields.io/badge/API-FastAPI-555555?style=flat-square) [![License: MIT](https://img.shields.io/badge/License-MIT-555555?style=flat-square)](LICENSE)

A FastAPI dashboard and provider-specific monitors for inspecting GPU workers, observations and operational costs across a mixed infrastructure stack.

The repository contains adapters for Akoya, Alphamine, Clore, Pearl, RunPod, TensorDock and Vast.ai, plus a separate Spheron dashboard. They share monitoring/state helpers, but they are not one interchangeable provider API.

## Pick the surface you need

| Area | Role |
| --- | --- |
| [monitors](monitors) | Provider/workload polling adapters. |
| [shared/base_monitor.py](shared/base_monitor.py) | Shared monitor behavior. |
| [dashboard/app.py](dashboard/app.py) | Main dashboard API. |
| [dashboard/state_store.py](dashboard/state_store.py) | Redis JSON access and local snapshot/archive helpers. |
| [spheron_dashboard](spheron_dashboard) | Separate provider-oriented interface. |

Redis holds shared observations; local JSON files support snapshots and archives. A dashboard row is only as fresh as its underlying adapter, so missing/stale data must be interpreted separately from a healthy worker.

## Set up a bounded local inspection

```console
python -m venv .venv
python -m pip install -r dashboard/requirements.txt
python -m compileall -q dashboard monitors shared
```

Each monitor directory declares its own dependencies. Review [.env.example](.env.example) and the service definitions in [docker-compose.yml](docker-compose.yml) before selecting any services; starting the entire Compose stack is not necessary to read the dashboard implementation.

## Operational scope

Some provider services contain provisioning or automation actions as well as observation code. Account credentials, Redis connectivity and workload configuration are operator inputs. No current provider pricing, live profitability, GPU allocation or behavioral test result is established by the syntax check above.

**Technology:** Python · FastAPI · httpx · Redis · JavaScript/HTML dashboards · Docker Compose

Project-authored source: [MIT](LICENSE). Third-party components retain their own notices and terms.
