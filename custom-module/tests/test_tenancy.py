import logging
import unittest

from cltl.combot.infra.event import Event
from cltl.combot.infra.event.memory import SynchronousEventBus
from cltl.combot.infra.time_util import timestamp_now
from cltl.combot.event.emissor import TextSignalEvent
from emissor.representation.scenario import TextSignal

from myorg.example.echo import EchoExample
from myorg.example.service import ExampleService

INPUT_TOPIC = "inputTopic"
OUTPUT_TOPIC = "outputTopic"


def _untenanted_event(text: str = "hi") -> Event:
    # Built by hand rather than published: SynchronousEventBus.publish stamps
    # "local" on the way through (memory.py), so an untenanted event cannot
    # reach a subscriber through the bus at all. The thing under test is the
    # branch in _process, not the bus.
    signal = TextSignal.for_scenario("scenario-1", timestamp_now(), timestamp_now(), None, text)
    return Event.for_payload(TextSignalEvent.for_speaker(signal))


class UntenantedEventWarningTest(unittest.TestCase):
    """`_process` warns once per process when an event carries no tenant."""

    def setUp(self):
        self.event_bus = SynchronousEventBus()
        self.service = ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(),
                                      self.event_bus, resource_manager=None)

    def test_warns_once_for_repeated_untenanted_events(self):
        with self.assertLogs(level=logging.WARNING) as logs:
            self.service._process(_untenanted_event("one"))
            self.service._process(_untenanted_event("two"))
            self.service._process(_untenanted_event("three"))

        tenant_warnings = [r for r in logs.records if "carries no tenant" in r.getMessage()]
        self.assertEqual(1, len(tenant_warnings))

    def test_no_warning_once_a_tenant_is_seen(self):
        self.service._process(_untenanted_event("one"))  # primes the flag

        with self.assertRaises(AssertionError):  # assertLogs raises if nothing was logged
            with self.assertLogs(level=logging.WARNING):
                tenanted = Event.with_tenant(_untenanted_event("two"), "tenant-a")
                self.service._process(tenanted)


class StartupWarningTest(unittest.TestCase):
    """`start()` warns once when the deployment's own bus has no tenant configured."""

    def setUp(self):
        self.event_bus = SynchronousEventBus()

    def tearDown(self):
        self.service.stop()

    def test_internal_bus_never_warns(self):
        # SynchronousEventBus has no tenants at all — warning here would train
        # people to ignore the warning. See integration/__main__.py's own
        # "no in-process meaning" reasoning for the same kind of guard.
        self.service = ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(),
                                      self.event_bus, resource_manager=None,
                                      shared_bus=False, tenant=None)
        with self.assertRaises(AssertionError):
            with self.assertLogs(level=logging.WARNING):
                self.service.start()

    def test_shared_bus_with_no_tenant_warns_once(self):
        self.service = ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(),
                                      self.event_bus, resource_manager=None,
                                      shared_bus=True, tenant=None)
        with self.assertLogs(level=logging.WARNING) as logs:
            self.service.start()

        self.assertEqual(1, len(logs.records))
        self.assertIn("[cltl.event.kombu] tenant", logs.records[0].getMessage())

    def test_shared_bus_with_a_tenant_does_not_warn(self):
        self.service = ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(),
                                      self.event_bus, resource_manager=None,
                                      shared_bus=True, tenant="tenant-a")
        with self.assertRaises(AssertionError):
            with self.assertLogs(level=logging.WARNING):
                self.service.start()


if __name__ == "__main__":
    unittest.main()
