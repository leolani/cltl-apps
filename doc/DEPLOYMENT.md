# Deploying cltl-apps

How to check this repository out, mount its configuration, and bring up
exactly the stacks you need — one tenant, several tenants, or just the
servers.

## Checkout

```bash
git clone https://github.com/leolani/cltl-apps.git
cd cltl-apps
```

Nothing else is required to run the published stacks: every service pulls
its image from `ghcr.io/leolani`. Docker and Docker Compose v2 are the only
prerequisites (Python 3.10 and PortAudio are needed only for
`clients/backend/run_host_server.sh`, the host microphone server).

## Directory model

Every `docker-compose.yml` under `servers/` and `clients/` lives two levels
below the repository root (`servers/<name>/docker-compose.yml`), so its
volume paths climb back out with `../../config` and `../../storage`. Run
`docker compose` commands from the repository root using `-f`, or `cd` into
a stack's own directory — the relative paths resolve either way.

## Config layering

Every stack mounts three files, not one directory — deliberately:

```yaml
volumes:
  - ../../config/default.config:/cltl-<name>/config/default.config:ro
  - ./config/custom.config:/cltl-<name>/config/custom.config:ro       # stack-local
  - ../../config/logging.config:/cltl-<name>/config/logging.config:ro
```

`config/default.config` (root) is the shared baseline — topic names, audio
settings, everything that is the same for every container in the
deployment. It is one file so a topic rename only happens once.

`config/custom.config` is **stack-local** (`servers/eliza/config/custom.config`,
`clients/chat-ui/config/custom.config`, …), for the handful of things that
are *not* the same everywhere:

- **Role**: `servers/eliza`'s `eliza-backend` runs `storage_main.py` and
  needs `[cltl.backend]` configured as a store; `clients/backend` proxies the
  host's microphone/camera server instead and needs the same section
  configured completely differently. The root default carries the storage
  role; `clients/backend/config/custom.config` overrides it.
- **Tenant id**: every `clients/*` stack's `config/custom.config` sets
  `[cltl.event.kombu] tenant: $CLTL_TENANT`. `servers/*` stacks carry no such
  override — they stay untenanted, shared by every tenant. See
  [Tenancy](#tenancy).

If you need a setting to differ for one specific tenant rather than one
role, add it to that tenant's own `clients/*/config/custom.config` invocation
— or, since compose config paths are just files, point `CLTL_TENANT`'s stack
at a copy of the directory with its own override. The common case (same
config, different tenant id via environment) needs no copy at all — that is
what `$CLTL_TENANT` interpolation is for.

`config/custom.config` (root) is for changes that should apply to *every*
stack — a platform-wide ASR model change, for example.

Separately, `config/servers.env` and `config/clients.env` are **Docker
Compose** variable files (`--env-file`), not app config — they supply the
`CLTL_TENANT`/host-port values a compose command interpolates before a
container ever starts, as opposed to `default.config`/`custom.config`, which
are read by the running container itself. See
[Bringing up stacks](#bringing-up-stacks).

## Tenancy

The deployment is multi-tenant: one shared `servers/` half serves several
isolated groups of users, and each `clients/` stack belongs to one of them.

```
   tenant-a                        shared servers/           tenant-b
   ────────────────────            ─────────────────         ────────────────────
   clients/chat-ui    :8003 ─────► servers/broker (rabbitmq) ◄───── clients/chat-ui    :8004
   clients/context                 servers/eliza                   clients/context
   clients/backend    :9001          (tenant: none)                clients/backend    :9002
     tenant: tenant-a               servers/vad-asr                  tenant: tenant-b
                                     servers/emissor
                                       (tenant: none)
```

One broker, one exchange, one Docker network (`cltl-platform`, created by
`servers/broker`). The **only** thing keeping two tenants apart is the
routing key each side binds: `cltl.topic.text_in.tenant-a` against
`cltl.topic.text_in.tenant-b`, while the shared `servers/eliza` binds
`cltl.topic.text_in.#` and hears both. Nothing here is separated by the
network — separation is cooperative (a routing key), not enforced.

A tenant id is one lowercase routing-key word (`^[a-z0-9][a-z0-9_-]*$`) — set
it via `CLTL_TENANT` in `config/clients.env` (or a per-tenant copy of it) for
that tenant, and give each tenant its own `CLTL_BACKEND_PORT`/`CLTL_CHATUI_PORT`/
`CLTL_MONITORING_PORT` so their published host ports don't collide.

`servers/*` stacks never set a tenant: they are the shared half, and setting
one would scope, say, `servers/eliza`'s ELIZA to a single tenant's traffic
instead of everyone's.

## Bringing up stacks

Every command below assumes the repository root as the working directory.

### Just the servers (no client, e.g. for `custom-module` development)

```bash
docker compose --env-file config/servers.env \
                -f servers/broker/docker-compose.yml \
                -f servers/eliza/docker-compose.yml \
                -f servers/vad-asr/docker-compose.yml \
                -f servers/emissor/docker-compose.yml up -d --wait --pull always
```

`--pull always` matters because `VERSION` (in `config/servers.env`) is a
configurable, moving tag — without it, Compose is happy with whatever image
is already cached locally rather than re-checking the registry for that tag.

Any subset of `servers/eliza`, `servers/vad-asr`, `servers/emissor` works,
as long as `servers/broker` is included in the same invocation — the others
depend on `rabbitmq` being healthy, which Compose can only resolve for a
service defined in the same merged project. `config/servers.env` currently
has nothing required in it — every `servers/*` image tag already defaults to
`:latest` — it exists so pinning `VERSION` is one edit instead of an inline
env var on every command; `--env-file` works the same with nothing set.

### One tenant, full stack

`servers/broker` must already be running (its network is `external: true` to
every other stack). **Do not** also list `servers/broker/docker-compose.yml`
in the command below: none of `clients/backend`, `clients/context`,
`clients/chat-ui` or `clients/monitoring` `depends_on` the `rabbitmq` service
directly (only `servers/eliza`, `servers/vad-asr` and `servers/emissor` do,
which is why broker's file belongs in *that* command above), and a client
stack's project name (`cltl-platform-client-<tenant>`) differs from broker's
(`cltl-platform`) — Compose would try to re-create the already-running
`rabbitmq` container under the client project and fail with a
container-name conflict.

```bash
cd clients/backend && ./run_host_server.sh &   # host mic server; skip for text-only
cd ../..

docker compose --env-file config/clients.env \
    -f clients/backend/docker-compose.yml \
    -f clients/context/docker-compose.yml \
    -f clients/chat-ui/docker-compose.yml \
    -f clients/monitoring/docker-compose.yml up -d --wait --pull always
```

`--pull always` matters here for the same reason as the servers command
above — `VERSION` is a configurable, moving tag, so every `up` should
re-check the registry rather than trust whatever is cached locally.

`clients/context` and `clients/chat-ui` still `depends_on: backend:
condition: service_healthy` — that resolves because `clients/backend`'s
service (named `backend`) is defined in this same invocation.
`clients/monitoring` has no `depends_on` of its own; it only needs
`servers/broker`/`servers/eliza` already running, same as the other three.
`config/clients.env` carries `CLTL_TENANT` and every published port for this
tenant — edit it (or use a copy, see below) rather than passing those inline.

### Monitoring

`clients/monitoring` is a per-scenario view (image, transcript, detected
faces) that `clients/chat-ui`'s Monitoring tab embeds via an iframe — part of
the command above by default. To run without it, drop
`-f clients/monitoring/docker-compose.yml` from the command and comment out
`CLTL_MONITORING_URL` in `config/clients.env` (an empty/unset value leaves the
tab out, which is safer than one whose iframe can't load because
`clients/monitoring` isn't actually running).

`CLTL_MONITORING_URL` must be a bare origin (`http://localhost:<CLTL_MONITORING_PORT>`,
no path) reachable from the browser, not the compose service name — the chat
UI frontend appends the page path itself — and kept in sync with
`CLTL_MONITORING_PORT` by hand, since Compose env files don't expand other
variables within themselves.

### A second tenant, same host

Copy `config/clients.env` (e.g. to `config/clients-tenant-b.env`) and edit
`CLTL_TENANT`, `CLTL_BACKEND_PORT`, `CLTL_CHATUI_PORT`, `CLTL_MONITORING_PORT`
and `CLTL_MONITORING_URL` to distinct values, then:

```bash
docker compose --env-file config/clients-tenant-b.env \
    -f clients/backend/docker-compose.yml \
    -f clients/context/docker-compose.yml \
    -f clients/chat-ui/docker-compose.yml \
    -f clients/monitoring/docker-compose.yml up -d --wait --pull always
```

Distinct `CLTL_TENANT`, distinct host ports, same servers/ half. Each
tenant's client stack is its own Compose project (`cltl-platform-client-<tenant>`),
so `docker compose -p cltl-platform-client-tenant-a ... down` tears down one
tenant without touching the other.

### Text-only (no host microphone server)

Set the mic topic empty in `clients/backend/config/custom.config`:

```ini
[cltl.backend.mic]
topic:
```

`run_host_server.sh` is then unnecessary — the chat UI becomes the sole
input channel.

### A remote server

If `servers/` runs on a different machine, point `config/default.config`'s
`[cltl.event.kombu] server` and `[cltl.backend.remote_storage] storage_url`
at that machine's address instead of the in-network `rabbitmq`/`eliza-backend`
hostnames, and ensure ports 5672 and 8001 are reachable from the client
machine.

## Troubleshooting

**Chat UI shows no responses** — confirm `servers/*` is running and healthy
(`docker compose -f servers/broker/docker-compose.yml ... ps`), and that this
tenant's `CLTL_TENANT` (in `config/clients.env`) matches across
`clients/backend`, `clients/context` and `clients/chat-ui` — a mismatch means
a reply is published on a routing key nothing is listening on. Check
RabbitMQ's management UI (<http://localhost:15672>, `eliza`/`eliza123`) for
traffic on the `cltl.combot` exchange.

**No voice detection** — confirm `run_host_server.sh` (or `leoserv`) is
running on the host and reachable at `http://localhost:8000/health`, and that
`[cltl.backend.mic] topic` is set in `clients/backend/config/custom.config`.

**Port already allocated** — another tenant, or a previous run, is using
that `CLTL_BACKEND_PORT`/`CLTL_CHATUI_PORT`/`CLTL_MONITORING_PORT` in
`config/clients.env`. Give each tenant its own copy with a distinct set.

**"no such file" from `--env-file`** — you passed `--env-file
config/clients.env` (or `config/servers.env`) from somewhere other than the
repository root, or renamed/moved the file. Compose refuses to start rather
than silently continuing with nothing set; re-run from the repository root or
fix the path.

**Monitoring tab missing or blank** — confirm `clients/monitoring` was
included in the `up` command and is healthy for this tenant, and that
`CLTL_MONITORING_URL` is uncommented in `config/clients.env` as a bare,
browser-reachable origin (`http://localhost:<CLTL_MONITORING_PORT>`, no path)
matching that same file's `CLTL_MONITORING_PORT` — commented out or
mismatched leaves the tab out rather than showing an error.
