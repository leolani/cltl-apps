import logging
import unittest
from queue import Empty, Queue

from cltl.combot.infra.event import Event
from cltl.combot.infra.event.memory import SynchronousEventBus
from cltl.combot.infra.time_util import timestamp_now
from cltl.combot.event.emissor import TextSignalEvent
from emissor.representation.scenario import TextSignal

from myorg.example.echo import EchoExample
from myorg.example.service import ExampleService

INPUT_TOPIC = "inputTopic"
OUTPUT_TOPIC = "outputTopic"


def _utterance(text: str, scenario_id: str = "scenario-1") -> TextSignalEvent:
    signal = TextSignal.for_scenario(scenario_id, timestamp_now(), timestamp_now(), None, text)
    return TextSignalEvent.for_speaker(signal)


class ExampleServiceTest(unittest.TestCase):
    def setUp(self):
        self.event_bus = SynchronousEventBus()
        self.service = ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(),
                                      self.event_bus, resource_manager=None)
        self.replies = Queue()
        self.event_bus.subscribe(OUTPUT_TOPIC, self.replies.put)

    def tearDown(self):
        self.service.stop()

    def _publish(self, text: str, scenario_id: str = "scenario-1", tenant: str = None) -> Event:
        event = Event.for_payload(_utterance(text, scenario_id))
        if tenant:
            event = Event.with_tenant(event, tenant)
        self.event_bus.publish(INPUT_TOPIC, event)
        return event

    def test_transforms_and_publishes_a_reply(self):
        self.service.start()

        self._publish("hello there")

        reply = self.replies.get(timeout=1)
        self.assertEqual("TextSignalEvent", reply.payload.type)
        self.assertIn("HELLO THERE", reply.payload.signal.text)
        self.assertRaises(Empty, lambda: self.replies.get(timeout=0.01))

    def test_a_declining_transform_publishes_nothing(self):
        # EchoExample.process returns None for blank text — the non-obvious
        # behaviour the template exists to demonstrate.
        self.service.start()

        self._publish("   ")

        self.assertRaises(Empty, lambda: self.replies.get(timeout=0.2))

    def test_reply_carries_the_source_scenario_id(self):
        # extract_scenario_id falls back from event.metadata.scenario_id to
        # payload.signal.time.container_id (cltl.combot.infra.event.util) —
        # publishing via Event.for_payload with no scenario_id in metadata
        # exercises exactly that fallback, which is the common case for a
        # signal published straight onto the bus rather than round-tripped
        # through a scenario-aware component first.
        self.service.start()

        self._publish("hi", scenario_id="scenario-xyz")

        reply = self.replies.get(timeout=1)
        self.assertEqual("scenario-xyz", reply.payload.signal.time.container_id)

    def test_reply_metadata_carries_scenario_id_when_the_source_event_has_one(self):
        self.service.start()

        event = Event.for_scenario_payload("scenario-xyz", _utterance("hi", "scenario-xyz"))
        self.event_bus.publish(INPUT_TOPIC, event)

        reply = self.replies.get(timeout=1)
        self.assertEqual("scenario-xyz", reply.metadata.scenario_id)

    def test_reply_carries_the_source_tenant(self):
        # The regression test for `source=event`: SynchronousEventBus stamps
        # "local" on anything untenanted, so if _process ever drops source=,
        # this assertion is what catches it.
        self.service.start()

        self._publish("hi", tenant="tenant-a")

        reply = self.replies.get(timeout=1)
        self.assertEqual("tenant-a", reply.metadata.tenant)

    def test_reply_is_annotated_as_the_agent(self):
        self.service.start()

        self._publish("hi")

        reply = self.replies.get(timeout=1)
        annotation_agents = [m.value for mention in reply.payload.signal.mentions
                             for m in mention.annotations if m.type == "ConversationalAgent"]
        self.assertIn("LEOLANI", annotation_agents)

    def test_stop_before_start_does_not_raise(self):
        # Regression guard: cltl-eliza and cltl-vad both write `if not
        # self._topic_worker: pass` here, which falls straight through to
        # `self._topic_worker.stop()` on None. This must `return` instead.
        service = ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(),
                                 self.event_bus, resource_manager=None)
        service.stop()  # must not raise

    def test_empty_input_topic_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            ExampleService("", OUTPUT_TOPIC, EchoExample(), self.event_bus, resource_manager=None)

    def test_empty_output_topic_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            ExampleService(INPUT_TOPIC, "", EchoExample(), self.event_bus, resource_manager=None)

    def test_a_raising_transform_does_not_kill_the_worker(self):
        processed = Queue()

        class FlakyExample:
            def __init__(self):
                self._calls = 0

            def process(self, text):
                self._calls += 1
                processed.put(self._calls)
                if self._calls == 1:
                    raise RuntimeError("boom")
                return f"ok: {text}"

        service = ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, FlakyExample(),
                                 self.event_bus, resource_manager=None)
        try:
            service.start()
            self._publish("first")  # TopicWorker logs and swallows the exception
            # TopicWorker's default buffer_size=1 with OVERWRITE would let a
            # second publish race the first out of the queue before the
            # worker thread drains it; wait for evidence the first was
            # actually picked up before sending the second.
            self.assertEqual(1, processed.get(timeout=1))

            self._publish("second")
            self.assertEqual(2, processed.get(timeout=1))

            # The worker processes on its own thread; the reply to the second
            # event is what proves the first one's exception did not kill it
            # — the ERROR log TopicWorker's bare except emits is subject to
            # the same cross-thread timing and is not asserted on directly.
            reply = self.replies.get(timeout=1)
            self.assertIn("ok: second", reply.payload.signal.text)
        finally:
            service.stop()


if __name__ == "__main__":
    unittest.main()
