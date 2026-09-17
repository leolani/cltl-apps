# cltl-example

A template for **attaching your own code to a running Leolani conversational
agent**. Copy this repository, replace one function, and your code is taking
part in the conversation.

You do not need to know the platform to start. The next three minutes explain
enough.

## What Leolani is, in one picture

Leolani is a conversational agent assembled from independent processes — a chat
UI, a speech recogniser, a dialogue engine, a memory store. None of them call
each other. They all talk to a **message bus**, publishing events on named
*topics* and subscribing to the topics they care about:

```
                        ┌─────────────────────┐
   you type ──────────► │      chat UI        │
                        └──────────┬──────────┘
                                   │ publishes on  cltl.topic.text_in
                        ═══════════▼═══════════════════════════  the bus
                                   │ delivers to every subscriber
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
              ┌─────────────┐            ┌──────────────┐
              │  cltl-eliza │            │ YOUR MODULE  │  ◄── this template
              └──────┬──────┘            └───────┬──────┘
                     │   publishes on  cltl.topic.text_out
                        ═══════════▼═══════════════════════════
                                   │
                        ┌──────────▼──────────┐
   you read  ◄───────── │      chat UI        │
                        └─────────────────────┘
```

The deployment you attach to is **multi-tenant**, which folds that picture in
half. One shared platform serves several isolated groups of users; your module
belongs to one of them:

```
   tenant-a                     shared server              tenant-b
   ─────────────────────        ─────────────────          ─────────────────────
   chat UI      :8000  ──────►  rabbitmq        ◄──────    chat UI      :8001
   YOUR MODULE                  cltl-eliza                 YOUR MODULE
     tenant: tenant-a             tenant: (none)             tenant: tenant-b
```

One broker, one exchange, one Docker network. The **only** thing keeping the
two tenants apart is the routing key each one binds — `cltl.topic.text_in.tenant-a`
against `cltl.topic.text_in.tenant-b`, while the shared ELIZA binds
`cltl.topic.text_in.#` and hears both. [`docs/tenancy.md`](docs/tenancy.md) is
the whole story.

The consequence that matters: **nothing in the platform needs to know your
module exists.** You subscribe to a topic that is already being published on,
and publish to a topic that is already being listened to. No registration, no
plugin API, no fork of the platform. That is what this template demonstrates,
and it is the whole reason it can be a separate repository.

## What this template is

A complete, working module — buildable, testable, dockerisable — wrapped around
one deliberately silly function:

```python
def process(self, text: str) -> Optional[str]:
    return f"YOU SAID: {text.upper()} (via myorg.example)"
```

That function is in `src/myorg/example/echo.py`, it is the *only* thing that is
placeholder, and replacing it is the point. Everything around it — the event
plumbing, the configuration, the tests, the Dockerfile — is real and is the
part worth keeping.

## Four ways to run it

The same module, at four levels of commitment. Start at the top; each step down
gains you something and costs you something.

| | You run | You get | You need |
|---|---|---|---|
| **1. Notebook** | `attach/example.ipynb` | See live events, publish a reply, poke at it interactively | Docker, Python |
| **2. Script** | `attach/listen.py` | The same thing, unattended | Docker, Python |
| **3. Component** | `attach/inprocess.py`, `src/main.py` | A packaged, tested, installable module | + a `cltl-dev` checkout |
| **4. Container** | `compose/example.compose.yml` | Runs inside the deployment like any platform module | + a `cltl-dev` checkout |

Levels 1 and 2 attach *from outside* to a deployment over the network — no
install of this template at all, which is why they are so cheap. Levels 3 and 4
are the module proper. The documentation calls these **rungs**, because the
climb is the point: the distance from "I have a Python function" to "it runs in
the deployment" is walked, not jumped.

## Get started

You need **Docker** and **Python 3.10**. You do *not* need the platform's
source code: the deployment runs from public images on `ghcr.io/leolani`, which
the first `docker compose up` pulls for you.

```bash
# terminal 1 — the shared half: broker + one ELIZA for every tenant
docker compose -f deployment/server.compose.yml up -d

# ...and one tenant, with its own chat UI
CLTL_TENANT=tenant-a CLTL_CHATUI_PORT=8000 \
    docker compose -f deployment/tenant.compose.yml up -d

# terminal 2 — a notebook that attaches to that tenant
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.notebook.txt jupyterlab
jupyter lab attach/example.ipynb
```

Then open the chat UI at <http://127.0.0.1:8000/chatui/static/chat.html>. It is
**blank**, and it stays blank until the notebook opens tenant-a's conversation a
few cells in. That is not a fault — see below.

Step by step, with what to expect at each point:
[`docs/getting-started.md`](docs/getting-started.md).

## Two things that will confuse you first

**Every message gets two replies.** This module subscribes to the same topic
`cltl-eliza` does and publishes to the same topic — so both answer. That is
deliberate: a module on its own private topic would prove nothing about
attaching to a *real* deployment. This module's reply is the one tagged
`(via myorg.example)`. [`docs/configuration.md`](docs/configuration.md) shows
how to give it a private topic instead.

**The chat UI is blank until something opens a scenario, and that something is
you.** A chat UI renders nothing until a conversation has been opened for it. In
a normal deployment `cltl-context` does that — but a *tenant's* conversation can
only be opened on that tenant's own bus, and the shared half does not have one.
So the job lands on the custom side.

This is the one part of the template that is **not** an example of custom
functionality, and it is kept in its own package, `myorg.tenant`, to say so.
`myorg.example` — the part you actually replace — contains no reference to a
scenario or a tenant. Delete `myorg.tenant` the day your deployment runs a
`cltl-context` per tenant. [`docs/tenancy.md`](docs/tenancy.md) has the
reasoning.

## What needs a platform checkout, and what doesn't

- **Running a deployment to attach to** — nothing extra.
  [`deployment/server.compose.yml`](deployment/server.compose.yml) and
  [`deployment/tenant.compose.yml`](deployment/tenant.compose.yml) are
  self-contained and pull published images. That is all rungs 1–2 need, and it
  is what a rung-4 container joins.
- **Building this template** (rungs 3–4) — a `cltl-dev` checkout, with this
  repository inside it. `make build` and the `Dockerfile` both resolve the
  platform's own libraries offline from a local package registry that the
  published *images* do not carry.

For rungs 1–2 the two platform libraries you need come from
`requirements.notebook.txt`, straight from GitHub. That tracks a moving branch
rather than a pinned release — the quick way in, not the way to build something
you intend to keep working.

## Documentation

Read in this order:

| | |
|---|---|
| [`getting-started.md`](docs/getting-started.md) | Rung 1, end to end, with exact commands |
| [`concepts.md`](docs/concepts.md) | Events, topics, and the one publishing rule that matters |
| [`deployment.md`](docs/deployment.md) | The deployment you attach to, and how to drive it |
| [`attaching.md`](docs/attaching.md) | Rungs 1–2: joining a live bus from outside |
| [`component.md`](docs/component.md) | Rung 3: the four-file module pattern |
| [`docker.md`](docs/docker.md) | Rung 4: building an image and joining the deployment |
| [`configuration.md`](docs/configuration.md) | Every setting, and which are yours to change |
| [`tenancy.md`](docs/tenancy.md) | **Read this one.** What a tenant is, and why your code opens a scenario |
| [`making-it-yours.md`](docs/making-it-yours.md) | The rename checklist |
| [`gotchas.md`](docs/gotchas.md) | Symptom → cause. Check here first when stuck |

## Make it yours

Renaming `myorg`/`example` to your own organisation and module is a short
mechanical checklist — [`docs/making-it-yours.md`](docs/making-it-yours.md).

The namespace is `myorg`, deliberately **not** `cltl`. A third-party module is
not part of the platform's distribution and must not squat in its package
namespace; that is visible in the very first import, on purpose.

## License

MIT — see [`LICENSE`](LICENSE).
