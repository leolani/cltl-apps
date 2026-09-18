"""Attach a plain Python process to a live Leolani deployment's event bus.

No DI container, no config files, no cltl-dev checkout needed — this is the
whole of what `KombuEventBus` actually asks for. Shared by the notebook
(`example.ipynb`) and the script (`listen.py`), and quoted in
`docs/attaching.md`, so there is exactly one definition to keep correct.

The three functions below map onto the three things that go wrong the first
time someone tries this:

  1. `register()`      — without it, `marshal(event, cls=Event)` raises
                          `TypeError: PAYLOAD is not a dataclass`.
  2. `event_bus()`      — the bus itself; a bare dict stands in for a
                          ConfigurationManager, following
                          integration/src/cltl_integration/runner/tenants.py:77-127.
  3. `wait_until_bound()` — `KombuEventBus.subscribe` returns before RabbitMQ
                          has actually bound the queue. Anything published in
                          that window is silently dropped by the exchange.
                          Without this, "the first message never arrived"
                          is the most common report this template will get.
  4. `start_scenario()`  — a tenanted chat UI renders nothing and refuses to
                          publish until a `ScenarioStarted` arrives on ITS
                          routing key, and in this template's deployment
                          nothing opens one for you: there is no cltl-context.
                          This is NOT something a normal attached module does.
                          It is the price of running the chat UI inside a
                          tenant. See docs/tenancy.md.
  5. `load_image()`      — an image signal carries no pixels. `signal.array` is
                          always `None` on the bus; `signal.files[0]` is a
                          `cltl-storage:image/<id>` reference, and turning that
                          into pixels is a second HTTP hop against a service
                          that answers in JSON-with-base64 rather than PNG
                          bytes. "I subscribed to the image topic and the
                          image was empty" is the report this one prevents.

`new_scenario`/`start_scenario`/`stop_scenario` below are deliberately a copy of
integration/src/cltl_integration/drivers/scenario.py and a parallel of this
template's own src/myorg/tenant/scenario.py, rather than an import of either:
rung 1 has nothing installed. Same reasoning as the echo transform duplicated in
attach/listen.py — see docs/component.md.
"""
import logging
import threading
import time
import uuid
from typing import Iterable, Mapping, Optional
from urllib.parse import unquote, urlparse

import requests
from cltl.combot.event.emissor import (MEN, SIG, Agent, LeolaniContext,
                                       ScenarioStarted, ScenarioStopped)
from cltl.combot.infra.config import Configuration, ConfigurationManager
from cltl.combot.infra.event.api import PAYLOAD, Event
from cltl.combot.infra.event.kombu import KombuEventBus
from cltl.combot.infra.time_util import timestamp_now
from emissor.representation.scenario import Modality, Scenario
from emissor.representation.util import marshal, register_type_var, unmarshal
from kombu.serialization import register as _register_serializer

logger = logging.getLogger(__name__)

SERIALIZER = "cltl-json"
EXCHANGE = "cltl.combot"

_registered = False
_lock = threading.Lock()


def register_event_types() -> None:
    """Register the generic type variables emissor needs to (un)marshal events.

    Idempotent and safe to call more than once — emissor keeps a process-global
    registry. Every component's own `src/main.py` does this same thing before
    constructing anything that touches the bus; see this template's own
    `src/main.py` or `integration/src/cltl_integration/serialization.py`.
    """
    global _registered
    with _lock:
        if _registered:
            return
        for type_var in (PAYLOAD, SIG, MEN):
            register_type_var(type_var)
        _registered = True


def _serializer(event: Event) -> str:
    register_event_types()
    return marshal(event, cls=Event)


def _deserializer(raw: str) -> Event:
    register_event_types()
    return unmarshal(raw, cls=Event)


class _DictConfiguration(Configuration):
    """The `.get(key, multi=False)` / `key in config` surface, over a plain dict."""

    def __init__(self, values: Mapping[str, str]):
        self._values = dict(values)

    def get(self, key, multi=False):
        if multi:
            return [v.strip() for v in self._values[key].split(",") if v.strip()]
        return self._values[key]

    def __contains__(self, key):
        return key in self._values


class _DictConfigurationManager(ConfigurationManager):
    """The one section `KombuEventBus` reads (`cltl.event.kombu`), nothing else.

    `KombuEventBus.__init__` asks a `ConfigurationManager` for exactly one
    config, and that `Configuration` for `.get(key)` and `'tenant' in config` —
    no DI container required. Same trick the integration harness uses to hand
    a test process a tenanted bus of its own.
    """

    def __init__(self, sections: Mapping[str, Mapping[str, str]]):
        self._sections = {name: _DictConfiguration(values) for name, values in sections.items()}

    def has_config(self, name: str) -> bool:
        return name in self._sections

    def get_config(self, name: str, callback=None) -> Configuration:
        if name not in self._sections:
            raise ValueError(f"No configuration for {name}")
        return self._sections[name]


def register() -> None:
    """Register event (de)serialization under the name `KombuEventBus` expects.

    `KombuEventBus` takes a serializer *name*, not a function, and looks it up
    in kombu's own registry at publish/consume time — it fails opaquely (a
    `SerializerNotInstalled` deep inside kombu, not at construction) if the
    name was never registered. Call this before constructing any bus.
    """
    register_event_types()
    _register_serializer(SERIALIZER, _serializer, _deserializer,
                         content_type='application/json', content_encoding='utf-8')


def event_bus(server: str, tenant: str = "", exchange: str = EXCHANGE,
             compression: str = "bzip2") -> KombuEventBus:
    """A `KombuEventBus` on someone else's running deployment.

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
    A subscriber never steals another consumer's
    messages regardless: every `subscribe` gets its own server-named,
    exclusive, auto-delete queue.
    """
    register()
    return KombuEventBus(SERIALIZER, _DictConfigurationManager({
        "cltl.event.kombu": {
            "server": server,
            "exchange": exchange,
            "compression": compression,
            "tenant": tenant,
        }}))


def binding_key(topic: str, tenant: str = "") -> str:
    """The routing key a subscriber to `topic` binds, as KombuEventBus builds it.

    A tenanted subscriber binds exactly `<topic>.<tenant>`. An untenanted one
    binds `<topic>.#`, and `#` in RabbitMQ matches ZERO OR MORE words — so it
    matches every tenant's traffic AND the bare topic. That asymmetry is the
    whole of the isolation mechanism, which is why it lives here as one
    testable function rather than inline. Mirrors `ComposeRunner.binding_key`
    in integration/src/cltl_integration/runner/compose.py.
    """
    return f"{topic}.{tenant}" if tenant else f"{topic}.#"


def wait_until_bound(management_url: Optional[str], topics: Iterable[str],
                     tenant: str = "", timeout: float = 30.0,
                     amqp_url: Optional[str] = None,
                     baseline: Optional[Mapping[str, int]] = None) -> None:
    """Block until RabbitMQ has actually bound queues for `topics`.

    `KombuEventBus.subscribe` starts a background consumer thread and returns
    immediately — the queue is declared and bound to the exchange somewhere in
    that thread's future, not before this call returns. Anything published
    into that window is routed to no queue and dropped, silently, because
    that is what a topic exchange does with an unroutable message.

    Counts bound queues rather than checking for their mere presence: the
    deployment's own modules are usually already subscribed to the same
    topics, so "is anything bound to cltl.topic.text_in" would be answered
    "yes" by somebody else's queue before this subscription even exists.
    Waiting for the count to rise by one is what makes the check about *this*
    subscription specifically. See
    integration/src/cltl_integration/runner/compose.py:446-513, which this is
    a single-runner-free reduction of.

    **Only call this for a topic THIS bus is subscribing to for the first
    time.** `KombuEventBus` keeps one consumer per topic — one queue, one
    binding — and a second `subscribe` to a topic it is already consuming just
    appends the handler to that consumer's list (`KombuEventBus.subscribe`). No
    new queue is created, so the count cannot rise and this call can only ever
    raise `TimeoutError` after the full timeout. The second handler is live the
    moment `subscribe` returns; there is genuinely nothing to wait for.

    `baseline` chooses WHICH question is being asked, and there are two:

    * `None` (the default) snapshots the counts now and waits for them to RISE
      — "is *my* subscription live", the question every `subscribe()` call
      wants answered.
    * `{}` — an all-zero baseline — turns the increment check into a PRESENCE
      check: "is *anyone* bound to this key yet". That is the question to ask
      before publishing to a subscriber that is not you, e.g. before opening a
      scenario the tenant's chat UI has to receive. Same trick, same reason, as
      `ComposeRunner.await_bindings(topics, {}, tenant)` in the platform's
      harness (integration/src/cltl_integration/runner/tenants.py).

    Without `management_url` (RabbitMQ's management plugin, default port
    15672), there is no way to ask the broker anything, so this falls back to
    a flat sleep and says so — the cheap version, usually enough, never
    provably correct.

    The management API needs credentials of its own. Pass `amqp_url` and they
    are taken from it — the same user that is already authenticating the AMQP
    connection is, in every deployment shipped here, also a management user.
    Without it the fallback pair is the integration harness's, which is right
    for that harness and wrong for every other broker: the mismatch surfaces
    as a 401, and a 401 degrades this call to the flat sleep above rather than
    failing, which is the quiet way to reintroduce the exact race this
    function exists to close.
    """
    if not management_url:
        logger.warning("No management_url given; sleeping 2s instead of "
                       "confirming the binding. This is the cheap, unreliable "
                       "fallback — see wait_until_bound's docstring.")
        time.sleep(2.0)
        return

    parsed = urlparse(amqp_url) if amqp_url else None
    auth = ((unquote(parsed.username or ""), unquote(parsed.password or ""))
            if parsed and parsed.username else ("eliza", "eliza123"))

    def counts():
        url = f"{management_url}/api/exchanges/%2F/{EXCHANGE}/bindings/source"
        try:
            response = requests.get(url, auth=auth, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Could not reach the management API at %s (%s); "
                           "falling back to a flat sleep.", url, e)
            return None
        result = {}
        for binding in response.json():
            key = binding["routing_key"]
            result[key] = result.get(key, 0) + 1
        return result

    before = counts() if baseline is None else dict(baseline)
    if before is None:
        time.sleep(2.0)
        return

    wanted = {binding_key(topic, tenant): before.get(binding_key(topic, tenant), 0) + 1
              for topic in topics}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = counts() or {}
        if all(current.get(key, 0) >= n for key, n in wanted.items()):
            return
        time.sleep(0.1)

    raise TimeoutError(
        f"RabbitMQ did not bind the expected queues within {timeout}s: {wanted}. "
        f"A publish now would be silently dropped.")


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
# A deliberate copy of integration/src/cltl_integration/drivers/scenario.py and
# a parallel of src/myorg/tenant/scenario.py — rungs 1-2 have nothing installed,
# which is the point of them.
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

    Call `wait_until_bound(..., baseline={})` for `scenario_topic` first: the
    subscriber that has to receive this is the chat UI, not you, so the default
    "wait for the count to rise" check would be answered by your own queue.
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

    If that import fails on a notebook whose venv demonstrably HAS cltl.backend,
    the kernel is not the venv — `import sys; sys.executable` says which
    interpreter you are actually on, and docs/gotchas.md says what to do about
    it. Every cell above this one works either way, which is what makes the
    symptom so misleading.
    """
    from cltl.backend.source.client_source import ClientImageSource

    with ClientImageSource(file_url, storage_url) as source:
        return source.capture().image
