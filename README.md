# GPU Operations Monitor

A multi-service dashboard for GPU worker status, provider observations and operational cost tracking.

## Features

- Shared monitor code supports several worker/provider adapters.
- Dashboard services aggregate observations and operational state.
- Cost and worker metadata support local review of infrastructure behavior.

## Stack

Python · FastAPI · httpx · Redis · JavaScript/HTML dashboards · Docker Compose

Redis and local JSON state support monitor results and dashboard history. Private provider configuration and runtime history are excluded.

## Getting started

Requirements are scoped per dashboard/monitor directory. Inspect compose service definitions; do not start the complete provider stack just to inspect the UI.

## How it works

```text
Provider/worker adapters → shared monitor logic → cached state → FastAPI dashboards
```

## Current limitations

Adapters include operational actions as well as monitoring. No cloud machine was provisioned, stopped or billed during review. Provider integrations and reported rates were not revalidated.

## License

Project-authored source code is licensed under the [MIT License](LICENSE). Third-party components and datasets retain their respective rights and licenses.
