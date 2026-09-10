"""Shared test scaffolding. Not named test_*.py, so neither `python -m
unittest` nor pytest tries to collect it as a suite on its own — see
docs/component.md on the make test / pytest reconciliation.
"""
from typing import Mapping

from cltl.combot.infra.config import Configuration, ConfigurationManager


class DictConfiguration(Configuration):
    """The `.get(key, multi=False)` / `key in config` surface, over a plain dict."""

    def __init__(self, values: Mapping[str, str]):
        self._values = dict(values)

    def get(self, key, multi=False):
        if multi:
            return [v.strip() for v in self._values[key].split(",") if v.strip()]
        return self._values[key]

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
