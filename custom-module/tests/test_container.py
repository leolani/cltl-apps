import unittest
from queue import Empty, Queue

from cltl.combot.infra.container import InfraContainer
from cltl.combot.infra.di_container import DIContainer, singleton
from cltl.combot.infra.event import Event
from cltl.combot.infra.event.memory import SynchronousEventBus
from cltl.combot.infra.time_util import timestamp_now
from cltl.combot.event.emissor import ImageSignalEvent, TextSignalEvent
from emissor.representation.scenario import TextSignal

from myorg.example.container import ExampleContainer
from tests.support import (DictConfigurationManager, fake_image_loader, image_signal,
                           pixels)

INPUT_TOPIC = "cltl.topic.text_in"
OUTPUT_TOPIC = "cltl.topic.text_out"
IMAGE_TOPIC = "cltl.topic.image"
IMAGE_URL = "cltl-storage:image/image-1"



def _reset_singletons():
    """Drop every cached @singleton in the process.

    `DIContainer._singletons` is a dict on `DIContainer` ITSELF, keyed by the
    bare method name — so a second container test class would otherwise be
    handed the first one's `example_service`, still bound to the first one's
    bus, and would see nothing on its own. Must be called on `DIContainer`:
    `_reset` is a classmethod doing `cls._singletons = dict()`, so calling it on
    a subclass shadows the attribute instead of clearing the one `@singleton`
    writes to. Same reasoning as `reset_process_state` in
    integration/src/cltl_integration/runner/inprocess.py.
    """
    DIContainer._reset()


class _InProcessContainer(ExampleContainer):
    """`ExampleContainer` with the two things a deployment normally supplies.

    Not `integration`'s `HarnessInfraContainer`: that lives in a component this
    template must not depend on, and it exists to compose MANY modules — see
    `integration/src/cltl_integration/runner/inprocess.py:69-88` for the recipe
    a real deployment follows (it is the one docs/component.md documents).
    Overriding two properties is all it takes to compose exactly one.

    `event_bus` is overridden rather than merely configured because
    `KombuEventBusContainer.event_bus` is a plain, non-`@singleton` property —
    every access would otherwise construct a fresh, real AMQP connection, and
    would hang this test suite on a machine with no broker.

    `resource_manager` is deliberately left alone: `ThreadedResourceContainer`
    is in-process and free, and letting the real one run is what makes this
    test exercise `provides=[output_topic]` for real.
    """

    def __init__(self, bus: SynchronousEventBus):
        self._bus = bus

    @property
    def config_manager(self):
        return DictConfigurationManager({
            "myorg.example": {
                "topic_input": INPUT_TOPIC,
                "topic_output": OUTPUT_TOPIC,
                "topic_image": IMAGE_TOPIC,
                # Never dialled — the loader it produces is replaced before any
                # image is published. It still has to be non-empty and expanded,
                # because from_config refuses both.
                "image_storage_url": "http://localhost:8002/storage/",
            },
            "cltl.event": {
                "implementation": "internal",
            },
        })

    @property
    def event_bus(self):
        return self._bus


class ContainerLifecycleTest(unittest.TestCase):
    def setUp(self):
        _reset_singletons()
        self.bus = SynchronousEventBus()
        self.container = _InProcessContainer(self.bus)
        self.replies = Queue()
        self.bus.subscribe(OUTPUT_TOPIC, self.replies.put)

    def test_start_processes_an_event_and_stop_leaves_no_worker(self):
        with self.container:
            signal = TextSignal.for_scenario("scenario-1", timestamp_now(), timestamp_now(), None, "hello")
            self.bus.publish(INPUT_TOPIC, Event.for_payload(TextSignalEvent.for_speaker(signal)))

            reply = self.replies.get(timeout=1)
            self.assertIn("HELLO", reply.payload.signal.text)

        # __exit__ has called stop(); starting again must work cleanly.
        with self.container:
            pass

    def test_singleton_accessors_are_prefixed(self):
        # @singleton keys its cache by the BARE method name across the whole
        # process, so an unprefixed accessor (`service` rather than
        # `example_service`) would collide with any other component mixed
        # into the same deployment that also defines `service`. This pins the
        # naming convention so a later rename cannot reintroduce that.
        members = dir(ExampleContainer)
        self.assertIn("example_service", members)
        self.assertIn("example", members)
        self.assertIn("image_example", members)
        self.assertNotIn("service", members)
        # `image` in particular would collide with more than one platform
        # component.
        self.assertNotIn("image", members)

    def test_an_image_round_trips_through_the_container(self):
        # The loader is the one thing a container cannot build for itself here:
        # there is no storage service in this process. Swapping it after
        # construction is what attach/inprocess.py does, for the same reason.
        with self.container:
            self.container.example_service._image_loader = fake_image_loader(
                {IMAGE_URL: pixels(700, 640)})

            signal = image_signal("scenario-1", IMAGE_URL, 700, 640)
            self.bus.publish(IMAGE_TOPIC, Event.for_scenario_payload(
                "scenario-1", ImageSignalEvent.create(signal)))

            self.assertIn("700x640", self.replies.get(timeout=1).payload.signal.text)


if __name__ == "__main__":
    unittest.main()
