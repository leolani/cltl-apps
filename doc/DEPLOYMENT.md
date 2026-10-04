# Deploying cltl-apps

There are two separate decisions here, and this guide is split along them:

- **[Part 1 — Modules](#part-1--modules)**: what each module is, what it
  needs from the others, and how it is configured. Nothing in Part 1 depends
  on how your deployment is laid out.
- **[Part 2 — Deployments](#part-2--deployments)**: the layouts you can build
  from those modules — everything on one machine, or a shared server with one
  tenant deployment per person — and what each one puts in `config/`.

The distinction matters because a module is not inherently a "server" or a
"tenant" module. `modules/backend` is the same image and the same compose
file in every layout; whether it holds the audio/image store or forwards to
another backend that does is a value in `config/custom.config`. Nothing in
`modules/` knows which layout it is part of.

---

# Part 1 — Modules

Each directory under `modules/` holds one `docker-compose.yml`, added to a
bring-up command with `-f`. They are deliberately uniform: every one of them
interpolates the same project name, declares the same network, mounts the
same three config files, and sets the same `extra_hosts`.

## The modules

| Module | Services | What it does |
|---|---|---|
| `event-bus` | `rabbitmq` | RabbitMQ, plus the Docker network the deployment's modules share |
| `backend` | `backend` | The `/storage` HTTP API and the proxy for the host's microphone/camera server |
| `eliza` | `eliza-eliza` | The ELIZA dialogue engine: consumes `text_in`, publishes `text_out` |
| `vad-asr` | `eliza-vad`, `eliza-asr` | Voice activity detection feeding speech recognition |
| `emissor` | `eliza-emissor` | Records interaction data to `storage/emissor`, serves it over REST |
| `context` | `context` | Opens and closes the conversation scenario; carries the BDI model and init intention |
| `chat-ui` | `chatui` | The web chat UI |
| `monitoring` | `monitoring` | Optional per-scenario view, embedded as a chat-ui tab |
| `reverse-proxy` | `caddy` (+ a `rabbitmq` override) | Optional TLS and Basic Auth in front of a public server |

### `modules/backend` is one module, not two

It used to be two: a `backend` for tenants and an `eliza-backend` inside
`modules/eliza` for servers. They were always the same `cltl-backend` image.
`main.py`'s `BackendContainer` extends `StorageContainer`, so a single
container runs both facets:

- **storage** — the `/storage` HTTP API, always mounted. With
  `[cltl.backend] audio_storage`/`image_storage` set to `local` it holds the
  store itself; set to `remote` it forwards to another backend's
  `storage_url`.
- **hardware I/O** — microphone, camera and text-to-speech, proxied from the
  host's microphone/camera server (`leoserv`). Each facet is switched off by
  leaving its topic empty.

So "a storage server" and "a tenant's audio proxy" are two configurations of
one module, which is why there is one directory for it.

## What depends on what

Two rules, and they are the only ordering constraints:

**A `depends_on` needs its target in the same `-f` invocation.** Compose can
only resolve `condition: service_healthy` for a service defined in the same
merged project. So:

- `eliza`, `vad-asr`, `emissor` and `reverse-proxy` each depend on
  `rabbitmq`, and must be brought up alongside `modules/event-bus`.
- `context` and `chat-ui` each depend on `backend`, and must be brought up
  alongside `modules/backend`.
- `monitoring` and `backend` declare no `depends_on` at all, so either can be
  brought up alone. `backend`'s lack of one is deliberate: a tenant
  deployment runs it with no local event bus, and a `depends_on` naming an
  absent service would make Compose refuse to start.

**`--pull always` belongs on every command.** `VERSION` is a configurable,
moving tag (`:latest` by default). Without `--pull always`, Compose is
content with whatever image is already cached locally, which silently stops
tracking a tag someone keeps pushing to. It re-checks the registry on every
`up`, costing a few seconds even when nothing has changed.

## Paths and the `-f` order gotcha

Every `modules/<name>/docker-compose.yml` sits exactly two levels below the
repository root, so its volume paths climb back out with `../../config` and
`../../storage`. Run `docker compose` from the repository root with `-f`, or
`cd` into a module's own directory — the relative paths resolve either way.

One real trap: **Compose resolves relative bind-mount paths against the
first `-f` file's directory, not each file's own.** The modules get away with
`../../` only because they all sit at the same depth. `modules/reverse-proxy`
mounts files from its own directory, so it has to spell them
repo-root-relative (`../../modules/reverse-proxy/Caddyfile`) to survive any
`-f` ordering.

## How a module is configured

Every module mounts the same three files from this checkout's own flat
`config/` — not a per-module copy:

```yaml
volumes:
  - ../../config/default.config:/cltl-<name>/config/default.config:ro
  - ../../config/custom.config:/cltl-<name>/config/custom.config:ro
  - ../../config/logging.config:/cltl-<name>/config/logging.config:ro
```

`default.config` is the platform baseline, identical in every deployment —
it comes from `templates/common/` and is where a platform-wide change (a
topic rename, an ASR default) is made once. `custom.config` is layered on
top of it by key: the platform reads one `ConfigParser` over both, so you
add only the sections and keys you want to change and everything else falls
through.

There is no per-module `custom.config`. A section relevant to only one module
(`[cltl.chat-ui] monitoring_url`, say) is simply a harmless no-op for the
others, exactly like any config key a given module does not read.

Values may contain `$VAR`, expanded from the container's environment. Prefer
literals: expansion uses `safe_substitute` and only **warns** when a variable
is unset, so a forgotten `CLTL_TENANT` becomes the literal routing-key word
`$CLTL_TENANT` rather than an error.

### Topic names, and what an empty one means

An empty topic is the platform's idiom for "this is not in this deployment",
not a missing value — `[cltl.backend.mic] topic:` is how you switch the
microphone off. Read topic names from config and never hardcode them: the
`default.config` shipped inside each component image uses legacy names, so a
module that falls through to its own shipped defaults starts healthy and
connected to nothing.

One wart to know about: `cltl-backend`'s `BackendService._start_tts` does not
check whether its topic is set, unlike the microphone and camera paths. An
empty `[cltl.backend.tts] topic` therefore still creates a consumer thread,
bound to a routing key that matches nothing. It is inert — no event ever
arrives and no audio device is opened — but it is why a server deployment's
backend shows one idle worker.

### What goes in the env file instead

The `<role>.env` file passed with `--env-file` carries only what Compose
needs *before any container exists*:

| Variable | Why Compose needs it |
|---|---|
| `VERSION` | image tag |
| `CLTL_PROJECT` | Compose project name, and the network name derived from it |
| `CLTL_BACKEND_PORT`, `CLTL_CHATUI_PORT`, `CLTL_MONITORING_PORT` | published host ports |
| `CLTL_STORAGE_BIND`, `CLTL_EMISSOR_BIND`, `CLTL_RABBITMQ_MGMT_BIND` | published bind addresses |
| `CLTL_HOSTNAME`, `CLTL_ACME_EMAIL` | `reverse-proxy` only; caddy will not start without them |

Everything the application itself reads — the tenant, where the event bus and
storage are, which facets are on — lives in `config/custom.config`.

`CLTL_PROJECT` also names the Docker network, so two deployments on one
machine are separated by changing that one value (and their ports). Its
default, `cltl-platform`, is the network name `custom-module/` joins as an
external network.

---

# Part 2 — Deployments

## Choosing a layout

| | Checkouts | Tenants | Use it when |
|---|---|---|---|
| [Standalone](#standalone-one-machine-no-tenants) | 1 | none | One machine, one user. Demos, development, a single-person agent |
| [Server + tenant](#server--tenant) | 2 | 1 | The server's work (ASR, dialogue, storage) belongs on a different machine from the person talking |
| [Multi-tenant](#a-second-tenant) | 1 + n | n | Several people, each with their own conversation, sharing one server |

A checkout's `config/` describes exactly one deployment, which is why the
split layouts need more than one checkout: the server half and the tenant
half disagree about where the event bus is and whether storage is local, and
those are the same keys in the same file. Two roles on one physical machine
are still two checkouts.

## Configure a checkout

`config/` starts empty (see [`../config/README.md`](../config/README.md)).
Populate it with the shared baseline plus exactly one role:

```bash
cp templates/common/config/* templates/standalone/config/* config/
# or templates/server/config/*
# or templates/tenant/config/*
```

Then edit the copied files for this specific deployment:

- **Standalone** — nothing to edit. The baseline already describes it.
- **Server** — usually nothing to edit; `config/server.env` has no required
  values unless you add `reverse-proxy`.
- **Tenant** — edit `config/custom.config`: the tenant id, and the server's
  address if it is not on this machine. Then `config/tenant.env` for this
  tenant's ports and `CLTL_PROJECT`.

`templates/module/` is not a config bundle — it points at
[`../custom-module/`](../custom-module/), which is self-contained and carries
its own `config/custom.config.example`.

## Standalone: one machine, no tenants

Every module in one Compose project, nothing repointed, no tenant anywhere:

```bash
cp templates/common/config/* templates/standalone/config/* config/

./modules/backend/run_host_server.sh &   # host mic server; skip for text-only

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

Because every module shares one project and one network, they reach each
other by Compose service name — `rabbitmq:5672` for the event bus,
`http://backend:8000/storage/` for storage. No host ports are involved in
the wiring, and `CLTL_*_BIND=127.0.0.1` in `config/standalone.env` can take
the published ones off every interface but loopback.

With no tenant configured, every module publishes on a bare routing key and
binds `<topic>.#`, which matches it. This is self-consistent only as long as
*nothing* sets a tenant — see [Tenancy](#tenancy) for why a half-configured
tenant fails silently.

`modules/context` logs `The BDIService can only run in a tenant context!`
once per event here. It is a warning, not an error: processing continues
normally, and a standalone deployment has no second tenant to be confused
with.

## Server + tenant

The server half is untenanted and shared; each tenant half carries one
tenant id. Two checkouts, each configured from its own template.

### The server

```bash
cp templates/common/config/* templates/server/config/* config/

docker compose --env-file config/server.env \
    -f modules/event-bus/docker-compose.yml \
    -f modules/backend/docker-compose.yml \
    -f modules/eliza/docker-compose.yml \
    -f modules/vad-asr/docker-compose.yml \
    -f modules/emissor/docker-compose.yml up -d --wait --pull always
```

Any subset works as long as `modules/event-bus` is in the same invocation.
`modules/backend` is what each tenant forwards its storage to, so leave it in
unless you have another store. `config/server.env` has nothing required in
it — every image tag already defaults to `:latest` — it exists so pinning
`VERSION` is one edit rather than an inline variable on every command.

What makes this a *server* is four keys in `config/custom.config`: the
microphone, camera and TTS topics are empty, and `text_output.remote_url` is
empty. Storage stays local and the tenant stays empty.

### A tenant

Run this from a tenant checkout, pointed at the server:

```bash
cp templates/common/config/* templates/tenant/config/* config/
# config/custom.config: set the tenant, and the server's host if it is not
# this machine. config/tenant.env: this tenant's ports and CLTL_PROJECT.

./modules/backend/run_host_server.sh &   # host mic server; skip for text-only

docker compose --env-file config/tenant.env \
    -f modules/backend/docker-compose.yml \
    -f modules/context/docker-compose.yml \
    -f modules/chat-ui/docker-compose.yml \
    -f modules/monitoring/docker-compose.yml up -d --wait --pull always
```

A tenant reaches the server over published host ports — AMQP (5672) and
storage (8001) — and joins no server-side Docker network. Not needing to is
what makes a genuinely separate machine possible.

> In earlier versions of this repository the tenant stacks declared an
> `external: true` network created only by the event bus, so a tenant-only
> checkout with no local server failed before reading a single config value:
> `network cltl-platform declared as external, but could not be found`. That
> requirement is gone; if you remember working around it, you no longer need
> to.

`config/tenant.env` sets `CLTL_PROJECT` and the ports rather than leaving
them at their defaults, because a tenant shares a machine with the server it
talks to: 8001 is already taken by the server's storage API, which is why the
tenant's backend is published on 9001.

## Tenancy

One event bus, one exchange. The only thing keeping two tenants apart is the
routing key each side binds.

```
   tenant-a checkout               server checkout            tenant-b checkout
   ────────────────────            ─────────────────         ────────────────────
   chat-ui    :8003 ─────────► event bus (rabbitmq) ◄────────  chat-ui    :8004
   context      │              backend  (tenant: none)         context
   backend    :9001 │          eliza    (tenant: none)         backend    :9002
     tenant: tenant-a │        vad-asr                           tenant: tenant-b
                      └──────► emissor ◄──────────────────────────┘
```

A tenanted module binds `<topic>.<tenant>` and hears only that tenant. An
untenanted one binds `<topic>.#`, which matches both a bare routing key and
any tenant's — which is how the shared `eliza` answers everybody.

The asymmetry is the thing to remember:

| Publisher | Subscriber | Meet? |
|---|---|---|
| untenanted (bare key) | untenanted (`<topic>.#`) | yes |
| `tenant-a` | untenanted (`<topic>.#`) | yes |
| `tenant-a` | `tenant-a` | yes |
| untenanted (bare key) | `tenant-a` | **no — silently** |

So a tenant is all-or-nothing per deployment. Set it everywhere (a tenant
deployment) or nowhere (standalone, or the server half); a deployment where
only some modules have one drops messages with nothing in the logs to say so.
Separation is cooperative — a routing key — not enforced by network
isolation.

A tenant id is one lowercase routing-key word (`^[a-z0-9][a-z0-9_-]*$`), set
as `[cltl.event.kombu] tenant` in that checkout's `config/custom.config`.

Replies find their way back without the server knowing any tenant: an event
built with `Event.for_payload(..., source=event)` inherits the source event's
tenant, so ELIZA's answer to tenant-a is published on tenant-a's routing key
even though ELIZA itself is untenanted.

## A second tenant

A second tenant is a second checkout, not a second value in one file:

```bash
git clone https://github.com/leolani/cltl-apps.git cltl-tenant-b
cd cltl-tenant-b
cp templates/common/config/* templates/tenant/config/* config/

# config/custom.config: tenant: tenant-b
# config/tenant.env:    CLTL_PROJECT=cltl-platform-tenant-b
#                       distinct CLTL_BACKEND_PORT / CLTL_CHATUI_PORT /
#                       CLTL_MONITORING_PORT

docker compose --env-file config/tenant.env \
    -f modules/backend/docker-compose.yml \
    -f modules/context/docker-compose.yml \
    -f modules/chat-ui/docker-compose.yml \
    -f modules/monitoring/docker-compose.yml up -d --wait --pull always
```

Distinct tenant, distinct `CLTL_PROJECT`, distinct host ports, same server.
Each tenant is its own Compose project on its own network, so tearing one
down never touches the other.

## A remote server

A tenant reaches the server through four values in its own
`config/custom.config`, all of which ship as `host.docker.internal` (correct
when the server is a separate checkout on this same machine):

```ini
[cltl.event.kombu]
server: amqp://eliza:eliza123@<server-host>:5672/

[cltl.backend]
storage_url: http://<server-host>:8001/storage/

[cltl.backend.remote_storage]
storage_url: http://<server-host>:8001/storage
```

For a server on another machine, replace `<server-host>` with its reachable
hostname or IP and make sure ports 5672 and 8001 are reachable from the
tenant.

Do **not** change `server_audio_url`, `server_image_url` or
`[cltl.backend.text_output] remote_url` to match. Those mean this tenant's
*own* machine, where `leoserv` listens, and stay `host.docker.internal`
however far away the server is.

## Fronting a public server with TLS and auth

The server command above is bare HTTP/AMQP with no authentication — correct
for a server co-located with its tenants, wrong once the host is reachable
from the public internet. `modules/reverse-proxy` adds `caddy`, terminating
TLS on `:443` and Basic-Auth-gating the storage API, the EMISSOR data API and
RabbitMQ's management UI, dispatched by URL path (`/storage/*`, `/emissor/*`,
`/rabbitmq/*` — see `modules/reverse-proxy/Caddyfile`). It is optional and
additive: leave it out and the deployment behaves exactly as before.

```bash
docker run --rm caddy:2.8-alpine caddy hash-password --plaintext '<password>'
echo '<user> <hash>' > config/basic-auth.auth   # one shared credential, every route

# set CLTL_HOSTNAME and CLTL_ACME_EMAIL in config/server.env first — caddy
# refuses to start without them

docker compose --env-file config/server.env \
    -f modules/event-bus/docker-compose.yml \
    -f modules/backend/docker-compose.yml \
    -f modules/eliza/docker-compose.yml \
    -f modules/vad-asr/docker-compose.yml \
    -f modules/emissor/docker-compose.yml \
    -f modules/reverse-proxy/docker-compose.yml up -d --wait --pull always
```

`modules/reverse-proxy` must stay in the same invocation as the rest: its
`depends_on: backend: condition: service_healthy` only resolves for a service
defined in the same merged project. A DNS name for `CLTL_HOSTNAME` must
already resolve to this host, with port 80 reachable, before the first `up` —
Caddy's ACME HTTP-01 challenge needs it. Watch
`docker compose logs -f caddy`.

The result: `https://<hostname>/storage/`, `https://<hostname>/emissor/` and
`https://<hostname>/rabbitmq/` replace `http://<host>:8001/...`, `:8002/...`
and `:15672` for anything reaching this deployment from outside. Once that
works, also set `CLTL_STORAGE_BIND`, `CLTL_EMISSOR_BIND` and
`CLTL_RABBITMQ_MGMT_BIND` to `127.0.0.1` in `config/server.env` and re-run
`up`, so the raw ports stop being reachable from outside the host at all.

AMQP (5672) is untouched by all of this: its auth is in-protocol SASL, so no
HTTP reverse proxy can add TLS or auth to it, and stock caddy cannot proxy
raw TCP. It keeps its plain binding regardless.

A tenant pointed at a proxied server needs path-prefixed HTTPS URLs, which
`<server-host>` and a port cannot express — override both storage keys in
the tenant's `config/custom.config`:

```ini
[cltl.backend]
storage_url: https://<hostname>/storage/

[cltl.backend.remote_storage]
storage_url: https://<hostname>/storage
```

Embed the shared credential (`https://<user>:<password>@<hostname>/storage/`)
if the tenant should authenticate without being prompted. One caveat either
way: `CltlAudioAdapter.send`
(`cltl-backend/src/cltl/backend/source/client_source.py`) rewrites this URL
before handing it to `requests` and drops any userinfo in the process, so a
tenant that uploads its own audio across the proxy gets a silent `401`
instead of an authenticated request — a known upstream gap.

There is no tenant-side key for the EMISSOR data API: nothing in
`templates/tenant/` consumes one, so `/emissor/*` behind the proxy is for
direct access only (a script, a notebook).

## Monitoring

`modules/monitoring` is a per-scenario view (image, transcript, detected
faces) that `modules/chat-ui`'s Monitoring tab embeds in an iframe. Two
independent switches:

- include `-f modules/monitoring/docker-compose.yml` to run it;
- set `[cltl.chat-ui] monitoring_url` in `config/custom.config` to show the
  tab.

Leave the URL empty (the shipped default) and the tab is simply absent, which
is safer than a tab whose iframe cannot load. It must be a bare origin
(`http://localhost:<CLTL_MONITORING_PORT>`, no path) reachable from the
**browser** — not a Compose service name and not the server's host — because
the chat UI frontend appends the page path itself. Keep it in step with
`CLTL_MONITORING_PORT` by hand; config files and env files do not expand each
other.

## Text-only (no host microphone server)

Set the mic topic empty in `config/custom.config`:

```ini
[cltl.backend.mic]
topic:
```

`run_host_server.sh` is then unnecessary and the chat UI becomes the sole
input channel.

## Troubleshooting

**Chat UI shows no responses** — check, in order:

1. The modules that answer are running and healthy (`docker compose -f ... ps`).
2. In a split layout, `[cltl.event.kombu] server` in this checkout's
   `config/custom.config` actually reaches the server's event bus.
3. The tenant is set consistently: every module in a checkout shares one
   `config/`, so this only breaks if you hand-edited a container's
   environment, or if one half of a split deployment has a tenant and the
   other does not — see the table in [Tenancy](#tenancy), where exactly one
   combination fails silently.

RabbitMQ's management UI (`http://<host>:15672`, `eliza`/`eliza123`) shows
traffic on the `cltl.combot` exchange, which is the fastest way to see
whether messages are being published on a routing key nothing binds.

**No voice detection** — confirm `run_host_server.sh` (or `leoserv`) is
running on the host and reachable at `http://localhost:8000/health`, and that
`[cltl.backend.mic] topic` is set in `config/custom.config`.

**Port already allocated** — another checkout, or a previous run, holds that
port. Give each checkout its own `CLTL_BACKEND_PORT` / `CLTL_CHATUI_PORT` /
`CLTL_MONITORING_PORT`.

**`network <name> ... incorrect label`, or two deployments interfering** —
two checkouts are sharing a `CLTL_PROJECT`, and so a network. Give each its
own value in its env file.

**"no such file" from `--env-file`** — you ran it from somewhere other than
the checkout's repository root, or `config/` is still empty because no
template has been copied into it yet.

**`depends_on` names an undefined service** — a module was brought up without
the one it depends on in the same `-f` invocation. See
[What depends on what](#what-depends-on-what).

**Monitoring tab missing or blank** — confirm `modules/monitoring` was
included and is healthy, and that `[cltl.chat-ui] monitoring_url` is a bare,
browser-reachable origin matching `CLTL_MONITORING_PORT`.

**Unexpanded environment variable in [section].key** — a `$VAR` in a config
value with nothing in the environment to expand it. The platform warns and
carries on with the literal text, so this is a warning you want to act on:
the usual cause is a value left as `$CLTL_TENANT` where a literal tenant id
belongs.
