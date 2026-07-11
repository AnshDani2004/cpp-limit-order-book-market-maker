#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "simulations" / "run_queue_position_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("run_queue_position_diagnostics", SCRIPT)
queue_diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(queue_diag)


class QueuePositionDiagnosticsTests(unittest.TestCase):
    def test_distance_and_queue_depth_buckets_are_deterministic(self):
        self.assertEqual(queue_diag.distance_bucket("5"), "0_to_5")
        self.assertEqual(queue_diag.distance_bucket("5.1"), "5_to_10")
        self.assertEqual(queue_diag.distance_bucket("20.1"), "20_to_40")
        self.assertEqual(queue_diag.distance_bucket("45"), "40_plus")

        self.assertEqual(queue_diag.queue_depth_bucket("0"), "0")
        self.assertEqual(queue_diag.queue_depth_bucket("100"), "1_to_100")
        self.assertEqual(queue_diag.queue_depth_bucket("501"), "501_to_1000")
        self.assertEqual(queue_diag.queue_depth_bucket("1001"), "1001_plus")

    def test_aggregate_group_reports_fill_probability_and_queue_depth(self):
        rows = [
            {
                "quote_quantity": "10",
                "filled_quantity": "10",
                "queue_quantity_ahead": "0",
                "queue_orders_ahead": "0",
                "distance_from_mid": "5",
                "whether_the_quote_ever_filled": "true",
                "time_to_first_fill_if_any": "3",
                "whether_it_was_canceled_unfilled": "false",
            },
            {
                "quote_quantity": "10",
                "filled_quantity": "0",
                "queue_quantity_ahead": "200",
                "queue_orders_ahead": "2",
                "distance_from_mid": "7",
                "whether_the_quote_ever_filled": "false",
                "time_to_first_fill_if_any": "",
                "whether_it_was_canceled_unfilled": "true",
            },
        ]

        summary = queue_diag.aggregate_group(rows, {"flow_profile": "fixture"})

        self.assertEqual(summary["flow_profile"], "fixture")
        self.assertEqual(summary["quote_count"], 2)
        self.assertEqual(summary["filled_quote_count"], 1)
        self.assertEqual(summary["fill_probability"], "0.5")
        self.assertEqual(summary["average_queue_quantity_ahead"], "100")
        self.assertEqual(summary["median_queue_quantity_ahead"], "100")
        self.assertEqual(summary["zero_queue_quantity_share"], "0.5")
        self.assertEqual(summary["average_time_to_first_fill"], "3")
        self.assertEqual(summary["canceled_unfilled_quotes"], 1)


if __name__ == "__main__":
    unittest.main()
