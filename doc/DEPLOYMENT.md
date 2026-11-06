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
| `chat-ui` | `chatui` | The web chat UI, with the Image, Monitoring and (opt-in) Display tabs beside the conversation and a status bar below it |
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

## On Windows

Everything above runs on Windows with Docker Desktop (WSL2 backend) as the
Docker runtime. Two commands differ, because they are bash:

```powershell
Copy-Item templates\common\config\*, templates\standalone\config\* config\   # or templates\tenant
start "leoserv" modules\backend\run_host_server.cmd   # host mic + camera, in its own window
```

`docker compose ... up` itself is the same command; replace the trailing `\`
line continuations with backticks in PowerShell, or put it on one line.

`run_host_server.cmd` is the Windows counterpart of `run_host_server.sh`:
same `venv\` next to it, same install of `cltl-backend[host]`, `cltl.combot`
and `emissor` from their `ref_scenarios` branches on GitHub, same leoserv
flags. Run it on Windows itself, not inside WSL, which has no camera. It
needs, once:

- **Python 3.10–3.13** from python.org, with the `py` launcher (the
  default). PyAudio has Windows wheels, with PortAudio bundled, only up to
  3.13; on 3.14 pip would try to compile it and fail. Set `CLTL_PYTHON` to a
  `python.exe` to choose one explicitly.
- **Git for Windows** on `PATH`: pip installs `cltl-backend` by cloning it.
- **Microphone and camera access** for desktop apps: Settings → Privacy &
  security → Microphone / Camera → *Let desktop apps access…*. Without it the
  microphone cannot be opened or records only silence, and leoserv exits at startup because it cannot
  open the camera (as it does on any OS with no camera).
- **The firewall prompt** on first start, since leoserv listens on every
  interface. Docker Desktop delivers `host.docker.internal` through its own
  proxy, so the containers reach it whether or not you allow it; a tenant
  whose leoserv must be reachable from another machine needs it allowed.
- **Port 8000 free.** Hyper-V and WinNAT reserve port ranges that can include
  it, and leoserv then fails with *An attempt was made to access a socket in
  a way forbidden by its access permissions*. Check with
  `netsh int ipv4 show excludedportrange protocol=tcp`.

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
Separation is cooperative — a routing key — unless the server gives each
tenant its own RabbitMQ user. `scripts/install-server.sh` does exactly that
when given a tenant list: a user named after each tenant id, with topic
permissions that let it publish, and bind its queues, only on routing keys
ending in `.<tenant>`. Then a tenant cannot read or write another tenant's
traffic even if it tries. See
[Installing a server on a cloud VM](#installing-a-server-on-a-cloud-vm).

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
[The chat UI's tabs and status bar](#the-chat-uis-tabs-and-status-bar).

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
tenant. That is plain AMQP and HTTP with the shipped default credentials, so
only do it on a network you trust; a server reachable from the internet
belongs behind `modules/reverse-proxy`, which changes all three URLs — see
the next two sections.

Do **not** change `server_audio_url`, `server_image_url` or
`[cltl.backend.text_output] remote_url` to match. Those mean this tenant's
*own* machine, where `leoserv` listens, and stay `host.docker.internal`
however far away the server is.

## Fronting a public server with TLS and auth

The server command above is bare HTTP/AMQP with the default credentials —
correct for a server co-located with its tenants, wrong once the host is
reachable from the public internet. `modules/reverse-proxy` fixes both
protocols:

- **HTTP** goes through `caddy` on `:443`: TLS with a Let's Encrypt
  certificate for `CLTL_HOSTNAME`, dispatched by URL path to the storage API
  (`/storage/*`), the EMISSOR data API (`/emissor/*`) and RabbitMQ's
  management UI (`/rabbitmq/*`) — see `modules/reverse-proxy/Caddyfile`. One
  shared Basic Auth credential guards the first two. The management UI is
  guarded by RabbitMQ's own login instead: it authenticates every request with
  the same `Authorization` header, so a caddy credential there would lock
  everyone out.
- **AMQP** cannot go through an HTTP proxy, so RabbitMQ terminates TLS itself:
  the module adds an AMQPS listener on `:5671` that serves caddy's
  certificate (`modules/reverse-proxy/rabbitmq.conf`).

Then the module's own ports — 5672, 8001, 8002, 15672 — are bound to
`127.0.0.1`, leaving 80, 443 and 5671 as the only ways in. Port 80 serves the
ACME challenge and nothing else; it does not redirect, so that a mistyped
`http://` URL cannot leak a credential.

**Use [`scripts/install-server.sh`](#installing-a-server-on-a-cloud-vm)**
rather than doing this by hand. Beyond the bring-up command below, a public
server needs several things set in step: a generated admin password in both
`config/server.env` and `config/custom.config`, a certificate in
`storage/rabbitmq-tls/` before RabbitMQ will start at all, that certificate
re-copied whenever caddy renews it, and non-admin users for the tenants.

For the record, the bring-up is the server command plus one file:

```bash
docker compose --env-file config/server.env \
    -f modules/event-bus/docker-compose.yml \
    -f modules/backend/docker-compose.yml \
    -f modules/eliza/docker-compose.yml \
    -f modules/vad-asr/docker-compose.yml \
    -f modules/emissor/docker-compose.yml \
    -f modules/reverse-proxy/docker-compose.yml up -d --wait --pull always
```

`scripts/server-compose.sh` is exactly that command, with any arguments
appended. `modules/reverse-proxy` must stay in the same invocation as the
rest: its `depends_on: backend: condition: service_healthy` only resolves for
a service defined in the same merged project, and it overrides the
`rabbitmq` service rather than defining one. A DNS name for `CLTL_HOSTNAME`
must already resolve to this host, with port 80 reachable, before the first
`up` — caddy's ACME HTTP-01 challenge needs it.

### A tenant of a public server

A tenant then reaches everything over TLS, by name:

```ini
[cltl.event.kombu]
tenant: tenant-a
server: amqps://tenant-a:<password>@<hostname>:5671/

[cltl.backend]
storage_url: https://<user>:<password>@<hostname>/storage/

[cltl.backend.remote_storage]
storage_url: https://<user>:<password>@<hostname>/storage
```

- The `amqps://` URL is that tenant's line in the server's
  `config/tenants.urls`. With per-tenant users, `tenant` must be the same id
  as the user: the broker refuses any other routing key.
- The storage credential is the server's Basic Auth user and password, from
  its `config/credentials`.
- Use the hostname, never an IP: `KombuEventBus` checks the broker's
  certificate against the host in the URL (it needs a `cltl-combot` with
  that check, which is what passes `server_hostname`; an older one still
  verifies the certificate chain, but not the name).
- For a broker whose certificate is not from a public CA, copy the CA into
  the tenant checkout's `storage/` and set `[cltl.event.kombu] ssl_ca_certs:
  ./storage/ca.pem`. Only the three config files are mounted individually,
  but every module mounts `storage/` under its own working directory, so that
  one relative path resolves in all of them. Left empty, as in
  `default.config`, the system's CA store is used.

There is no tenant-side key for the EMISSOR data API: nothing in
`templates/tenant/` consumes one, so `/emissor/*` behind the proxy is for
direct access only (a script, a notebook).

## Installing a server on a cloud VM

`scripts/install-server.sh` turns a fresh Ubuntu 22.04 or 24.04 machine into
a public server — the server role behind `modules/reverse-proxy`, as
described above — and keeps it running across reboots. Before running it:

1. Give the machine a DNS name: an A record pointing at its public IP. Use
   a static (elastic, reserved) IP, or the name breaks when the IP changes.
2. Open inbound TCP **80, 443 and 5671** in the cloud provider's security
   group (and 22 for yourself). Nothing else needs to be reachable; the
   script does not configure a host firewall.
3. Optionally, write a tenant list: one tenant id per line, `#` comments
   allowed.

Then, on the machine:

```bash
curl -fsSL https://raw.githubusercontent.com/leolani/cltl-apps/main/scripts/install-server.sh \
    | sudo bash -s -- --hostname combot.example.org --email you@example.org \
                      --tenants tenants.txt
```

It clones this repository into `/opt/cltl-apps` (`--dir`, `--repo`, `--ref`
to change that) and runs itself from there; from an existing checkout,
`sudo scripts/install-server.sh ...` does the same in place. `--help` lists
every option. A first run takes a while: several GB of images, then the ASR
module downloads its Whisper model.

What it does:

- installs Docker Engine and the Compose plugin from Docker's apt repository,
  if `docker compose` is not already there;
- populates `config/` from `templates/common` and `templates/server`, and
  sets `CLTL_HOSTNAME`, `CLTL_ACME_EMAIL`, `VERSION` and the `127.0.0.1`
  binds in `config/server.env`;
- generates the event bus's admin password (into `config/server.env` and
  `[cltl.event.kombu] server` in `config/custom.config`) and the Basic Auth
  password (into `config/basic-auth.auth`, as a bcrypt hash);
- checks that the hostname resolves to this machine;
- creates the RabbitMQ users for the tenants (below);
- installs and starts `cltl-server.service` (the stack, via
  `scripts/server-compose.sh`) and `cltl-rabbitmq-cert.timer` (a daily
  `scripts/sync-rabbitmq-cert.sh`, which hands caddy's renewed certificate to
  RabbitMQ without restarting it);
- checks the result from this machine: the module ports are loopback-only,
  `/storage/` needs the credential, and 5671 presents a valid certificate for
  the hostname. Then it prints a summary with every URL and credential.

| File | Holds |
|---|---|
| `config/credentials` | every generated secret (root-only). Not `credentials.config`, which the platform would load into every module |
| `config/tenants.urls` | one `<id> amqps://<id>:<password>@<hostname>:5671/` line per tenant user (root-only) |
| `config/server.env`, `config/custom.config` | as in any server checkout, plus the values above |
| `storage/rabbitmq-tls/` | RabbitMQ's copy of caddy's certificate |

### Tenant users

| Installer run | RabbitMQ users |
|---|---|
| `--tenants FILE` | one per id, named after it, confined by topic permissions to routing keys ending in `.<id>` |
| no list, no tenants yet | one shared user, `tenant`: any tenant id works, and separation stays cooperative |

All tenant users can only touch the `cltl.combot` exchange and their own
broker-named queues, and none has access to the management UI. The admin
user `eliza` is used only by the server's own modules, over the Docker
network.

Tenants are added, never removed: a re-run with a longer list creates the
new users and keeps everyone else's password. A user that exists on the
broker but is in neither the list nor `config/tenants.urls` is reported, with
the `rabbitmqctl delete_user` command to remove it. To add one tenant
without the installer:

```bash
sudo scripts/add-tenant.sh tenant-c     # prints its amqps:// URL
```

### Running it

```bash
sudo scripts/server-compose.sh ps                 # or logs -f caddy, restart eliza-asr, ...
sudo systemctl status cltl-server                 # the stack, started at boot
sudo scripts/install-server.sh                    # upgrade: pull checkout + images, restart
```

A re-run needs no flags: every value given once is kept in `config/`, and
secrets are generated once and never rotated. Pass `--version <tag>` to pin
the images.

Checks after the first install, from your own machine:

```bash
curl -u <user>:<password> https://<hostname>/storage/      # anything but 401
openssl s_client -connect <hostname>:5671 -servername <hostname> -verify_return_error < /dev/null
```

The last line should end in `Verify return code: 0 (ok)`. Then bring up one
tenant against it, as [above](#a-tenant-of-a-public-server), and confirm the
agent answers in that tenant's chat UI.

`scripts/test/run.sh` runs the installer end to end in a throwaway systemd
container, with Pebble standing in for Let's Encrypt.

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

## The chat UI's tabs and status bar

The column beside the conversation is a tab strip. The Image and Monitoring
tabs are on in the shipped `templates/common/config/default.config`, the
Display tab is not. `GET /chatui/config` tells the page which ones this
deployment offers: a tab whose key is off is left out, a single remaining tab
loses the strip, and none leaves the column out. Below the conversation is a
status bar, also on.

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
`http://localhost:8005/monitoring` — so the switch to remember is the other one:
include `-f modules/monitoring/docker-compose.yml`, or the tab is there with
nothing behind it. Both layouts' commands above already include it.

To drop the tab instead, set `monitoring_url` empty in
`config/custom.config`; it is then simply absent, which is safer than a tab
whose iframe cannot load.

The URL needs the **origin and the `/monitoring` path**:
`http://localhost:<CLTL_MONITORING_PORT>/monitoring`. The chat UI frontend
appends only `/static/monitoring.html?scenario=<id>` to it, and
`cltl-monitoring` mounts its app under `/monitoring` on its own dispatcher —
exactly as the chat UI itself lives under `/chatui` — so dropping the prefix
gives the iframe a 404 while every other part of the deployment looks fine.

It must be reachable from the **browser**, so not a Compose service name and,
on a tenant, not the server's host. Keep it in step with
`CLTL_MONITORING_PORT` by hand; config files and env files do not expand each
other, so a second tenant that moves that port must override
`monitoring_url` as well.

`[cltl.monitoring] active_interval` is `0` here, meaning every scenario is
recorded whether or not anything is polling for it. The component's own
default of 15 seconds suits a camera-fed deployment; it does not suit this
one, because the tabs share a strip. While a person annotates an image
the Monitoring tab is hidden, nothing is polling, and the image they submit
would be discarded on arrival with no replay — so the tab would be blank
when they switched to it.

### Status bar

Any module can tell the person what it is doing by publishing a
`StatusEvent` (`cltl.combot.event.status`) on `[cltl.chat-ui.events]
topic_status`, which is `cltl.topic.status` in the baseline. The bar shows
the most severe open status, newest first among equals; clicking it opens a
timeline of the last `[cltl.chat-ui] status_history` events.

A status with a `key` stays until a later one with the same key replaces it,
or ends it with `resolved=True`; one without a key should carry a `ttl` in
seconds. A `persistent` status is not shown in the bar at all, but as a line
in the transcript, where it stays.

The chat UI only keeps statuses of the running scenario, and forgets them
when the scenario stops. A publisher therefore has to build its event with
`Event.for_payload(status, source=<the event it reacts to>)`, which is what
copies `scenario_id` (and the tenant) onto it; a status without one is
dropped. `custom-module/` publishes statuses while it fetches an uploaded
image, as an example.

Nothing in the platform's own module set publishes statuses yet, so until
something does the bar reads "No status". Set `topic_status` empty in
`config/custom.config` to leave it out.

### Display

The **Display** tab shows a page a module asks to have shown: a
`DisplayEvent(url, name)` (`cltl.combot.event.display`) on
`[cltl.chat-ui.events] topic_display`. The newest page is on view and named
on the tab; the earlier ones of the scenario stay in a list, up to
`[cltl.chat-ui] display_history`.

It is off in the baseline, because nothing in it publishes pages. To turn it
on, add to `config/custom.config`:

```ini
[cltl.chat-ui.events]
topic_display: cltl.topic.display
```

The URL is loaded by the **browser**, in an iframe, so it has to be one the
browser can reach. Only `http(s)` URLs on `localhost` (or `127.0.0.1`,
`::1`) are shown, plus hosts listed, comma-separated, in `[cltl.chat-ui]
display_allowed_hosts`; anything else is dropped with a warning in the chat
UI's log. A page served by a remote server needs that server's host there.
As with statuses, only events of the running scenario count, so publish with
`source=`.

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

**Monitoring tab shows "URL not found"** — `[cltl.chat-ui] monitoring_url` is
missing its `/monitoring` path. The frontend appends only
`/static/monitoring.html` to that value, so the mount prefix has to be in it:
`http://localhost:8005/monitoring`, not `http://localhost:8005`.

**Monitoring tab missing or blank** — the tab is on by default, so blank
almost always means `modules/monitoring` was left out of the `-f` list, or is
unhealthy. Otherwise confirm `monitoring_url` is browser-reachable and
matches this checkout's `CLTL_MONITORING_PORT` — a second tenant has to
repoint it by hand.

**Status bar never changes** — nothing is publishing on
`[cltl.chat-ui.events] topic_status`, which is the case for the platform's
own modules. If something is, check that it publishes on the same topic, and
with `source=` an event of the running scenario: a status without that
scenario's id is dropped without a word.

**Display tab missing** — `[cltl.chat-ui.events] topic_display` is empty,
which is the baseline. See [Display](#display).

**Display tab shows nothing although a page was published** — the URL is not
`http(s)` on `localhost` or a host in `[cltl.chat-ui] display_allowed_hosts`,
or the event carried another scenario's id. The chat UI logs `Dropped display
of <url>` for the first.

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
