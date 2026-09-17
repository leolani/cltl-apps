import unittest
from pathlib import Path

from setuptools import find_namespace_packages

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"


class PackagingTest(unittest.TestCase):
    def test_namespace_package_is_found_but_not_installed_itself(self):
        packages = find_namespace_packages(include=['myorg.*'], where=str(SRC))

        self.assertIn("myorg.example", packages)
        # One distribution, two packages. `include=['myorg.*']` picks both up
        # with no change to setup.py — which is what the `.*` is for.
        self.assertIn("myorg.tenant", packages)
        # `myorg` itself must NOT be in the list — that is what leaves it a
        # PEP 420 namespace package with no __init__.py content of its own,
        # so a second distribution (myorg.other_module) can share the
        # top-level namespace without either one shadowing the other.
        self.assertNotIn("myorg", packages)

    def test_myorg_init_is_empty(self):
        content = (SRC / "myorg" / "__init__.py").read_text()
        self.assertEqual("", content.strip())

    def test_example_init_is_empty(self):
        content = (SRC / "myorg" / "example" / "__init__.py").read_text()
        self.assertEqual("", content.strip())

    def test_tenant_init_is_empty(self):
        content = (SRC / "myorg" / "tenant" / "__init__.py").read_text()
        self.assertEqual("", content.strip())

    def test_tenant_has_no_api_module(self):
        # Deliberate, and pinned so nobody "completes the pattern".
        # myorg/example/api.py exists because EchoExample is meant to be
        # replaced; nothing in myorg.tenant is. A scenario is built exactly one
        # way, and the whole package is meant to be DELETED once the deployment
        # has a cltl-context of its own — an ABC there would advertise a choice
        # that does not exist. See src/myorg/tenant/scenario.py.
        self.assertFalse((SRC / "myorg" / "tenant" / "api.py").exists())

    def test_main_is_not_under_the_namespace_package(self):
        # src/main.py is deliberately top-level, so find_namespace_packages
        # never picks it up and it never ships in the distribution — see
        # docs/component.md.
        self.assertTrue((SRC / "main.py").is_file())
        self.assertFalse((SRC / "myorg" / "main.py").exists())


if __name__ == "__main__":
    unittest.main()
