#!/usr/bin/env python
"""Rung 3, headless — the installed component, composed in one process.

No broker, no Docker, no meta-repo runner: this is the recipe
`integration/src/cltl_integration/runner/inprocess.py:69-88` follows for a
whole deployment, reduced to exactly one module. Run after `make build`:

    venv/bin/python attach/inprocess.py

Prints the reply this template's own ExampleService produces for a hand-built
utterance, then shuts the container down cleanly. This is
`tests/test_container.py` with `print` instead of `assert` — see that file for
the same recipe under test.
"""
from queue import Queue

from cltl.combot.infra.container import InfraContainer
from cltl.combot.infra.di_container import singleton
from cltl.combot.infra.event import Event
from cltl.combot.infra.event.memory import SynchronousEventBus
from cltl.combot.infra.time_util import timestamp_now
from cltl.combot.event.emissor import TextSignalEvent
from emissor.representation.scenario import TextSignal

from myorg.example.container import ExampleContainer

INPUT_TOPIC = "cltl.topic.text_in"
OUTPUT_TOPIC = "cltl.topic.text_out"


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
    """

    def __init__(self, bus):
        self._bus = bus

    @property
    def config_manager(self):
        return _DictConfigurationManager({
            "myorg.example": {"topic_input": INPUT_TOPIC, "topic_output": OUTPUT_TOPIC},
            "cltl.event": {"implementation": "internal"},
        })

    @property
    def event_bus(self):
        return self._bus


def main():
    bus = SynchronousEventBus()
    replies = Queue()
    bus.subscribe(OUTPUT_TOPIC, replies.put)

    application = ApplicationContainer(bus)
    with application:
        signal = TextSignal.for_scenario("scenario-demo", timestamp_now(), timestamp_now(), None, "hello there")
        bus.publish(INPUT_TOPIC, Event.for_payload(TextSignalEvent.for_speaker(signal)))

        reply = replies.get(timeout=5)
        print(reply.payload.signal.text)


if __name__ == "__main__":
    main()
