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
| `emissor` | `eliza-emissor` | Records interaction data to `storage/emissor` as it arrives, serves it over REST |
| `context` | `context` | Opens and closes the conversation scenario; carries the BDI model and init intention |
| `chat-ui` | `chatui` | The web chat UI, with the Image and Monitoring tabs beside the conversation |
| `monitoring` | `monitoring` | Optional per-scenario view, embedded as the chat UI's Monitoring tab |
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
  leaving its topic empty — the camera needs its `rate` cleared too, see
  [Recording from the camera](#recording-from-the-camera).

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
| `CLTL_CONTEXT_START_DELAY` | seconds `context` waits before starting; see [The scenario-start race](#the-scenario-start-race) |
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

./modules/backend/run_host_server.sh &   # host mic + camera; skip for text-only

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

# config/custom.config: tenant: tenant-b, and monitoring_url on the new
#                       monitoring port below
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

The one port that is not purely a Compose matter is `CLTL_MONITORING_PORT`:
`[cltl.chat-ui] monitoring_url` is the URL the **browser** uses to reach it,
so moving the port and not repointing the URL leaves this tenant's Monitoring
tab iframed onto tenant-a's view. See
[The chat UI's two tabs](#the-chat-uis-two-tabs).

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

## Recording from the camera

The baseline records the host's camera, one image every five seconds:

```ini
[cltl.backend.image]
topic: cltl.topic.image
rate: 0.2
```

`rate` is images per second. The two keys gate different things, which is
worth knowing before switching either off: `rate` decides whether the
container builds a camera at all, `topic` whether the thread that records
from it runs. A rate with no topic is the awkward middle — a camera is
created and a session opened against the host server, and nothing ever reads
from it — so switch the camera off by clearing **both**, as
`templates/server/` does.

Each image is published on `cltl.topic.image`, stored under `storage/image`,
recorded by `modules/emissor` into the scenario, and shown in the chat UI's
Monitoring tab. That tab is the only place in a running deployment where you
can watch frames arrive, which is most of why both defaults changed together.
Nothing in this platform's module set *interprets* an image — see
[Image upload](#image-upload) for the same caveat about uploads.

Like the microphone, this needs `modules/backend/run_host_server.sh` on the
machine with the camera. Two things follow from that, both easy to get wrong:

- **Recording does not start until a scenario is open.** The thread logs `No
  active scenario, waiting to start recording images` once a second until
  `modules/context` opens one, and the chat UI's consent question is answered.
- **The resolution is `leoserv`'s, not `[cltl.video] resolution`.** With
  `[cltl.backend] run_server` false — which is every layout here — the
  container proxies the host server instead of opening a camera, so it *asks*
  leoserv what the resolution is rather than telling it. `[cltl.video]` is
  read only by a backend running its own server. `run_host_server.sh`
  therefore passes `--resolution VGA` explicitly, matching `[cltl.video]`:
  leoserv's own default is `NATIVE`, and on a modern webcam that stores
  full-resolution frames every five seconds for no gain downstream.

At 0.2 images per second a conversation of a few minutes is a few dozen VGA
frames, which is the trade this default is picking. Raise `rate` for a denser
record, or set both keys empty for none.

## The chat UI's two tabs

The column beside the conversation is a tab strip, and both tabs are on in
the shipped `templates/common/config/default.config`. `GET /chatui/config`
tells the page which ones this deployment offers: a tab whose key is off is
left out, a single remaining tab loses the strip, and neither leaves the
column out.

### Image upload

`[cltl.chat-ui] image_upload: True` gives the chat UI an **Image** tab: a
person uploads a picture, drags labelled rectangles over it and submits.

Submitting PUTs the pixels to `[cltl.chat-ui] image_storage_url` and
publishes **one** `ImageSignalEvent` on `[cltl.chat-ui.events] topic_image`,
carrying a region per rectangle inside the signal rather than on a separate
topic. It publishes nothing on `topic_utterance`, so **the agent does not
answer a picture** — the image is echoed into the transcript, recorded by
`modules/emissor` and shown in the Monitoring tab, and that is all. Nothing
in this platform's module set interprets it; interpreting it is what
`custom-module/` is for.

`image_storage_url` is left empty on purpose, so that it falls back to
`[cltl.backend] storage_url` — the value `modules/emissor` and
`modules/monitoring` resolve the published `cltl-storage:image/<id>`
reference against. Setting one without the other is how a scenario ends up
recording a reference to pixels nothing can fetch. A tenant repoints
`storage_url` at the server and the upload follows it, with no second value
to keep in step.

Persisting it needs one more key, which the baseline also sets:
`[cltl.emissor-data] flush_interval: 0`, writing each signal as it arrives.
At the library's own default of `-1` the pixels still reach
`storage/emissor/<scenario>/image/`, but the annotated signal that references
them stays in memory until the scenario stops cleanly — and nothing a person
can do in the chat UI stops one, so the record would simply never appear.

Note that `[cltl.chat-ui.events] topic_image` is not
`[cltl.backend.image] topic`: the latter is the host camera, which every
layout here leaves empty. The two publish the same kind of signal from
different sources.

To drop the tab, set `image_upload: False` in `config/custom.config`.

### Monitoring

`modules/monitoring` is a per-scenario view (image, transcript, detected
faces) that the chat UI's **Monitoring** tab embeds in an iframe. The tab is
on in the shipped config — `[cltl.chat-ui] monitoring_url` is
`http://localhost:8005` — so the switch to remember is the other one:
include `-f modules/monitoring/docker-compose.yml`, or the tab is there with
nothing behind it. Both layouts' commands above already include it.

To drop the tab instead, set `monitoring_url` empty in
`config/custom.config`; it is then simply absent, which is safer than a tab
whose iframe cannot load.

The URL must be a bare origin (`http://localhost:<CLTL_MONITORING_PORT>`, no
path) reachable from the **browser** — not a Compose service name and not the
server's host — because the chat UI frontend appends the page path itself.
Keep it in step with `CLTL_MONITORING_PORT` by hand; config files and env
files do not expand each other, so a second tenant that moves that port must
override `monitoring_url` as well.

`[cltl.monitoring] active_interval` is `0` here, meaning every scenario is
recorded whether or not anything is polling for it. The component's own
default of 15 seconds suits a camera-fed deployment; it does not suit this
one, because the two tabs share a strip. While a person annotates an image
the Monitoring tab is hidden, nothing is polling, and the image they submit
would be discarded on arrival with no replay — so the tab would be blank
when they switched to it.

## The scenario-start race

`modules/context` opens the conversation scenario the moment it comes up, and
nothing replays that event. `modules/emissor` subscribes a few seconds after
its own container starts, and a scenario opened while it was still
subscribing is one it never learns about: it logs

```
Skipping signal for stopped or unknown Scenario <id>
```

for every signal of that conversation and writes nothing — no `image.json`,
no `text.json`, not even a scenario folder. The conversation works normally
in the chat UI, so the only symptom is an empty `storage/emissor/`.

The two containers start together in a standalone bring-up, and which one
wins is a matter of two or three seconds. `modules/context` therefore sleeps
before starting, `CLTL_CONTEXT_START_DELAY` seconds, 10 by default. Nothing
`depends_on` context, so this only moves when context itself reports healthy;
it does not hold up the rest of the bring-up.

A `depends_on: eliza-emissor: condition: service_healthy` would be the honest
instrument, and it is not available here: a tenant runs `context` with no
local emissor, and Compose refuses to start a project whose `depends_on`
names an absent service — `required: false` does not change that. It is the
same constraint that keeps `depends_on: rabbitmq` out of `modules/backend`;
see [What depends on what](#what-depends-on-what).

Set `CLTL_CONTEXT_START_DELAY=0` to switch the delay off. That is reasonable
on a tenant, whose emissor lives in a server deployment that came up long
before. If you ever do hit the race, `docker compose … restart context`
re-opens a scenario against an already-listening emissor and the next
conversation records normally.

## Text-only (no host microphone server)

Switch off both facets that need the host server — the microphone and, since
it is on by default now, the camera:

```ini
[cltl.backend.mic]
topic:

[cltl.backend.image]
topic:
rate: 0
```

`run_host_server.sh` is then unnecessary and the chat UI becomes the sole
input channel. Clearing only the mic topic is not enough: the camera would
keep trying to reach a host server that is not running, logging a capture
failure every second. See [Recording from the
camera](#recording-from-the-camera).

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

**`Failed to capture to image` once a second** — the camera is on (it is by
default) and `run_host_server.sh` is not running on this machine, or not
reachable at `[cltl.backend] server_image_url`. Start it, or switch the
camera off as [Text-only](#text-only-no-host-microphone-server) shows.

**`No active scenario, waiting to start recording images`** — not an error.
The camera waits for `modules/context` to open a scenario and for the chat
UI's consent question to be answered.

**Nothing in `storage/emissor/` after a conversation** — usually the
scenario-start race, not a broken pipeline: `modules/emissor`'s log will show
`Skipping signal for stopped or unknown Scenario`. See
[The scenario-start race](#the-scenario-start-race).

**Monitoring tab missing or blank** — it is on by default, so blank almost
always means `modules/monitoring` was left out of the `-f` list, or is
unhealthy. Otherwise confirm `[cltl.chat-ui] monitoring_url` is a bare,
browser-reachable origin matching this checkout's `CLTL_MONITORING_PORT` —
a second tenant has to repoint it by hand.

**Image tab missing** — `[cltl.chat-ui] image_upload` is off, or
`external_input` is not `True`. Both are on in the shipped baseline, so this
is a `config/custom.config` override.

**An uploaded image appears in the transcript but nowhere else** — the agent
is not meant to answer it (see [Image upload](#image-upload)). If it is also
missing from the Monitoring tab and from `storage/emissor/`, the pixels never
reached storage: check `[cltl.chat-ui] image_storage_url`, which should be
empty so that it falls back to `[cltl.backend] storage_url`, and that
`modules/backend` is reachable from the chat UI container.

**Unexpanded environment variable in [section].key** — a `$VAR` in a config
value with nothing in the environment to expand it. The platform warns and
carries on with the literal text, so this is a warning you want to act on:
the usual cause is a value left as `$CLTL_TENANT` where a literal tenant id
belongs.
