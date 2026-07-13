#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_fill_rate_artifacts.py"
ARTIFACTS = ROOT / "artifacts" / "fill_diagnostics"
SPEC = importlib.util.spec_from_file_location("validate_fill_rate_artifacts", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def run_config_rows():
    config = {"mode": "full", "seeds": "10", "events": "2500"}
    for scenario in validator.EXPECTED_SCENARIOS:
        config[f"scenario:{scenario}"] = (
            "flow=itch-calibrated;quote_size=10;refresh=10;market_multiplier=1.0;"
            f"risk_aversion=0.002;risk_controls=False;inventory_cap=20000;"
            f"force_zero_queue_quotes={scenario == 'physical_zero_queue_itch_calibrated_flow'}"
        )
    for regime in ["low-volatility", "high-volatility", "trending"]:
        config[f"seeds:{regime}"] = " ".join(str(index) for index in range(10))
    return config


def report():
    return validator.ValidationReport()


def minimal_lifecycle_row(**overrides):
    row = {
        "quote_id": "1",
        "strategy_name": "naive symmetric",
        "seed": "3001",
        "seed_index": "0",
        "regime": "low volatility",
        "flow_type": "itch_calibrated",
        "scenario": "physical_zero_queue_itch_calibrated_flow",
        "side": "buy",
        "price": "100",
        "size": "10",
        "event_index_submitted": "0",
        "event_index_first_fill": "",
        "lifetime_events": "10",
        "initial_queue_ahead": "0",
        "displayed_depth_at_price": "10",
        "total_filled_size": "0",
        "remaining_size": "10",
        "final_status": "canceled_before_execution",
        "no_fill_reason": "canceled_before_execution",
    }
    row.update(overrides)
    return row


def mechanism_rows(break_monotonicity=False):
    rows = []
    values = {
        "hand_chosen_flow": 0.70,
        "itch_calibrated_flow": 0.02,
        "physical_zero_queue_itch_calibrated_flow": 0.021,
        "increased_execution_intensity_2x": 0.04,
        "increased_execution_intensity_5x": 0.09,
        "increased_execution_intensity_10x": 0.18,
        "requote_frequency_fast_5": 0.01,
        "requote_frequency_slow_25": 0.05,
    }
    if break_monotonicity:
        values["increased_execution_intensity_5x"] = 0.03
    for strategy in validator.STRATEGIES:
        for regime in validator.EXPECTED_REGIMES:
            for scenario, fill_rate in values.items():
                rows.append(
                    {
                        "scenario": scenario,
                        "strategy_name": strategy,
                        "regime": regime,
                        "seed_index": "0",
                        "fill_rate_by_quote_count": str(fill_rate),
                        "external_execution_events_count": "500" if scenario == "hand_chosen_flow" else "10",
                    }
                )
    return rows


class FillRateArtifactValidatorTests(unittest.TestCase):
    def test_validator_passes_checked_full_artifacts(self):
        validation = validator.validate_artifacts(ARTIFACTS, ROOT)
        self.assertFalse(validation.failures)

    def test_missing_required_column_fails(self):
        validation = report()
        headers = {name: set(columns) for name, columns in validator.REQUIRED_FILES.items()}
        headers["quote_lifecycle.csv"].remove("quote_id")
        validator.validate_schema(headers, validation)
        self.assertTrue(any("missing columns" in failure for failure in validation.failures))

    def test_broken_same_seed_pairing_fails(self):
        rows = [
            {
                "scenario": "itch_calibrated_flow",
                "regime": "low volatility",
                "seed_index": "0",
                "strategy_name": "naive symmetric",
                "seed": "3001",
                "flow_type": "itch-calibrated",
            },
            {
                "scenario": "itch_calibrated_flow",
                "regime": "low volatility",
                "seed_index": "0",
                "strategy_name": "avellaneda stoikov",
                "seed": "9999",
                "flow_type": "itch-calibrated",
            },
        ]
        validation = report()
        validator.validate_same_seed_pairing(rows, run_config_rows(), validation)
        self.assertTrue(any("broken same-seed" in failure for failure in validation.failures))

    def test_physical_zero_queue_nonzero_initial_queue_fails(self):
        rows = [minimal_lifecycle_row(initial_queue_ahead="12")]
        validation = report()
        validator.validate_physical_zero_queue(rows, [{"scenario": "zero_initial_queue_subset"}], validation)
        self.assertTrue(any("initial_queue_ahead" in failure for failure in validation.failures))

    def test_monotonicity_check_fails_on_corrupted_fixture(self):
        validation = report()
        validator.validate_mechanism_results(mechanism_rows(break_monotonicity=True), [], validation)
        self.assertTrue(any("monotonicity" in failure for failure in validation.failures))

    def test_missing_no_fill_reason_fails(self):
        rows = [minimal_lifecycle_row(scenario="itch_calibrated_flow", no_fill_reason="")]
        validation = report()
        validator.validate_no_fill_reasons(rows, [], validation)
        self.assertTrue(any("no_fill_reason" in failure for failure in validation.failures))


if __name__ == "__main__":
    unittest.main()
