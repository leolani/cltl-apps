# cltl-apps

Deployment stacks for the Leolani conversational-agent platform, assembled
from published `ghcr.io/leolani/cltl-*` images — plus a template for
attaching your own code to one.

There are two independent things to choose here, and keeping them apart is
the quickest way to understand this repository:

1. **Which modules you run.** Each directory under `modules/` is one
   `docker-compose.yml` you add to a bring-up command with `-f`. They are
   uniform: same project name, same network, same config mounts.
2. **How the deployment is laid out.** Everything on one machine, or split
   into a shared server plus one tenant deployment per person. This is
   decided by `config/`, not by which modules exist — see
   [`doc/DEPLOYMENT.md`](doc/DEPLOYMENT.md).

A module is not inherently a "server" or a "tenant" module. `modules/backend`
is literally the same image and the same compose file in every deployment;
whether it holds the audio/image store or forwards to another one that does
is a value in `config/custom.config`.

## Layout

```
cltl-apps/
├── modules/           the platform's modules — one compose file each
│   ├── event-bus/       RabbitMQ + this deployment's Docker network
│   ├── backend/         storage API + host microphone/camera proxy
│   ├── eliza/           the ELIZA dialogue engine
│   ├── vad-asr/         voice activity detection + speech recognition
│   ├── emissor/         EMISSOR interaction-data capture + REST API
│   ├── context/         opens/closes the conversation scenario, BDI model
│   ├── chat-ui/         the web chat UI
│   ├── monitoring/      per-scenario view, embedded as a chat-ui tab
│   └── reverse-proxy/   optional TLS + auth in front of a public server
├── templates/        config to copy into a checkout's config/
│   ├── common/         the platform baseline, shared by every role
│   ├── standalone/     everything on one machine, no tenant
│   ├── server/         the shared, untenanted half
│   ├── tenant/         one tenant's user-facing half
│   └── module/         pointer at custom-module/, see below
├── custom-module/    template: attach your own code via the event bus
├── config/           THIS checkout's own config — generated, not tracked;
│                       populate it from templates/, see config/README.md
├── storage/          THIS checkout's own persisted data
└── doc/              architecture overview and the deployment guide
```

## The modules

| Module | Used by | What it does |
|---|---|---|
| `event-bus` | standalone, server | RabbitMQ, and the Docker network the deployment's modules share. Everything else talks through it |
| `backend` | **all** | The `/storage` HTTP API and the proxy for the host's microphone/camera server. One container, both facets, selected by config |
| `eliza` | standalone, server | The ELIZA dialogue engine: consumes `text_in`, publishes `text_out` |
| `vad-asr` | standalone, server | Voice activity detection feeding speech recognition. One module, since nothing wants VAD without ASR |
| `emissor` | standalone, server | Records interaction data to `storage/emissor` and serves it over REST |
| `context` | standalone, tenant | Opens and closes the conversation scenario, without which the chat UI renders nothing |
| `chat-ui` | standalone, tenant | The web chat UI — and the only input channel in a text-only deployment. Carries the Image and Monitoring tabs, both on by default |
| `monitoring` | standalone, tenant | Optional per-scenario view (image, transcript, faces), embedded as the chat UI's Monitoring tab. Leave it out and set `monitoring_url` empty together |
| `reverse-proxy` | server (optional) | Caddy: TLS on `:443` and Basic Auth over storage, EMISSOR and the RabbitMQ UI |

"Used by" is a convention, not a constraint: it says which deployments
normally include a module, not which ones are able to. `modules/event-bus` is
absent from a tenant deployment only because a tenant reaches the server's
event bus instead of running its own.

Two rules bind the list together. Anything with a `depends_on` needs the
module it names in the **same** `-f` invocation — Compose can only resolve a
health condition for a service in the same merged project, so `eliza`,
`vad-asr`, `emissor` and `reverse-proxy` must be brought up alongside
`event-bus`, and `context` and `chat-ui` alongside `backend`. And `--pull
always` matters on every command below, because `VERSION` is a moving tag
(`:latest` by default): without it Compose is content with a stale cached
image.

## Example setups

### One machine, one user, no tenants

The simplest thing that works, and a good first run. One checkout, every
module, no tenant configured anywhere:

```bash
git clone https://github.com/leolani/cltl-apps.git && cd cltl-apps
cp templates/common/config/* templates/standalone/config/* config/

./modules/backend/run_host_server.sh &   # host mic + camera; skip for text-only

docker compose --env-file config/standalone.env \
    -f modules/event-bus/docker-compose.yml \
    -f modules/backend/docker-compose.yml \
    -f modules/eliza/docker-compose.yml \
    -f modules/vad-asr/docker-compose.yml \
    -f modules/emissor/docker-compose.yml \
    -f modules/context/docker-compose.yml \
    -f modules/chat-ui/docker-compose.yml \
    -f modules/monitoring/docker-compose.yml up -d --wait --pull always
```

Nothing to edit: every module is in one Compose project, so they reach each
other by service name, and with no tenant set they all publish on bare
routing keys and bind `<topic>.#`.

### A shared server, with separate tenants

Two checkouts, because the two halves have different `config/`. The server
runs untenanted and serves everyone; each tenant is its own checkout:

```bash
# the server
git clone https://github.com/leolani/cltl-apps.git cltl-server && cd cltl-server
cp templates/common/config/* templates/server/config/* config/
docker compose --env-file config/server.env \
    -f modules/event-bus/docker-compose.yml \
    -f modules/backend/docker-compose.yml \
    -f modules/eliza/docker-compose.yml \
    -f modules/vad-asr/docker-compose.yml \
    -f modules/emissor/docker-compose.yml up -d --wait --pull always
cd ..

# one tenant
git clone https://github.com/leolani/cltl-apps.git cltl-tenant-a && cd cltl-tenant-a
cp templates/common/config/* templates/tenant/config/* config/
# config/custom.config already points at host.docker.internal, which reaches
# the server checkout above on this same machine. Set the `tenant` key
# there for a tenant other than tenant-a, or a real hostname for a server
# on another machine.
./modules/backend/run_host_server.sh &

docker compose --env-file config/tenant.env \
    -f modules/backend/docker-compose.yml \
    -f modules/context/docker-compose.yml \
    -f modules/chat-ui/docker-compose.yml \
    -f modules/monitoring/docker-compose.yml up -d --wait --pull always
```

A second tenant is another checkout with its own tenant id, its own
`CLTL_PROJECT` and its own ports. See
[`doc/DEPLOYMENT.md`](doc/DEPLOYMENT.md) for that, for a genuinely remote
server, and for putting `modules/reverse-proxy` in front of a public one.

## Ports

Chat UI: <http://localhost:8003/chatui/static/chat.html> — answer the agent's
opening consent question before anything else, or nothing responds. Beside
the conversation are two tabs, both on by default: **Image**, to upload a
picture and mark regions on it, and **Monitoring**, an iframe onto
`modules/monitoring`. See
[doc/DEPLOYMENT.md](doc/DEPLOYMENT.md#the-chat-uis-two-tabs).

| Port | Service | Set by |
|---|---|---|
| 5672 | RabbitMQ AMQP (`modules/event-bus`) | fixed |
| 15672 | RabbitMQ management UI (`eliza` / `eliza123`) | fixed |
| 8001 | Storage API (`modules/backend`) | `CLTL_BACKEND_PORT` |
| 8002 | EMISSOR data API (`modules/emissor`) | fixed |
| 8003 | Chat UI (`modules/chat-ui`) | `CLTL_CHATUI_PORT` |
| 8005 | Monitoring view (`modules/monitoring`) | `CLTL_MONITORING_PORT` |
| 8000 | Host microphone/camera server (`leoserv`, on the host, not in Docker) | fixed |

In the split layout a tenant's `backend` moves to 9001 (`CLTL_BACKEND_PORT`
in `config/tenant.env`), because 8001 is already taken by the server
checkout's own.

## Attaching your own code

[`custom-module/`](custom-module/) is a minimal template demonstrating event
bus subscription and publishing with correct tenant-id handling — the pattern
to copy for adding custom processing to a running deployment. It attaches to
a deployment; it does not build one. The fastest way to see it live is
[`custom-module/custom-module.ipynb`](custom-module/custom-module.ipynb),
which connects to the bus cell by cell.

[`doc/LEOLANI.md`](doc/LEOLANI.md) is the narrative architecture overview of
the platform and its agent variants — read that first if you want the "why"
before the "how".


## References
Feel free to use our work but cite us:
* Baez Santamaria, S., Baier, T., Kim, T., Krause, L., Kruijt, J., & Vossen, P. (2021). EMISSOR: A platform for capturing multimodal interactions as episodic memories and interpretations with situated scenario-based ontological references. In Proceedings of the First workshop Beyond Language: Multimodal Semantic Representations in conjunction with IWCS 2022
* T. Baier, S. Báez Santamaría, P. Vossen: A modular architecture for creating multimodal embodied agents with an episodic Knowledge Graph as an explainable and controllable long-term memory, in: Dialogue & Discourse Volume 14, ed. 3, pages 25-59

