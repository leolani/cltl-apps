"""attach/connect.py is not part of the myorg package — it is loaded here the
same way a notebook or script loads it, via importlib rather than sys.path
manipulation (CLAUDE.md forbids the latter outright).
"""
import importlib.util
import unittest
from pathlib import Path

ATTACH_DIR = Path(__file__).resolve().parent.parent / "attach"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ATTACH_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConnectHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connect = _load("connect")

    def test_dict_configuration_manager_supplies_kombu_config(self):
        manager = self.connect._DictConfigurationManager({
            "cltl.event.kombu": {
                "server": "amqp://localhost:5672/",
                "exchange": "cltl.combot",
                "compression": "bzip2",
                "tenant": "",
            }})

        self.assertTrue("cltl.event.kombu" in manager)
        config = manager.get_config("cltl.event.kombu")

        self.assertEqual("amqp://localhost:5672/", config.get("server"))
        # An absent key and an empty value are not the same thing:
        # KombuEventBus does `config.get('tenant') if 'tenant' in config else
        # None`, so the key must be PRESENT (even empty) for a bus explicitly
        # configured with no tenant to behave the same as one where the
        # concept was never mentioned at all.
        self.assertTrue("tenant" in config)
        self.assertEqual("", config.get("tenant"))

    def test_missing_section_raises(self):
        manager = self.connect._DictConfigurationManager({})
        with self.assertRaises(ValueError):
            manager.get_config("cltl.event.kombu")

    def test_register_is_idempotent(self):
        # Calling register() twice must not raise (kombu.serialization.register
        # would otherwise be asked to register the same name twice).
        self.connect.register()
        self.connect.register()


if __name__ == "__main__":
    unittest.main()
