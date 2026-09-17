"""`myorg.tenant.service` — the scenario lifecycle, and the strict tenant check.

The strict check is the half worth reading. `ExampleService` only WARNS about a
missing tenant (tests/test_tenancy.py pins that, and it stays true); this
service refuses to start. The asymmetry is deliberate and documented in
docs/tenancy.md — `myorg.example` is the part you replace and has to keep
working quietly on an ordinary single-tenant deployment, whereas this service
exists only because of tenant separation.
"""
import unittest
from queue import Empty, Queue

from cltl.combot.infra.event.memory import SynchronousEventBus

from myorg.tenant.service import TenantService
from tests.support import DictConfigurationManager

SCENARIO_TOPIC = "cltl.topic.scenario"


def _service(**kwargs):
    """A service on an in-process bus. `start_delay=0` — never sleep in a test."""
    bus = kwargs.pop("event_bus", None) or SynchronousEventBus()
    kwargs.setdefault("start_delay", 0)
    return TenantService(SCENARIO_TOPIC, bus, resource_manager=None, **kwargs), bus


def _config(**overrides):
    tenant_section = {
        "topic_scenario": SCENARIO_TOPIC,
        "start_scenario": "True",
        "start_delay": "0",
        "agent": "Leolani",
        "speaker": "Human",
        "location": "unknown",
    }
    tenant_section.update(overrides.pop("myorg.tenant", {}))

    sections = {
        "myorg.tenant": tenant_section,
        "cltl.event": {"implementation": overrides.pop("implementation", "internal")},
    }
    if "tenant" in overrides:
        sections["cltl.event.kombu"] = {"tenant": overrides.pop("tenant")}

    assert not overrides, f"unused: {overrides}"
    return DictConfigurationManager(sections)


class ScenarioLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.service, self.bus = _service()
        self.events = Queue()
        self.bus.subscribe(SCENARIO_TOPIC, self.events.put)

    def test_start_announces_one_scenario(self):
        self.service.start()

        event = self.events.get(timeout=1)
        self.assertEqual("ScenarioStarted", event.payload.type)
        self.assertEqual(self.service.scenario.id, event.payload.scenario.id)
        # for_scenario_payload, not for_payload: the event is self-describing to
        # anything using extract_scenario_id.
        self.assertEqual(self.service.scenario.id, event.metadata.scenario_id)
        self.assertTrue(self.events.empty())

    def test_stop_closes_the_same_scenario(self):
        self.service.start()
        started = self.events.get(timeout=1)

        self.service.stop()
        stopped = self.events.get(timeout=1)

        self.assertEqual("ScenarioStopped", stopped.payload.type)
        self.assertEqual(started.payload.scenario.id, stopped.payload.scenario.id)
        self.assertIsNotNone(stopped.payload.scenario.ruler.end)

    def test_stop_without_start_is_silent(self):
        # The `return`-not-`pass` lesson, restated for this service's sentinel:
        # cltl-eliza and cltl-vad both fall through here and raise.
        self.service.stop()

        with self.assertRaises(Empty):
            self.events.get(timeout=0.1)

    def test_stop_is_idempotent(self):
        self.service.start()
        self.events.get(timeout=1)

        self.service.stop()
        self.events.get(timeout=1)
        self.service.stop()

        with self.assertRaises(Empty):
            self.events.get(timeout=0.1)

    def test_start_scenario_false_announces_nothing(self):
        service, bus = _service(start_scenario=False)
        events = Queue()
        bus.subscribe(SCENARIO_TOPIC, events.put)

        service.start()
        service.stop()

        with self.assertRaises(Empty):
            events.get(timeout=0.1)

    def test_start_delay_is_skipped_on_an_in_process_bus(self):
        # A SynchronousEventBus dispatches in the publishing thread and has no
        # binding window, so there is nothing to wait for. A 30s delay that was
        # NOT skipped would hang this test rather than fail it, which is why the
        # assertion is on the elapsed time.
        import time
        service, _ = _service(start_delay=30, shared_bus=False)

        before = time.monotonic()
        service.start()

        self.assertLess(time.monotonic() - before, 1.0)

    def test_empty_topic_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            TenantService("", SynchronousEventBus(), resource_manager=None)

        self.assertIn("topic_scenario", str(caught.exception))


class StrictTenantCheckTest(unittest.TestCase):
    """On a shared bus, a tenant service without a usable tenant must not start."""

    def _construct(self, tenant):
        return TenantService(SCENARIO_TOPIC, SynchronousEventBus(), resource_manager=None,
                             start_delay=0, shared_bus=True, tenant=tenant)

    def test_a_good_tenant_constructs(self):
        self._construct("tenant-a")
        self._construct("tenant_b")
        self._construct("t1")

    def test_missing_tenant_is_rejected(self):
        for tenant in (None, ""):
            with self.subTest(tenant=tenant), self.assertRaises(ValueError) as caught:
                self._construct(tenant)
            self.assertIn("tenant", str(caught.exception).lower())

    def test_unexpanded_variable_is_rejected(self):
        # The repo's most-documented failure mode: EnvInterpolation passes an
        # unset variable through as a literal with only a warning, and the bus
        # then binds a real, valid, permanently empty queue.
        for tenant in ("$CLTL_TENANT", "${CLTL_TENANT}"):
            with self.subTest(tenant=tenant), self.assertRaises(ValueError) as caught:
                self._construct(tenant)
            self.assertIn("CLTL_TENANT", str(caught.exception))

    def test_a_tenant_that_is_not_one_routing_key_word_is_rejected(self):
        # A '.', '*' or '#' silently changes which keys `<topic>.<tenant>`
        # matches. Uppercase is rejected because `docker compose` lowercases an
        # interpolated project name but NOT the container environment, so the
        # two halves would bind different keys.
        for tenant in ("tenant.a", "tenant#", "tenant*", "Tenant_A", "-leading", "_leading"):
            with self.subTest(tenant=tenant), self.assertRaises(ValueError):
                self._construct(tenant)

    def test_an_in_process_bus_is_exempt(self):
        # SynchronousEventBus stamps every event "local" and dispatches to every
        # subscriber: there are no tenants to get wrong. Same guard
        # ExampleService applies to its own warning.
        TenantService(SCENARIO_TOPIC, SynchronousEventBus(), resource_manager=None,
                      start_delay=0, shared_bus=False, tenant=None)

    def test_not_opening_a_scenario_is_exempt(self):
        # start_scenario: false is the documented escape hatch for a deployment
        # that has its own cltl-context. Refusing to start there would be
        # obstructive, and the service does nothing anyway.
        TenantService(SCENARIO_TOPIC, SynchronousEventBus(), resource_manager=None,
                      start_delay=0, shared_bus=True, tenant=None, start_scenario=False)


class FromConfigTest(unittest.TestCase):
    def test_reads_its_section(self):
        service = TenantService.from_config(SynchronousEventBus(), None, _config())

        self.assertEqual(SCENARIO_TOPIC, service._topic_scenario)
        self.assertTrue(service._start_scenario)
        self.assertEqual(0, service._start_delay)

    def test_defaults_when_the_optional_keys_are_absent(self):
        config = DictConfigurationManager({
            "myorg.tenant": {"topic_scenario": SCENARIO_TOPIC},
            "cltl.event": {"implementation": "internal"},
        })

        service = TenantService.from_config(SynchronousEventBus(), None, config)

        self.assertTrue(service._start_scenario)
        self.assertEqual("Leolani", service._agent)

    def test_a_kombu_bus_without_a_tenant_refuses(self):
        config = _config(implementation="kombu", tenant="")

        with self.assertRaises(ValueError):
            TenantService.from_config(SynchronousEventBus(), None, config)

    def test_a_kombu_bus_with_a_tenant_is_built(self):
        config = _config(implementation="kombu", tenant="tenant-a")

        service = TenantService.from_config(SynchronousEventBus(), None, config)

        self.assertEqual("tenant-a", service._tenant)
        self.assertTrue(service._shared_bus)


if __name__ == "__main__":
    unittest.main()
