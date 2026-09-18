import unittest

import numpy as np

from myorg.example.echo import MARKER as ECHO_MARKER
from myorg.example.imagesize import MARKER, ImageSizeExample


class ImageSizeExampleTest(unittest.TestCase):
    def setUp(self):
        self.example = ImageSizeExample()

    def test_reports_width_by_height(self):
        # 64 wide, 48 high — NOT square, on purpose. numpy's shape is
        # (rows, cols) = (height, width) while the answer says width first, so
        # a square fixture would pass with the two swapped and this is the only
        # mistake available in the file under test.
        image = np.zeros((48, 64, 3), dtype=np.uint8)

        self.assertEqual(f"The image you uploaded is 64x48{MARKER}",
                         self.example.describe(image))

    def test_a_greyscale_image_has_no_channel_axis_and_still_works(self):
        # Nothing in this deployment produces one, but `shape[:2]` is what makes
        # it a non-event rather than an IndexError.
        self.assertIn("64x48", self.example.describe(np.zeros((48, 64), dtype=np.uint8)))

    def test_none_returns_none(self):
        self.assertIsNone(self.example.describe(None))

    def test_empty_image_returns_none(self):
        # A zero-byte upload can still decode to an empty array, and "0x0"
        # would be worse than silence.
        self.assertIsNone(self.example.describe(np.zeros((0, 0, 3), dtype=np.uint8)))

    def test_the_marker_matches_the_text_placeholder(self):
        # The two placeholders each declare their own copy, so that deleting
        # one does not break the other — this is where that duplication is
        # stopped from drifting. See the comment in imagesize.py.
        self.assertEqual(ECHO_MARKER, MARKER)


if __name__ == "__main__":
    unittest.main()
