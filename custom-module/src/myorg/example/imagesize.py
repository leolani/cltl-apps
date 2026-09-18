import numpy as np

from myorg.example.api import ImageExample

# The same string echo.py uses, written out again rather than imported from it.
# Both files are placeholders meant to be replaced — and replaced
# independently: someone who keeps the text half and throws away the image half
# should not be left with an import from a file they deleted, nor with a third
# "shared constants" module to notice. tests/test_imagesize.py asserts the two
# strings are equal, which is where that coupling belongs.
MARKER = " (via myorg.example)"


class ImageSizeExample(ImageExample):
    """Measures the picture you sent it and reads the number back. Delete this.

    The image-side counterpart of EchoExample, and silly for the same reason:
    a placeholder that looked like real vision would invite improvement, and a
    placeholder that obviously is not invites replacement. What it does
    demonstrate is worth keeping — that by the time your code is called, the
    pixels are simply *there*, with no reference to resolve and no HTTP left to
    do. `ExampleService` did that part.
    """

    def describe(self, image: np.ndarray):
        if image is None or image.size == 0:
            # Nothing to measure. The fetch can legitimately produce an empty
            # array (a zero-byte upload that still decoded), and an answer of
            # "0x0" would be worse than silence.
            return None

        # Rows first. numpy is row-major, so shape is (height, width, channels)
        # while every human and every UI says "width by height" — this one line
        # is the whole bug surface of this file, which is why
        # tests/test_imagesize.py measures a NON-square image: a square one
        # passes with the two swapped.
        height, width = image.shape[:2]

        return f"The image you uploaded is {width}x{height}{MARKER}"
