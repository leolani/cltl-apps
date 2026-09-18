#!/usr/bin/env python
"""Rung 3, headless — the installed component, composed in one process.

No broker, no Docker, no meta-repo runner: this is the recipe
`integration/src/cltl_integration/runner/inprocess.py:69-88` follows for a
whole deployment, reduced to exactly one module. Run after `make build`:

    venv/bin/python attach/inprocess.py

Prints the replies this template's own ExampleService produces for a hand-built
utterance and a hand-built image signal, then shuts the container down cleanly.
This is `tests/test_container.py` with `print` instead of `assert` — see that
file for the same recipe under test.

The image half runs here with **no storage service and no HTTP at all**, which
is the whole payoff of `ExampleService` taking its image loader as an argument:
the fake below is one lambda. `ClientImageSource` would need a real endpoint
answering in the platform's JSON-with-base64 wire format; a test or a demo needs
the pixels, not the round trip.
"""
from queue import Queue

import numpy as np
from cltl.combot.event.emissor import ImageSignalEvent, TextSignalEvent
from cltl.combot.infra.event import Event
from cltl.combot.infra.event.memory import SynchronousEventBus
from cltl.combot.infra.time_util import timestamp_now
from emissor.representation.scenario import ImageSignal, TextSignal

from myorg.example.container import ExampleContainer

INPUT_TOPIC = "cltl.topic.text_in"
OUTPUT_TOPIC = "cltl.topic.text_out"
IMAGE_TOPIC = "cltl.topic.image"

SCENARIO_ID = "scenario-demo"
# 64 wide, 48 high — deliberately not square, so that a reply saying "48x64"
# would be visibly wrong rather than accidentally right. numpy is (rows, cols).
WIDTH, HEIGHT = 64, 48
IMAGE_URL = "cltl-storage:image/image-demo"


class _DictConfiguration:
    def __init__(self, values):
        self._values = dict(values)

    def get(self, key, multi=False):
        return self._values[key]

    def __contains__(self, key):
        return key in self._values


class _DictConfigurationManager:
    def __init__(self, sections):
        self._sections = {name: _DictConfiguration(v) for name, v in sections.items()}

    def has_config(self, name):
        return name in self._sections

    def get_config(self, name, callback=None):
        return self._sections[name]

    def __contains__(self, name):
        return self.has_config(name)


class ApplicationContainer(ExampleContainer):
    """Exactly what a deployment does — see docs/component.md — reduced to one
    module and one in-process bus, with no broker and no other containers.

    `ExampleContainer` alone, deliberately: unlike `src/main.py` this does NOT
    mix in `TenantContainer`. Nothing in `myorg.example` knows what a scenario
    is, so nothing here has to open one — the signals below carry a scenario id
    they invented themselves and that is enough. That is the clearest
    demonstration available that opening a scenario is a tenancy chore rather
    than part of this component; see docs/tenancy.md.
    """

    def __init__(self, bus):
        self._bus = bus

    @property
    def config_manager(self):
        return _DictConfigurationManager({
            "myorg.example": {
                "topic_input": INPUT_TOPIC,
                "topic_output": OUTPUT_TOPIC,
                "topic_image": IMAGE_TOPIC,
                # Never dialled: the loader built from it is replaced below,
                # before anything starts. It still has to be non-empty and
                # expanded, because `from_config` refuses both — which is
                # itself worth seeing from here.
                "image_storage_url": "http://localhost:8002/storage/",
            },
            "cltl.event": {"implementation": "internal"},
        })

    @property
    def event_bus(self):
        return self._bus


def _image_signal():
    """An ImageSignal shaped exactly as cltl-chat-ui publishes one.

    The pixels are NOT in it — `ImageSignal.for_scenario` hardcodes
    `array=None`, and `files` carries a `cltl-storage:` reference instead. The
    size is declared twice over: in `ruler.bounds` here, and in the shape of
    whatever the reference resolves to. `ExampleService` answers with the
    second and warns when they disagree.
    """
    return ImageSignal.for_scenario(SCENARIO_ID, timestamp_now(), timestamp_now(),
                                    IMAGE_URL, (0, 0, WIDTH, HEIGHT),
                                    signal_id="image-demo")


def main():
    bus = SynchronousEventBus()
    replies = Queue()
    bus.subscribe(OUTPUT_TOPIC, replies.put)

    application = ApplicationContainer(bus)
    with application:
        # Swapped after construction, and before anything is published: the
        # service holds the loader `from_config` built, and there is no storage
        # service in this process to talk to. A deployment never does this; a
        # demo and a test both do. tests/test_service.py uses the same seam.
        application.example_service._image_loader = (
            lambda url: np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8))

        signal = TextSignal.for_scenario(SCENARIO_ID, timestamp_now(), timestamp_now(), None, "hello there")
        bus.publish(INPUT_TOPIC, Event.for_payload(TextSignalEvent.for_speaker(signal)))
        print(replies.get(timeout=5).payload.signal.text)

        bus.publish(IMAGE_TOPIC, Event.for_scenario_payload(
            SCENARIO_ID, ImageSignalEvent.create(_image_signal())))
        print(replies.get(timeout=5).payload.signal.text)


if __name__ == "__main__":
    main()
