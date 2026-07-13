#!/usr/bin/env python3

import argparse
import csv
import math
import os
import platform
import shutil
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path


STRATEGIES = ["naive", "avellaneda-stoikov"]
REGIMES = ["low-volatility", "high-volatility", "trending"]
REGIME_SEED_BASE = {
    "low-volatility": 3001,
    "high-volatility": 3002,
    "trending": 3003,
}

LIFECYCLE_FIELDS = [
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
    "event_index_canceled_or_replaced",
    "event_index_first_fill",
    "event_index_last_fill",
    "lifetime_events",
    "initial_queue_ahead",
    "queue_ahead_at_each_relevant_event",
    "queue_ahead_before_first_fill",
    "displayed_depth_at_price",
    "submitted_at_best",
    "still_at_best_before_execution_events",
    "total_filled_size",
    "remaining_size",
    "final_status",
    "no_fill_reason",
]

OPPORTUNITY_FIELDS = [
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
    "market_maker_size_at_touched_level",
    "size_executed_before_reaching_maker_quote",
    "maker_fill_size_from_this_event",
    "reason_if_maker_was_not_filled",
]

SUMMARY_METRICS = [
    "fill_rate",
    "gross_spread_capture",
    "inventory_pnl",
    "adverse_selection_cost",
    "fee_pnl",
    "net_pnl_after_fees",
    "terminal_liquidation_cost",
    "terminal_inventory_penalty",
    "risk_adjusted_pnl",
    "maximum_drawdown",
    "inventory_mean",
    "inventory_variance",
    "max_abs_inventory",
    "pre_liquidation_inventory",
    "final_inventory",
    "maker_fills",
    "market_maker_filled_quantity",
]


@dataclass(frozen=True)
class Scenario:
    name: str
    flow_profile: str
    quote_size: int = 10
    refresh_cadence: int = 10
    market_multiplier: float = 1.0
    risk_aversion: float = 0.002
    risk_controls: bool = False
    inventory_cap: int = 20_000
    force_zero_queue_quotes: bool = False


def quick_scenarios():
    return [
        Scenario("hand_chosen_flow", "hand-chosen"),
        Scenario("itch_calibrated_flow", "itch-calibrated"),
        Scenario("physical_zero_queue_itch_calibrated_flow", "itch-calibrated", force_zero_queue_quotes=True),
        Scenario("increased_execution_intensity_2x", "itch-calibrated", market_multiplier=2.0),
        Scenario("increased_execution_intensity_5x", "itch-calibrated", market_multiplier=5.0),
        Scenario("increased_execution_intensity_10x", "itch-calibrated", market_multiplier=10.0),
        Scenario("quote_size_1", "itch-calibrated", quote_size=1),
        Scenario("quote_size_10", "itch-calibrated", quote_size=10),
        Scenario("quote_size_100", "itch-calibrated", quote_size=100),
        Scenario("requote_frequency_fast_5", "itch-calibrated", refresh_cadence=5),
        Scenario("requote_frequency_slow_25", "itch-calibrated", refresh_cadence=25),
        Scenario("as_risk_aversion_low", "hand-chosen", risk_aversion=0.001),
        Scenario("as_risk_aversion_high", "hand-chosen", risk_aversion=0.005),
        Scenario("inventory_cap_5000", "hand-chosen", risk_controls=True, inventory_cap=5_000),
    ]


def full_scenarios():
    return [
        Scenario("hand_chosen_flow", "hand-chosen"),
        Scenario("itch_calibrated_flow", "itch-calibrated"),
        Scenario("physical_zero_queue_itch_calibrated_flow", "itch-calibrated", force_zero_queue_quotes=True),
        Scenario("increased_execution_intensity_2x", "itch-calibrated", market_multiplier=2.0),
        Scenario("increased_execution_intensity_5x", "itch-calibrated", market_multiplier=5.0),
        Scenario("increased_execution_intensity_10x", "itch-calibrated", market_multiplier=10.0),
        Scenario("requote_frequency_fast_5", "itch-calibrated", refresh_cadence=5),
        Scenario("requote_frequency_slow_25", "itch-calibrated", refresh_cadence=25),
    ]


def parse_args():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true", help="run the 2-seed broad diagnostic")
    mode.add_argument("--full", action="store_true", help="run the focused 10-seed diagnostic")
    parser.add_argument(
        "--events",
        type=int,
        help="events per run; defaults to 5000 in quick mode and 2500 in full mode",
    )
    parser.add_argument("--seeds", type=int)
    parser.add_argument("--output-dir")
    parser.add_argument("--build-dir", default="build/fill_rate_diagnostics")
    parser.add_argument("--markout-horizon", type=int, default=50)
    parser.add_argument("--curve-sample-stride", type=int, default=100_000_000)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-runs", action="store_true")
    args = parser.parse_args()
    if not args.quick and not args.full:
        args.quick = True
    if args.seeds is None:
        args.seeds = 10 if args.full else 2
    if args.events is None:
        args.events = 2_500 if args.full else 5_000
    if args.output_dir is None:
        args.output_dir = "artifacts/fill_diagnostics" if args.full else "artifacts/fill_diagnostics_quick"
    return args


def run(command, cwd):
    subprocess.run(command, cwd=cwd, check=True)


def configure_and_build(root, build_dir):
    cmake = os.environ.get("CMAKE", "cmake")
    run([cmake, "-S", ".", "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF"], root)
    run([cmake, "--build", str(build_dir), "--config", "Release", "--target", "market_maker_sim"], root)


def executable_path(root, build_dir):
    if platform.system() == "Windows":
        return root / build_dir / "Release" / "market_maker_sim.exe"
    return root / build_dir / "market_maker_sim"


def seed_for(regime, seed_index):
    return REGIME_SEED_BASE[regime] + seed_index * 1000


def strategy_label(strategy):
    return "naive symmetric" if strategy == "naive" else "avellaneda stoikov"


def scenario_run_dir(output_dir, scenario, strategy, regime, seed_index):
    return output_dir / "_runs" / scenario.name / strategy / regime / f"seed_{seed_index}"


def run_one(root, executable, args, scenario, strategy, regime, seed_index, output_dir):
    run_dir = scenario_run_dir(output_dir, scenario, strategy, regime, seed_index)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    command = [
        str(executable),
        "--strategy",
        strategy,
        "--events",
        str(args.events),
        "--markout-horizon",
        str(args.markout_horizon),
        "--curve-sample-stride",
        str(args.curve_sample_stride),
        "--flow-profile",
        scenario.flow_profile,
        "--regime",
        regime,
        "--seed",
        str(seed_for(regime, seed_index)),
        "--quote-size",
        str(scenario.quote_size),
        "--refresh-cadence",
        str(scenario.refresh_cadence),
        "--external-market-intensity-multiplier",
        f"{scenario.market_multiplier:.12g}",
        "--risk-aversion",
        f"{scenario.risk_aversion:.12g}",
        "--output-dir",
        str(run_dir),
    ]
    if scenario.force_zero_queue_quotes:
        command.append("--force-zero-queue-quotes")
    if scenario.risk_controls:
        command.extend(["--risk-controls", "--terminal-liquidation", "--inventory-cap", str(scenario.inventory_cap)])
    run(command, root)
    return run_dir


def read_rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, rows, fieldnames=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        if not rows:
            raise RuntimeError(f"no rows to write for {path}")
        fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def bool_text(value):
    return "true" if value else "false"


def is_true(value):
    return str(value).lower() == "true"


def to_int(value, default=0):
    if value in (None, ""):
        return default
    return int(float(value))


def to_float(value, default=0.0):
    if value in (None, ""):
        return default
    return float(value)


def classify_no_fill_reason(row, refresh_cadence):
    filled = to_int(row["filled_quantity"])
    size = to_int(row["quote_quantity"])
    queue_ahead = to_int(row["queue_quantity_ahead"])
    distance = abs(to_float(row["distance_from_mid"]))
    canceled_unfilled = is_true(row["whether_it_was_canceled_unfilled"])

    if filled >= size and size > 0:
        return "filled"
    if filled > 0:
        return "partially_filled"
    if canceled_unfilled and refresh_cadence <= 5:
        return "replaced_before_execution"
    if canceled_unfilled:
        return "canceled_before_execution"
    if queue_ahead > 0:
        return "behind_queue"
    if distance > 20:
        return "spread_too_wide"
    return "never_touched_by_opposite_flow"


def lifecycle_from_quote(row, scenario, seed_index):
    submitted = to_int(row["event_index"])
    size = to_int(row["quote_quantity"])
    filled = to_int(row["filled_quantity"])
    first_fill_delta = row["time_to_first_fill_if_any"]
    first_fill = submitted + to_int(first_fill_delta) if first_fill_delta != "" else ""
    canceled = ""
    if is_true(row["whether_it_was_canceled_unfilled"]):
        canceled = submitted + scenario.refresh_cadence
    lifetime = to_int(first_fill_delta) if first_fill_delta != "" else scenario.refresh_cadence
    reason = classify_no_fill_reason(row, scenario.refresh_cadence)
    if reason == "filled":
        status = "filled"
    elif reason == "partially_filled":
        status = "partially_filled"
    elif reason in {"canceled_before_execution", "replaced_before_execution"}:
        status = reason
    else:
        status = "open_at_measurement_end" if not is_true(row["whether_it_was_canceled_unfilled"]) else "unfilled"

    queue_ahead = to_int(row["queue_quantity_ahead"])
    displayed_depth = to_int(row["total_level_quantity_before_quote"]) + size
    submitted_at_best = abs(to_float(row["distance_from_mid"])) <= 10.0
    return {
        "quote_id": row["quote_order_id"],
        "strategy_name": row["strategy"],
        "seed": row["seed"],
        "seed_index": seed_index,
        "regime": row["regime"],
        "flow_type": row["flow_profile"],
        "scenario": scenario.name,
        "side": row["side"],
        "price": row["price"],
        "size": size,
        "event_index_submitted": submitted,
        "event_index_canceled_or_replaced": canceled,
        "event_index_first_fill": first_fill,
        "event_index_last_fill": first_fill,
        "lifetime_events": lifetime,
        "initial_queue_ahead": queue_ahead,
        "queue_ahead_at_each_relevant_event": queue_ahead,
        "queue_ahead_before_first_fill": queue_ahead if first_fill != "" else "",
        "displayed_depth_at_price": displayed_depth,
        "submitted_at_best": bool_text(submitted_at_best),
        "still_at_best_before_execution_events": bool_text(submitted_at_best),
        "total_filled_size": filled,
        "remaining_size": max(0, size - filled),
        "final_status": status,
        "no_fill_reason": reason,
    }


def opportunity_from_row(row, scenario, seed_index):
    maker_present = is_true(row["market_maker_quote_present_at_touched_level"])
    maker_fill = to_int(row["maker_fill_size_from_event"])
    reason = row["no_fill_reason"]
    if maker_fill <= 0 and not reason:
        reason = "unknown_or_unclassified"
    return {
        "event_index": row["event_index"],
        "flow_type": row["flow_profile"],
        "scenario": scenario.name,
        "strategy_name": row["strategy"],
        "seed": row["seed"],
        "seed_index": seed_index,
        "regime": row["regime"],
        "side_of_aggressive_flow": row["aggressive_side"],
        "execution_price": row["execution_price"],
        "execution_size": row["execution_size"],
        "best_bid_before_event": row["best_bid_before"],
        "best_ask_before_event": row["best_ask_before"],
        "displayed_depth_at_touched_level": row["displayed_depth_at_touched_level"],
        "market_maker_quote_present_at_touched_level": bool_text(maker_present),
        "market_maker_queue_position": row["market_maker_queue_quantity"],
        "market_maker_size_at_touched_level": row["market_maker_size_at_touched_level"],
        "size_executed_before_reaching_maker_quote": row["size_executed_before_reaching_market_maker"],
        "maker_fill_size_from_this_event": maker_fill,
        "reason_if_maker_was_not_filled": reason,
    }


def collect_outputs(output_dir, scenarios, seeds):
    lifecycle_rows = []
    opportunity_rows = []
    strategy_rows = []
    for scenario in scenarios:
        for strategy in STRATEGIES:
            for regime in REGIMES:
                for seed_index in range(seeds):
                    run_dir = scenario_run_dir(output_dir, scenario, strategy, regime, seed_index)
                    summary = read_rows(run_dir / "summary.csv")[0]
                    summary["scenario"] = scenario.name
                    summary["seed_index"] = str(seed_index)
                    summary["flow_type"] = scenario.flow_profile
                    strategy_rows.append(summary)

                    for row in read_rows(run_dir / "quote_queue_events.csv"):
                        lifecycle_rows.append(lifecycle_from_quote(row, scenario, seed_index))
                    for row in read_rows(run_dir / "execution_opportunities.csv"):
                        opportunity_rows.append(opportunity_from_row(row, scenario, seed_index))
    return lifecycle_rows, opportunity_rows, strategy_rows


def group_rows(rows, fields):
    grouped = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        grouped.setdefault(key, []).append(row)
    return grouped


def mean(values):
    return sum(values) / len(values) if values else 0.0


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def stddev(values):
    return statistics.stdev(values) if len(values) >= 2 else 0.0


def ci95(values):
    if len(values) < 2:
        value = mean(values)
        return value, value
    half_width = 1.96 * stddev(values) / math.sqrt(len(values))
    center = mean(values)
    return center - half_width, center + half_width


def decompose_group(key_fields, quote_rows, opportunity_rows, strategy_row):
    quotes = len(quote_rows)
    filled_quotes = [row for row in quote_rows if to_int(row["total_filled_size"]) > 0]
    partial_fills = [
        row for row in quote_rows if 0 < to_int(row["total_filled_size"]) < to_int(row["size"])
    ]
    full_fills = [row for row in quote_rows if to_int(row["total_filled_size"]) >= to_int(row["size"])]
    submitted_size = sum(to_int(row["size"]) for row in quote_rows)
    filled_size = sum(to_int(row["total_filled_size"]) for row in quote_rows)
    lifetimes = [to_int(row["lifetime_events"]) for row in quote_rows]
    queue_ahead = [to_int(row["initial_queue_ahead"]) for row in quote_rows]
    execution_events = len(opportunity_rows)
    executed_volume = sum(to_int(row["execution_size"]) for row in opportunity_rows)
    maker_price_events = [
        row for row in opportunity_rows if is_true(row["market_maker_quote_present_at_touched_level"])
    ]
    maker_reached = [row for row in opportunity_rows if to_int(row["maker_fill_size_from_this_event"]) > 0]

    output = dict(key_fields)
    output.update(
        {
            "quotes_submitted": quotes,
            "quotes_canceled_or_replaced": sum(
                1
                for row in quote_rows
                if row["final_status"] in {"canceled_before_execution", "replaced_before_execution"}
            ),
            "quotes_filled": len(filled_quotes),
            "partial_fills": len(partial_fills),
            "full_fills": len(full_fills),
            "fill_rate_by_quote_count": f"{(len(filled_quotes) / quotes if quotes else 0.0):.12g}",
            "fill_rate_by_submitted_size": f"{(filled_size / submitted_size if submitted_size else 0.0):.12g}",
            "average_quote_lifetime": f"{mean(lifetimes):.12g}",
            "median_quote_lifetime": f"{(statistics.median(lifetimes) if lifetimes else 0.0):.12g}",
            "average_initial_queue_ahead": f"{mean(queue_ahead):.12g}",
            "median_initial_queue_ahead": f"{(statistics.median(queue_ahead) if queue_ahead else 0.0):.12g}",
            "percent_quotes_submitted_at_best": f"{(sum(1 for row in quote_rows if is_true(row['submitted_at_best'])) / quotes if quotes else 0.0):.12g}",
            "percent_quote_lifetime_spent_at_best": f"{(sum(1 for row in quote_rows if is_true(row['still_at_best_before_execution_events'])) / quotes if quotes else 0.0):.12g}",
            "external_execution_events_count": execution_events,
            "external_executed_volume": executed_volume,
            "external_executed_volume_at_maker_quoted_price": sum(
                to_int(row["execution_size"]) for row in maker_price_events
            ),
            "maker_eligible_execution_events": len(maker_price_events),
            "maker_reached_by_execution_events": len(maker_reached),
            "maker_missed_due_to_queue_events": sum(
                1 for row in opportunity_rows if row["reason_if_maker_was_not_filled"] == "behind_queue"
            ),
            "maker_missed_due_to_no_opposite_flow": sum(
                1 for row in quote_rows if row["no_fill_reason"] == "never_touched_by_opposite_flow"
            ),
            "maker_missed_due_to_quote_not_at_touched_price": sum(
                1
                for row in opportunity_rows
                if row["reason_if_maker_was_not_filled"] == "quote_not_at_touched_price"
            ),
            "maker_missed_due_to_cancellation_or_replacement_before_execution": sum(
                1
                for row in quote_rows
                if row["no_fill_reason"] in {"canceled_before_execution", "replaced_before_execution"}
            ),
            "hard_cap_bid_blocks": strategy_row.get("hard_cap_bid_blocks", "0"),
            "hard_cap_ask_blocks": strategy_row.get("hard_cap_ask_blocks", "0"),
        }
    )
    return output


def build_decomposition(lifecycle_rows, opportunity_rows, strategy_rows):
    fields = ["scenario", "flow_type", "strategy_name", "regime", "seed", "seed_index"]
    quote_groups = group_rows(lifecycle_rows, fields)
    opportunity_groups = group_rows(opportunity_rows, fields)
    strategy_groups = {}
    for row in strategy_rows:
        key = (
            row["scenario"],
            row["flow_type"],
            row["strategy"],
            row["regime"],
            row["seed"],
            row["seed_index"],
        )
        strategy_groups[key] = row

    rows = []
    for key in sorted(quote_groups):
        key_fields = {field: value for field, value in zip(fields, key)}
        rows.append(
            decompose_group(
                key_fields,
                quote_groups[key],
                opportunity_groups.get(key, []),
                strategy_groups.get(key, {}),
            )
        )

    zero_queue_rows = [
        row
        for row in lifecycle_rows
        if row["scenario"] == "itch_calibrated_flow" and to_int(row["initial_queue_ahead"]) == 0
    ]
    zero_groups = group_rows(zero_queue_rows, fields)
    for key in sorted(zero_groups):
        key_fields = {field: value for field, value in zip(fields, key)}
        key_fields["scenario"] = "zero_initial_queue_subset"
        rows.append(decompose_group(key_fields, zero_groups[key], [], {}))
    return rows


def aggregate_summary(rows, group_fields, metrics):
    grouped = group_rows(rows, group_fields)
    output = []
    for key in sorted(grouped):
        base = {field: value for field, value in zip(group_fields, key)}
        for metric in metrics:
            values = [to_float(row[metric]) for row in grouped[key]]
            low, high = ci95(values)
            record = dict(base)
            record.update(
                {
                    "metric": metric,
                    "sample_count": len(values),
                    "mean": f"{mean(values):.12g}",
                    "stddev": f"{stddev(values):.12g}",
                    "median": f"{(statistics.median(values) if values else 0.0):.12g}",
                    "p05": f"{percentile(values, 0.05):.12g}",
                    "p95": f"{percentile(values, 0.95):.12g}",
                    "ci95_low": f"{low:.12g}",
                    "ci95_high": f"{high:.12g}",
                }
            )
            output.append(record)
    return output


def build_strategy_comparison_by_seed(strategy_rows):
    output = []
    for row in strategy_rows:
        copied = {
            "scenario": row["scenario"],
            "flow_type": row["flow_type"],
            "strategy_name": row["strategy"],
            "regime": row["regime"],
            "seed": row["seed"],
            "seed_index": row["seed_index"],
        }
        for field in SUMMARY_METRICS:
            copied[field] = row.get(field, "0")
        output.append(copied)
    return output


def build_paired_differences(strategy_rows, decomposition_rows):
    output = []
    strategy_by_key = {
        (row["scenario"], row["regime"], row["seed_index"], row["strategy"]): row for row in strategy_rows
    }
    strategy_regimes = sorted({row["regime"] for row in strategy_rows})
    strategy_seed_indexes = sorted({row["seed_index"] for row in strategy_rows})
    for scenario in sorted({row["scenario"] for row in strategy_rows}):
        for regime in strategy_regimes:
            for seed_index in strategy_seed_indexes:
                naive = strategy_by_key.get((scenario, regime, seed_index, "naive symmetric"))
                avellaneda = strategy_by_key.get((scenario, regime, seed_index, "avellaneda stoikov"))
                if not naive or not avellaneda:
                    continue
                for metric in SUMMARY_METRICS:
                    output.append(
                        {
                            "comparison": "avellaneda_stoikov_minus_naive",
                            "scenario": scenario,
                            "regime": regime,
                            "seed_index": seed_index,
                            "metric": metric,
                            "left_value": avellaneda.get(metric, "0"),
                            "right_value": naive.get(metric, "0"),
                            "delta": f"{to_float(avellaneda.get(metric, 0)) - to_float(naive.get(metric, 0)):.12g}",
                        }
                    )

    decomp_by_key = {
        (row["scenario"], row["strategy_name"], row["regime"], row["seed_index"]): row
        for row in decomposition_rows
    }
    decomp_regimes = sorted({row["regime"] for row in decomposition_rows})
    decomp_seed_indexes = sorted({row["seed_index"] for row in decomposition_rows})
    for strategy in ["naive symmetric", "avellaneda stoikov"]:
        for regime in decomp_regimes:
            for seed_index in decomp_seed_indexes:
                base = decomp_by_key.get(("itch_calibrated_flow", strategy, regime, seed_index))
                zero = decomp_by_key.get(("zero_initial_queue_subset", strategy, regime, seed_index))
                physical_zero = decomp_by_key.get(
                    ("physical_zero_queue_itch_calibrated_flow", strategy, regime, seed_index)
                )
                hand = decomp_by_key.get(("hand_chosen_flow", strategy, regime, seed_index))
                if base and zero:
                    output.append(
                        {
                            "comparison": "zero_initial_queue_subset_minus_normal_itch",
                            "scenario": "zero_initial_queue_subset",
                            "regime": regime,
                            "seed_index": seed_index,
                            "metric": "fill_rate_by_quote_count",
                            "left_value": zero["fill_rate_by_quote_count"],
                            "right_value": base["fill_rate_by_quote_count"],
                            "delta": f"{to_float(zero['fill_rate_by_quote_count']) - to_float(base['fill_rate_by_quote_count']):.12g}",
                        }
                    )
                if base and physical_zero:
                    output.append(
                        {
                            "comparison": "physical_zero_queue_minus_normal_itch",
                            "scenario": "physical_zero_queue_itch_calibrated_flow",
                            "regime": regime,
                            "seed_index": seed_index,
                            "metric": "fill_rate_by_quote_count",
                            "left_value": physical_zero["fill_rate_by_quote_count"],
                            "right_value": base["fill_rate_by_quote_count"],
                            "delta": f"{to_float(physical_zero['fill_rate_by_quote_count']) - to_float(base['fill_rate_by_quote_count']):.12g}",
                        }
                    )
                slow = decomp_by_key.get(("requote_frequency_slow_25", strategy, regime, seed_index))
                if base and slow:
                    output.append(
                        {
                            "comparison": "requote_frequency_slow_25_minus_itch",
                            "scenario": "requote_frequency_slow_25",
                            "regime": regime,
                            "seed_index": seed_index,
                            "metric": "fill_rate_by_quote_count",
                            "left_value": slow["fill_rate_by_quote_count"],
                            "right_value": base["fill_rate_by_quote_count"],
                            "delta": f"{to_float(slow['fill_rate_by_quote_count']) - to_float(base['fill_rate_by_quote_count']):.12g}",
                        }
                    )
                if base and hand:
                    output.append(
                        {
                            "comparison": "itch_calibrated_minus_hand_chosen",
                            "scenario": "itch_calibrated_flow",
                            "regime": regime,
                            "seed_index": seed_index,
                            "metric": "fill_rate_by_quote_count",
                            "left_value": base["fill_rate_by_quote_count"],
                            "right_value": hand["fill_rate_by_quote_count"],
                            "delta": f"{to_float(base['fill_rate_by_quote_count']) - to_float(hand['fill_rate_by_quote_count']):.12g}",
                        }
                    )
                for multiplier in ["2x", "5x", "10x"]:
                    boosted = decomp_by_key.get((f"increased_execution_intensity_{multiplier}", strategy, regime, seed_index))
                    if base and boosted:
                        output.append(
                            {
                                "comparison": f"execution_intensity_{multiplier}_minus_itch",
                                "scenario": f"increased_execution_intensity_{multiplier}",
                                "regime": regime,
                                "seed_index": seed_index,
                                "metric": "fill_rate_by_quote_count",
                                "left_value": boosted["fill_rate_by_quote_count"],
                                "right_value": base["fill_rate_by_quote_count"],
                                "delta": f"{to_float(boosted['fill_rate_by_quote_count']) - to_float(base['fill_rate_by_quote_count']):.12g}",
                            }
                        )
    return output


def keyed_decomposition(decomposition_rows):
    return {
        (row["scenario"], row["strategy_name"], row["regime"], row["seed_index"]): row
        for row in decomposition_rows
    }


def build_zero_queue_comparison(decomposition_rows):
    rows = []
    by_key = keyed_decomposition(decomposition_rows)
    seed_indexes = sorted({row["seed_index"] for row in decomposition_rows})
    regimes = sorted({row["regime"] for row in decomposition_rows})
    for strategy in ["naive symmetric", "avellaneda stoikov"]:
        for regime in regimes:
            for seed_index in seed_indexes:
                baseline = by_key.get(("itch_calibrated_flow", strategy, regime, seed_index))
                derived = by_key.get(("zero_initial_queue_subset", strategy, regime, seed_index))
                physical = by_key.get(("physical_zero_queue_itch_calibrated_flow", strategy, regime, seed_index))
                if not baseline or not derived or not physical:
                    continue
                baseline_fill = to_float(baseline["fill_rate_by_quote_count"])
                derived_fill = to_float(derived["fill_rate_by_quote_count"])
                physical_fill = to_float(physical["fill_rate_by_quote_count"])
                if physical_fill > baseline_fill and derived_fill > baseline_fill:
                    interpretation = "both_zero_queue_views_increase_fill_rate"
                elif physical_fill > baseline_fill:
                    interpretation = "physical_zero_queue_increases_fill_rate_but_subset_does_not"
                elif derived_fill > baseline_fill:
                    interpretation = "derived_subset_increases_fill_rate_but_physical_control_does_not"
                else:
                    interpretation = "zero_queue_does_not_increase_fill_rate"
                rows.append(
                    {
                        "regime": regime,
                        "strategy": strategy,
                        "seed": baseline["seed"],
                        "baseline_fill_rate": baseline["fill_rate_by_quote_count"],
                        "zero_initial_queue_subset_fill_rate": derived["fill_rate_by_quote_count"],
                        "physical_zero_queue_fill_rate": physical["fill_rate_by_quote_count"],
                        "baseline_external_execution_count": baseline["external_execution_events_count"],
                        "physical_zero_queue_external_execution_count": physical["external_execution_events_count"],
                        "interpretation": interpretation,
                    }
                )
    return rows


def build_mechanism_summary(decomposition_rows):
    paired = build_paired_differences([], decomposition_rows)
    grouped = group_rows(paired, ["comparison", "scenario", "regime", "metric"])
    rows = []
    for key in sorted(grouped):
        comparison, scenario, regime, metric = key
        values = [to_float(row["delta"]) for row in grouped[key]]
        low, high = ci95(values)
        rows.append(
            {
                "comparison": comparison,
                "scenario": scenario,
                "regime": regime,
                "metric": metric,
                "sample_count": len(values),
                "mean_delta": f"{mean(values):.12g}",
                "stddev_delta": f"{stddev(values):.12g}",
                "median_delta": f"{(statistics.median(values) if values else 0.0):.12g}",
                "p05_delta": f"{percentile(values, 0.05):.12g}",
                "p95_delta": f"{percentile(values, 0.95):.12g}",
                "ci95_low": f"{low:.12g}",
                "ci95_high": f"{high:.12g}",
            }
        )
    return rows


def build_mechanism_attribution_summary(decomposition_rows):
    rows = []
    by_key = keyed_decomposition(decomposition_rows)
    seed_indexes = sorted({row["seed_index"] for row in decomposition_rows})
    regimes = sorted({row["regime"] for row in decomposition_rows})
    for strategy in ["naive symmetric", "avellaneda stoikov"]:
        for regime in regimes:
            sparse_effects = []
            queue_effects = []
            lifetime_effects = []
            strategy_effects = []
            for seed_index in seed_indexes:
                hand = by_key.get(("hand_chosen_flow", strategy, regime, seed_index))
                baseline = by_key.get(("itch_calibrated_flow", strategy, regime, seed_index))
                physical = by_key.get(("physical_zero_queue_itch_calibrated_flow", strategy, regime, seed_index))
                slow = by_key.get(("requote_frequency_slow_25", strategy, regime, seed_index))
                if hand and baseline:
                    sparse_effects.append(
                        abs(to_float(hand["fill_rate_by_quote_count"]) - to_float(baseline["fill_rate_by_quote_count"]))
                    )
                if physical and baseline:
                    queue_effects.append(
                        abs(to_float(physical["fill_rate_by_quote_count"]) - to_float(baseline["fill_rate_by_quote_count"]))
                    )
                if slow and baseline:
                    lifetime_effects.append(
                        abs(to_float(slow["fill_rate_by_quote_count"]) - to_float(baseline["fill_rate_by_quote_count"]))
                    )

                other_strategy = "avellaneda stoikov" if strategy == "naive symmetric" else "naive symmetric"
                same_scenario = by_key.get(("itch_calibrated_flow", other_strategy, regime, seed_index))
                if same_scenario and baseline:
                    strategy_effects.append(
                        abs(to_float(same_scenario["fill_rate_by_quote_count"]) - to_float(baseline["fill_rate_by_quote_count"]))
                    )

            effects = {
                "sparse_execution_flow": mean(sparse_effects),
                "queue_position": mean(queue_effects),
                "quote_lifetime": mean(lifetime_effects),
                "strategy_choice": mean(strategy_effects),
                "quote_size": 0.0,
            }
            total = sum(effects.values())
            largest = max(effects, key=effects.get)
            for mechanism, effect in effects.items():
                rows.append(
                    {
                        "regime": regime,
                        "strategy": strategy,
                        "mechanism": mechanism,
                        "mean_absolute_fill_rate_effect": f"{effect:.12g}",
                        "relative_share_of_observed_effects": f"{(effect / total if total else 0.0):.12g}",
                        "interpretation": (
                            "largest observed effect in this diagnostic"
                            if mechanism == largest and effect > 0
                            else "secondary or not identified as a primary blocker"
                        ),
                    }
                )
            rows.append(
                {
                    "regime": regime,
                    "strategy": strategy,
                    "mechanism": "residual_unexplained",
                    "mean_absolute_fill_rate_effect": "0",
                    "relative_share_of_observed_effects": "0",
                    "interpretation": "not estimated by this controlled-difference attribution",
                }
            )
    return rows


def write_run_config(output_dir, args, scenarios):
    rows = [
        {"field": "mode", "value": "full" if args.full else "quick"},
        {"field": "events", "value": args.events},
        {"field": "seeds", "value": args.seeds},
        {"field": "regimes", "value": " ".join(REGIMES)},
        {"field": "strategies", "value": " ".join(STRATEGIES)},
        {
            "field": "zero_initial_queue_subset",
            "value": "derived subset of quotes with zero initial displayed queue ahead",
        },
        {
            "field": "physical_zero_queue_implementation",
            "value": "market maker quote is shifted to a nearby non-crossing empty same-side price level when needed",
        },
        {"field": "opportunity_trace", "value": "C++ simulator rows emitted before each synthetic market event"},
    ]
    for regime in REGIMES:
        rows.append(
            {
                "field": f"seeds:{regime}",
                "value": " ".join(str(seed_for(regime, seed_index)) for seed_index in range(args.seeds)),
            }
        )
    for scenario in scenarios:
        rows.append(
            {
                "field": f"scenario:{scenario.name}",
                "value": (
                    f"flow={scenario.flow_profile};quote_size={scenario.quote_size};"
                    f"refresh={scenario.refresh_cadence};market_multiplier={scenario.market_multiplier};"
                    f"risk_aversion={scenario.risk_aversion};risk_controls={scenario.risk_controls};"
                    f"inventory_cap={scenario.inventory_cap};"
                    f"force_zero_queue_quotes={scenario.force_zero_queue_quotes}"
                ),
            }
        )
    write_rows(output_dir / "run_config.csv", rows, ["field", "value"])


def main():
    args = parse_args()
    if args.events <= 0:
        raise RuntimeError("--events must be positive")
    if args.seeds <= 0:
        raise RuntimeError("--seeds must be positive")

    root = Path(__file__).resolve().parents[1]
    output_dir = root / args.output_dir
    build_dir = Path(args.build_dir)
    scenarios = full_scenarios() if args.full else quick_scenarios()

    output_dir.mkdir(parents=True, exist_ok=True)
    if not args.skip_runs:
        if not args.skip_build:
            configure_and_build(root, build_dir)
        executable = executable_path(root, build_dir)
        for scenario in scenarios:
            for strategy in STRATEGIES:
                for regime in REGIMES:
                    for seed_index in range(args.seeds):
                        run_one(root, executable, args, scenario, strategy, regime, seed_index, output_dir)

    lifecycle_rows, opportunity_rows, strategy_rows = collect_outputs(output_dir, scenarios, args.seeds)
    decomposition_rows = build_decomposition(lifecycle_rows, opportunity_rows, strategy_rows)
    strategy_by_seed = build_strategy_comparison_by_seed(strategy_rows)
    strategy_summary = aggregate_summary(
        strategy_by_seed,
        ["scenario", "flow_type", "strategy_name", "regime"],
        SUMMARY_METRICS,
    )
    decomposition_summary = aggregate_summary(
        decomposition_rows,
        ["scenario", "flow_type", "strategy_name", "regime"],
        [
            "fill_rate_by_quote_count",
            "fill_rate_by_submitted_size",
            "average_quote_lifetime",
            "average_initial_queue_ahead",
            "percent_quotes_submitted_at_best",
            "external_execution_events_count",
            "maker_eligible_execution_events",
            "maker_reached_by_execution_events",
            "maker_missed_due_to_queue_events",
            "maker_missed_due_to_quote_not_at_touched_price",
        ],
    )
    paired = build_paired_differences(strategy_rows, decomposition_rows)
    mechanism_summary = build_mechanism_summary(decomposition_rows)
    zero_queue_comparison = build_zero_queue_comparison(decomposition_rows)
    mechanism_attribution = build_mechanism_attribution_summary(decomposition_rows)
    statistical_summary = strategy_summary + decomposition_summary

    write_run_config(output_dir, args, scenarios)
    write_rows(output_dir / "quote_lifecycle.csv", lifecycle_rows, LIFECYCLE_FIELDS)
    write_rows(output_dir / "execution_opportunities.csv", opportunity_rows, OPPORTUNITY_FIELDS)
    write_rows(output_dir / "fill_decomposition_by_seed.csv", decomposition_rows)
    write_rows(output_dir / "fill_decomposition_summary.csv", decomposition_summary)
    write_rows(output_dir / "strategy_comparison_by_seed.csv", strategy_by_seed)
    write_rows(output_dir / "strategy_comparison_summary.csv", strategy_summary)
    write_rows(output_dir / "statistical_summary.csv", statistical_summary)
    write_rows(output_dir / "paired_differences.csv", paired)
    write_rows(output_dir / "mechanism_summary.csv", mechanism_summary)
    write_rows(output_dir / "zero_queue_comparison.csv", zero_queue_comparison)
    write_rows(output_dir / "mechanism_attribution_summary.csv", mechanism_attribution)

    print(output_dir)
    print(f"scenarios={len(scenarios)} seeds={args.seeds} lifecycle_rows={len(lifecycle_rows)} opportunities={len(opportunity_rows)}")


if __name__ == "__main__":
    main()
