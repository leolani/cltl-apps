import abc
from typing import Optional

import numpy as np


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


class ImageExample(abc.ABC):
    """The one thing this component does to an incoming image.

    A second interface rather than a second method on :class:`Example`, because
    the two are replaced independently: a module that answers text and a module
    that looks at pictures are different jobs, and `Example`'s docstring above
    promises "a string in, a string or None out". Both are wired by the same
    `ExampleService`, which dispatches on the topic an event arrived on.
    """

    @abc.abstractmethod
    def describe(self, image: np.ndarray) -> Optional[str]:
        """What to say about an image, or None to say nothing.

        `image` is the pixels themselves: a numpy array of shape
        `(height, width, channels)`, RGB, `uint8` — note rows first, which is
        the one thing in this file worth getting right on the first try.

        A numpy array, deliberately, and NOT `cltl.backend.api.camera.Image`,
        which is what the platform's own storage client hands back. numpy is a
        *data* type; `cltl.backend`'s `Image` belongs to a service, and an
        implementation of this interface has no business knowing that the
        pixels arrived over HTTP from anywhere in particular. That boundary is
        what keeps tests/test_imagesize.py four assertions with no scaffolding,
        and it is enforced by tests/test_layering.py.

        Same `None` contract as `Example.process`, for the same two reasons.
        """
        raise NotImplementedError()
