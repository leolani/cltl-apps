# The deployment

The agent this template attaches *to*. None of it is this template, and none of
it needs the platform's source code — it is three published images, RabbitMQ,
and two configuration files. (Four images, and a fifth that is opt-in, once you
count the image store and the monitoring view below.)

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
| Image store | <http://127.0.0.1:8002/storage/> — `GET /health`, `GET /image/<id>` |

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
| server | `storage` | `cltl-backend`'s image store, where uploaded pixels live |
| tenant | `cltl-chat-ui` | The web chat page, and the bridge between it and the bus |
| tenant | `monitoring` | *Opt-in.* Per-scenario view of what the platform perceived |

Plus, per tenant, whatever custom side you attach.

`storage` runs `cltl-backend`'s `src/storage_main.py`, not its `src/main.py`.
That entry point is `StorageContainer` alone — the `/storage` HTTP endpoint and
nothing else, with no microphone, camera or text-to-speech, none of which exists
here. It is also the only one that is safe on a shared bus: `BackendContainer`
constructs an `EventLogService` that subscribes to `event_bus.topics`, and
`KombuEventBus.topics` unions consumed topics with the tenant-suffixed routing
keys it has *published* on — so on the server half it would subscribe to
`cltl.topic.text_out.tenant-a` as though that were a topic name.

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

## Images, and where the pixels actually are

The chat UI has an **Image** panel beside the conversation: upload a picture,
drag labelled rectangles over it, press Submit. Two things about what that does
are worth knowing before you subscribe to it.

**It publishes one `ImageSignalEvent` on `cltl.topic.image`, and nothing on the
utterance topic.** So `cltl-eliza` never sees a picture. Where text draws two
replies — ELIZA's and yours — an image draws exactly one. The picture is also
echoed straight into the transcript without an event, which is why it appears
there whether or not anything is listening.

**The event does not contain the image.** `ImageSignal.for_scenario` leaves
`signal.array` as `None`; what travels is a reference:

```python
signal.files       == ["cltl-storage:image/<id>"]
signal.ruler.bounds == (0, 0, 700, 640)      # declared by the browser
signal.array       is None                    # always, on the bus
signal.id          == "<id>"                  # the same id as in files
```

`cltl-storage:` is a scheme, not a URL. It resolves against
`[cltl.backend] storage_url` — `http://storage:8000/storage/` inside the network,
`http://127.0.0.1:8002/storage/` outside it — giving
`GET …/storage/image/<id>`, which answers **JSON with the pixels base64-encoded**
rather than the PNG bytes you might expect:

```json
{"image": {"__type": "np.ndarray", "data": "<base64>",
           "shape": [640, 700, 3], "dtype": "uint8"},
 "view": [0, 700, 0, 640], "depth": null}
```

`ClientImageSource` (`cltl.backend.source.client_source`) does both halves —
scheme and decoding — and is what this template uses at every rung. See
[`concepts.md`](concepts.md#payloads).

**The trailing slash on `storage_url` is load-bearing.** The reference is
resolved with `urljoin(storage_url, "image/<id>")`, and `urljoin` drops the last
path segment of a base that does not end in one, so `…:8002/storage` looks for
`…:8002/image/<id>` and 404s from a URL that reads correctly in a log.

**The chat UI's upload of the pixels is best-effort.** It PUTs them to storage
and swallows the failure, publishing the reference either way — so a reference
that resolves to nothing is a normal event, not a bug. Everything downstream is
written to expect it. An unstored id answers **HTTP 500** with a `KeyError`, not
404.

One more asymmetry, and it is deliberate: **storage is shared and untenanted.**
`StorageContainer` subscribes to no topic, so it has no tenant dimension to get
right — it is shared infrastructure like the broker. What follows is that two
tenants' pixels sit in one store, separated only by the opaque uuid each image is
filed under. [`tenancy.md`](tenancy.md) says what that does and does not buy you.

## The Monitoring tab is opt-in

`cltl-monitoring` keeps one view per scenario of what the platform perceived and
serves it as an annotated JPEG; the chat UI embeds that page in a **Monitoring**
tab. It runs **once per tenant**, because unlike storage it *subscribes* — one
shared instance would aggregate every tenant's conversation behind a single URL.

It is off by default, and not by preference: `ghcr.io/leolani/cltl-monitoring`
is **not a published package**. It answers `unauthorized` for `:latest` and for a
version tag alike, while every other image this deployment uses pulls
anonymously from the same registry. Turn it on once the image exists, or once you
have built and tagged it yourself:

```bash
CLTL_TENANT=tenant-a CLTL_CHATUI_PORT=8000 \
    CLTL_MONITORING_PORT=8010 \
    CLTL_MONITORING_URL=http://127.0.0.1:8010/monitoring \
    docker compose --profile monitoring -f deployment/tenant.compose.yml up -d
```

Two variables because two different things read them: the port is published by
compose, and the URL is what a *browser* is told to fetch — so `127.0.0.1` and
the published port, never `monitoring:8000`. `CLTL_MONITORING_URL` empty (the
default) leaves the tab out of the page altogether, which beats a tab whose
iframe cannot load.

Note that nothing in the compose file uses `:?` for these. A service excluded by
a profile is still *interpolated*, so a required variable would fail the default
`up` too — for a service that `up` does not start.

`[cltl.monitoring] active_interval` is set to **0** rather than the shipped
default of 15. That default is seconds-without-a-request after which a scenario
stops being recorded, and it exists for a camera-fed deployment where decoding
frames for nobody is real work. Here images arrive one at a time from a person:
one submitted while the interval had lapsed would be dropped on arrival, with no
replay, leaving the tab permanently blank for anyone who was not already looking.

## One network, on purpose

Every project shares the network named `cltl-example`, created by the server
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

`deployment/config/tenant/` is mounted into the chat UI, into `cltl-monitoring`,
and — as `custom.config` — into a rung-4 module container. Sharing one file is
the point: `$CLTL_STORAGE_URL` is read by all three, so the address of the image
store cannot drift between them. Extra sections are ignored by whoever does not
read them.

`deployment/storage/image/` and `deployment/storage/audio/` are **committed**,
with a `.gitkeep` each explaining why. `CachedImageStorage.__init__` calls
`os.makedirs(os.path.dirname(storage_path))`, which creates the *parent* of the
directory rather than the directory — a known upstream bug — and `cv2.imwrite`
into a missing directory returns `False` rather than raising. The result is a
`204 No Content` on the PUT and a `KeyError` on the GET, with nothing anywhere
saying the directory does not exist.

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

The conversation is not persisted: there is no `cltl-emissor-data` here, so
`down` takes the transcript with it. Uploaded **pixels** do outlive it, in
`deployment/storage/image/` — one `<id>.png` and one `<id>_meta.json` per
upload, gitignored. Delete them when you are done; nothing else will.
