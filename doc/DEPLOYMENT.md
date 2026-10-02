# Deploying cltl-apps

How to check this repository out, configure it from a template, and bring up
exactly the stacks you need — one tenant, several tenants, or just the
servers.

## One checkout per deployment

A single `cltl-apps` checkout is dedicated to exactly **one** deployment: a
server (the shared `servers/*` half), one tenant's client
(`clients/*`), or a standalone attached module. There is no shared checkout
that serves several roles at once — even two roles running on the same
physical machine (a demo server + client, or a second tenant) are two
separate `git clone`s, each configured from its own template. This is
deliberate: it means a checkout's `config/` never has to represent more than
one role, and "which deployment is this?" is never implicit in which compose
command you happen to type.

## Checkout

```bash
git clone https://github.com/leolani/cltl-apps.git
cd cltl-apps
```

Nothing else is required to run the published stacks: every service pulls
its image from `ghcr.io/leolani`. Docker and Docker Compose v2 are the only
prerequisites (Python 3.10 and PortAudio are needed only for
`clients/backend/run_host_server.sh`, the host microphone server).

## Configure from a template

`config/` starts empty (see `config/README.md`) — populate it by copying the
template matching this checkout's role:

```bash
cp templates/server/config/* config/    # this checkout is a server
# or
cp templates/client/config/* config/    # this checkout is one tenant's client
```

Then edit the copied files for this specific deployment:

- **Server checkout**: usually nothing to edit — `config/custom.config` and
  `config/servers.env` only carry optional, commented-out examples (a
  platform-wide ASR model change, an image version pin).
- **Client checkout**: edit `config/clients.env` — set `CLTL_TENANT` and this
  tenant's ports, and `CLTL_SERVER_HOST` if the server isn't co-located (see
  [A remote server](#a-remote-server)).

`templates/module/` is not a config bundle — it points at
[`custom-module/`](../custom-module/), which is fully self-contained (a third
party clones it as its own separate repo) and carries its own
`config/custom.config.example`.

## Directory model

Every `docker-compose.yml` under `servers/` and `clients/` lives two levels
below the repository root (`servers/<name>/docker-compose.yml`), so its
volume paths climb back out with `../../config` and `../../storage`. Run
`docker compose` commands from the repository root using `-f`, or `cd` into
a stack's own directory — the relative paths resolve either way.

## Config layering

Every stack in this checkout mounts the same three files from this
checkout's own flat `config/`, not a per-stack copy:

```yaml
volumes:
  - ../../config/default.config:/cltl-<name>/config/default.config:ro
  - ../../config/custom.config:/cltl-<name>/config/custom.config:ro
  - ../../config/logging.config:/cltl-<name>/config/logging.config:ro
```

`config/default.config` is this checkout's role-specific baseline — already
correct for every stack this checkout runs, because a checkout only ever
plays one role (server or client). It comes from a template
(`templates/server/` or `templates/client/`), which is where a platform-wide
change (a topic rename, say) should be made once and then re-copied — a
deployment checkout's own `config/` is a filled-in copy, not a live link back
to the template.

`config/custom.config` is for the handful of values that differ for *this
specific deployment* rather than for the role in general — a tenant id, a
monitoring URL, a per-deployment ASR tweak. The default/custom split exists
so those few edits are easy to find and diff against the template's stock
version, without needing to hand-edit the (rarely-touched) baseline.

There is no more per-stack `custom.config` (e.g. a separate one for
`clients/backend` vs. `clients/chat-ui`) — every stack in a client checkout
shares the same one, the same way every stack in a server checkout always
has. A section that's only relevant to one of the stacks (e.g. `[cltl.chat-ui]
monitoring_url` only matters to `clients/chat-ui`) is simply a harmless no-op
for the others, exactly like any other config key a given stack doesn't read.

## Tenancy

The deployment is multi-tenant: one shared server checkout serves several
isolated tenants, each its own client checkout.

```
   tenant-a checkout               server checkout            tenant-b checkout
   ────────────────────            ─────────────────         ────────────────────
   clients/chat-ui    :8003 ─────► servers/broker (rabbitmq) ◄───── clients/chat-ui    :8004
   clients/context      │         servers/eliza                   clients/context
   clients/backend    :9001          (tenant: none)                clients/backend    :9002
     tenant: tenant-a     │        servers/vad-asr                   tenant: tenant-b
                          └──────► servers/emissor ◄──────────────────┘
                                     (tenant: none)
     (CLTL_SERVER_HOST)                                        (CLTL_SERVER_HOST)
```

One broker, one exchange. The **only** thing keeping two tenants apart is the
routing key each side binds: `cltl.topic.text_in.tenant-a` against
`cltl.topic.text_in.tenant-b`, while the shared `servers/eliza` binds
`cltl.topic.text_in.#` and hears both. Separation is cooperative (a routing
key), not enforced by network isolation.

A tenant id is one lowercase routing-key word (`^[a-z0-9][a-z0-9_-]*$`) — set
it via `CLTL_TENANT` in that tenant's own checkout's `config/clients.env`.

**A second tenant is a second checkout.** Clone `cltl-apps` again, copy
`templates/client/config/*` into its `config/`, and give it its own
`CLTL_TENANT` and `CLTL_BACKEND_PORT`/`CLTL_CHATUI_PORT`/`CLTL_MONITORING_PORT`
(and `CLTL_SERVER_HOST`, pointed at the same server checkout) so its published
host ports don't collide with the first tenant's.

`servers/*` stacks never set a tenant: they are the shared half, and setting
one would scope, say, `servers/eliza`'s ELIZA to a single tenant's traffic
instead of everyone's.

## Bringing up stacks

Every command below assumes the repository root (of the relevant checkout)
as the working directory.

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

Run this from a **client checkout** (`config/` populated from
`templates/client/`), pointed at a server checkout via `CLTL_SERVER_HOST` —
co-located (same machine, default `host.docker.internal`) or remote (see
[A remote server](#a-remote-server)):

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
`clients/monitoring` has no `depends_on` of its own; it only needs the server
checkout's `servers/broker`/`servers/eliza` already running and reachable via
`CLTL_SERVER_HOST`, same as the other three. `config/clients.env` carries
`CLTL_TENANT`, `CLTL_SERVER_HOST` and every published port for this tenant —
edit it directly (this checkout only ever serves this one tenant).

### Monitoring

`clients/monitoring` is a per-scenario view (image, transcript, detected
faces) that `clients/chat-ui`'s Monitoring tab embeds via an iframe — part of
the command above by default. To run without it, drop
`-f clients/monitoring/docker-compose.yml` from the command and comment out
`CLTL_MONITORING_URL` in `config/clients.env` (an empty/unset value leaves the
tab out, which is safer than one whose iframe can't load because
`clients/monitoring` isn't actually running).

`CLTL_MONITORING_URL` must be a bare origin (`http://localhost:<CLTL_MONITORING_PORT>`,
no path) reachable from the browser, not `CLTL_SERVER_HOST` or a compose
service name — the chat UI frontend appends the page path itself — and kept
in sync with `CLTL_MONITORING_PORT` by hand, since Compose env files don't
expand other variables within themselves.

### A second tenant

A second tenant is a **second checkout** (see [Tenancy](#tenancy) above), not
a copy of one file within the same checkout:

```bash
git clone https://github.com/leolani/cltl-apps.git cltl-client-tenant-b
cd cltl-client-tenant-b
cp templates/client/config/* config/
# edit config/clients.env: distinct CLTL_TENANT, CLTL_BACKEND_PORT,
# CLTL_CHATUI_PORT, CLTL_MONITORING_PORT, CLTL_MONITORING_URL — and the same
# CLTL_SERVER_HOST as tenant-a's checkout, if pointed at the same server

docker compose --env-file config/clients.env \
    -f clients/backend/docker-compose.yml \
    -f clients/context/docker-compose.yml \
    -f clients/chat-ui/docker-compose.yml \
    -f clients/monitoring/docker-compose.yml up -d --wait --pull always
```

Distinct `CLTL_TENANT`, distinct host ports, same server. Each tenant's
client stack is its own Compose project (`cltl-platform-client-<tenant>`) in
its own checkout, so tearing one down (`docker compose down` from that
checkout) never touches the other.

### Text-only (no host microphone server)

Set the mic topic empty in `config/custom.config` (client checkout):

```ini
[cltl.backend.mic]
topic:
```

`run_host_server.sh` is then unnecessary — the chat UI becomes the sole
input channel.

### A remote server

A client checkout reaches the server via **`CLTL_SERVER_HOST`**
(`config/clients.env`) alone — nothing else. If the server checkout is on a
different machine, set `CLTL_SERVER_HOST` to that machine's reachable
hostname or IP, and ensure ports `5672` (AMQP) and `8001` (storage) are
reachable from the client machine. `CLTL_SERVER_HOST` defaults to
`host.docker.internal`, which is correct when the server checkout runs on
this same machine (a separate checkout, per [above](#one-checkout-per-deployment)).

Client stacks do not join any server-side Docker network — they never did
need to for this to work, and not needing to is what makes a genuinely
separate machine possible at all. (In earlier versions of this repository,
`clients/*` declared an `external: true` network created only by
`servers/broker` — which meant a client-only checkout with no local server
failed to start at all, before ever reaching a config value: `network
cltl-platform declared as external, but could not be found`. That
requirement has been removed; upgrading from memory of the old behavior, you
no longer need to work around it.)

## Troubleshooting

**Chat UI shows no responses** — confirm the server checkout's `servers/*` is
running and healthy (`docker compose -f servers/broker/docker-compose.yml
... ps`), that `CLTL_SERVER_HOST` in this client checkout's
`config/clients.env` actually reaches it, and that this tenant's
`CLTL_TENANT` matches across `clients/backend`, `clients/context` and
`clients/chat-ui` (they share one `config/`, so this only breaks if you hand-
edited one container's environment differently) — a mismatch means a reply
is published on a routing key nothing is listening on. Check RabbitMQ's
management UI (`http://<CLTL_SERVER_HOST>:15672`, `eliza`/`eliza123`) for
traffic on the `cltl.combot` exchange.

**No voice detection** — confirm `run_host_server.sh` (or `leoserv`) is
running on the host and reachable at `http://localhost:8000/health`, and that
`[cltl.backend.mic] topic` is set in this checkout's `config/custom.config`.

**Port already allocated** — another tenant checkout, or a previous run, is
using that `CLTL_BACKEND_PORT`/`CLTL_CHATUI_PORT`/`CLTL_MONITORING_PORT` on
this machine. Give each tenant checkout's `config/clients.env` its own set.

**"no such file" from `--env-file`** — you passed `--env-file
config/clients.env` (or `config/servers.env`) from somewhere other than this
checkout's repository root, or `config/` is still empty because you haven't
copied a template into it yet (see [Configure from a
template](#configure-from-a-template)).

**Monitoring tab missing or blank** — confirm `clients/monitoring` was
included in the `up` command and is healthy for this tenant, and that
`CLTL_MONITORING_URL` is uncommented in `config/clients.env` as a bare,
browser-reachable origin (`http://localhost:<CLTL_MONITORING_PORT>`, no path)
matching that same file's `CLTL_MONITORING_PORT` — commented out or
mismatched leaves the tab out rather than showing an error.
