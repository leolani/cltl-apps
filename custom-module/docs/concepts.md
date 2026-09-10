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
- **`tenant`** — which isolated set of users this belongs to, on a deployment
  serving several. Empty on a single-tenant deployment, which is the normal
  case and the one this template ships. See [`tenancy.md`](tenancy.md).

You rarely construct these yourself. `Event.for_payload(payload, source=event)`
does it correctly, and the section below is about why that `source=` matters
more than anything else on this page.

## Topics

Plain strings, and the platform's are namespaced `cltl.topic.*`:

| Topic | Carries |
|---|---|
| `cltl.topic.text_in` | what a person said |
| `cltl.topic.text_out` | what the agent says back |
| `cltl.topic.scenario` | a conversation opening or closing |
| `cltl.topic.image` | an image signal |
| `cltl.topic.vad`, `cltl.topic.microphone` | audio pipeline internals |

This template subscribes to the first and publishes to the second. That is the
entire integration surface — which is the point of the architecture.

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

## The one rule: always pass `source=`

```python
self._event_bus.publish(topic, Event.for_payload(payload, source=event))
```

`source=event` is the only thing that copies `scenario_id` and `tenant` from the
event you are answering onto your answer. Leave it out and:

- your reply has **no `scenario_id`**, so nothing that groups events by
  conversation will find it — including the chat UI, which will not display it;
- your reply has **no `tenant`**, which on a multi-tenant deployment means it
  is published to a routing key no subscriber is listening on. It reaches
  nobody, silently.

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
