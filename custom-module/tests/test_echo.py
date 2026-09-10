import unittest

from myorg.example.echo import EchoExample, MARKER


class EchoExampleTest(unittest.TestCase):
    def setUp(self):
        self.example = EchoExample(prefix="YOU SAID:")

    def test_transforms_and_uppercases(self):
        result = self.example.process("hello there")
        self.assertEqual(f"YOU SAID: HELLO THERE{MARKER}", result)

    def test_blank_text_returns_none(self):
        self.assertIsNone(self.example.process(""))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(self.example.process("   \t  "))

    def test_own_output_returns_none(self):
        # The loop guard: text already carrying the marker is not re-processed.
        already = f"YOU SAID: HELLO{MARKER}"
        self.assertIsNone(self.example.process(already))


if __name__ == "__main__":
    unittest.main()
