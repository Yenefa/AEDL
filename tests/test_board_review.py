import unittest

from tools.board_review import review_exit_code, review_usb_routing


GOOD_PINS = {
    "J1.A6": "USB_DP_CONN",
    "J1.B6": "USB_DP_CONN",
    "R7.1": "USB_DP_CONN",
    "R7.2": "USB_DP",
    "U1.14": "USB_DP",
    "J1.A7": "USB_DM_CONN",
    "J1.B7": "USB_DM_CONN",
    "R8.1": "USB_DM_CONN",
    "R8.2": "USB_DM",
    "U1.13": "USB_DM",
}


def segment(net, length):
    return {"net": net, "x1": 0.0, "y1": 0.0, "x2": length, "y2": 0.0}


class BoardReviewTests(unittest.TestCase):
    def test_board_review_process_fails_closed_on_any_non_pass_status(self):
        self.assertEqual(review_exit_code([{"status": "pass"}]), 0)
        self.assertEqual(review_exit_code([{"status": "fail"}]), 1)
        self.assertEqual(review_exit_code([{"status": "unknown"}]), 1)
        self.assertEqual(review_exit_code([{}]), 1)

    def test_usb_review_measures_both_sides_of_each_series_resistor(self):
        segments = [
            segment("USB_DP_CONN", 18.0),
            segment("USB_DP", 2.0),
            segment("USB_DM_CONN", 17.6),
            segment("USB_DM", 2.1),
        ]

        result = review_usb_routing(segments, GOOD_PINS)

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["measured"]["logical_channel_lengths_mm"]["D+"], 20.0)
        self.assertEqual(result["measured"]["logical_channel_lengths_mm"]["D-"], 19.7)
        self.assertEqual(result["measured"]["endpoint_mismatches"], [])

    def test_usb_review_rejects_crossed_mcu_endpoint_identity(self):
        crossed = dict(GOOD_PINS)
        crossed["U1.14"] = "USB_DM"
        crossed["U1.13"] = "USB_DP"
        segments = [
            segment("USB_DP_CONN", 18.0),
            segment("USB_DP", 2.0),
            segment("USB_DM_CONN", 18.0),
            segment("USB_DM", 2.0),
        ]

        result = review_usb_routing(segments, crossed)

        self.assertEqual(result["status"], "fail")
        self.assertIn("U1.14", " ".join(result["measured"]["endpoint_mismatches"]))
        self.assertIn("U1.13", " ".join(result["measured"]["endpoint_mismatches"]))


if __name__ == "__main__":
    unittest.main()
