"""Open and close one tenant's scenario. NOT custom functionality — see scenario.py.

Structurally this is the smallest service in the platform: it subscribes to
nothing, so it has no `TopicWorker` at all. `myorg/example/service.py` next door
is the shape to copy for a component that actually processes events.
"""
import logging
import re
import time
from typing import Optional

from cltl.combot.event.emissor import ScenarioStarted, ScenarioStopped
from cltl.combot.infra.config import ConfigurationManager
from cltl.combot.infra.event import Event, EventBus
from cltl.combot.infra.resource import ResourceManager
from cltl.combot.infra.time_util import timestamp_now

from myorg.tenant.scenario import new_scenario

logger = logging.getLogger(__name__)

# A tenant id becomes one word of an AMQP routing key, so it may not contain a
# separator or a wildcard: KombuEventBus builds `<topic>.<tenant>`, and a '.',
# '*' or '#' would quietly change which keys that pattern matches. Copied from
# integration/src/cltl_integration/topology.py, which enforces the same rule on
# the deployment side.
_TENANT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Seconds to wait before announcing the scenario. See TenantService.start.
DEFAULT_START_DELAY = 5.0


class TenantService:
    """Publishes `ScenarioStarted` on start and `ScenarioStopped` on stop.

    That is the whole of it. The scenario it opens is what makes the tenant's
    `cltl-chat-ui` willing to render and publish anything at all
    (`ChatUiService._create_payload` raises `ValueError: No active scenario`
    otherwise), and it is published on the tenant's own bus because a tenant's
    scenario cannot be opened from the untenanted side.

    **No `TopicWorker`, deliberately.** A `TopicWorker` is a subscribe-and-
    dispatch loop; this service subscribes to nothing. Adding one would cost a
    thread and — under kombu, where this service publishes on
    `<topic_scenario>.<tenant>` — a queue bound to the very key it publishes
    on, so it would receive its own `ScenarioStarted` straight back.
    `InfraContainer` asks nothing more of a service than `start()` and
    `stop()`: `DIContainer.start`/`stop` are no-ops that `__enter__`/`__exit__`
    call (cltl.combot.infra.di_container), and there is no worker registry to
    register with.
    """

    @classmethod
    def from_config(cls, event_bus: EventBus, resource_manager: ResourceManager,
                    config_manager: ConfigurationManager):
        config = config_manager.get_config("myorg.tenant")

        topic_scenario = config.get("topic_scenario")
        start_scenario = config.get_boolean("start_scenario") if "start_scenario" in config else True
        start_delay = config.get_float("start_delay") if "start_delay" in config else DEFAULT_START_DELAY
        agent = config.get("agent") if "agent" in config else "Leolani"
        speaker = config.get("speaker") if "speaker" in config else "Human"
        location = config.get("location") if "location" in config else "unknown"

        # Read exactly as ExampleService.from_config reads them, guards
        # included — a standalone run may legitimately have neither section.
        implementation = (config_manager.get_config("cltl.event").get("implementation")
                          if "cltl.event" in config_manager else None)
        tenant = None
        if "cltl.event.kombu" in config_manager:
            kombu_config = config_manager.get_config("cltl.event.kombu")
            tenant = kombu_config.get("tenant") if "tenant" in kombu_config else None

        return cls(topic_scenario, event_bus, resource_manager,
                   start_scenario=start_scenario, start_delay=start_delay,
                   agent=agent, speaker=speaker, location=location,
                   shared_bus=(implementation != "internal"), tenant=tenant)

    def __init__(self, topic_scenario: str, event_bus: EventBus,
                 resource_manager: ResourceManager,
                 start_scenario: bool = True, start_delay: float = DEFAULT_START_DELAY,
                 agent: str = "Leolani", speaker: str = "Human", location: str = "unknown",
                 shared_bus: bool = False, tenant: str = None):
        if not topic_scenario:
            raise ValueError("[myorg.tenant] topic_scenario is empty. There is no "
                             "topic to announce the scenario on, so the tenant's "
                             "chat UI would never see one and would stay blank "
                             "forever — a misconfiguration, not an optional "
                             "output, so it is rejected here.")

        # Where ExampleService only WARNS about a missing tenant, this refuses.
        # The asymmetry is the point and is documented in docs/tenancy.md:
        # myorg.example is the part you replace and must keep working quietly on
        # an ordinary single-tenant deployment, whereas this service exists only
        # because of tenant separation, so "no tenant" is a contradiction in
        # terms. Skipped when the bus has no tenants (internal) or when this
        # service is not opening a scenario at all.
        if shared_bus and start_scenario:
            self._reject_bad_tenant(tenant)

        self._topic_scenario = topic_scenario
        self._event_bus = event_bus
        self._resource_manager = resource_manager

        self._start_scenario = start_scenario
        self._start_delay = start_delay
        self._agent = agent
        self._speaker = speaker
        self._location = location

        self._shared_bus = shared_bus
        self._tenant = tenant

        self._scenario = None

    @staticmethod
    def _reject_bad_tenant(tenant: Optional[str]) -> None:
        """Fail the process rather than come up healthy and route to nobody.

        Raised from `__init__`, i.e. during `@singleton` construction, so
        `src/main.py` exits non-zero before it ever binds port 8000 — the
        container is *exited*, not green and silent. It must stay fail-fast
        rather than something a caller retries: a `@singleton` factory that
        raises leaves a poisoned `None` in `DIContainer._singletons`
        (cltl.combot.infra.di_container), so a second attempt in the same
        process cannot succeed anyway.
        """
        if not tenant:
            raise ValueError(
                "[cltl.event.kombu] tenant is empty, but this service opens a "
                "tenant's scenario. An untenanted bus publishes on the bare "
                "'<topic_scenario>' routing key, which no tenanted chat UI "
                "binds — the scenario would reach nobody, the tenant's chat UI "
                "would stay blank forever, and nothing would log an error. Set "
                "$CLTL_TENANT to this tenant's id, or set [myorg.tenant] "
                "start_scenario to false if something else opens the scenario. "
                "See docs/tenancy.md.")

        if tenant.startswith("$"):
            raise ValueError(
                f"[cltl.event.kombu] tenant is {tenant!r} — an UNEXPANDED "
                f"environment variable, not a tenant id. Config values "
                f"interpolate $VAR at read time, and an unset variable is "
                f"passed through as the literal string with only a warning "
                f"(cltl.combot.infra.config.local.EnvInterpolation), after "
                f"which KombuEventBus binds a real, valid, permanently empty "
                f"queue. Declare the variable in the environment even when you "
                f"think it is set. See docs/tenancy.md.")

        if not _TENANT_ID.match(tenant):
            raise ValueError(
                f"[cltl.event.kombu] tenant is {tenant!r}, which is not one "
                f"lowercase routing-key word (^[a-z0-9][a-z0-9_-]*$). "
                f"KombuEventBus builds '<topic>.<tenant>', so a '.', '*' or "
                f"'#' silently changes which keys that pattern matches. Note "
                f"that `docker compose` lowercases an interpolated project "
                f"name: but NOT the value it puts in the container "
                f"environment, so CLTL_TENANT=Tenant_A yields a project named "
                f"'...tenant_a' and a tenant id of 'Tenant_A' — and the two "
                f"halves of the deployment then bind different keys. See "
                f"docs/tenancy.md.")

    @property
    def app(self):
        # Returns None: this service has no HTTP surface. To add one, see
        # cltl-monitoring/src/cltl_service/monitoring/service.py's `app`
        # property for the pattern (a lazily built, memoized Flask app).
        return None

    @property
    def scenario(self):
        """The open scenario, or None. Not a `@singleton` on the container.

        It is per-`start()` state rather than a component: a singleton holding
        it would survive a stop/start cycle and hand the second run the first
        run's scenario id.
        """
        return self._scenario

    def start(self, timeout=30):
        if not self._start_scenario:
            logger.info("[myorg.tenant] start_scenario is false; not opening a "
                        "scenario. Something else must, or the tenant's chat UI "
                        "stays blank.")
            return

        if self._shared_bus and self._start_delay > 0:
            # The same sleep, for the same reason, as cltl-context/src/main.py's
            # before it publishes the 'init' intention: KombuEventBus.subscribe
            # returns before RabbitMQ has bound the queue, and a topic exchange
            # drops a message matching no binding — silently, on both sides. The
            # subscriber that matters here is the tenant's chat UI, in a
            # DIFFERENT compose project, which `depends_on` cannot order us
            # against; hence longer than cltl-context's one second. Raising it
            # costs only startup latency. Skipped on a SynchronousEventBus,
            # which dispatches in the publishing thread and has no such window.
            logger.debug("Waiting %ss for subscribers to bind before opening the scenario",
                         self._start_delay)
            time.sleep(self._start_delay)

        self._scenario = new_scenario(agent=self._agent, speaker=self._speaker,
                                      location=self._location)
        # for_scenario_payload, not for_payload: it additionally stamps
        # metadata.scenario_id, which costs nothing and makes the event
        # self-describing to anything using extract_scenario_id. The TENANT is
        # stamped by the bus itself on publish (KombuEventBus.publish) — that is
        # the entire isolation mechanism, and it is why this has to run on the
        # tenant's own bus rather than the deployment's.
        self._event_bus.publish(
            self._topic_scenario,
            Event.for_scenario_payload(self._scenario.id, ScenarioStarted.create(self._scenario)))

        logger.info("Opened scenario %s for tenant %s", self._scenario.id,
                    self._tenant if self._tenant else "(untenanted)")

    def stop(self):
        # `return`, not a fall-through `pass`: stopping a service that never
        # opened a scenario must be a no-op, and clearing the scenario makes a
        # second stop() one too. Same lesson as ExampleService.stop.
        if not self._scenario:
            return

        self._scenario.ruler.end = timestamp_now()
        self._event_bus.publish(
            self._topic_scenario,
            Event.for_scenario_payload(self._scenario.id, ScenarioStopped.create(self._scenario)))

        logger.info("Closed scenario %s", self._scenario.id)
        self._scenario = None
