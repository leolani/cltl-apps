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
"""
import logging
import threading
import time
from typing import Iterable, Mapping, Optional
from urllib.parse import unquote, urlparse

import requests
from cltl.combot.event.emissor import MEN, SIG
from cltl.combot.infra.config import Configuration, ConfigurationManager
from cltl.combot.infra.event.api import PAYLOAD, Event
from cltl.combot.infra.event.kombu import KombuEventBus
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
    the deployment in deployment/deployment.compose.yml (docs/deployment.md).
    The integration harness's demo stacks use eliza/eliza123 on an ephemeral
    port instead, printed under `broker` by `make -C integration demo-<name>
    DEMO_FLAGS='--tier compose'`.

    `tenant` empty (the default) subscribes to every tenant on the exchange —
    fine for a single-tenant deployment, and see docs/tenancy.md before using
    this against a shared one. A subscriber never steals another consumer's
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


def wait_until_bound(management_url: Optional[str], topics: Iterable[str],
                     tenant: str = "", timeout: float = 30.0,
                     amqp_url: Optional[str] = None) -> None:
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

    def binding_key(topic: str) -> str:
        return f"{topic}.{tenant}" if tenant else f"{topic}.#"

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

    before = counts()
    if before is None:
        time.sleep(2.0)
        return

    wanted = {binding_key(topic): before.get(binding_key(topic), 0) + 1 for topic in topics}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = counts() or {}
        if all(current.get(key, 0) >= n for key, n in wanted.items()):
            return
        time.sleep(0.1)

    raise TimeoutError(
        f"RabbitMQ did not bind the expected queues within {timeout}s: {wanted}. "
        f"A publish now would be silently dropped.")
