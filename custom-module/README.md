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
# terminal 1 — a Leolani deployment: broker, chat UI, ELIZA, context/BDI
docker compose -f deployment/deployment.compose.yml up

# terminal 2 — a notebook that attaches to it
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.notebook.txt jupyterlab
jupyter lab attach/example.ipynb
```

Then open the chat UI at <http://127.0.0.1:8000/chatui/static/chat.html> and
**answer "yes"** to its opening question before typing anything else.

Step by step, with what to expect at each point:
[`docs/getting-started.md`](docs/getting-started.md).

## Two things that will confuse you first

**Every message gets two replies.** This module subscribes to the same topic
`cltl-eliza` does and publishes to the same topic — so both answer. That is
deliberate: a module on its own private topic would prove nothing about
attaching to a *real* deployment. This module's reply is the one tagged
`(via myorg.example)`. [`docs/configuration.md`](docs/configuration.md) shows
how to give it a private topic instead.

**Until you say "yes", only *this* module answers.** The agent asks for consent
before starting a conversation, and `cltl-eliza` stays silent until you give
it. This template deliberately has no such gating, so it answers from the very
first message. One reply to your first message is the handshake working, not a
fault.

## What needs a platform checkout, and what doesn't

- **Running a deployment to attach to** — nothing extra.
  [`deployment/deployment.compose.yml`](deployment/deployment.compose.yml) is
  self-contained and pulls published images. That is all rungs 1–2 need, and it
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
| [`tenancy.md`](docs/tenancy.md) | Running one bus for several isolated conversations |
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
