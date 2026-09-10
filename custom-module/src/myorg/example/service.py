import logging

from cltl.combot.event.emissor import TextSignalEvent
from cltl.combot.infra.config import ConfigurationManager
from cltl.combot.infra.event import Event, EventBus
from cltl.combot.infra.event.util import extract_scenario_id
from cltl.combot.infra.resource import ResourceManager
from cltl.combot.infra.time_util import timestamp_now
from cltl.combot.infra.topic_worker import TopicWorker
from emissor.representation.scenario import TextSignal

from myorg.example.api import Example

logger = logging.getLogger(__name__)


class ExampleService:
    """Subscribes to one topic, runs an :class:`Example`, publishes to another.

    Structurally this is cltl-eliza's ElizaService — see
    cltl-eliza/src/cltl_service/eliza/service.py — with two of its bugs fixed
    rather than copied: `stop()` returns instead of falling through a `pass`
    when there is no worker (cltl-monitoring gets this right, cltl-eliza and
    cltl-vad do not), and `_process` never publishes without `source=event`
    (cltl-eliza's greeting branch does, which drops tenant and scenario_id —
    see docs/tenancy.md).
    """

    @classmethod
    def from_config(cls, example: Example, event_bus: EventBus, resource_manager: ResourceManager,
                    config_manager: ConfigurationManager):
        config = config_manager.get_config("myorg.example")

        input_topic = config.get("topic_input")
        output_topic = config.get("topic_output")

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
                   shared_bus=(implementation != "internal"), tenant=tenant)

    def __init__(self, input_topic: str, output_topic: str, example: Example,
                 event_bus: EventBus, resource_manager: ResourceManager,
                 shared_bus: bool = False, tenant: str = None):
        if not input_topic:
            raise ValueError("[myorg.example] topic_input is empty. Subscribing to an "
                             "empty topic string binds a queue under kombu that can "
                             "never receive anything (see docs/component.md) — this is "
                             "a misconfiguration, not an optional input, so it is "
                             "rejected here rather than silently skipped.")
        if not output_topic:
            raise ValueError("[myorg.example] topic_output is empty; see topic_input above.")

        self._input_topic = input_topic
        self._output_topic = output_topic
        self._example = example
        self._event_bus = event_bus
        self._resource_manager = resource_manager

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
        self._topic_worker = TopicWorker([self._input_topic], self._event_bus,
                                         provides=[self._output_topic],
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

    def _process(self, event: Event[TextSignalEvent]):
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

    def _create_payload(self, response, scenario_id):
        signal = TextSignal.for_scenario(scenario_id, timestamp_now(), timestamp_now(), None, response)
        # for_agent, not for_speaker: annotates the signal as coming from the
        # agent, which is what puts the reply on the agent's side of the chat.
        return TextSignalEvent.for_agent(signal)
