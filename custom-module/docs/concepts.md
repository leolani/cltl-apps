# Concepts

The vocabulary you need to read this template's code — and no more than that.
Four ideas: events, topics, payloads, and one rule about replying.

## Events

Everything on the bus is an `Event`: a **payload** (what happened) plus
**metadata** (the circumstances).

```python
@dataclass
class Event(Generic[PAYLOAD]):
    id: str
    payload: PAYLOAD
    metadata: EventMetadata

@dataclass
class EventMetadata:
    timestamp: int
    offset: int = -1
    topic: str = ""
    tenant: Optional[str] = None
    scenario_id: Optional[str] = None
```

Three of those fields do real work for you:

- **`topic`** — stamped by the bus on delivery, not by the publisher. Inside a
  subscriber it tells you which of the topics you subscribed to this event
  arrived on, which is how one worker can handle several.
- **`scenario_id`** — which conversation this belongs to. A Leolani deployment
  groups everything by scenario; an event without one is orphaned, and the chat
  UI will not show it.
- **`tenant`** — which isolated set of users this belongs to. This template's
  deployment serves several, so it is set on everything your module sees, and
  the routing key it produces is the only thing keeping one tenant's
  conversation out of another's. Empty means "every tenant", which is what the
  shared `cltl-eliza` runs as. See [`tenancy.md`](tenancy.md).

You rarely construct these yourself. `Event.for_payload(payload, source=event)`
does it correctly, and the section below is about why that `source=` matters
more than anything else on this page.

## Topics

Plain strings, and the platform's are namespaced `cltl.topic.*`:

| Topic | Carries |
|---|---|
| `cltl.topic.text_in` | what a person said |
| `cltl.topic.text_out` | what the agent says back |
| `cltl.topic.scenario` | a conversation opening or closing — published here by `myorg.tenant`, because this deployment has no `cltl-context`; see [`tenancy.md`](tenancy.md) |
| `cltl.topic.image` | an image signal — a *reference* to a picture, never the pixels |
| `cltl.topic.vad`, `cltl.topic.microphone` | audio pipeline internals |

This template subscribes to the first and the fourth, and publishes to the
second. That is the entire integration surface — which is the point of the
architecture.

**Read topic names from configuration, never hardcode them.** `ExampleService`
takes them from `[myorg.example] topic_input` / `topic_output`, so a deployment
can rewire your module without touching its code. This is not a style
preference: platform components ship *legacy* topic names in their standalone
defaults, and a deployment that fails to override them comes up perfectly
healthy and connected to nothing. See
[`configuration.md`](configuration.md#the-legacy-names-trap).

## Payloads

What a person said travels as a `TextSignalEvent` wrapping a `TextSignal`:

```python
from emissor.representation.scenario import TextSignal
from cltl.combot.event.emissor import TextSignalEvent
from cltl.combot.infra.time_util import timestamp_now

signal = TextSignal.for_scenario(scenario_id, timestamp_now(), timestamp_now(),
                                 None, "hello")
payload = TextSignalEvent.for_agent(signal)     # or .for_speaker(signal)
```

`for_agent` marks the signal as coming from the agent, `for_speaker` as coming
from the person — which is, among other things, what puts it on the correct
side of the chat UI. This template only ever publishes `for_agent`; see
`ExampleService._create_payload`.

### An image is a reference

`ImageSignalEvent` has one factory, `create`, and no `for_speaker`/`for_agent`:
an image has no notion of who uttered it, so provenance is not annotated at all.
What it wraps is the surprise:

```python
signal = event.payload.signal          # an emissor ImageSignal
signal.array                           # None. ALWAYS None, on the bus.
signal.files                           # ["cltl-storage:image/<id>"]
signal.ruler.bounds                    # (0, 0, width, height) — a MultiIndex
signal.mentions                        # regions somebody drew, if any
```

The pixels never travel. `ImageSignal.for_scenario` hardcodes `array=None`, and
getting at the picture means resolving `files[0]` against the deployment's image
store — a second HTTP hop, which `ClientImageSource` does for you:

```python
from cltl.backend.source.client_source import ClientImageSource

with ClientImageSource(signal.files[0], storage_url) as source:
    image = source.capture().image     # np.ndarray, (height, width, 3), RGB
```

It must be used as a context manager — `capture()` raises outside one — and
`storage_url` must end in a slash. This template wraps those three lines in
exactly one place per rung: `ExampleService._storage_loader` for the installed
component, `connect.load_image` for the notebook and the script.

Note `(height, width)`. numpy is row-major, so `shape[0]` is the height while
every person and every UI says "width by height". It is the only real mistake
available in `myorg/example/imagesize.py`, which is why its test measures a
non-square image.

The size is therefore declared **twice**: in `signal.ruler.bounds`, by whoever
published the signal, and in the shape of whatever the reference resolves to.
Answering with the second is the difference between trusting a reference and
having resolved it — `ExampleService` does that, and warns when the two
disagree.

## The one rule: always pass `source=`

```python
self._event_bus.publish(topic, Event.for_payload(payload, source=event))
```

`source=event` is the only thing that copies `scenario_id` and `tenant` from the
event you are answering onto your answer. Leave it out and:

- your reply has **no `scenario_id`**, so nothing that groups events by
  conversation will find it — including the chat UI, which will not display it;
- your reply has **no `tenant`**, which on this deployment means it is published
  to the bare routing key that no tenanted subscriber binds. It reaches nobody,
  silently. Not hypothetical — every deployment in this repository is
  multi-tenant.

This is the single most common bug in a hand-written module — common enough
that a shipped platform component has it in one of its branches. `_process` in
this template always passes it, and `tests/test_service.py` pins that.

## `None` means "say nothing"

`Example.process` returns `Optional[str]`. Returning `None` — or an empty or
whitespace-only string — publishes **nothing at all**, rather than an event
with empty text. Two reasons that distinction is real: the chat UI renders an
empty reply as a blank bubble, and a deployment with persistence enabled
records it.

`echo.py` has two `None` branches worth understanding before you replace it:
one for empty input (speech recognition emits these when a segment turns out to
hold no speech), and one that recognises this module's own output — a loop
guard, for the moment someone points `topic_output` back at `topic_input` to
see a quick round trip.
