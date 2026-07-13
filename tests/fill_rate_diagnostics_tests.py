#!/usr/bin/env python3

import importlib.util
import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_fill_rate_diagnostics.py"
ARTIFACTS = ROOT / "artifacts" / "fill_diagnostics"
SPEC = importlib.util.spec_from_file_location("generate_fill_rate_diagnostics", SCRIPT)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


def read_csv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


class FillRateDiagnosticsTests(unittest.TestCase):
    def test_lifecycle_schema_contains_required_fields(self):
        required = {
            "quote_id",
            "strategy_name",
            "seed",
            "regime",
            "flow_type",
            "event_index_submitted",
            "event_index_first_fill",
            "initial_queue_ahead",
            "displayed_depth_at_price",
            "submitted_at_best",
            "total_filled_size",
            "remaining_size",
            "final_status",
            "no_fill_reason",
        }
        self.assertTrue(required.issubset(set(diag.LIFECYCLE_FIELDS)))

    def test_execution_opportunity_schema_contains_required_fields(self):
        required = {
            "event_index",
            "flow_type",
            "side_of_aggressive_flow",
            "execution_price",
            "execution_size",
            "best_bid_before_event",
            "best_ask_before_event",
            "displayed_depth_at_touched_level",
            "market_maker_quote_present_at_touched_level",
            "market_maker_queue_position",
            "maker_fill_size_from_this_event",
            "reason_if_maker_was_not_filled",
        }
        self.assertTrue(required.issubset(set(diag.OPPORTUNITY_FIELDS)))

    def test_no_fill_reason_classification_is_deterministic(self):
        base = {
            "filled_quantity": "0",
            "quote_quantity": "10",
            "queue_quantity_ahead": "0",
            "distance_from_mid": "5",
            "whether_it_was_canceled_unfilled": "false",
        }

        filled = dict(base, filled_quantity="10")
        partial = dict(base, filled_quantity="3")
        replaced = dict(base, whether_it_was_canceled_unfilled="true")
        behind = dict(base, queue_quantity_ahead="100")
        wide = dict(base, distance_from_mid="30")

        self.assertEqual(diag.classify_no_fill_reason(filled, 10), "filled")
        self.assertEqual(diag.classify_no_fill_reason(partial, 10), "partially_filled")
        self.assertEqual(diag.classify_no_fill_reason(replaced, 5), "replaced_before_execution")
        self.assertEqual(diag.classify_no_fill_reason(replaced, 10), "canceled_before_execution")
        self.assertEqual(diag.classify_no_fill_reason(behind, 10), "behind_queue")
        self.assertEqual(diag.classify_no_fill_reason(wide, 10), "spread_too_wide")
        self.assertEqual(diag.classify_no_fill_reason(base, 10), "never_touched_by_opposite_flow")

    def test_lifecycle_retains_failed_no_fill_quotes(self):
        scenario = diag.Scenario("fixture", "itch-calibrated", refresh_cadence=10)
        row = {
            "event_index": "20",
            "quote_order_id": "100",
            "strategy": "naive symmetric",
            "regime": "low volatility",
            "flow_profile": "itch_calibrated",
            "seed": "3001",
            "side": "buy",
            "price": "995",
            "reference_mid": "1000",
            "distance_from_mid": "5",
            "quote_quantity": "10",
            "queue_orders_ahead": "0",
            "queue_quantity_ahead": "0",
            "total_level_quantity_before_quote": "0",
            "whether_the_quote_ever_filled": "false",
            "filled_quantity": "0",
            "time_to_first_fill_if_any": "",
            "whether_it_was_canceled_unfilled": "true",
        }
        lifecycle = diag.lifecycle_from_quote(row, scenario, seed_index=0)
        self.assertEqual(lifecycle["quote_id"], "100")
        self.assertEqual(lifecycle["total_filled_size"], 0)
        self.assertEqual(lifecycle["remaining_size"], 10)
        self.assertEqual(lifecycle["final_status"], "canceled_before_execution")

    def test_fill_decomposition_aggregation_counts_queue_and_opportunities(self):
        quotes = [
            {
                "total_filled_size": "10",
                "size": "10",
                "lifetime_events": "3",
                "initial_queue_ahead": "0",
                "submitted_at_best": "true",
                "still_at_best_before_execution_events": "true",
                "final_status": "filled",
                "no_fill_reason": "filled",
            },
            {
                "total_filled_size": "0",
                "size": "10",
                "lifetime_events": "10",
                "initial_queue_ahead": "50",
                "submitted_at_best": "false",
                "still_at_best_before_execution_events": "false",
                "final_status": "unfilled",
                "no_fill_reason": "behind_queue",
            },
        ]
        opportunities = [
            {
                "execution_size": "15",
                "market_maker_quote_present_at_touched_level": "true",
                "maker_fill_size_from_this_event": "10",
                "reason_if_maker_was_not_filled": "filled",
            },
            {
                "execution_size": "5",
                "market_maker_quote_present_at_touched_level": "true",
                "maker_fill_size_from_this_event": "0",
                "reason_if_maker_was_not_filled": "behind_queue",
            },
        ]
        row = diag.decompose_group({"scenario": "fixture"}, quotes, opportunities, {})
        self.assertEqual(row["quotes_submitted"], 2)
        self.assertEqual(row["quotes_filled"], 1)
        self.assertEqual(row["maker_missed_due_to_queue_events"], 1)
        self.assertEqual(row["maker_eligible_execution_events"], 2)
        self.assertEqual(row["maker_reached_by_execution_events"], 1)

    def test_zero_queue_control_is_derived_without_dropping_quotes(self):
        rows = [
            {
                "scenario": "itch_calibrated_flow",
                "flow_type": "itch-calibrated",
                "strategy_name": "naive symmetric",
                "regime": "low volatility",
                "seed": "3001",
                "seed_index": "0",
                "initial_queue_ahead": "0",
                "total_filled_size": "1",
                "size": "10",
                "lifetime_events": "1",
                "submitted_at_best": "true",
                "still_at_best_before_execution_events": "true",
                "final_status": "partially_filled",
                "no_fill_reason": "partially_filled",
            },
            {
                "scenario": "itch_calibrated_flow",
                "flow_type": "itch-calibrated",
                "strategy_name": "naive symmetric",
                "regime": "low volatility",
                "seed": "3001",
                "seed_index": "0",
                "initial_queue_ahead": "50",
                "total_filled_size": "0",
                "size": "10",
                "lifetime_events": "1",
                "submitted_at_best": "false",
                "still_at_best_before_execution_events": "false",
                "final_status": "unfilled",
                "no_fill_reason": "behind_queue",
            },
        ]
        decomposition = diag.build_decomposition(rows, [], [])
        zero_rows = [row for row in decomposition if row["scenario"] == "zero_initial_queue_subset"]
        self.assertEqual(len(zero_rows), 1)
        self.assertEqual(zero_rows[0]["quotes_submitted"], 1)
        self.assertEqual(decomposition[0]["quotes_submitted"], 2)

    def test_quick_scenarios_include_broad_controls(self):
        names = {scenario.name for scenario in diag.quick_scenarios()}
        self.assertIn("hand_chosen_flow", names)
        self.assertIn("itch_calibrated_flow", names)
        self.assertIn("physical_zero_queue_itch_calibrated_flow", names)
        self.assertIn("increased_execution_intensity_2x", names)
        self.assertIn("increased_execution_intensity_5x", names)
        self.assertIn("increased_execution_intensity_10x", names)
        self.assertIn("quote_size_1", names)
        self.assertIn("quote_size_10", names)
        self.assertIn("quote_size_100", names)
        self.assertIn("requote_frequency_fast_5", names)
        self.assertIn("requote_frequency_slow_25", names)
        self.assertIn("as_risk_aversion_low", names)
        self.assertIn("as_risk_aversion_high", names)
        self.assertIn("inventory_cap_5000", names)

    def test_full_scenarios_are_focused_and_include_physical_zero_queue(self):
        scenarios = diag.full_scenarios()
        names = {scenario.name for scenario in scenarios}
        self.assertEqual(len(scenarios), 8)
        self.assertIn("hand_chosen_flow", names)
        self.assertIn("itch_calibrated_flow", names)
        self.assertIn("physical_zero_queue_itch_calibrated_flow", names)
        self.assertIn("increased_execution_intensity_2x", names)
        self.assertIn("increased_execution_intensity_5x", names)
        self.assertIn("increased_execution_intensity_10x", names)
        self.assertIn("requote_frequency_fast_5", names)
        self.assertIn("requote_frequency_slow_25", names)
        physical = next(scenario for scenario in scenarios if scenario.name == "physical_zero_queue_itch_calibrated_flow")
        baseline = next(scenario for scenario in scenarios if scenario.name == "itch_calibrated_flow")
        self.assertTrue(physical.force_zero_queue_quotes)
        self.assertEqual(physical.flow_profile, baseline.flow_profile)
        self.assertEqual(physical.quote_size, baseline.quote_size)
        self.assertEqual(physical.refresh_cadence, baseline.refresh_cadence)
        self.assertEqual(physical.market_multiplier, baseline.market_multiplier)

    def test_paired_difference_schema_is_deterministic(self):
        strategy_rows = [
            {
                "scenario": "fixture",
                "flow_type": "hand-chosen",
                "strategy": "naive symmetric",
                "regime": "low-volatility",
                "seed_index": "0",
                **{metric: "1" for metric in diag.SUMMARY_METRICS},
            },
            {
                "scenario": "fixture",
                "flow_type": "hand-chosen",
                "strategy": "avellaneda stoikov",
                "regime": "low-volatility",
                "seed_index": "0",
                **{metric: "3" for metric in diag.SUMMARY_METRICS},
            },
        ]
        paired = diag.build_paired_differences(strategy_rows, [])
        self.assertTrue(paired)
        self.assertEqual(paired[0]["comparison"], "avellaneda_stoikov_minus_naive")
        self.assertEqual(paired[0]["scenario"], "fixture")
        self.assertEqual(paired[0]["delta"], "2")

    def test_zero_queue_comparison_schema_is_deterministic(self):
        rows = [
            {
                "scenario": "itch_calibrated_flow",
                "flow_type": "itch-calibrated",
                "strategy_name": "naive symmetric",
                "regime": "low-volatility",
                "seed": "3001",
                "seed_index": "0",
                "fill_rate_by_quote_count": "0.02",
                "external_execution_events_count": "20",
            },
            {
                "scenario": "zero_initial_queue_subset",
                "flow_type": "itch-calibrated",
                "strategy_name": "naive symmetric",
                "regime": "low-volatility",
                "seed": "3001",
                "seed_index": "0",
                "fill_rate_by_quote_count": "0.05",
                "external_execution_events_count": "0",
            },
            {
                "scenario": "physical_zero_queue_itch_calibrated_flow",
                "flow_type": "itch-calibrated",
                "strategy_name": "naive symmetric",
                "regime": "low-volatility",
                "seed": "3001",
                "seed_index": "0",
                "fill_rate_by_quote_count": "0.04",
                "external_execution_events_count": "20",
            },
        ]
        comparison = diag.build_zero_queue_comparison(rows)
        self.assertEqual(len(comparison), 1)
        self.assertEqual(comparison[0]["baseline_fill_rate"], "0.02")
        self.assertEqual(comparison[0]["zero_initial_queue_subset_fill_rate"], "0.05")
        self.assertEqual(comparison[0]["physical_zero_queue_fill_rate"], "0.04")

    def test_mechanism_attribution_schema_is_deterministic(self):
        rows = []
        for scenario, fill_rate in [
            ("hand_chosen_flow", "0.7"),
            ("itch_calibrated_flow", "0.02"),
            ("physical_zero_queue_itch_calibrated_flow", "0.04"),
            ("requote_frequency_slow_25", "0.06"),
        ]:
            rows.append(
                {
                    "scenario": scenario,
                    "flow_type": "itch-calibrated",
                    "strategy_name": "naive symmetric",
                    "regime": "low-volatility",
                    "seed": "3001",
                    "seed_index": "0",
                    "fill_rate_by_quote_count": fill_rate,
                }
            )
        attribution = diag.build_mechanism_attribution_summary(rows)
        self.assertTrue(attribution)
        self.assertIn("mechanism", attribution[0])
        self.assertIn("mean_absolute_fill_rate_effect", attribution[0])

    def test_checked_full_run_config_records_ten_seed_focused_mode(self):
        rows = {row["field"]: row["value"] for row in read_csv(ARTIFACTS / "run_config.csv")}
        self.assertEqual(rows["mode"], "full")
        self.assertEqual(rows["events"], "2500")
        self.assertEqual(rows["seeds"], "10")
        self.assertEqual(
            rows["seeds:low-volatility"],
            "3001 4001 5001 6001 7001 8001 9001 10001 11001 12001",
        )
        self.assertIn("force_zero_queue_quotes=True", rows["scenario:physical_zero_queue_itch_calibrated_flow"])
        self.assertIn("force_zero_queue_quotes=False", rows["scenario:itch_calibrated_flow"])

    def test_checked_full_physical_zero_queue_artifact_has_zero_initial_queue(self):
        rows = [
            row
            for row in read_csv(ARTIFACTS / "quote_lifecycle.csv")
            if row["scenario"] == "physical_zero_queue_itch_calibrated_flow"
        ]
        self.assertEqual(len(rows), 30_000)
        self.assertTrue(rows)
        self.assertTrue(all(int(float(row["initial_queue_ahead"])) == 0 for row in rows))

    def test_checked_full_statistical_summary_uses_ten_seed_samples(self):
        rows = read_csv(ARTIFACTS / "statistical_summary.csv")
        self.assertTrue(rows)
        self.assertTrue(all(row["sample_count"] == "10" for row in rows))

    def test_checked_full_zero_queue_comparison_has_all_paired_rows(self):
        rows = read_csv(ARTIFACTS / "zero_queue_comparison.csv")
        self.assertEqual(len(rows), 60)
        self.assertTrue(
            all(
                row["interpretation"]
                in {
                    "both_zero_queue_views_increase_fill_rate",
                    "physical_zero_queue_increases_fill_rate_but_subset_does_not",
                    "derived_subset_increases_fill_rate_but_physical_control_does_not",
                    "zero_queue_does_not_increase_fill_rate",
                }
                for row in rows
            )
        )


if __name__ == "__main__":
    unittest.main()
