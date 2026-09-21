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

    def _assert_no_infra_import(self, path: Path):
        offending = [m for m in _imported_modules(path) if m.startswith(FORBIDDEN_PREFIXES)]
        self.assertEqual([], offending,
                         f"{path.name} imports platform infrastructure ({offending}); "
                         f"pure logic must not depend on EventBus/TopicWorker, nor on "
                         f"where a signal's pixels happen to be stored.")


if __name__ == "__main__":
    unittest.main()
