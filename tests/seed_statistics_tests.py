#!/usr/bin/env python3

import csv
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "simulations" / "run_seed_statistics.py"
SPEC = importlib.util.spec_from_file_location("run_seed_statistics", SCRIPT)
seed_stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed_stats)


class SeedStatisticsTests(unittest.TestCase):
    def test_confidence_interval_uses_sample_standard_deviation(self):
        values = [1.0, 2.0, 3.0]

        mean, low, high = seed_stats.confidence_interval_95(values)

        self.assertEqual(mean, 2.0)
        self.assertAlmostEqual(seed_stats.sample_stddev(values), 1.0)
        self.assertAlmostEqual(low, 2.0 - 1.96 / math.sqrt(3.0))
        self.assertAlmostEqual(high, 2.0 + 1.96 / math.sqrt(3.0))

    def test_aggregate_and_comparison_rows_are_deterministic(self):
        raw_rows = []
        for strategy, values in [
            ("naive symmetric", [10.0, 12.0, 14.0]),
            ("avellaneda stoikov", [20.0, 22.0, 24.0]),
        ]:
            for index, value in enumerate(values):
                row = {
                    "risk_mode": "uncontrolled",
                    "external_flow_profile": "hand_chosen",
                    "regime": "low volatility",
                    "strategy": strategy,
                }
                for metric in seed_stats.METRICS:
                    row[metric] = "0"
                row["net_pnl_after_fees"] = str(value)
                row["risk_adjusted_pnl"] = str(value)
                row["final_inventory"] = str(index)
                row["inventory_variance"] = str(value)
                row["fill_rate"] = "0.5"
                raw_rows.append(row)

        aggregate = seed_stats.aggregate_rows(raw_rows)
        lookup = {
            (row["strategy"], row["metric"]): row
            for row in aggregate
        }

        self.assertEqual(lookup[("naive symmetric", "net_pnl_after_fees")]["sample_count"], 3)
        self.assertEqual(lookup[("naive symmetric", "net_pnl_after_fees")]["mean"], "12")
        self.assertEqual(lookup[("avellaneda stoikov", "net_pnl_after_fees")]["mean"], "22")

        comparisons = seed_stats.comparison_rows(aggregate)
        pnl = [
            row for row in comparisons
            if row["metric"] == "net_pnl_after_fees"
            and row["left_strategy"] == "avellaneda stoikov"
            and row["right_strategy"] == "naive symmetric"
        ][0]
        self.assertEqual(pnl["mean_delta"], "10")
        self.assertEqual(pnl["ci95_overlap"], "false")

    def test_paired_delta_summary_is_deterministic(self):
        raw_rows = []
        for strategy, values in [
            ("naive symmetric", [10.0, 12.0, 14.0]),
            ("avellaneda stoikov", [20.0, 32.0, 44.0]),
        ]:
            for index, value in enumerate(values):
                row = {
                    "risk_mode": "uncontrolled",
                    "external_flow_profile": "hand_chosen",
                    "regime": "low volatility",
                    "strategy": strategy,
                    "seed_index": str(index),
                }
                for metric in seed_stats.METRICS:
                    row[metric] = "0"
                row["net_pnl_after_fees"] = str(value)
                row["risk_adjusted_pnl"] = str(value)
                row["final_inventory"] = str(value)
                row["inventory_variance"] = str(value)
                row["fill_rate"] = str(value)
                row["maximum_drawdown"] = str(value)
                row["gross_spread_capture"] = str(value)
                row["adverse_selection_cost"] = str(value)
                raw_rows.append(row)

        aggregate = seed_stats.aggregate_rows(raw_rows)
        comparisons = seed_stats.comparison_rows(aggregate)
        deltas = seed_stats.paired_delta_rows(raw_rows, comparisons)
        self.assertEqual(len(deltas), len(seed_stats.PAIRED_DELTA_METRICS) * 3)

        summary = seed_stats.paired_delta_summary_rows(deltas)
        pnl = [
            row for row in summary
            if row["metric"] == "net_pnl_after_fees"
            and row["left_strategy"] == "avellaneda stoikov"
            and row["right_strategy"] == "naive symmetric"
        ][0]
        self.assertEqual(pnl["sample_count"], 3)
        self.assertEqual(pnl["mean_delta"], "20")
        self.assertEqual(pnl["stddev_delta"], "10")
        self.assertEqual(pnl["paired_ci95_excludes_zero"], "true")
        self.assertAlmostEqual(float(pnl["ci95_low"]), 20.0 - 1.96 * 10.0 / math.sqrt(3.0))
        self.assertAlmostEqual(float(pnl["ci95_high"]), 20.0 + 1.96 * 10.0 / math.sqrt(3.0))

        claims = seed_stats.paired_delta_claim_rows(summary, comparisons)
        claim = [
            row for row in claims
            if row["metric"] == "net_pnl_after_fees"
            and row["left_strategy"] == "avellaneda stoikov"
            and row["right_strategy"] == "naive symmetric"
        ][0]
        self.assertEqual(claim["paired_delta_conclusion"], "left_higher")
        self.assertEqual(claim["previous_unpaired_ci95_overlap"], "false")
        self.assertEqual(claim["changed_from_unpaired"], "false")

    def test_write_rows_round_trips_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.csv"
            seed_stats.write_rows(path, [{"a": "1", "b": "2"}])
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows, [{"a": "1", "b": "2"}])


if __name__ == "__main__":
    unittest.main()
