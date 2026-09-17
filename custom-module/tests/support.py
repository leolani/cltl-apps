"""Shared test scaffolding. Not named test_*.py, so neither `python -m
unittest` nor pytest tries to collect it as a suite on its own — see
docs/component.md on the make test / pytest reconciliation.
"""
from typing import Mapping

from cltl.combot.infra.config import Configuration, ConfigurationManager


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
