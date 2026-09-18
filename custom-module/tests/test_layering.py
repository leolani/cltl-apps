"""api.py and echo.py must stay pure logic — no EventBus, no TopicWorker, no
config. That boundary is what lets tests/test_echo.py be four assertions with
no scaffolding. There is no directory split enforcing it (unlike the
platform's own cltl/ vs cltl_service/ convention), so it is enforced by AST
instead.
"""
import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "myorg" / "example"
# `cltl.backend` joins the list for the image half: `ImageExample` is handed a
# numpy array precisely so that an implementation of it cannot know the pixels
# arrived over HTTP from a storage service. Resolving the reference is
# service.py's job. numpy itself is fine — it is a data type, not a platform
# service.
FORBIDDEN_PREFIXES = ("cltl.combot.infra", "cltl.backend")

TENANT_SRC = Path(__file__).resolve().parent.parent / "src" / "myorg" / "tenant"
# A NARROWER rule for myorg/tenant/scenario.py, rather than a relaxation of the
# blanket one above. That file is platform mechanics, not domain logic, so the
# boundary its docstring actually claims is "no bus, no worker, no config, no
# resource manager" — publishing lives in service.py. `timestamp_now`
# (cltl.combot.infra.time_util) is the one deliberate exception: it is a clock,
# and integration/src/cltl_integration/drivers/scenario.py imports it for the
# same reason.
FORBIDDEN_FOR_SCENARIO = ("cltl.combot.infra.event",
                          "cltl.combot.infra.topic_worker",
                          "cltl.combot.infra.config",
                          "cltl.combot.infra.resource")


def _imported_modules(path: Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


class LayeringTest(unittest.TestCase):
    def test_api_has_no_infra_dependency(self):
        self._assert_no_infra_import(SRC / "api.py")

    def test_echo_has_no_infra_dependency(self):
        self._assert_no_infra_import(SRC / "echo.py")

    def test_imagesize_has_no_infra_or_backend_dependency(self):
        self._assert_no_infra_import(SRC / "imagesize.py")

    def test_scenario_does_not_touch_the_bus(self):
        path = TENANT_SRC / "scenario.py"
        offending = [m for m in _imported_modules(path)
                     if m.startswith(FORBIDDEN_FOR_SCENARIO)]
        self.assertEqual([], offending,
                         f"{path.name} imports {offending}; building a Scenario must "
                         f"not require an EventBus — service.py is what publishes it.")

    def test_scenario_may_read_the_clock(self):
        # Pins the exception as an exception, so that widening it later is a
        # visible edit rather than a quiet one.
        self.assertIn("cltl.combot.infra.time_util",
                      list(_imported_modules(TENANT_SRC / "scenario.py")))

    def _assert_no_infra_import(self, path: Path):
        offending = [m for m in _imported_modules(path) if m.startswith(FORBIDDEN_PREFIXES)]
        self.assertEqual([], offending,
                         f"{path.name} imports platform infrastructure ({offending}); "
                         f"pure logic must not depend on EventBus/TopicWorker, nor on "
                         f"where a signal's pixels happen to be stored.")


if __name__ == "__main__":
    unittest.main()
