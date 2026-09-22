# cltl-apps

Deployment stacks for the Leolani conversational-agent platform, assembled
from published `ghcr.io/leolani/cltl-*` images — plus a template for
attaching your own code to one.

## Layout

```
cltl-apps/
├── clients/          user-facing stacks — one set per tenant
│   ├── backend/       proxies the host's microphone/camera server
│   ├── context/       opens/closes a tenant's conversation scenario
│   └── chat-ui/       the web chat UI
├── servers/          shared platform stacks — one instance for every tenant
│   ├── broker/         RabbitMQ + the platform network
│   ├── eliza/          storage API + the ELIZA dialogue engine
│   ├── vad-asr/        voice activity detection + speech recognition
│   └── emissor/        EMISSOR interaction-data capture + REST API
├── custom-module/    template: attach your own code via the event bus
├── config/            shared configuration, mounted by every stack above
├── storage/           shared persisted data, mounted by every stack above
└── doc/               architecture overview and the deployment guide
```

Every stack under `servers/` and `clients/` is a separate Docker Compose
file, invoked together with `-f`, sharing this repository's root `config/`
and `storage/` directories. **Start here:**
[`doc/DEPLOYMENT.md`](doc/DEPLOYMENT.md) — checkout, configuration, and every
stack-selection command, including running more than one tenant at once.

[`doc/LEOLANI.md`](doc/LEOLANI.md) is the narrative architecture overview of
the platform and its agent variants — read that first if you want the "why"
before the "how".

## Quick start (one tenant, everything on one machine)

```bash
# 1. the shared platform half
docker compose -f servers/broker/docker-compose.yml up -d --wait
docker compose -f servers/broker/docker-compose.yml \
                -f servers/eliza/docker-compose.yml \
                -f servers/vad-asr/docker-compose.yml \
                -f servers/emissor/docker-compose.yml up -d --wait
```

```bash
# 2. host microphone server (outside Docker — a container has no microphone)
cd clients/backend && ./run_host_server.sh &
cd ../..

```

```bash
# 3. this tenant's client half (servers/broker must already be up — do not
#    re-list it here: its project name differs from the client stacks', and
#    Compose would try to re-create the already-running rabbitmq container)
CLTL_TENANT=tenant-a CLTL_BACKEND_PORT=9001 CLTL_CHATUI_PORT=8003 \
    docker compose -f clients/backend/docker-compose.yml \
                    -f clients/context/docker-compose.yml \
                    -f clients/chat-ui/docker-compose.yml up -d --wait
```

Chat UI: <http://localhost:8003/chatui/static/chat.html> — answer the agent's
opening consent question before anything else, or nothing responds.

| Port | Service |
|---|---|
| 5672 / 15672 | RabbitMQ AMQP / management UI (`eliza` / `eliza123`) |
| 8001 | Storage REST API (servers/eliza) |
| 8002 | EMISSOR data API (servers/emissor) |
| 9001 | This tenant's client backend API (`CLTL_BACKEND_PORT`) |
| 8003 | This tenant's chat UI (`CLTL_CHATUI_PORT`) |
| 8000 | Host microphone server (`leoserv`, on the host, not in Docker) |

`VERSION=<tag> docker compose pull` pins images; default is `:latest`. A
second tenant runs the same step-3 command with different `CLTL_TENANT` and
port values — see [`doc/DEPLOYMENT.md`](doc/DEPLOYMENT.md) for multi-tenant
and partial-stack (server-only, client-only) invocations.

## Attaching your own code

[`custom-module/`](custom-module/) is a minimal template demonstrating event
bus subscription/publishing with correct tenant-id handling — the pattern to
copy for adding custom processing to a running deployment. It attaches to an
already-running deployment; it does not build one. The fastest way to see it
live is [`custom-module/custom-module.ipynb`](custom-module/custom-module.ipynb),
a notebook that connects to one tenant's bus cell by cell.
