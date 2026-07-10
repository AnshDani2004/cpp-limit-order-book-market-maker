#!/usr/bin/env python3

import importlib.util
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "itch_intensity_calibration.py"
SPEC = importlib.util.spec_from_file_location("itch_intensity_calibration", MODULE_PATH)
itch_intensity_calibration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(itch_intensity_calibration)


def u48(value):
    return value.to_bytes(6, "big")


def add_message(order_ref, timestamp, side, shares, stock, price):
    return (
        b"A"
        + struct.pack(">H", 1)
        + struct.pack(">H", 2)
        + u48(timestamp)
        + struct.pack(">Q", order_ref)
        + side.encode("ascii")
        + struct.pack(">I", shares)
        + stock.encode("ascii").ljust(8, b" ")
        + struct.pack(">I", price)
    )


def execute_message(order_ref, timestamp, shares):
    return (
        b"E"
        + struct.pack(">H", 1)
        + struct.pack(">H", 2)
        + u48(timestamp)
        + struct.pack(">Q", order_ref)
        + struct.pack(">I", shares)
        + struct.pack(">Q", 999)
    )


def delete_message(order_ref, timestamp):
    return b"D" + struct.pack(">H", 1) + struct.pack(">H", 2) + u48(timestamp) + struct.pack(">Q", order_ref)


def replace_message(old_ref, new_ref, timestamp, shares, price):
    return (
        b"U"
        + struct.pack(">H", 1)
        + struct.pack(">H", 2)
        + u48(timestamp)
        + struct.pack(">Q", old_ref)
        + struct.pack(">Q", new_ref)
        + struct.pack(">I", shares)
        + struct.pack(">I", price)
    )


class ItchIntensityCalibrationTests(unittest.TestCase):
    def test_measurement_counts_filled_and_unfilled_quote_segments_by_distance(self):
        payloads = [
            add_message(100, 10, "B", 100, "TEST", 9900),
            add_message(200, 20, "S", 100, "TEST", 10100),
            add_message(300, 30, "B", 25, "TEST", 9950),
            delete_message(300, 40),
            add_message(400, 50, "S", 40, "TEST", 10050),
            execute_message(400, 60, 40),
        ]
        messages = [itch_intensity_calibration.itch_replay.parse_message(payload) for payload in payloads]

        result = itch_intensity_calibration.measure_intensity(messages, ["TEST"], 1.0)
        rows = itch_intensity_calibration.bucket_rows(result)
        summary = itch_intensity_calibration.coverage_summary(result, rows)

        self.assertEqual(2, summary.closed_quote_segments)
        self.assertEqual(1, summary.filled_quote_segments)
        self.assertEqual(1, summary.execution_messages_in_segments)
        self.assertEqual(0, summary.right_censored_quote_segments)
        self.assertEqual(1, summary.non_empty_distance_buckets)
        self.assertEqual(1, summary.positive_fill_buckets)
        self.assertEqual(2, result.skipped_one_sided_mid_segments)
        self.assertEqual(0, result.skipped_crossed_mid_segments)
        self.assertEqual(2, rows[0]["quote_observations"])
        self.assertEqual(1, rows[0]["filled_quote_segments"])
        self.assertAlmostEqual(0.5, rows[0]["fill_probability"])

        diagnostic_rows = itch_intensity_calibration.bucket_diagnostic_rows(result)
        self.assertEqual(1, len(diagnostic_rows))
        self.assertEqual(2, diagnostic_rows[0]["quote_observations"])
        self.assertEqual(2, diagnostic_rows[0]["distinct_order_refs"])
        self.assertEqual(2, diagnostic_rows[0]["distinct_side_price_levels"])
        self.assertEqual(1, diagnostic_rows[0]["top_side_price_count"])
        self.assertAlmostEqual(0.5, diagnostic_rows[0]["top_side_price_share"])
        self.assertAlmostEqual(0.0, diagnostic_rows[0]["replace_close_share"])
        self.assertFalse(diagnostic_rows[0]["maintenance_bucket"])

    def test_crossed_books_do_not_create_quote_segments(self):
        payloads = [
            add_message(100, 10, "B", 100, "TEST", 10000),
            add_message(200, 20, "S", 100, "TEST", 9900),
            add_message(300, 30, "B", 100, "TEST", 9800),
            delete_message(300, 40),
        ]
        messages = [itch_intensity_calibration.itch_replay.parse_message(payload) for payload in payloads]

        result = itch_intensity_calibration.measure_intensity(messages, ["TEST"], 1.0)
        rows = itch_intensity_calibration.bucket_rows(result)
        summary = itch_intensity_calibration.coverage_summary(result, rows)

        self.assertEqual(0, summary.closed_quote_segments)
        self.assertEqual(0, summary.non_empty_distance_buckets)
        self.assertEqual(2, result.skipped_one_sided_mid_segments)
        self.assertEqual(1, result.skipped_crossed_mid_segments)

    def test_start_time_filters_measured_segments_without_losing_book_state(self):
        payloads = [
            add_message(100, 10, "B", 100, "TEST", 9900),
            add_message(200, 20, "S", 100, "TEST", 10100),
            add_message(300, 30, "B", 25, "TEST", 9950),
            delete_message(300, 40),
            add_message(400, 50, "S", 40, "TEST", 10050),
            execute_message(400, 60, 40),
        ]
        messages = [itch_intensity_calibration.itch_replay.parse_message(payload) for payload in payloads]

        result = itch_intensity_calibration.measure_intensity(messages, ["TEST"], 1.0, start_time_ns=45)
        rows = itch_intensity_calibration.bucket_rows(result)
        summary = itch_intensity_calibration.coverage_summary(result, rows)

        self.assertEqual(1, summary.closed_quote_segments)
        self.assertEqual(1, summary.filled_quote_segments)
        self.assertEqual(1, rows[0]["quote_observations"])
        self.assertEqual(1, rows[0]["filled_quote_segments"])
        self.assertEqual(10, result.first_timestamp)
        self.assertEqual(60, result.last_timestamp)

    def test_replace_only_zero_fill_bucket_is_flagged_as_maintenance(self):
        payloads = [
            add_message(100, 10, "B", 100, "TEST", 10000),
            add_message(200, 20, "S", 100, "TEST", 10100),
            add_message(300, 30, "B", 100, "TEST", 9000),
        ]
        old_ref = 300
        for index in range(50):
            new_ref = 301 + index
            payloads.append(replace_message(old_ref, new_ref, 40 + index, 100, 9000))
            old_ref = new_ref
        payloads.append(delete_message(old_ref, 100))
        messages = [itch_intensity_calibration.itch_replay.parse_message(payload) for payload in payloads]

        result = itch_intensity_calibration.measure_intensity(messages, ["TEST"], 1.0, start_time_ns=40)
        diagnostic_rows = itch_intensity_calibration.bucket_diagnostic_rows(result)
        maintenance_rows = [row for row in diagnostic_rows if row["maintenance_bucket"]]

        self.assertEqual(1, len(maintenance_rows))
        self.assertEqual(50, maintenance_rows[0]["quote_observations"])
        self.assertEqual(0, maintenance_rows[0]["filled_quote_segments"])
        self.assertGreaterEqual(maintenance_rows[0]["replace_close_share"], 0.95)
        self.assertAlmostEqual(1.0, maintenance_rows[0]["replace_message_share"])

    def test_fit_gate_passes_when_thresholds_are_met(self):
        summary = itch_intensity_calibration.CoverageSummary(
            closed_quote_segments=500,
            filled_quote_segments=100,
            execution_messages_in_segments=100,
            right_censored_quote_segments=0,
            non_empty_distance_buckets=8,
            positive_fill_buckets=5,
            symbol_count=1,
        )

        itch_intensity_calibration.assert_fit_gate(summary)

    def test_fit_gate_rejects_sparse_positive_fill_buckets(self):
        summary = itch_intensity_calibration.CoverageSummary(
            closed_quote_segments=500,
            filled_quote_segments=100,
            execution_messages_in_segments=100,
            right_censored_quote_segments=0,
            non_empty_distance_buckets=8,
            positive_fill_buckets=4,
            symbol_count=1,
        )

        with self.assertRaises(itch_intensity_calibration.CalibrationGateError) as context:
            itch_intensity_calibration.assert_fit_gate(summary)

        self.assertIn("positive_fill_buckets 4 below 5", str(context.exception))


if __name__ == "__main__":
    unittest.main()
