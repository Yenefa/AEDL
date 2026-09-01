import unittest

from tools.polish_m2_usb_skew import (
    ORIGINAL_END,
    ORIGINAL_START,
    POLISH_MIDPOINT,
    added_length_mm,
    same_segment,
)


class PolishM2UsbSkewTests(unittest.TestCase):
    def test_polish_adds_only_the_bounded_length_needed_for_usb_skew(self):
        added = added_length_mm(ORIGINAL_START, ORIGINAL_END, POLISH_MIDPOINT)
        self.assertGreater(added, 1.2)
        self.assertLess(added, 1.3)
        self.assertLess(POLISH_MIDPOINT[1], ORIGINAL_START[1])

    def test_target_match_is_orientation_independent_and_tolerance_bounded(self):
        self.assertTrue(same_segment(ORIGINAL_START, ORIGINAL_END))
        self.assertTrue(same_segment(ORIGINAL_END, ORIGINAL_START))
        self.assertFalse(same_segment((38.7, 4.7841), ORIGINAL_END))


if __name__ == "__main__":
    unittest.main()
