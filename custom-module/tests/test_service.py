import logging
import unittest
from queue import Empty, Queue

from cltl.combot.infra.event import Event
from cltl.combot.infra.event.memory import SynchronousEventBus
from cltl.combot.infra.time_util import timestamp_now
from cltl.combot.event.emissor import ImageSignalEvent, TextSignalEvent
from emissor.representation.scenario import TextSignal

from myorg.example.echo import EchoExample
from myorg.example.imagesize import ImageSizeExample
from myorg.example.service import ExampleService
from tests.support import fake_image_loader, image_signal, pixels

INPUT_TOPIC = "inputTopic"
OUTPUT_TOPIC = "outputTopic"
IMAGE_TOPIC = "imageTopic"
IMAGE_URL = "cltl-storage:image/image-1"


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
            # The worker's buffer is small and its rejection strategy is
            # OVERWRITE (see BUFFER_SIZE in service.py), so a burst of publishes
            # can drop the older ones; wait for evidence the first was actually
            # picked up before sending the second.
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


class ExampleImageServiceTest(unittest.TestCase):
    """The second modality. A separate class rather than edits to the one above:
    the text path is unchanged and its tests should keep saying so.
    """

    def setUp(self):
        self.event_bus = SynchronousEventBus()
        self.replies = Queue()
        self.event_bus.subscribe(OUTPUT_TOPIC, self.replies.put)
        self.service = self._service({IMAGE_URL: pixels(64, 48)})

    def tearDown(self):
        self.service.stop()

    def _service(self, images):
        return ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(),
                              self.event_bus, resource_manager=None,
                              image_topic=IMAGE_TOPIC, image_example=ImageSizeExample(),
                              image_loader=fake_image_loader(images))

    def _publish_image(self, url: str = IMAGE_URL, width: int = 64, height: int = 48,
                       scenario_id: str = "scenario-1", tenant: str = None) -> Event:
        signal = image_signal(scenario_id, url, width, height)
        event = Event.for_scenario_payload(scenario_id, ImageSignalEvent.create(signal))
        if tenant:
            event = Event.with_tenant(event, tenant)
        self.event_bus.publish(IMAGE_TOPIC, event)

        return event

    def test_an_image_draws_one_reply_with_its_size(self):
        self.service.start()

        self._publish_image()

        reply = self.replies.get(timeout=1)
        self.assertEqual("TextSignalEvent", reply.payload.type)
        self.assertIn("64x48", reply.payload.signal.text)
        self.assertRaises(Empty, lambda: self.replies.get(timeout=0.01))

    def test_the_reply_carries_the_source_tenant_and_scenario(self):
        # The same `source=event` regression guard the text path has, on the
        # branch that was added second and could have forgotten it.
        self.service.start()

        self._publish_image(tenant="tenant-a", scenario_id="scenario-xyz")

        reply = self.replies.get(timeout=1)
        self.assertEqual("tenant-a", reply.metadata.tenant)
        self.assertEqual("scenario-xyz", reply.metadata.scenario_id)

    def test_a_signal_with_no_file_reference_publishes_nothing(self):
        self.service.start()

        signal = image_signal("scenario-1", IMAGE_URL, 64, 48)
        signal.files = []
        self.event_bus.publish(IMAGE_TOPIC, Event.for_scenario_payload(
            "scenario-1", ImageSignalEvent.create(signal)))

        self.assertRaises(Empty, lambda: self.replies.get(timeout=0.2))

    def test_pixels_that_were_never_stored_publish_nothing(self):
        # The publisher's upload is best-effort — cltl-chat-ui skips it when cv2
        # is unavailable and records the reference anyway — so a reference that
        # resolves to nothing is a normal event, not a bug to crash on.
        self.service = self._service({IMAGE_URL: None})
        self.service.start()

        self._publish_image()

        self.assertRaises(Empty, lambda: self.replies.get(timeout=0.2))

    def test_a_failed_fetch_does_not_kill_the_worker(self):
        self.service = self._service({IMAGE_URL: None, "cltl-storage:image/ok": pixels(8, 4)})
        self.service.start()

        self._publish_image()
        self._publish_image(url="cltl-storage:image/ok", width=8, height=4)

        self.assertIn("8x4", self.replies.get(timeout=1).payload.signal.text)

    def test_text_still_round_trips_with_the_image_path_on(self):
        self.service.start()

        signal = TextSignal.for_scenario("scenario-1", timestamp_now(), timestamp_now(), None, "hello")
        self.event_bus.publish(INPUT_TOPIC, Event.for_payload(TextSignalEvent.for_speaker(signal)))

        self.assertIn("HELLO", self.replies.get(timeout=1).payload.signal.text)

    def test_a_size_mismatch_is_answered_with_the_pixels(self):
        # The signal declares the size too, in ruler.bounds. When the two
        # disagree, the pixels win — they are what was actually retrieved — and
        # the disagreement is logged rather than swallowed.
        self.service.start()

        with self.assertLogs("myorg.example.service", level=logging.WARNING) as logs:
            self._publish_image(width=700, height=640)  # pixels are really 64x48
            reply = self.replies.get(timeout=1)

        self.assertIn("64x48", reply.payload.signal.text)
        self.assertTrue(any("700x640" in line for line in logs.output), logs.output)

    def test_topics_is_one_topic_when_the_image_path_is_off(self):
        service = ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(),
                                 self.event_bus, resource_manager=None)

        self.assertEqual([INPUT_TOPIC], service.topics)
        self.assertEqual([INPUT_TOPIC, IMAGE_TOPIC], self.service.topics)

    def test_a_half_wired_image_path_is_rejected_at_construction(self):
        # An image_topic with nothing to answer it would subscribe, receive and
        # drop every image in silence. The topic is optional; a half of it is
        # not.
        with self.assertRaises(ValueError):
            ExampleService(INPUT_TOPIC, OUTPUT_TOPIC, EchoExample(), self.event_bus,
                           resource_manager=None, image_topic=IMAGE_TOPIC,
                           image_example=ImageSizeExample())


class StorageUrlTest(unittest.TestCase):
    """`_storage_loader`'s three branches — the `myorg.tenant` strictness
    pattern applied to the one address this module cannot work without.
    """

    def test_an_empty_url_is_rejected(self):
        with self.assertRaises(ValueError) as e:
            ExampleService._storage_loader("")
        self.assertIn("image_storage_url", str(e.exception))

    def test_an_unexpanded_variable_is_rejected(self):
        # EnvInterpolation passes an undefined variable through verbatim with
        # only a warning, so this is what an unset CLTL_STORAGE_URL looks like
        # by the time it gets here.
        with self.assertRaises(ValueError) as e:
            ExampleService._storage_loader("$CLTL_STORAGE_URL")
        self.assertIn("UNEXPANDED", str(e.exception))

    def test_a_missing_trailing_slash_is_normalised_not_rejected(self):
        # Normalised, because eliza-server's own custom.config ships it without
        # one and this module has to work against a deployment config it does
        # not control. urljoin() would otherwise drop the last path segment.
        with self.assertLogs("myorg.example.service", level=logging.WARNING) as logs:
            loader = ExampleService._storage_loader("http://localhost:8002/storage")

        self.assertTrue(callable(loader))
        self.assertTrue(any("urljoin" in line for line in logs.output), logs.output)


if __name__ == "__main__":
    unittest.main()
