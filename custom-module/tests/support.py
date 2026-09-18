"""Shared test scaffolding. Not named test_*.py, so neither `python -m
unittest` nor pytest tries to collect it as a suite on its own — see
docs/component.md on the make test / pytest reconciliation.
"""
from typing import Mapping, Optional

import numpy as np
from cltl.combot.infra.config import Configuration, ConfigurationManager
from cltl.combot.infra.time_util import timestamp_now
from emissor.representation.scenario import ImageSignal


class DictConfiguration(Configuration):
    """The `.get(key, multi=False)` / `key in config` surface, over a plain dict.

    The typed accessors are implemented rather than inherited: `Configuration`
    leaves them `NotImplementedError`, and the real `LocalConfiguration` gets
    them from configparser. `TenantService.from_config` reads `start_scenario`
    with `get_boolean` and `start_delay` with `get_float`, exactly as
    `cltl-context/src/main.py` reads its own `start_scenario`, so a test double
    that only answers `get()` would force the production code into a less
    idiomatic shape to suit the test.
    """

    # configparser's own vocabulary — see Configuration.get_boolean's contract.
    _TRUE = ("1", "yes", "true", "on")
    _FALSE = ("0", "no", "false", "off")

    def __init__(self, values: Mapping[str, str]):
        self._values = dict(values)

    def get(self, key, multi=False):
        if multi:
            return [v.strip() for v in self._values[key].split(",") if v.strip()]
        return self._values[key]

    def get_int(self, key):
        return int(self._values[key])

    def get_float(self, key):
        return float(self._values[key])

    def get_boolean(self, key):
        value = str(self._values[key]).strip().lower()
        if value in self._TRUE:
            return True
        if value in self._FALSE:
            return False
        raise ValueError(f"Not a boolean: {self._values[key]!r}")

    def __contains__(self, key):
        return key in self._values


class DictConfigurationManager(ConfigurationManager):
    """A `ConfigurationManager` over nested dicts — no config files, no DI container.

    Follows integration/src/cltl_integration/runner/tenants.py's
    `_TenantConfigurationManager`: it is exactly what `KombuEventBus` and
    `ExampleService.from_config` ask a configuration for, and nothing more.
    """

    def __init__(self, sections: Mapping[str, Mapping[str, str]]):
        self._sections = {name: DictConfiguration(values) for name, values in sections.items()}

    def has_config(self, name: str) -> bool:
        return name in self._sections

    def get_config(self, name: str, callback=None) -> Configuration:
        if name not in self._sections:
            raise ValueError(f"No configuration for {name}")
        return self._sections[name]


def pixels(width: int, height: int, channels: int = 3) -> np.ndarray:
    """An array shaped like a decoded image. Rows first, as numpy has it.

    Synthesised rather than committed, and an array rather than an encoded PNG,
    because that is what a subscriber actually receives: cltl-backend's storage
    answers in JSON with the pixel buffer base64-encoded, and
    `ClientImageSource` hands back the decoded `np.ndarray`. A PNG fixture would
    be testing a decoder nothing in this repository owns. Same reasoning as
    cltl-dev/integration/src/cltl_integration/drivers/image.py, one layer up.
    """
    return np.zeros((height, width, channels), dtype=np.uint8)


def fake_image_loader(images: Mapping[str, Optional[np.ndarray]]):
    """Stands in for the fetch from cltl-backend's image storage.

    The production loader is three lines around `ClientImageSource` (see
    `ExampleService._storage_loader`); this is what makes the service testable
    without a broker AND without an HTTP server, which is the reason the loader
    is injected at all. A url mapped to None raises, standing in for pixels
    that were never stored — the chat UI's upload of them is best-effort, so
    that case is not hypothetical.
    """
    def load(url: str) -> np.ndarray:
        if url not in images:
            raise KeyError(f"No image with id {url} found in the storage")
        image = images[url]
        if image is None:
            raise ValueError(f"Requests to {url} failed (404)")
        return image

    return load


def image_signal(scenario_id: str, url: str, width: int, height: int,
                 signal_id: str = "image-1") -> ImageSignal:
    """An `ImageSignal` shaped exactly as cltl-chat-ui publishes one.

    Bounds `(0, 0, width, height)`, one `cltl-storage:` reference in `files`,
    `signal_id == image_id`, and `array` left None by the factory — the pixels
    never travel on the bus. Mirrors
    `cltl_service.chatui.schema.create_image_signal`, minus the regions this
    module ignores.
    """
    return ImageSignal.for_scenario(scenario_id, timestamp_now(), timestamp_now(),
                                    url, (0, 0, width, height), signal_id=signal_id)
