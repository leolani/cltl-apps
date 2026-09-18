"""Attach a plain Python process to a live Leolani deployment's event bus.

No DI container, no config files, no cltl-dev checkout needed — this is the
whole of what `KombuEventBus` actually asks for. Shared by the notebook
(`example.ipynb`) and the script (`listen.py`), and quoted in
`docs/attaching.md`, so there is exactly one definition to keep correct.

The functions below map onto the things that go wrong the first time someone
tries this:

  1. serialization       — the module-level block just below. Without the type
                          vars, `marshal(event, cls=Event)` raises `TypeError:
                          PAYLOAD is not a dataclass`; without the kombu
                          registration, `KombuEventBus` fails with a
                          `SerializerNotInstalled` raised deep inside kombu at
                          publish time rather than at construction.
  2. `event_bus()`       — the bus itself. `KombuEventBus` wants a
                          `ConfigurationManager`, and the platform's own
                          `LocalConfigurationManager` takes a plain
                          `ConfigParser` — which is buildable from a dict in two
                          lines. No container, no file on disk.
  3. `start_scenario()`  — a tenanted chat UI renders nothing and refuses to
                          publish until a `ScenarioStarted` arrives on ITS
                          routing key, and in this template's deployment
                          nothing opens one for you: there is no cltl-context.
                          This is NOT something a normal attached module does.
                          It is the price of running the chat UI inside a
                          tenant. See docs/tenancy.md.
  4. `load_image()`      — an image signal carries no pixels. `signal.array` is
                          always `None` on the bus; `signal.files[0]` is a
                          `cltl-storage:image/<id>` reference, and turning that
                          into pixels is a second HTTP hop against a service
                          that answers in JSON-with-base64 rather than PNG
                          bytes. "I subscribed to the image topic and the
                          image was empty" is the report this one prevents.

There is a fifth, and it has no function here because there is nothing honest
to put in one: `KombuEventBus.subscribe` returns BEFORE RabbitMQ has bound the
queue, and anything published into that window is dropped by the exchange
without an error on either side. The notebook and `listen.py` close that window
with a flat `time.sleep`, which is a guess rather than a check. Why that is
good enough here — and what it is not good enough for — is in
docs/attaching.md.

`new_scenario`/`start_scenario`/`stop_scenario` below are deliberately a
duplicate of this template's own src/myorg/tenant/scenario.py (and of the
publishing half of src/myorg/tenant/service.py), rather than an import: rung 1
has nothing installed. They are a close variant of
integration/src/cltl_integration/drivers/scenario.py rather than a copy of it —
that one publishes with `Event.for_payload` and hardcodes its agent and
location. Same reasoning as the echo transform duplicated in attach/listen.py —
see docs/component.md.
"""
import json
import logging
import sys
import uuid
from configparser import ConfigParser
from typing import Optional

from cltl.combot.event.emissor import (MEN, SIG, Agent, LeolaniContext,
                                       ScenarioStarted, ScenarioStopped)
from cltl.combot.infra.config.local import LocalConfigurationManager
from cltl.combot.infra.event.api import PAYLOAD, Event
from cltl.combot.infra.event.kombu import KombuEventBus
from cltl.combot.infra.time_util import timestamp_now
from emissor.representation.scenario import Modality, Scenario
from emissor.representation.util import marshal, register_type_var, unmarshal
# Safe to import under its own name now. It was aliased for a while because
# this module also defined a function called `register`, which shadowed it and
# turned the call below into infinite self-recursion disguised as a TypeError
# about unexpected keyword arguments (docs/plans/bootstrap.md, gotcha 4).
from kombu.serialization import register

logger = logging.getLogger(__name__)

SERIALIZER = "cltl-json"
EXCHANGE = "cltl.combot"


# ---------------------------------------------------------------------------
# Serialization, done once at import.
#
# Every component's own src/main.py does exactly this before constructing
# anything that touches the bus. No lazy guard and no lock: `register_type_var`
# is a single dict assignment (emissor/representation/util.py) and kombu's
# `register` writes one registry entry, so doing either twice is a no-op. The
# notebook repeats this block verbatim in its setup cell, on purpose — the
# repeat registers the same name with equivalent functions and changes nothing.
# ---------------------------------------------------------------------------

register_type_var(PAYLOAD)
register_type_var(SIG)
register_type_var(MEN)


def serializer(obj) -> str:
    return marshal(obj, cls=Event)


def deserializer(obj: str):
    return unmarshal(obj, cls=Event)


register(SERIALIZER, serializer, deserializer,
         content_type='application/json', content_encoding='utf-8')


def event_json(event: Event, indent: int = 2) -> str:
    """The JSON that actually crossed the broker for `event`, pretty-printed.

    Not a reconstruction and not a `repr`: `marshal(event, cls=Event)` is the
    very function kombu was handed above as the `cltl-json` serializer, so this
    is the publisher's bytes with whitespace added. Reading it is the fastest
    way to settle what a payload really contains — that an image signal's
    `array` is `null`, that `files` holds a `cltl-storage:` reference, and that
    the tenant an event belongs to rides in `metadata.tenant`.

    Note what `metadata.topic` is NOT. It holds the BARE topic, not the routing
    key: the tenant suffix exists only in AMQP, and `KombuEventBus` stamps the
    plain topic you subscribed with on delivery (`_topic_handler`, via
    `Event.with_topic`). That is precisely why dispatching on
    `event.metadata.topic` works — see `listen.py`'s handler and
    `ExampleService._process`. If the suffix were there, both would stop
    matching.

    A round trip through `json.loads` rather than `indent=` on the marshaller:
    emissor's `marshal` takes no formatting options, and parsing what it
    produced also proves it is JSON rather than something JSON-shaped.
    """
    return json.dumps(json.loads(serializer(event)), indent=indent)


def event_bus(server: str, tenant: str = "", exchange: str = EXCHANGE,
              compression: str = "bzip2") -> KombuEventBus:
    """A `KombuEventBus` on someone else's running deployment.

    `KombuEventBus.__init__` asks a `ConfigurationManager` for one section,
    `cltl.event.kombu`, and asks that `Configuration` for `.get(key)` and
    `'tenant' in config` — no DI container required. The platform's own
    `LocalConfigurationManager` wraps a plain `ConfigParser`, and a
    `ConfigParser` is buildable from a dict, so the four values below are the
    entire configuration this process needs.

    `interpolation=None` is load-bearing rather than tidiness. The default
    interpolation scans every value on read, so a percent-encoded broker
    password — `amqp://user:p%40ss@host/` — parses fine here and then raises
    `InterpolationSyntaxError` from inside `KombuEventBus.__init__`. Nothing
    below wants `$VAR` expansion: this config is composed in Python, which is
    where a caller can interpolate whatever it likes.

    `server` is the AMQP URL — `amqp://leolani:leolani@127.0.0.1:5672/` for
    the deployment in deployment/server.compose.yml (docs/deployment.md). The
    integration harness's demo stacks use eliza/eliza123 on an ephemeral port
    instead, printed under `broker` by `make -C integration demo-<name>
    DEMO_FLAGS='--tier compose'`.

    `tenant` names the tenant to join, and on this template's deployment you
    want one: it is what scopes both what you receive and what you publish.
    Empty subscribes to every tenant on the exchange, which makes a fine
    read-only observer but CANNOT open a scenario — an untenanted publish lands
    on the bare topic key that no tenanted subscriber binds. See docs/tenancy.md.
    A subscriber never steals another consumer's messages regardless: every
    `subscribe` gets its own server-named, exclusive, auto-delete queue.

    How the tenant becomes a routing key is `KombuEventBus`'s business and
    nobody else's. Publish and subscribe with bare topic names; the bus builds
    `<topic>.<tenant>` (or binds `<topic>.#` when untenanted) on its own.
    """
    parser = ConfigParser({}, strict=False, interpolation=None)
    parser.read_dict({
        "cltl.event.kombu": {
            "server": server,
            "exchange": exchange,
            "compression": compression,
            # Present even when empty, and that is not the same as absent:
            # KombuEventBus does `config.get('tenant') if 'tenant' in config
            # else None`, so an explicitly untenanted bus has to say so.
            "tenant": tenant,
        }})

    return KombuEventBus(SERIALIZER, LocalConfigurationManager(parser))


# ---------------------------------------------------------------------------
# Opening a tenant's conversation.
#
# NOT custom functionality, and not something an attached module normally does.
# It is here because cltl-chat-ui runs INSIDE a tenant (it publishes utterances
# without source=, so an untenanted one would route to a bare topic key nothing
# binds), it renders nothing and refuses to publish until it has seen a
# ScenarioStarted, and a tenant's ScenarioStarted can only be published on that
# tenant's own bus. This template's deployment runs no cltl-context, so the
# custom side has to open it. See docs/tenancy.md.
#
# A deliberate duplicate of src/myorg/tenant/scenario.py and service.py — rungs
# 1-2 have nothing installed, which is the point of them.
# ---------------------------------------------------------------------------

AGENT_URI = "http://cltl.nl/leolani/world/leolani"
SPEAKER_URI = "http://cltl.nl/leolani/world/human_speaker"

SIGNALS = {
    Modality.IMAGE.name.lower(): "./image.json",
    Modality.TEXT.name.lower(): "./text.json",
    Modality.AUDIO.name.lower(): "./audio.json",
}


def new_scenario(scenario_id: Optional[str] = None, agent: str = "Leolani",
                 speaker: str = "Human", location: str = "unknown") -> Scenario:
    """A `Scenario` ready to be announced. `ruler.end` is None — i.e. still open."""
    context = LeolaniContext(Agent(agent, AGENT_URI), Agent(speaker, SPEAKER_URI),
                             str(uuid.uuid4()), location, [], [])

    return Scenario.new_instance(scenario_id or str(uuid.uuid4()),
                                 timestamp_now(), None, context, SIGNALS)


def start_scenario(event_bus: KombuEventBus, scenario_topic: str,
                   scenario_id: Optional[str] = None, **kwargs) -> Scenario:
    """Publish `ScenarioStarted` and return the scenario.

    Publish it on a TENANTED bus. An untenanted one routes this to the bare
    `<scenario_topic>` key, which a tenanted chat UI does not bind, so the
    conversation would open for nobody — silently, as ever.

    The subscriber that has to receive this is the chat UI, in another
    container, so give it a moment: `time.sleep(5)` before this call, matching
    what `[myorg.tenant] start_delay` budgets for the identical problem at rung
    4. That is a guess, not a check — see docs/attaching.md.
    """
    scenario = new_scenario(scenario_id, **kwargs)
    event_bus.publish(scenario_topic,
                      Event.for_scenario_payload(scenario.id, ScenarioStarted.create(scenario)))

    return scenario


def stop_scenario(event_bus: KombuEventBus, scenario_topic: str, scenario: Scenario) -> None:
    """Close the conversation. Do this before `bus.close()`, not after.

    The chat UI clears its transcript when a scenario stops, which is how you
    can see this land rather than taking it on faith.
    """
    scenario.ruler.end = timestamp_now()
    event_bus.publish(scenario_topic,
                      Event.for_scenario_payload(scenario.id, ScenarioStopped.create(scenario)))


# ---------------------------------------------------------------------------
# Getting at the pixels.
#
# THIS one is ordinary custom functionality, unlike the scenario block above —
# any module that cares about images does exactly this. It is separate only
# because it is the second modality, and because the thing it does is
# unobvious: the event does not carry the picture.
# ---------------------------------------------------------------------------

DEFAULT_STORAGE_URL = "http://127.0.0.1:8002/storage/"


def load_image(file_url: str, storage_url: str = DEFAULT_STORAGE_URL):
    """The pixels a signal's `files[0]` refers to, as a numpy array.

    Shape is `(height, width, channels)` — rows first, RGB, `uint8`. An image
    signal carries no pixels at all: `ImageSignal.for_scenario` hardcodes
    `array=None`, and `files` holds one `cltl-storage:image/<id>` reference.

    `storage_url` **must end in a slash.** The reference is resolved with
    `urljoin(storage_url, "image/<id>")` inside cltl-backend's transport adapter
    (`cltl/backend/source/client_source.py`), and `urljoin` drops the last path
    segment of a base that does not end in one — so `…:8002/storage` looks for
    `…:8002/image/<id>` and 404s from a URL that reads correctly in a log. The
    installed module (`myorg/example/service.py`) appends the slash for you and
    warns; here you get to see the trap, which is what rung 1 is for.

    `ClientImageSource` is the platform's own client and is used rather than a
    hand-rolled `requests.get` for two reasons: it resolves the `cltl-storage:`
    scheme, and it decodes the wire format, which is JSON with the pixels
    base64-encoded under an `{"__type": "np.ndarray", "shape": …}` envelope. It
    also raises outside a `with` block, so the context manager is not optional.

    Imported inside the function: rung 1's text cells must keep working when
    `cltl.backend` is not installed (it is the third and least essential line in
    requirements.notebook.txt). Parallel to `ExampleService._storage_loader`,
    which is the installed version of the same three lines.

    That import is also the one most likely to fail for a reason that is not a
    missing install, so it reports the interpreter it failed on. Every cell
    above this one needs only `cltl.combot` and `emissor`, which the wrong
    environment usually also has — so a notebook whose kernel is not the venv
    works perfectly right up to here and then fails on a package you can see is
    installed. docs/gotchas.md says what to do about it.
    """
    try:
        from cltl.backend.source.client_source import ClientImageSource
    except ImportError as e:
        raise ImportError(
            f"{e}. This is the first thing here that needs cltl.backend, so the "
            f"usual cause is not a missing install but a kernel running on the "
            f"wrong interpreter: this process is {sys.executable}. If that is "
            f"not the venv you installed requirements.notebook.txt into, see "
            f"docs/gotchas.md — everything above this point works either way, "
            f"which is what makes the symptom so misleading.") from e

    with ClientImageSource(file_url, storage_url) as source:
        return source.capture().image
