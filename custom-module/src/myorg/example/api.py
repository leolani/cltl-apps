import abc
from typing import Optional


class Example(abc.ABC):
    """The one thing this component does to an incoming utterance.

    Deliberately narrow: a string in, a string or None out. No EventBus, no
    TopicWorker, no configuration — this file is where the logic that could be
    unit-tested on a desert island lives; `service.py` is where it meets the
    platform. Keeping that boundary is what makes tests/test_echo.py four
    assertions with no scaffolding.
    """

    @abc.abstractmethod
    def process(self, text: str) -> Optional[str]:
        """What to say back, or None to say nothing.

        None is not an error and not an empty string: a caller must publish
        nothing at all for it, not an event with empty text. A module that has
        no opinion about an utterance should stay silent rather than publish
        an empty reply — the chat UI would render it as a blank bubble, and
        cltl-emissor-data would persist it.
        """
        raise NotImplementedError()
