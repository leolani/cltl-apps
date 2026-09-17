# The deployment

The agent this template attaches *to*. None of it is this template, and none of
it needs the platform's source code — it is three published images, RabbitMQ,
and two configuration files.

It is **multi-tenant**, which means it comes in two halves: one shared server,
and one stack per tenant. Read [`tenancy.md`](tenancy.md) for why; this page is
how to run it.

```bash
# the shared half — broker + one ELIZA for everyone
docker compose -f deployment/server.compose.yml up -d

# one stack per tenant
CLTL_TENANT=tenant-a CLTL_CHATUI_PORT=8000 \
    docker compose -f deployment/tenant.compose.yml up -d
CLTL_TENANT=tenant-b CLTL_CHATUI_PORT=8001 \
    docker compose -f deployment/tenant.compose.yml up -d
```

| | |
|---|---|
| tenant-a chat UI | <http://127.0.0.1:8000/chatui/static/chat.html> |
| tenant-b chat UI | <http://127.0.0.1:8001/chatui/static/chat.html> |
| Broker (AMQP) | `amqp://leolani:leolani@127.0.0.1:5672/` |
| RabbitMQ management | <http://127.0.0.1:15672> — `leolani` / `leolani` |

The broker ports are **fixed**, deliberately. The platform's test harness
randomises its ports so concurrent runs cannot collide; a deployment meant to be
driven by a person following a document needs an address that can be written
down. The cost is that two copies of this stack collide — override
`CLTL_AMQP_PORT` and `CLTL_MANAGEMENT_PORT` if you need a second.

The chat UI port is the opposite: **required**, with no default. Two tenants on
one host must publish on different ports, and being told to pick one reads
better than discovering "port is already allocated" on the second `up`.

## Both chat UIs are blank. That is the exercise.

Open either one and nothing is there.

A chat UI renders nothing until a conversation — a *scenario* — has been opened
for it, and this deployment contains nothing that opens one. There is no
`cltl-context` in either half. That is not an omission to work around; it is the
thing the deployment is arranged to show.

A tenant's scenario can only be opened on that tenant's own bus, so it falls to
the custom side: the notebook (rung 1), `attach/listen.py` (rung 2), or the
module's own container (rung 4). Whichever you run, the chat UI for **that
tenant** comes alive at that moment, and the other tenant's stays blank.

This replaces the consent handshake earlier versions of this template had. There
is no *"Do you want to talk to me?"* and no "say yes first" — the shared ELIZA
is ungated and answers from the first message. The reason is in
[`tenancy.md`](tenancy.md#why-there-is-no-intention-gating).

## What is in it

| Half | Service | Does |
|---|---|---|
| server | `rabbitmq` | The message bus every tenant talks through |
| server | `cltl-eliza` | The dialogue logic — one instance, serving every tenant |
| tenant | `cltl-chat-ui` | The web chat page, and the bridge between it and the bus |

Plus, per tenant, whatever custom side you attach.

**Why ELIZA is shared and the chat UI is not.** ELIZA replies with
`source=event`, which copies the tenant onto its answer, and an untenanted bus
routes on the *event's* tenant — so one instance serves everyone and each answer
goes back to exactly the tenant that asked. The chat UI publishes **without**
`source=`, so an untenanted one would route to a bare topic key that no tenanted
module binds. It has to live inside the tenant. The full table is in
[`tenancy.md`](tenancy.md#routing-as-a-table).

**No audio** — no microphone backend, no voice activity detection, no speech
recognition. Those need a sound device, a storage volume and a large model
download on first use, and none of it changes what attaching to the event bus
looks like. A module this deployment does not run has no section in its
configuration at all, rather than a disabled one.

The full platform deployment — every module, audio included — lives in the
`cltl-dev` repository. This file is a deliberate reduction of it, not a
replacement, and does not track it.

## One network, on purpose

All three projects share the network named `cltl-example`, created by the server
half and joined by everything else as an `external` network. Nothing here is
separated by the network; the tenants are separated by a routing key, and the
deployment is arranged so that is impossible to miss.

Practical consequences: `rabbitmq` resolves as a hostname in every container, so
there is no `host.docker.internal` indirection to get wrong; and bringing a
tenant up with the server down fails immediately with *"network cltl-example
declared as external, but could not be found"*, which is a good hard failure.

## Naming the projects

`deployment/tenant.compose.yml` and `compose/example.compose.yml` both declare

```yaml
name: cltl-example-tenant-${CLTL_TENANT:?set CLTL_TENANT to this tenant's id, e.g. tenant-a}
```

so one `docker compose -f … up` per tenant is all there is to remember, and an
unset `CLTL_TENANT` fails at interpolation before anything starts. That last
part earns its keep: an unexpanded `$CLTL_TENANT` reaching the bus as a literal
string is this repository's most-documented failure mode, and it is otherwise
completely silent. `-p` still overrides the name if you need it to.

## The configuration

`deployment/config/server/` and `deployment/config/tenant/` are each mounted
read-only over the relevant image's own `config/` directory. That is not a
nicety. Every platform image ships a `config/` using **legacy** topic names
intended for standalone single-process runs; a deployment that lets those
defaults stand comes up entirely healthy and wired to nothing. The mounted
files supply the canonical `cltl.topic.*` names that actually connect the
modules to each other.

The `[cltl.event.kombu]` block is **byte-identical** in both. The only
difference between the server and a tenant, and between one tenant and another,
is `CLTL_TENANT` in the container environment — which is interpolated when the
value is read rather than when the file is parsed. Configuration is written
once; the tenant arrives from the outside.

The two `logging.config` files are real copies rather than symlinks: compose
mounts a *directory*, and a relative symlink would be resolved inside the
container, where its target does not exist.

## Pinning a version

`CLTL_IMAGE_TAG` selects the image tag, defaulting to `latest`, on both halves:

```bash
CLTL_IMAGE_TAG=<a published tag> docker compose -f deployment/server.compose.yml up -d
```

Worth doing for anything you intend to reproduce. `latest` moves.

## Shutting down — tenants first

```bash
CLTL_TENANT=tenant-b docker compose -f deployment/tenant.compose.yml down
CLTL_TENANT=tenant-a docker compose -f deployment/tenant.compose.yml down
docker compose -f deployment/server.compose.yml down
```

The server half owns the network. Tearing it down while tenant containers are
still attached leaves the network undeletable and prints a confusing warning.

Stop any attached listener *before* all of that. A listener whose broker
vanishes retries forever and needs `kill -9` — see
[`gotchas.md`](gotchas.md).

The conversation is not persisted: this deployment runs no storage service and
mounts no volume, so `down` takes the transcript with it.
