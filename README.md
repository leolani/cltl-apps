# cltl-apps

Deployment stacks for the Leolani conversational-agent platform, assembled
from published `ghcr.io/leolani/cltl-*` images — plus a template for
attaching your own code to one.

**One git checkout = one deployment.** Clone this repo once per node of your
distributed application — once for the shared server, once per client/tenant
— even if two of them end up running on the same machine. Each checkout gets
its own `config/`, adapted to that one deployment via a template. See
[`doc/DEPLOYMENT.md`](doc/DEPLOYMENT.md) for the full story.

## Layout

```
cltl-apps/
├── templates/        config templates to copy into a checkout's config/
│   ├── server/         for servers/* — one instance, shared by every tenant
│   ├── client/         for clients/* — one instance per tenant
│   └── module/         pointer at custom-module/, see below
├── clients/           user-facing stacks for THIS checkout's one tenant
│   ├── backend/         proxies the host's microphone/camera server
│   ├── context/         opens/closes this tenant's conversation scenario
│   ├── chat-ui/         the web chat UI
│   └── monitoring/      per-scenario view, shown as a chat-ui tab
├── servers/           shared platform stacks for THIS checkout's server
│   ├── broker/          RabbitMQ + this checkout's platform network
│   ├── eliza/           storage API + the ELIZA dialogue engine
│   ├── vad-asr/         voice activity detection + speech recognition
│   └── emissor/         EMISSOR interaction-data capture + REST API
├── custom-module/     template: attach your own code via the event bus
├── config/            THIS checkout's own config — generated, not tracked;
│                        populate it from templates/, see config/README.md
├── storage/           THIS checkout's own persisted data
└── doc/               architecture overview and the deployment guide
```

A checkout only ever runs one role's worth of stacks — either `servers/*`
(for a server node) or `clients/*` (for a client/tenant node) — though which
of that role's compose files you combine with `-f` stays flexible (e.g. just
`servers/vad-asr` on its own). **Start here:**
[`doc/DEPLOYMENT.md`](doc/DEPLOYMENT.md) — checkout, template, and every
stack-selection command, including running more than one tenant.

[`doc/LEOLANI.md`](doc/LEOLANI.md) is the narrative architecture overview of
the platform and its agent variants — read that first if you want the "why"
before the "how".

## Quick start

Bringing up a demo needs **two** checkouts — one configured as the server,
one as the client — even on a single machine:

```bash
git clone https://github.com/leolani/cltl-apps.git cltl-server && cd cltl-server
cp templates/server/config/* config/
docker compose --env-file config/servers.env \
                -f servers/broker/docker-compose.yml \
                -f servers/eliza/docker-compose.yml \
                -f servers/vad-asr/docker-compose.yml \
                -f servers/emissor/docker-compose.yml up -d --wait --pull always
cd ..

git clone https://github.com/leolani/cltl-apps.git cltl-client && cd cltl-client
cp templates/client/config/* config/
# config/clients.env's CLTL_SERVER_HOST default (host.docker.internal)
# already reaches cltl-server/ above on this same machine — no edit needed.

cd clients/backend && ./run_host_server.sh &   # host mic server (needs Python 3.10 + PortAudio on this machine); skip for text-only
cd ../..
docker compose --env-file config/clients.env \
    -f clients/backend/docker-compose.yml \
    -f clients/context/docker-compose.yml \
    -f clients/chat-ui/docker-compose.yml \
    -f clients/monitoring/docker-compose.yml up -d --wait --pull always
```

`--pull always` matters because `VERSION` is a moving, configurable tag
(`:latest` by default): without it, Compose is content with whatever image is
already cached locally, which silently stops tracking a tag someone keeps
pushing to. It re-checks the registry on every `up`, which costs a few
seconds even when nothing changed.

Chat UI: <http://localhost:8003/chatui/static/chat.html> — answer the agent's
opening consent question before anything else, or nothing responds.

| Port | Service |
|---|---|
| 5672 / 15672 | RabbitMQ AMQP / management UI (`eliza` / `eliza123`) |
| 8001 | Storage REST API (servers/eliza) |
| 8002 | EMISSOR data API (servers/emissor) |
| 9001 | This tenant's client backend API (`CLTL_BACKEND_PORT`) |
| 8003 | This tenant's chat UI (`CLTL_CHATUI_PORT`) |
| 8005 | This tenant's monitoring view (`CLTL_MONITORING_PORT`) |
| 8000 | Host microphone server (`leoserv`, on the host, not in Docker) |

`VERSION=<tag>` before any command above pins every image to that tag instead
of `:latest`. A second tenant is a third checkout, configured from
`templates/client/` again with its own `CLTL_TENANT` and port values — see
[`doc/DEPLOYMENT.md`](doc/DEPLOYMENT.md) for multi-tenant and partial-stack
(server-only, client-only) invocations, a genuinely remote server, and its
[monitoring section](doc/DEPLOYMENT.md#monitoring) for dropping
`clients/monitoring` (the chat UI's Monitoring tab) if you don't want it.

## Attaching your own code

[`custom-module/`](custom-module/) is a minimal template demonstrating event
bus subscription/publishing with correct tenant-id handling — the pattern to
copy for adding custom processing to a running deployment. It attaches to an
already-running deployment; it does not build one. The fastest way to see it
live is [`custom-module/custom-module.ipynb`](custom-module/custom-module.ipynb),
a notebook that connects to one tenant's bus cell by cell.
