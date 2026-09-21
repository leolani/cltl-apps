# cltl-example

A minimal template for **attaching your own code to a running Leolani
conversational agent**, demonstrating exactly one thing: subscribing to the
event bus, publishing a reply, and handling a tenant id correctly. Copy this
repository, replace one function, and your code is taking part in the
conversation.

## What Leolani is, in one picture

Leolani is a conversational agent assembled from independent processes — a chat
UI, a speech recogniser, a dialogue engine, a memory store. None of them call
each other. They all talk to a **message bus**, publishing events on named
*topics* and subscribing to the topics they care about:

```
                        ┌─────────────────────┐
   you type ──────────► │      chat UI        │ ◄──── you upload a picture
                        └────┬───────────┬────┘
        publishes on         │           │    publishes on  cltl.topic.image
        cltl.topic.text_in   │           │
                        ═════▼═══════════▼═════════════════════  the bus
                                   │ delivers to every subscriber
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
              ┌─────────────┐            ┌──────────────┐
              │  cltl-eliza │            │ YOUR MODULE  │  ◄── this template
              │  (text only)│            │ text + image │
              └──────┬──────┘            └───────┬──────┘
                     │   publishes on  cltl.topic.text_out
                        ═══════════▼═══════════════════════════
                                   │
                        ┌──────────▼──────────┐
   you read  ◄───────── │      chat UI        │
                        └─────────────────────┘
```

A deployment built to run this module (see the repository root's
[`servers/` and `clients/`](../doc/DEPLOYMENT.md)) is **multi-tenant**: one
shared platform serves several isolated groups of users, and your module
belongs to one of them. The **only** thing keeping tenants apart is the
routing key each side binds — `cltl.topic.text_in.tenant-a` against
`cltl.topic.text_in.tenant-b`, while the shared `cltl-eliza` binds
`cltl.topic.text_in.#` and hears both. See
[`../doc/DEPLOYMENT.md#tenancy`](../doc/DEPLOYMENT.md#tenancy) for the whole
story — this module's job is to get that one part right, nothing else.

The consequence that matters: **nothing in the platform needs to know your
module exists.** You subscribe to a topic that is already being published on,
and publish to a topic that is already being listened to. No registration, no
plugin API, no fork of the platform.

## What this template is

A complete, working module — buildable, testable, dockerisable — wrapped
around two deliberately silly functions, one per modality:

```python
def process(self, text: str) -> Optional[str]:              # echo.py
    return f"YOU SAID: {text.upper()} (via myorg.example)"

def describe(self, image: np.ndarray) -> Optional[str]:     # imagesize.py
    height, width = image.shape[:2]
    return f"The image you uploaded is {width}x{height} (via myorg.example)"
```

Those two functions, in `src/myorg/example/echo.py` and `imagesize.py`, are
the *only* things that are placeholder, and replacing them is the point.
Everything around them — the event plumbing (`src/myorg/example/service.py`),
the configuration, the tests — is real and is what handles a tenant id
correctly:

- `ExampleService.start()` warns once if the deployment's bus has no tenant
  configured (`[cltl.event.kombu] tenant` empty), because that failure is
  otherwise silent — see `tests/test_tenancy.py`.
- `ExampleService._process()` warns once if an incoming *event* carries no
  tenant, and every reply is published with `source=event` — the only thing
  that copies a tenant (and scenario id) from an incoming event onto the
  reply this module sends back. Dropping that is the most common way a reply
  silently reaches nobody.

Opening the conversation's scenario is **not** this module's job — that is
the platform's own `cltl-context`, one instance per tenant (see
[`../clients/context`](../clients/context)). A standalone copy of this
template used to carry a throwaway scenario-opener for deployments that had
none of their own; against this platform there always is one, so
`src/main.py` composes nothing beyond the one container below.

## Two ways to run it

| | You run | You get | You need |
|---|---|---|---|
| **Component** | `src/main.py` | A packaged, tested, installable module, run standalone against a real deployment's broker | a Python 3.10 venv, `pip install -r requirements.txt` |
| **Container** | `compose/example.compose.yml` | Runs inside the deployment like any platform module | `../servers/broker` (+ whichever `servers/*` the deployment needs) and one tenant's `../clients/context` already running |

Both levels attach to an **already-running** deployment — this repository
builds no deployment of its own. See
[`../doc/DEPLOYMENT.md`](../doc/DEPLOYMENT.md) for bringing one up.

### Component

```bash
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config/custom.config.example config/custom.config
# edit config/custom.config: set CLTL_AMQP_URL / CLTL_TENANT / CLTL_STORAGE_URL
# as instructed in the file's own header

CLTL_AMQP_URL=amqp://eliza:eliza123@127.0.0.1:5672/ CLTL_TENANT=tenant-a \
    CLTL_STORAGE_URL=http://127.0.0.1:8001/storage/ \
    python src/main.py
```

### Container

```bash
CLTL_TENANT=tenant-a docker compose -f compose/example.compose.yml up
```

See the header comment in `compose/example.compose.yml` for the full
sequence, including which stacks must already be running.

## Two things that will confuse you first

**Every *typed* message gets two replies.** This module subscribes to the
same topic `cltl-eliza` does and publishes to the same topic — so both
answer. That is deliberate: a module on its own private topic would prove
nothing about attaching to a *real* deployment. This module's reply is the
one tagged `(via myorg.example)`.

**An uploaded image gets one.** Submitting from the chat UI's Image panel
publishes an image signal and *no* utterance, so `cltl-eliza` — which
subscribes to `cltl.topic.text_in` and nothing else — never sees a picture.

## Make it yours

Rename `myorg`/`example` (`setup.py`, `src/myorg/`, `config/default.config`'s
`[myorg.example]` section, `Dockerfile`'s image labels) to your own
organisation and module. The namespace is `myorg`, deliberately **not**
`cltl`: a third-party module is not part of the platform's distribution and
must not squat in its package namespace.

## License

MIT — see [`LICENSE`](LICENSE).
