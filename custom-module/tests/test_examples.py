"""attach/connect.py is not part of the myorg package — it is loaded here the
same way a notebook or script loads it, via importlib rather than sys.path
manipulation (CLAUDE.md forbids the latter outright).
"""
import importlib.util
import unittest
import unittest.mock
from pathlib import Path

ATTACH_DIR = Path(__file__).resolve().parent.parent / "attach"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ATTACH_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EventBusConfigTest(unittest.TestCase):
    """What `connect.event_bus` builds, asserted through `connect.event_bus`.

    kombu's `Connection` and `Exchange` are lazy, so constructing a
    `KombuEventBus` opens no socket and starts no thread — nothing here needs a
    broker. That makes it worth testing the real path rather than a copy of the
    three lines inside it.
    """

    @classmethod
    def setUpClass(cls):
        cls.connect = _load("connect")

    def _bus(self, server="amqp://localhost:5672/", **kwargs):
        bus = self.connect.event_bus(server, **kwargs)
        self.addCleanup(bus.close)

        return bus

    def test_an_empty_tenant_is_present_rather_than_absent(self):
        # The distinction the whole configuration exists to carry.
        # KombuEventBus does `config.get('tenant') if 'tenant' in config else
        # None`, so a key that is present-but-empty yields '' while a missing
        # one yields None. Both are falsy and the bus behaves identically, but
        # '' is the proof that the key was written at all -- and a config that
        # silently dropped it would bind the wrong routing key with no error.
        self.assertEqual("", self._bus(tenant="")._tenant)
        self.assertEqual("", self._bus()._tenant)

    def test_a_tenant_reaches_the_bus(self):
        self.assertEqual("tenant-a", self._bus(tenant="tenant-a")._tenant)

    def test_a_percent_encoded_password_survives(self):
        # Why the parser is built with interpolation=None. Under the default
        # interpolation this parses fine and then raises InterpolationSyntaxError
        # from inside KombuEventBus.__init__, on `config.get('server')` --
        # nowhere near the value that caused it. Percent-encoded broker
        # credentials are not hypothetical -- attach/ used to unquote() them.
        self._bus("amqp://leolani:p%40ss@127.0.0.1:5672/", tenant="tenant-a")

    def test_loading_connect_twice_is_safe(self):
        # Serialization is registered at import: the type vars with emissor and
        # 'cltl-json' with kombu. Both registries are plain dicts, so a second
        # import must overwrite rather than complain -- which is also what lets
        # example.ipynb repeat the block verbatim in its setup cell.
        _load("connect")
        _load("connect")


class EventJsonTest(unittest.TestCase):
    """`event_json` is what example.ipynb folds into a <details> block.

    It is only worth showing if it is genuinely the wire format: a reader opens
    it to settle what a payload contains, and a pretty-printed `repr` dressed up
    as JSON would answer that question wrongly.
    """

    @classmethod
    def setUpClass(cls):
        cls.connect = _load("connect")

    def _event(self):
        from cltl.combot.event.emissor import TextSignalEvent
        from cltl.combot.infra.event.api import Event
        from emissor.representation.scenario import TextSignal

        # Angle brackets because the notebook renders this inside HTML and has
        # to escape it; a payload carries whatever somebody typed.
        signal = TextSignal.for_scenario("s-1", 0, 1, None, "<hello>")

        return Event.for_payload(TextSignalEvent.for_speaker(signal))

    def test_it_is_the_serializer_kombu_was_given(self):
        import json

        event = self._event()

        self.assertEqual(json.loads(self.connect.serializer(event)),
                         json.loads(self.connect.event_json(event)))

    def test_it_reaches_the_payload(self):
        import json

        parsed = json.loads(self.connect.event_json(self._event()))

        self.assertEqual("<hello>", parsed["payload"]["signal"]["text"])

    def test_it_is_indented_for_reading(self):
        self.assertIn("\n  ", self.connect.event_json(self._event()))


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

    def test_a_failed_import_names_the_interpreter(self):
        # docs/gotchas.md promises this, and it is the only place the hint can
        # land: every cell above load_image needs only cltl.combot and emissor,
        # which the wrong environment usually also has -- so a notebook on the
        # wrong kernel works perfectly until here and then fails on a package
        # you can see is installed.
        #
        # A None in sys.modules is how you make an import fail for a package
        # that IS installed: Python raises rather than re-importing.
        import sys

        with unittest.mock.patch.dict(
                sys.modules, {"cltl.backend.source.client_source": None}):
            with self.assertRaises(ImportError) as raised:
                self.connect.load_image("cltl-storage:image/x")

        self.assertIn(sys.executable, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
