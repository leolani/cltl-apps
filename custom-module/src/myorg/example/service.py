import logging
from typing import Callable, Optional

import numpy as np
from cltl.combot.event.emissor import TextSignalEvent
from cltl.combot.infra.config import ConfigurationManager
from cltl.combot.infra.event import Event, EventBus
from cltl.combot.infra.event.util import extract_scenario_id
from cltl.combot.infra.resource import ResourceManager
from cltl.combot.infra.time_util import timestamp_now
from cltl.combot.infra.topic_worker import TopicWorker
from emissor.representation.scenario import TextSignal

from myorg.example.api import Example, ImageExample

logger = logging.getLogger(__name__)

# Two topics on one worker, and an HTTP round trip on one of them. The
# TopicWorker default is buffer_size=1 with RejectionStrategy.OVERWRITE, which
# DISCARDS a queued event when a second one arrives — so with the image path on,
# an utterance published while a fetch from storage was in flight would simply
# vanish. cltl-chat-ui uses 256 and cltl-monitoring its own constant for exactly
# this reason. Eight is ample for a conversation driven by one person.
BUFFER_SIZE = 8


class ExampleService:
    """Subscribes to one or two topics, runs an :class:`Example` or an
    :class:`ImageExample`, publishes to a third.

    Structurally this is cltl-eliza's ElizaService — see
    cltl-eliza/src/cltl_service/eliza/service.py — with two of its bugs fixed
    rather than copied: `stop()` returns instead of falling through a `pass`
    when there is no worker (cltl-monitoring gets this right, cltl-eliza and
    cltl-vad do not), and `_process` never publishes without `source=event`
    (cltl-eliza's greeting branch does, which drops tenant and scenario_id —
    see docs/tenancy.md).

    One worker for both modalities, dispatching on `event.metadata.topic`. That
    is what `TopicWorker`'s topic list is for, and it is why `topic` is stamped
    by the bus on delivery rather than by the publisher — see docs/concepts.md.
    cltl-monitoring's `_process` is the same shape with six topics.
    """

    @classmethod
    def from_config(cls, example: Example, image_example: ImageExample, event_bus: EventBus,
                    resource_manager: ResourceManager, config_manager: ConfigurationManager):
        config = config_manager.get_config("myorg.example")

        input_topic = config.get("topic_input")
        output_topic = config.get("topic_output")

        # Absent or empty turns the image half off entirely — the platform's own
        # idiom for "not in this deployment" ([cltl.backend.image] topic: and
        # [cltl.asr] implementation: are the same switch). It has to be filtered
        # rather than passed on: TopicWorker would subscribe to the empty
        # string, which under kombu is a real queue bound to `.<tenant>` and a
        # consumer thread that can never receive anything.
        image_topic = config.get("topic_image") if "topic_image" in config else None
        image_loader = None
        if image_topic:
            storage_url = (config.get("image_storage_url")
                           if "image_storage_url" in config else None)
            image_loader = cls._storage_loader(storage_url)

        # Tenanting is the BUS's job, not this service's — KombuEventBus binds
        # `<topic>.<tenant>` and RabbitMQ does the filtering
        # (cltl.combot.infra.event.kombu). This service never compares
        # tenants: a Python-side check here could only ever be dead code on a
        # correctly configured bus, or false reassurance on a broken one. What
        # it DOES do is say out loud, once, when the bus has been left
        # untenanted — because that failure is otherwise completely silent.
        # See docs/tenancy.md.
        implementation = (config_manager.get_config("cltl.event").get("implementation")
                          if "cltl.event" in config_manager else None)
        tenant = None
        if "cltl.event.kombu" in config_manager:
            kombu_config = config_manager.get_config("cltl.event.kombu")
            tenant = kombu_config.get("tenant") if "tenant" in kombu_config else None

        return cls(input_topic, output_topic, example, event_bus, resource_manager,
                   shared_bus=(implementation != "internal"), tenant=tenant,
                   image_topic=image_topic, image_example=image_example,
                   image_loader=image_loader)

    @staticmethod
    def _storage_loader(storage_url: Optional[str]) -> Callable[[str], np.ndarray]:
        """A callable that turns a signal's file reference into pixels.

        The cltl.backend import is inside this method rather than at module
        level, so a deployment with `topic_image` empty never pulls it in — nor
        `requests`, which comes with it. Same rule as the platform's lazy ML
        imports (see cltl-asr/src/cltl_service/asr/container.py), and the same
        placement cltl-emissor-data uses for this very import
        (cltl/emissordata/file_storage.py).

        `ClientImageSource` is the platform's own client, and using it rather
        than hand-rolling an HTTP call buys two things: it resolves the
        `cltl-storage:` URL scheme (a `requests` transport adapter, see
        cltl/backend/source/client_source.py), and it decodes the wire format,
        which is JSON with the pixels base64-encoded rather than the PNG bytes
        one might reasonably expect.

        Returned as `Callable[[str], np.ndarray]` — "pixels for this url" —
        rather than cltl-monitoring's `Callable[[str], ImageSource]`. Narrower
        on purpose: `capture()` raises outside a `with` block, so the context
        manager is written once, here, where it cannot be forgotten; and a test
        or attach/inprocess.py can substitute `lambda url: array` with no fake
        HTTP server at all.
        """
        if not storage_url:
            raise ValueError(
                "[myorg.example] image_storage_url is empty while topic_image is "
                "set. An image signal carries no pixels — signal.array is always "
                "None on the bus — only a `cltl-storage:image/<id>` reference, and "
                "resolving it needs the address of the deployment's storage "
                "service. Set it (or $CLTL_STORAGE_URL), or empty topic_image to "
                "run text-only. See docs/configuration.md.")
        if storage_url.startswith("$"):
            raise ValueError(
                f"[myorg.example] image_storage_url is {storage_url!r} — an "
                "UNEXPANDED variable. EnvInterpolation passes an undefined "
                "variable through verbatim with only a warning "
                "(cltl.combot.infra.config.local), so this would be used as a "
                "literal URL and every fetch would fail. Define it in the "
                "container environment; compose/example.compose.yml does. See "
                "docs/gotchas.md.")
        if not storage_url.endswith("/"):
            # Normalised rather than refused, because eliza-server's own
            # custom.config ships it without the slash and this module has to
            # work against a deployment config it does not control. The trap is
            # real: the reference is resolved with urljoin(storage_url,
            # "image/<id>"), and urljoin DROPS the last path segment of a base
            # that does not end in a slash — so ".../storage" silently resolves
            # to ".../image/<id>", a 404 from a URL that looks right in a log.
            logger.warning(
                "[myorg.example] image_storage_url %r does not end in '/'. "
                "Appending one: the reference is resolved with urljoin(), which "
                "would otherwise drop the last path segment and look for "
                "'image/<id>' one level too high. See docs/gotchas.md.",
                storage_url)
            storage_url += "/"

        # Imported here, and deliberately AFTER the checks above: a
        # misconfigured address should be reported as a misconfigured address
        # rather than as an ImportError from a package the text-only path never
        # touches.
        from cltl.backend.source.client_source import ClientImageSource

        def load(file_url: str) -> np.ndarray:
            with ClientImageSource(file_url, storage_url) as source:
                return source.capture().image

        return load

    def __init__(self, input_topic: str, output_topic: str, example: Example,
                 event_bus: EventBus, resource_manager: ResourceManager,
                 shared_bus: bool = False, tenant: str = None,
                 image_topic: str = None, image_example: ImageExample = None,
                 image_loader: Callable[[str], np.ndarray] = None):
        if not input_topic:
            raise ValueError("[myorg.example] topic_input is empty. Subscribing to an "
                             "empty topic string binds a queue under kombu that can "
                             "never receive anything (see docs/component.md) — this is "
                             "a misconfiguration, not an optional input, so it is "
                             "rejected here rather than silently skipped.")
        if not output_topic:
            raise ValueError("[myorg.example] topic_output is empty; see topic_input above.")
        if image_topic and not (image_example and image_loader):
            # Unlike the topics above, the image half IS optional — but a
            # half-wired one is not. An image_topic with nothing to answer it
            # would subscribe, receive, and drop every image in silence.
            raise ValueError("[myorg.example] topic_image is set but no image_example "
                             "and/or image_loader was supplied. Pass both, or leave "
                             "topic_image empty to run text-only.")

        self._input_topic = input_topic
        self._output_topic = output_topic
        self._example = example
        self._event_bus = event_bus
        self._resource_manager = resource_manager

        self._image_topic = image_topic
        self._image_example = image_example
        self._image_loader = image_loader

        # Only used to decide whether the empty-tenant warning in start() is
        # relevant at all — SynchronousEventBus has no tenants, so warning
        # about one in rung 3's in-process default would just train people to
        # ignore the warning. See integration/src/cltl_integration/__main__.py's
        # own "no in-process meaning" reasoning for the same kind of guard.
        self._shared_bus = shared_bus
        self._tenant = tenant
        self._warned_untenanted = False

        self._topic_worker = None

    @property
    def app(self):
        # Returns None: this module has no HTTP surface. To add one, see
        # cltl-monitoring/src/cltl_service/monitoring/service.py's `app`
        # property for the pattern (a lazily built, memoized Flask app).
        return None

    @property
    def topics(self):
        """The topics to subscribe to — one or two, never an empty string."""
        return [topic for topic in (self._input_topic, self._image_topic) if topic]

    def start(self, timeout=30):
        if self._shared_bus and not self._tenant:
            logger.warning(
                "[cltl.event.kombu] tenant is empty. This module will bind "
                "'%s.#', which under kombu matches every tenant on the "
                "exchange, and it will process and answer every one of them. "
                "That is correct for a single-tenant deployment and wrong for "
                "a shared broker. Set [cltl.event.kombu] tenant (or "
                "$CLTL_TENANT) to this deployment's id — one lowercase "
                "routing-key word, ^[a-z0-9][a-z0-9_-]*$. Starting anyway; "
                "see docs/tenancy.md.", self._input_topic)

        # No `intentions=`/`intention_topic=`: TopicWorker._check_intention
        # keeps ONE active flag per worker and never reads
        # event.metadata.tenant, so a module shared across tenants would be
        # gated by whichever tenant spoke last. Pinned as a known defect by
        # integration/tests/slices/test_intention_routing.py::TestTenantScopedGating
        # (xfail(strict=True)). See docs/tenancy.md.
        self._topic_worker = TopicWorker(self.topics, self._event_bus,
                                         provides=[self._output_topic],
                                         buffer_size=BUFFER_SIZE,
                                         resource_manager=self._resource_manager,
                                         processor=self._process,
                                         name=self.__class__.__name__)
        self._topic_worker.start().wait()

    def stop(self):
        if not self._topic_worker:
            return
        self._topic_worker.stop()
        self._topic_worker.await_stop()
        self._topic_worker = None

    def _process(self, event: Event):
        if not event.metadata.tenant and not self._warned_untenanted:
            # Once per process, not once per event — a misconfigured
            # deployment would otherwise log one of these per utterance.
            # TopicWorker runs _process on a single thread, so this flag
            # cannot race with itself.
            self._warned_untenanted = True
            logger.warning(
                "Event %s on %s carries no tenant. An untenanted bus "
                "publishes on the EVENT's tenant, so a reply built without "
                "source=event routes to the bare '%s' key — which '<topic>.#' "
                "subscribers match but no tenanted subscriber binds. In a "
                "multi-tenant deployment such a reply reaches nobody. Logged "
                "once; see docs/tenancy.md.",
                event.id, event.metadata.topic, self._output_topic)

        # Dispatch on the topic the bus stamped on delivery, not on the payload
        # type. Both are available, but the topic is the one a deployment can
        # rewire from configuration — which is the whole point of reading topic
        # names from config in the first place.
        if self._image_topic and event.metadata.topic == self._image_topic:
            response = self._describe_image(event)
        else:
            response = self._example.process(event.payload.signal.text)

        if not response:
            # None (or empty) means "no opinion" — publish nothing at all,
            # rather than an event carrying empty text.
            return

        scenario_id = extract_scenario_id(event)
        payload = self._create_payload(response, scenario_id)
        # source=event is not decoration: Event.with_source is the only thing
        # that copies tenant and scenario_id onto the reply. Omitting it is
        # the exact bug cltl-eliza's greeting branch has — see the class
        # docstring and docs/tenancy.md.
        self._event_bus.publish(self._output_topic, Event.for_payload(payload, source=event))

    def _describe_image(self, event: Event) -> Optional[str]:
        """Fetch the pixels the signal points at, and hand them to the example."""
        signal = event.payload.signal

        if not signal.files:
            logger.warning("Image signal %s carries no file reference; nothing to "
                           "fetch. A publisher is expected to put one "
                           "'cltl-storage:image/<id>' entry in signal.files.",
                           signal.id)
            return None

        file_url = signal.files[0]
        try:
            image = self._image_loader(file_url)
        except Exception as e:
            # Deliberately not re-raised. TopicWorker would log and swallow it
            # anyway, and a reference that resolves to nothing is a thing that
            # happens: the publisher's upload of the pixels is itself
            # best-effort (cltl-chat-ui skips it when cv2 is unavailable, and
            # records the reference regardless). Three causes, in the order
            # they actually occur — the log line says so because the symptom,
            # "I uploaded an image and nothing answered", says nothing at all.
            logger.warning(
                "Could not load the pixels for image signal %s from %s: %s. "
                "Either they were never stored (the publisher's upload is "
                "best-effort and needs cv2), or the storage service is not "
                "running, or [myorg.example] image_storage_url points somewhere "
                "else. See docs/gotchas.md.", signal.id, file_url, e)
            return None

        # The declared size is already on the bus: signal.ruler is a MultiIndex
        # whose bounds are (0, 0, width, height). Comparing it with what came
        # back is what makes the fetch more than ceremony — it is the difference
        # between trusting a reference and having resolved it.
        self._warn_on_size_mismatch(signal, image)

        return self._image_example.describe(image)

    @staticmethod
    def _warn_on_size_mismatch(signal, image: np.ndarray) -> None:
        bounds = getattr(signal.ruler, "bounds", None)
        if not bounds or len(bounds) != 4 or image is None or image.ndim < 2:
            return

        declared = (bounds[2] - bounds[0], bounds[3] - bounds[1])
        actual = (image.shape[1], image.shape[0])
        if declared != actual:
            logger.warning(
                "Image signal %s declares bounds %s, i.e. %sx%s, but the pixels "
                "fetched from storage are %sx%s. Answering with the pixels, which "
                "are the thing that was actually retrieved.",
                signal.id, tuple(bounds), declared[0], declared[1], actual[0], actual[1])

    def _create_payload(self, response, scenario_id):
        signal = TextSignal.for_scenario(scenario_id, timestamp_now(), timestamp_now(), None, response)
        # for_agent, not for_speaker: annotates the signal as coming from the
        # agent, which is what puts the reply on the agent's side of the chat.
        return TextSignalEvent.for_agent(signal)
