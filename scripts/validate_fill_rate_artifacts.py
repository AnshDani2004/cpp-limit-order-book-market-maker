#!/usr/bin/env python3

import argparse
import csv
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


STRATEGIES = {"naive symmetric", "avellaneda stoikov"}
EXPECTED_SCENARIOS = {
    "hand_chosen_flow",
    "itch_calibrated_flow",
    "physical_zero_queue_itch_calibrated_flow",
    "increased_execution_intensity_2x",
    "increased_execution_intensity_5x",
    "increased_execution_intensity_10x",
    "requote_frequency_fast_5",
    "requote_frequency_slow_25",
}
EXPECTED_REGIMES = {"low volatility", "high volatility", "trending"}
EXPECTED_SEED_COUNT = 10

LIFECYCLE_COLUMNS = {
    "quote_id",
    "strategy_name",
    "seed",
    "seed_index",
    "regime",
    "flow_type",
    "scenario",
    "side",
    "price",
    "size",
    "event_index_submitted",
    "event_index_first_fill",
    "lifetime_events",
    "initial_queue_ahead",
    "displayed_depth_at_price",
    "total_filled_size",
    "remaining_size",
    "final_status",
    "no_fill_reason",
}
OPPORTUNITY_COLUMNS = {
    "event_index",
    "flow_type",
    "scenario",
    "strategy_name",
    "seed",
    "seed_index",
    "regime",
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
DECOMPOSITION_COLUMNS = {
    "scenario",
    "flow_type",
    "strategy_name",
    "regime",
    "seed",
    "seed_index",
    "quotes_submitted",
    "quotes_filled",
    "partial_fills",
    "full_fills",
    "fill_rate_by_quote_count",
    "fill_rate_by_submitted_size",
    "external_execution_events_count",
    "external_executed_volume",
    "maker_eligible_execution_events",
    "maker_reached_by_execution_events",
    "maker_missed_due_to_queue_events",
    "maker_missed_due_to_no_opposite_flow",
    "maker_missed_due_to_quote_not_at_touched_price",
    "maker_missed_due_to_cancellation_or_replacement_before_execution",
}
STRATEGY_COLUMNS = {
    "scenario",
    "flow_type",
    "strategy_name",
    "regime",
    "seed",
    "seed_index",
    "fill_rate",
    "gross_spread_capture",
    "inventory_pnl",
    "fee_pnl",
    "net_pnl_after_fees",
    "risk_adjusted_pnl",
    "inventory_variance",
    "max_abs_inventory",
    "final_inventory",
    "maker_fills",
    "market_maker_filled_quantity",
}
PAIRED_COLUMNS = {
    "comparison",
    "scenario",
    "regime",
    "seed_index",
    "metric",
    "left_value",
    "right_value",
    "delta",
}
ZERO_QUEUE_COLUMNS = {
    "regime",
    "strategy",
    "seed",
    "baseline_fill_rate",
    "zero_initial_queue_subset_fill_rate",
    "physical_zero_queue_fill_rate",
    "baseline_external_execution_count",
    "physical_zero_queue_external_execution_count",
    "interpretation",
}
MECHANISM_COLUMNS = {
    "comparison",
    "scenario",
    "regime",
    "metric",
    "sample_count",
    "mean_delta",
    "ci95_low",
    "ci95_high",
}
ATTRIBUTION_COLUMNS = {
    "regime",
    "strategy",
    "mechanism",
    "mean_absolute_fill_rate_effect",
    "relative_share_of_observed_effects",
    "interpretation",
}
RUN_CONFIG_COLUMNS = {"field", "value"}

REQUIRED_FILES = {
    "quote_lifecycle.csv": LIFECYCLE_COLUMNS,
    "execution_opportunities.csv": OPPORTUNITY_COLUMNS,
    "fill_decomposition_by_seed.csv": DECOMPOSITION_COLUMNS,
    "strategy_comparison_by_seed.csv": STRATEGY_COLUMNS,
    "paired_differences.csv": PAIRED_COLUMNS,
    "zero_queue_comparison.csv": ZERO_QUEUE_COLUMNS,
    "mechanism_summary.csv": MECHANISM_COLUMNS,
    "mechanism_attribution_summary.csv": ATTRIBUTION_COLUMNS,
    "run_config.csv": RUN_CONFIG_COLUMNS,
}

NO_FILL_REASONS = {
    "filled",
    "partially_filled",
    "canceled_before_execution",
    "replaced_before_execution",
    "never_touched_by_opposite_flow",
    "price_not_at_best",
    "insufficient_opposite_execution_volume",
    "behind_queue",
    "inventory_limit_blocked_quote",
    "quote_size_too_large_for_available_flow",
    "spread_too_wide",
    "crossed_or_invalid_quote_rejected",
    "terminal_liquidation_only",
    "unknown_or_unclassified",
}
OPPORTUNITY_REASONS = NO_FILL_REASONS | {"quote_not_at_touched_price", "no_opposite_liquidity"}


class ValidationFailure(RuntimeError):
    pass


class ValidationReport:
    def __init__(self):
        self.failures = []
        self.warnings = []
        self.lines = []

    def ok(self, message):
        self.lines.append(f"PASS: {message}")

    def note(self, message):
        self.lines.append(f"INFO: {message}")

    def warn(self, message):
        self.warnings.append(message)
        self.lines.append(f"WARN: {message}")

    def fail(self, message):
        self.failures.append(message)
        self.lines.append(f"FAIL: {message}")

    def require(self, condition, message):
        if condition:
            self.ok(message)
        else:
            self.fail(message)

    def assert_clean(self):
        if self.failures:
            raise ValidationFailure("\n".join(self.failures))

    def text(self):
        status = "PASSED" if not self.failures else "FAILED"
        header = [
            "Fill-rate artifact validation report",
            f"Status: {status}",
            f"Failures: {len(self.failures)}",
            f"Warnings: {len(self.warnings)}",
            "",
        ]
        return "\n".join(header + self.lines)


def read_csv(path):
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def read_required_artifacts(artifact_dir):
    artifacts = {}
    headers = {}
    for name in REQUIRED_FILES:
        path = artifact_dir / name
        if not path.exists():
            raise ValidationFailure(f"missing required artifact: {path}")
        fieldnames, rows = read_csv(path)
        headers[name] = set(fieldnames)
        artifacts[name] = rows
    return headers, artifacts


def to_float(value, default=0.0):
    if value in (None, ""):
        return default
    return float(value)


def to_int(value, default=0):
    if value in (None, ""):
        return default
    return int(float(value))


def is_true(value):
    return str(value).strip().lower() == "true"


def close_enough(left, right, tolerance=1e-9):
    return abs(left - right) <= tolerance


def key(row):
    return (row["scenario"], row["strategy_name"], row["regime"], row["seed_index"])


def group_rows(rows, fields):
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in fields)].append(row)
    return grouped


def validate_schema(headers, report):
    for filename, required in REQUIRED_FILES.items():
        missing = sorted(required - headers.get(filename, set()))
        report.require(not missing, f"{filename} has required columns")
        if missing:
            report.fail(f"{filename} missing columns: {', '.join(missing)}")


def run_config_map(rows):
    return {row["field"]: row["value"] for row in rows}


def parse_scenario_config(value):
    result = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        name, raw = part.split("=", 1)
        result[name] = raw
    return result


def expected_seed_indexes(strategy_rows):
    return sorted({row["seed_index"] for row in strategy_rows}, key=lambda value: int(value))


def validate_full_coverage(strategy_rows, decomposition_rows, zero_rows, run_config, report):
    scenarios = {row["scenario"] for row in strategy_rows}
    regimes = {row["regime"] for row in strategy_rows}
    strategies = {row["strategy_name"] for row in strategy_rows}
    seeds_by_regime = defaultdict(set)
    for row in strategy_rows:
        seeds_by_regime[row["regime"]].add(row["seed_index"])

    report.require(scenarios == EXPECTED_SCENARIOS, "strategy comparison covers the 8 focused scenarios")
    report.require(regimes == EXPECTED_REGIMES, "strategy comparison covers all 3 regimes")
    report.require(strategies == STRATEGIES, "strategy comparison covers both strategies")
    for regime in sorted(EXPECTED_REGIMES):
        report.require(
            len(seeds_by_regime[regime]) == EXPECTED_SEED_COUNT,
            f"{regime} has {EXPECTED_SEED_COUNT} deterministic seed indexes",
        )

    expected_keys = {
        (scenario, strategy, regime, seed)
        for scenario in EXPECTED_SCENARIOS
        for strategy in STRATEGIES
        for regime in EXPECTED_REGIMES
        for seed in seeds_by_regime[regime]
    }
    actual_keys = {(row["scenario"], row["strategy_name"], row["regime"], row["seed_index"]) for row in strategy_rows}
    missing = sorted(expected_keys - actual_keys)
    report.require(not missing, "both strategies present for every seed/regime/scenario")
    if missing:
        report.fail(f"missing strategy rows: {missing[:5]}")

    decomp_keys = {(row["scenario"], row["strategy_name"], row["regime"], row["seed_index"]) for row in decomposition_rows}
    missing_decomp = sorted(expected_keys - decomp_keys)
    report.require(not missing_decomp, "fill decomposition covers every physical scenario pair")
    if missing_decomp:
        report.fail(f"missing decomposition rows: {missing_decomp[:5]}")

    zero_expected = {
        (strategy, regime, seed)
        for strategy in STRATEGIES
        for regime in EXPECTED_REGIMES
        for seed in seeds_by_regime[regime]
    }
    zero_actual = {(row["strategy"], row["regime"], seed_index_for_seed(strategy_rows, row)) for row in zero_rows}
    missing_zero = sorted(zero_expected - zero_actual)
    report.require(not missing_zero, "zero_queue_comparison covers every seed/regime/strategy")
    if missing_zero:
        report.fail(f"missing zero queue comparison rows: {missing_zero[:5]}")

    report.require(run_config.get("mode") == "full", "run_config records full mode")
    report.require(run_config.get("seeds") == str(EXPECTED_SEED_COUNT), "run_config records 10 seeds")
    for scenario in sorted(EXPECTED_SCENARIOS):
        report.require(f"scenario:{scenario}" in run_config, f"run_config records {scenario}")
    for regime_flag in ["low-volatility", "high-volatility", "trending"]:
        field = f"seeds:{regime_flag}"
        values = run_config.get(field, "").split()
        report.require(len(values) == EXPECTED_SEED_COUNT, f"run_config records {EXPECTED_SEED_COUNT} seeds for {regime_flag}")


def seed_index_for_seed(strategy_rows, zero_row):
    seed_to_index = {
        (row["regime"], row["seed"]): row["seed_index"]
        for row in strategy_rows
        if row["scenario"] == "itch_calibrated_flow"
    }
    return seed_to_index.get((zero_row["regime"], zero_row["seed"]), "")


def validate_same_seed_pairing(strategy_rows, run_config, report):
    scenario_configs = {
        field.removeprefix("scenario:"): parse_scenario_config(value)
        for field, value in run_config.items()
        if field.startswith("scenario:")
    }
    grouped = group_rows(strategy_rows, ["scenario", "regime", "seed_index"])
    broken = []
    for group_key, rows in grouped.items():
        if {row["strategy_name"] for row in rows} != STRATEGIES or len(rows) != 2:
            broken.append(group_key)
            continue
        seeds = {row["seed"] for row in rows}
        flow_types = {row["flow_type"] for row in rows}
        if len(seeds) != 1 or len(flow_types) != 1:
            broken.append(group_key)

    report.require(not broken, "naive and AS rows share seed, regime, scenario, and flow profile")
    if broken:
        report.fail(f"broken same-seed strategy pairs: {broken[:5]}")

    for scenario in EXPECTED_SCENARIOS:
        config = scenario_configs.get(scenario, {})
        report.require("quote_size" in config and "refresh" in config, f"{scenario} records quote size and refresh cadence")
        if scenario not in {"requote_frequency_fast_5", "requote_frequency_slow_25"}:
            report.require(config.get("refresh") == "10", f"{scenario} keeps baseline refresh cadence")
        if scenario != "physical_zero_queue_itch_calibrated_flow":
            report.require(config.get("force_zero_queue_quotes") != "True", f"{scenario} is not marked physical zero-queue")
    physical = scenario_configs.get("physical_zero_queue_itch_calibrated_flow", {})
    report.require(physical.get("force_zero_queue_quotes") == "True", "physical zero-queue scenario is marked in run_config")
    report.note(f"global event count from run_config: {run_config.get('events', 'unknown')}")


def validate_physical_zero_queue(lifecycle_rows, decomposition_rows, report):
    physical = [row for row in lifecycle_rows if row["scenario"] == "physical_zero_queue_itch_calibrated_flow"]
    report.require(bool(physical), "physical zero-queue quote lifecycle rows are present")
    nonzero = [row for row in physical if to_int(row["initial_queue_ahead"]) != 0]
    negative_queue = [row for row in physical if to_int(row["initial_queue_ahead"]) < 0]
    negative_depth = [row for row in physical if to_int(row["displayed_depth_at_price"]) < 0]
    report.require(not nonzero, "physical zero-queue initial_queue_ahead is always 0")
    report.require(not negative_queue, "physical zero-queue initial_queue_ahead is never negative")
    report.require(not negative_depth, "physical zero-queue displayed_depth_at_price is nonnegative")

    groups = group_rows(physical, ["strategy_name", "regime", "seed_index"])
    report.require(
        len(groups) == len(STRATEGIES) * len(EXPECTED_REGIMES) * EXPECTED_SEED_COUNT,
        "physical zero-queue rows cover every seed/regime/strategy",
    )

    derived_lifecycle = [row for row in lifecycle_rows if row["scenario"] == "zero_initial_queue_subset"]
    report.require(not derived_lifecycle, "zero_initial_queue_subset is not emitted as a physical lifecycle scenario")
    derived_decomp = [row for row in decomposition_rows if row["scenario"] == "zero_initial_queue_subset"]
    report.require(bool(derived_decomp), "zero_initial_queue_subset appears only as derived decomposition output")
    report.note("quote non-crossing check skipped: lifecycle artifact does not carry best bid/ask before quote")


def compute_decomposition_from_quotes(lifecycle_rows, opportunity_rows):
    quote_groups = group_rows(lifecycle_rows, ["scenario", "flow_type", "strategy_name", "regime", "seed", "seed_index"])
    opportunity_groups = group_rows(
        opportunity_rows, ["scenario", "flow_type", "strategy_name", "regime", "seed", "seed_index"]
    )
    rows = {}
    for group_key, quotes in quote_groups.items():
        rows[group_key] = summarize_quote_group(quotes, opportunity_groups.get(group_key, []))

    baseline_zero = [
        row
        for row in lifecycle_rows
        if row["scenario"] == "itch_calibrated_flow" and to_int(row["initial_queue_ahead"]) == 0
    ]
    for group_key, quotes in group_rows(
        baseline_zero, ["scenario", "flow_type", "strategy_name", "regime", "seed", "seed_index"]
    ).items():
        derived_key = ("zero_initial_queue_subset",) + group_key[1:]
        rows[derived_key] = summarize_quote_group(quotes, [])
    return rows


def summarize_quote_group(quotes, opportunities):
    quote_count = len(quotes)
    filled_quotes = [row for row in quotes if to_int(row["total_filled_size"]) > 0]
    partial = [row for row in quotes if 0 < to_int(row["total_filled_size"]) < to_int(row["size"])]
    full = [row for row in quotes if to_int(row["total_filled_size"]) >= to_int(row["size"])]
    submitted_size = sum(to_int(row["size"]) for row in quotes)
    filled_size = sum(to_int(row["total_filled_size"]) for row in quotes)
    return {
        "quotes_submitted": quote_count,
        "quotes_filled": len(filled_quotes),
        "partial_fills": len(partial),
        "full_fills": len(full),
        "fill_rate_by_quote_count": len(filled_quotes) / quote_count if quote_count else 0.0,
        "fill_rate_by_submitted_size": filled_size / submitted_size if submitted_size else 0.0,
        "external_execution_events_count": len(opportunities),
        "external_executed_volume": sum(to_int(row["execution_size"]) for row in opportunities),
        "maker_eligible_execution_events": sum(
            1 for row in opportunities if is_true(row["market_maker_quote_present_at_touched_level"])
        ),
        "maker_reached_by_execution_events": sum(
            1 for row in opportunities if to_int(row["maker_fill_size_from_this_event"]) > 0
        ),
        "maker_missed_due_to_queue_events": sum(
            1 for row in opportunities if row["reason_if_maker_was_not_filled"] == "behind_queue"
        ),
        "maker_missed_due_to_quote_not_at_touched_price": sum(
            1 for row in opportunities if row["reason_if_maker_was_not_filled"] == "quote_not_at_touched_price"
        ),
        "maker_missed_due_to_no_opposite_flow": sum(
            1 for row in quotes if row["no_fill_reason"] == "never_touched_by_opposite_flow"
        ),
        "maker_missed_due_to_cancellation_or_replacement_before_execution": sum(
            1
            for row in quotes
            if row["no_fill_reason"] in {"canceled_before_execution", "replaced_before_execution"}
        ),
    }


def validate_fill_and_execution_reconciliation(lifecycle_rows, opportunity_rows, decomposition_rows, report):
    computed = compute_decomposition_from_quotes(lifecycle_rows, opportunity_rows)
    mismatches = []
    count_fields = [
        "quotes_submitted",
        "quotes_filled",
        "partial_fills",
        "full_fills",
        "external_execution_events_count",
        "external_executed_volume",
        "maker_eligible_execution_events",
        "maker_reached_by_execution_events",
        "maker_missed_due_to_queue_events",
        "maker_missed_due_to_no_opposite_flow",
        "maker_missed_due_to_quote_not_at_touched_price",
        "maker_missed_due_to_cancellation_or_replacement_before_execution",
    ]
    rate_fields = ["fill_rate_by_quote_count", "fill_rate_by_submitted_size"]
    for row in decomposition_rows:
        group_key = (row["scenario"], row["flow_type"], row["strategy_name"], row["regime"], row["seed"], row["seed_index"])
        expected = computed.get(group_key)
        if expected is None:
            mismatches.append((group_key, "missing computed group", "", ""))
            continue
        for field in count_fields:
            if to_int(row[field]) != int(expected[field]):
                mismatches.append((group_key, field, row[field], expected[field]))
        for field in rate_fields:
            if not close_enough(to_float(row[field]), expected[field], 1e-9):
                mismatches.append((group_key, field, row[field], expected[field]))
    report.require(not mismatches, "fill decomposition and execution opportunity counts reconcile")
    if mismatches:
        report.fail(f"decomposition mismatches: {mismatches[:5]}")


def validate_mechanism_summary(decomposition_rows, mechanism_rows, report):
    decomp = {
        (row["scenario"], row["strategy_name"], row["regime"], row["seed_index"]): to_float(row["fill_rate_by_quote_count"])
        for row in decomposition_rows
    }
    comparisons = {
        "itch_calibrated_minus_hand_chosen": ("itch_calibrated_flow", "hand_chosen_flow"),
        "physical_zero_queue_minus_normal_itch": (
            "physical_zero_queue_itch_calibrated_flow",
            "itch_calibrated_flow",
        ),
        "zero_initial_queue_subset_minus_normal_itch": ("zero_initial_queue_subset", "itch_calibrated_flow"),
        "requote_frequency_slow_25_minus_itch": ("requote_frequency_slow_25", "itch_calibrated_flow"),
        "execution_intensity_2x_minus_itch": ("increased_execution_intensity_2x", "itch_calibrated_flow"),
        "execution_intensity_5x_minus_itch": ("increased_execution_intensity_5x", "itch_calibrated_flow"),
        "execution_intensity_10x_minus_itch": ("increased_execution_intensity_10x", "itch_calibrated_flow"),
    }
    mismatches = []
    for row in mechanism_rows:
        if row["metric"] != "fill_rate_by_quote_count":
            continue
        left, right = comparisons[row["comparison"]]
        deltas = []
        for strategy in STRATEGIES:
            seed_indexes = {
                seed
                for scenario, row_strategy, regime, seed in decomp
                if scenario in {left, right} and row_strategy == strategy and regime == row["regime"]
            }
            for seed in seed_indexes:
                left_value = decomp.get((left, strategy, row["regime"], seed))
                right_value = decomp.get((right, strategy, row["regime"], seed))
                if left_value is not None and right_value is not None:
                    deltas.append(left_value - right_value)
        if not deltas:
            mismatches.append((row["comparison"], row["regime"], "no deltas"))
            continue
        mean_delta = sum(deltas) / len(deltas)
        if not close_enough(mean_delta, to_float(row["mean_delta"]), 1e-9):
            mismatches.append((row["comparison"], row["regime"], row["mean_delta"], mean_delta))
    report.require(not mismatches, "mechanism summary mean deltas reconcile")
    if mismatches:
        report.fail(f"mechanism summary mismatches: {mismatches[:5]}")


def validate_no_fill_reasons(lifecycle_rows, opportunity_rows, report):
    missing = [row for row in lifecycle_rows if to_int(row["total_filled_size"]) == 0 and not row["no_fill_reason"]]
    invalid = [row for row in lifecycle_rows if row["no_fill_reason"] not in NO_FILL_REASONS]
    unknown = [row for row in lifecycle_rows if row["no_fill_reason"] == "unknown_or_unclassified"]
    contradictory = [
        row
        for row in lifecycle_rows
        if to_int(row["total_filled_size"]) >= to_int(row["size"]) > 0
        and row["no_fill_reason"] not in {"filled", "partially_filled"}
    ]
    partial_bad = [
        row
        for row in lifecycle_rows
        if row["final_status"] == "partially_filled"
        and not (0 < to_int(row["total_filled_size"]) < to_int(row["size"]))
    ]
    opportunity_invalid = [
        row for row in opportunity_rows if row["reason_if_maker_was_not_filled"] not in OPPORTUNITY_REASONS
    ]
    report.require(not missing, "every unfilled quote has a no_fill_reason")
    report.require(not invalid, "quote no_fill_reason values belong to taxonomy")
    report.require(not opportunity_invalid, "execution opportunity no-fill reasons belong to taxonomy")
    report.require(not unknown, "unknown_or_unclassified quote reason count is zero")
    report.require(not contradictory, "filled quotes do not carry contradictory no-fill reasons")
    report.require(not partial_bad, "partially filled quotes have consistent status and size")
    counts = Counter(row["no_fill_reason"] for row in lifecycle_rows)
    report.note("quote no-fill reason counts: " + ", ".join(f"{name}={counts[name]}" for name in sorted(counts)))


def validate_pnl(strategy_rows, report):
    mismatches = []
    bad_numbers = []
    for row in strategy_rows:
        identity = to_float(row["gross_spread_capture"]) + to_float(row["inventory_pnl"]) + to_float(row["fee_pnl"])
        net = to_float(row["net_pnl_after_fees"])
        if not close_enough(identity, net, 1e-5):
            mismatches.append((row["scenario"], row["strategy_name"], row["regime"], row["seed_index"], net, identity))
        for field in [
            "gross_spread_capture",
            "inventory_pnl",
            "fee_pnl",
            "net_pnl_after_fees",
            "risk_adjusted_pnl",
            "inventory_variance",
            "max_abs_inventory",
            "fill_rate",
        ]:
            value = to_float(row[field])
            if not math.isfinite(value):
                bad_numbers.append((row["scenario"], row["strategy_name"], field, row[field]))
        if to_float(row["inventory_variance"]) < -1e-12:
            bad_numbers.append((row["scenario"], row["strategy_name"], "inventory_variance", row["inventory_variance"]))
        if to_float(row["max_abs_inventory"]) < 0:
            bad_numbers.append((row["scenario"], row["strategy_name"], "max_abs_inventory", row["max_abs_inventory"]))
        if to_int(row["maker_fills"]) < 0 or to_int(row["market_maker_filled_quantity"]) < 0:
            bad_numbers.append((row["scenario"], row["strategy_name"], "fill_count", "negative"))
    report.require(not mismatches, "strategy PnL identity reconciles")
    report.require(not bad_numbers, "PnL, inventory, and fill fields are finite and nonnegative where required")
    if mismatches:
        report.fail(f"PnL mismatches: {mismatches[:5]}")
    if bad_numbers:
        report.fail(f"bad numeric fields: {bad_numbers[:5]}")


def mean_fill_rates(decomposition_rows):
    grouped = defaultdict(list)
    for row in decomposition_rows:
        grouped[(row["scenario"], row["strategy_name"], row["regime"])].append(to_float(row["fill_rate_by_quote_count"]))
    return {group_key: sum(values) / len(values) for group_key, values in grouped.items()}


def mean_execution_counts(decomposition_rows):
    grouped = defaultdict(list)
    for row in decomposition_rows:
        grouped[(row["scenario"], row["strategy_name"], row["regime"])].append(
            to_float(row["external_execution_events_count"])
        )
    return {group_key: sum(values) / len(values) for group_key, values in grouped.items()}


def validate_mechanism_results(decomposition_rows, paired_rows, report):
    fills = mean_fill_rates(decomposition_rows)
    executions = mean_execution_counts(decomposition_rows)
    failures = []
    support_rows = []
    for strategy in sorted(STRATEGIES):
        for regime in sorted(EXPECTED_REGIMES):
            hand = fills[("hand_chosen_flow", strategy, regime)]
            itch = fills[("itch_calibrated_flow", strategy, regime)]
            physical = fills[("physical_zero_queue_itch_calibrated_flow", strategy, regime)]
            hand_exec = executions[("hand_chosen_flow", strategy, regime)]
            itch_exec = executions[("itch_calibrated_flow", strategy, regime)]
            physical_delta = physical - itch
            flow_delta = hand - itch
            support_rows.append((strategy, regime, hand, itch, physical, hand_exec, itch_exec))
            if not (hand > itch + 0.25 and hand_exec > itch_exec * 10):
                failures.append((strategy, regime, "sparse execution collapse", hand, itch, hand_exec, itch_exec))
            if not (physical_delta < 0.05 and flow_delta > max(physical_delta * 10, 0.25)):
                failures.append((strategy, regime, "physical zero-queue rescue", physical_delta, flow_delta))

            intensity = [
                fills[("itch_calibrated_flow", strategy, regime)],
                fills[("increased_execution_intensity_2x", strategy, regime)],
                fills[("increased_execution_intensity_5x", strategy, regime)],
                fills[("increased_execution_intensity_10x", strategy, regime)],
            ]
            if intensity != sorted(intensity):
                failures.append((strategy, regime, "intensity monotonicity", intensity))

            cadence = [
                fills[("requote_frequency_fast_5", strategy, regime)],
                fills[("itch_calibrated_flow", strategy, regime)],
                fills[("requote_frequency_slow_25", strategy, regime)],
            ]
            if cadence != sorted(cadence):
                failures.append((strategy, regime, "requote cadence monotonicity", cadence))

    as_fill_deltas = [
        abs(to_float(row["delta"]))
        for row in paired_rows
        if row["comparison"] == "avellaneda_stoikov_minus_naive" and row["metric"] == "fill_rate"
    ]
    flow_deltas = [
        abs(to_float(row["delta"]))
        for row in paired_rows
        if row["comparison"] == "itch_calibrated_minus_hand_chosen" and row["metric"] == "fill_rate_by_quote_count"
    ]
    if as_fill_deltas and flow_deltas and max(as_fill_deltas) >= max(flow_deltas):
        failures.append(("strategy comparison", "AS fill-rate delta is not small relative to flow-profile delta"))

    report.require(not failures, "headline mechanism checks are supported by artifacts")
    for strategy, regime, hand, itch, physical, hand_exec, itch_exec in support_rows:
        report.note(
            f"{strategy} {regime}: hand_fill={hand:.6f} itch_fill={itch:.6f} "
            f"physical_zero_fill={physical:.6f} hand_exec={hand_exec:.1f} itch_exec={itch_exec:.1f}"
        )
    if failures:
        report.fail(f"mechanism result failures: {failures[:5]}")


def validate_docs(repo_root, report):
    paths = [repo_root / "README.md", repo_root / "docs" / "fill_rate_queue_diagnostics.md"]
    combined = "\n".join(path.read_text() for path in paths)
    lowered = combined.lower()
    failures = []
    for stale in ["zero_queue_control", "default diagnostic uses two seeds"]:
        if stale in lowered:
            failures.append(stale)
    overclaim_patterns = [
        r"\bclaim(?:s|ed)? alpha\b",
        r"\bproduction ready\b",
        r"\bguaranteed profit",
        r"\bbroad avellaneda stoikov superiority\b",
        r"\bbroad as dominance\b",
    ]
    for pattern in overclaim_patterns:
        if re.search(pattern, lowered):
            failures.append(pattern)
    report.require(not failures, "README and fill-rate docs avoid stale wording and clear overclaims")
    if failures:
        report.fail(f"documentation overclaim/stale wording hits: {failures}")


def validate_artifacts(artifact_dir, repo_root=None):
    artifact_dir = Path(artifact_dir)
    repo_root = Path(repo_root) if repo_root else artifact_dir.parents[1]
    report = ValidationReport()
    headers, artifacts = read_required_artifacts(artifact_dir)
    validate_schema(headers, report)

    lifecycle = artifacts["quote_lifecycle.csv"]
    opportunities = artifacts["execution_opportunities.csv"]
    decomposition = artifacts["fill_decomposition_by_seed.csv"]
    strategy_rows = artifacts["strategy_comparison_by_seed.csv"]
    paired = artifacts["paired_differences.csv"]
    zero_queue = artifacts["zero_queue_comparison.csv"]
    mechanism = artifacts["mechanism_summary.csv"]
    run_config = run_config_map(artifacts["run_config.csv"])

    report.note(f"quote_lifecycle rows: {len(lifecycle)}")
    report.note(f"execution_opportunities rows: {len(opportunities)}")
    report.note(f"fill_decomposition_by_seed rows: {len(decomposition)}")
    report.note(f"strategy_comparison_by_seed rows: {len(strategy_rows)}")

    validate_full_coverage(strategy_rows, decomposition, zero_queue, run_config, report)
    validate_same_seed_pairing(strategy_rows, run_config, report)
    validate_physical_zero_queue(lifecycle, decomposition, report)
    validate_fill_and_execution_reconciliation(lifecycle, opportunities, decomposition, report)
    validate_mechanism_summary(decomposition, mechanism, report)
    validate_no_fill_reasons(lifecycle, opportunities, report)
    validate_pnl(strategy_rows, report)
    validate_mechanism_results(decomposition, paired, report)
    validate_docs(repo_root, report)
    return report


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", default="artifacts/fill_diagnostics")
    return parser.parse_args()


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    artifact_dir = repo_root / args.artifact_dir
    try:
        report = validate_artifacts(artifact_dir, repo_root)
    except ValidationFailure as error:
        print("Fill-rate artifact validation report")
        print("Status: FAILED")
        print(str(error))
        return 1
    print(report.text())
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
