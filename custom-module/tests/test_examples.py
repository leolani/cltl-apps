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


class BindingKeyTest(unittest.TestCase):
    """The routing rule the whole of docs/tenancy.md is about, as an assertion."""

    @classmethod
    def setUpClass(cls):
        cls.connect = _load("connect")

    def test_a_tenanted_subscriber_binds_exactly_its_own_tenant(self):
        self.assertEqual("cltl.topic.scenario.tenant-a",
                         self.connect.binding_key("cltl.topic.scenario", "tenant-a"))

    def test_an_untenanted_subscriber_binds_every_tenant(self):
        # `#` matches ZERO OR MORE words in RabbitMQ, so this matches every
        # tenant's traffic AND the bare topic. That asymmetry is what lets one
        # shared cltl-eliza serve every tenant.
        self.assertEqual("cltl.topic.scenario.#",
                         self.connect.binding_key("cltl.topic.scenario", ""))
        self.assertEqual("cltl.topic.scenario.#",
                         self.connect.binding_key("cltl.topic.scenario"))


class ScenarioHelperTest(unittest.TestCase):
    """connect.new_scenario is a deliberate COPY of myorg.tenant.scenario's.

    Rungs 1-2 install nothing from this template, so the duplication has to
    exist. Asserting the same shape in both places is what keeps the two copies
    from drifting — see tests/test_scenario.py for the other one.
    """

    @classmethod
    def setUpClass(cls):
        cls.connect = _load("connect")

    def test_shape_matches_the_packaged_version(self):
        from myorg.tenant import scenario as packaged

        scenario = self.connect.new_scenario(agent="A", speaker="S", location="L")

        self.assertEqual(packaged.AGENT_URI, self.connect.AGENT_URI)
        self.assertEqual(packaged.SPEAKER_URI, self.connect.SPEAKER_URI)
        self.assertEqual(packaged.SIGNALS, self.connect.SIGNALS)

        self.assertEqual("A", scenario.context.agent.name)
        self.assertEqual("S", scenario.context.speaker.name)
        self.assertEqual("L", scenario.context.location)
        self.assertIsNone(scenario.ruler.end)

    def test_an_explicit_id_is_honoured(self):
        self.assertEqual("s-1", self.connect.new_scenario("s-1").id)


class ImageHelperTest(unittest.TestCase):
    """attach/'s image code is a deliberate COPY of the packaged version's.

    Two copies, for the same reason `transform`/`EchoExample` are two copies:
    rungs 1-2 install nothing. These assertions are what keep them from
    drifting.
    """

    @classmethod
    def setUpClass(cls):
        cls.connect = _load("connect")
        cls.listen = _load("listen")

    def test_load_image_documents_the_trailing_slash(self):
        # The whole trap, in the one place a reader of rung 1 will meet it:
        # urljoin() drops the last path segment of a base without a slash, so
        # `.../storage` looks for `.../image/<id>` and 404s from a URL that
        # reads correctly in a log.
        doc = self.connect.load_image.__doc__
        self.assertIn("urljoin", doc)
        self.assertIn("must end in a slash", doc)

    def test_the_default_storage_url_has_one(self):
        self.assertTrue(self.connect.DEFAULT_STORAGE_URL.endswith("/"))

    def test_describe_image_agrees_with_the_packaged_placeholder(self):
        import numpy as np

        from myorg.example.imagesize import ImageSizeExample

        # Non-square, so that a swapped width and height is visible.
        image = np.zeros((48, 64, 3), dtype=np.uint8)

        self.assertIn("64x48", self.listen.describe_image(image))
        self.assertEqual(ImageSizeExample().describe(image).replace(
            "myorg.example", "attach/listen.py"),
            self.listen.describe_image(image))

    def test_describe_image_declines_the_same_inputs(self):
        import numpy as np

        self.assertIsNone(self.listen.describe_image(None))
        self.assertIsNone(self.listen.describe_image(np.zeros((0, 0, 3), dtype=np.uint8)))


class WaitUntilBoundBaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connect = _load("connect")

    def test_no_management_url_still_takes_the_flat_sleep_path(self):
        # `baseline` must not disturb the documented fallback: with no
        # management API there is nothing to ask, whichever question was meant.
        self.connect.wait_until_bound(None, ["cltl.topic.scenario"], baseline={})


if __name__ == "__main__":
    unittest.main()
