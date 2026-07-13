#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_fill_rate_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("generate_fill_rate_diagnostics", SCRIPT)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


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
        zero_rows = [row for row in decomposition if row["scenario"] == "zero_queue_control"]
        self.assertEqual(len(zero_rows), 1)
        self.assertEqual(zero_rows[0]["quotes_submitted"], 1)
        self.assertEqual(decomposition[0]["quotes_submitted"], 2)

    def test_default_scenarios_include_required_controls(self):
        names = {scenario.name for scenario in diag.default_scenarios()}
        self.assertIn("hand_chosen_flow", names)
        self.assertIn("itch_calibrated_flow", names)
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


if __name__ == "__main__":
    unittest.main()
