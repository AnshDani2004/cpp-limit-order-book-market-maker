#!/usr/bin/env python3

import argparse
import csv
import math
import os
import platform
import shutil
import subprocess
from pathlib import Path


STRATEGIES = ["naive", "avellaneda-stoikov", "avellaneda-stoikov-calibrated"]
FLOW_PROFILES = ["hand-chosen", "itch-calibrated"]
REGIMES = ["low-volatility", "high-volatility", "trending"]
RISK_MODES = ["uncontrolled", "risk-controlled"]

REGIME_SEED_BASE = {
    "low-volatility": 3001,
    "high-volatility": 3002,
    "trending": 3003,
}

METRICS = [
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
    "inventory_variance",
    "pre_liquidation_inventory",
    "final_inventory",
    "terminal_liquidation_quantity",
    "terminal_liquidation_residual_inventory",
    "maker_fills",
    "taker_fills",
    "passive_taker_fills",
    "terminal_liquidation_trades",
    "hard_cap_bid_blocks",
    "hard_cap_ask_blocks",
]

CLAIM_METRICS = [
    "net_pnl_after_fees",
    "risk_adjusted_pnl",
    "final_inventory",
    "inventory_variance",
    "fill_rate",
]

COMPARISON_PAIRS = [
    ("avellaneda stoikov", "naive symmetric"),
    ("avellaneda stoikov calibrated", "naive symmetric"),
    ("avellaneda stoikov calibrated", "avellaneda stoikov"),
]

PAIRED_DELTA_METRICS = [
    "net_pnl_after_fees",
    "risk_adjusted_pnl",
    "final_inventory",
    "inventory_variance",
    "fill_rate",
    "maximum_drawdown",
    "gross_spread_capture",
    "adverse_selection_cost",
]

T_CRITICAL_95 = {
    29: 2.045229642132703,
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=200_000)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--markout-horizon", type=int, default=50)
    parser.add_argument("--curve-sample-stride", type=int, default=100_000_000)
    parser.add_argument("--strategies", nargs="+", default=STRATEGIES, choices=STRATEGIES)
    parser.add_argument("--flow-profiles", nargs="+", default=FLOW_PROFILES, choices=FLOW_PROFILES)
    parser.add_argument("--regimes", nargs="+", default=REGIMES, choices=REGIMES)
    parser.add_argument("--risk-modes", nargs="+", default=RISK_MODES, choices=RISK_MODES)
    parser.add_argument("--inventory-cap", type=int, default=20_000)
    parser.add_argument("--build-dir", default="build/stage5c")
    parser.add_argument("--output-dir", default="benchmarks/results/stage5c_seed_statistics")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-runs", action="store_true")
    return parser.parse_args()


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
    return REGIME_SEED_BASE[regime] + 1000 * seed_index


def read_single_summary(path):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise RuntimeError(f"expected one summary row in {path}")
    return rows[0]


def run_one(root, executable, args, risk_mode, flow_profile, strategy, regime, seed_index, scratch_dir):
    seed = seed_for(regime, seed_index)
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)
    scratch_dir.mkdir(parents=True)

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
        flow_profile,
        "--regime",
        regime,
        "--seed",
        str(seed),
        "--output-dir",
        str(scratch_dir),
    ]
    if risk_mode == "risk-controlled":
        command.extend(["--risk-controls", "--terminal-liquidation", "--inventory-cap", str(args.inventory_cap)])

    run(command, root)
    row = read_single_summary(scratch_dir / "summary.csv")
    row["risk_mode"] = risk_mode
    row["flow_profile_cli"] = flow_profile
    row["strategy_cli"] = strategy
    row["regime_cli"] = regime
    row["seed_index"] = str(seed_index)
    return row


def write_rows(path, rows):
    if not rows:
        raise RuntimeError("no rows to write")
    with path.open("w", newline="") as handle:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sample_mean(values):
    return sum(values) / len(values)


def sample_stddev(values):
    if len(values) < 2:
        return 0.0
    mean = sample_mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def confidence_interval_95(values):
    mean = sample_mean(values)
    stddev = sample_stddev(values)
    if len(values) < 2:
        return mean, mean, mean
    t_value = T_CRITICAL_95.get(len(values) - 1, 1.96)
    half_width = t_value * stddev / math.sqrt(len(values))
    return mean, mean - half_width, mean + half_width


def aggregate_rows(raw_rows):
    grouped = {}
    for row in raw_rows:
        key = (row["risk_mode"], row["external_flow_profile"], row["regime"], row["strategy"])
        grouped.setdefault(key, []).append(row)

    aggregate = []
    for key in sorted(grouped):
        risk_mode, flow_profile, regime, strategy = key
        rows = grouped[key]
        for metric in METRICS:
            values = [float(row[metric]) for row in rows]
            mean, low, high = confidence_interval_95(values)
            aggregate.append(
                {
                    "risk_mode": risk_mode,
                    "flow_profile": flow_profile,
                    "regime": regime,
                    "strategy": strategy,
                    "metric": metric,
                    "sample_count": len(values),
                    "mean": f"{mean:.12g}",
                    "stddev": f"{sample_stddev(values):.12g}",
                    "ci95_low": f"{low:.12g}",
                    "ci95_high": f"{high:.12g}",
                }
            )
    return aggregate


def intervals_overlap(left_low, left_high, right_low, right_high):
    return max(left_low, right_low) <= min(left_high, right_high)


def comparison_rows(aggregate):
    lookup = {}
    for row in aggregate:
        key = (row["risk_mode"], row["flow_profile"], row["regime"], row["strategy"], row["metric"])
        lookup[key] = row

    comparisons = []
    prefixes = sorted({(row["risk_mode"], row["flow_profile"], row["regime"]) for row in aggregate})
    for risk_mode, flow_profile, regime in prefixes:
        for left_strategy, right_strategy in COMPARISON_PAIRS:
            for metric in CLAIM_METRICS:
                left = lookup.get((risk_mode, flow_profile, regime, left_strategy, metric))
                right = lookup.get((risk_mode, flow_profile, regime, right_strategy, metric))
                if left is None or right is None:
                    continue
                left_mean = float(left["mean"])
                right_mean = float(right["mean"])
                left_low = float(left["ci95_low"])
                left_high = float(left["ci95_high"])
                right_low = float(right["ci95_low"])
                right_high = float(right["ci95_high"])
                overlap = intervals_overlap(left_low, left_high, right_low, right_high)
                comparisons.append(
                    {
                        "risk_mode": risk_mode,
                        "flow_profile": flow_profile,
                        "regime": regime,
                        "metric": metric,
                        "left_strategy": left_strategy,
                        "right_strategy": right_strategy,
                        "left_mean": f"{left_mean:.12g}",
                        "right_mean": f"{right_mean:.12g}",
                        "mean_delta": f"{left_mean - right_mean:.12g}",
                        "left_ci95_low": f"{left_low:.12g}",
                        "left_ci95_high": f"{left_high:.12g}",
                        "right_ci95_low": f"{right_low:.12g}",
                        "right_ci95_high": f"{right_high:.12g}",
                        "ci95_overlap": "true" if overlap else "false",
                    }
                )
    return comparisons


def paired_delta_rows(raw_rows, comparisons):
    raw_lookup = {}
    for row in raw_rows:
        key = (
            row["risk_mode"],
            row["external_flow_profile"],
            row["regime"],
            row["strategy"],
            row["seed_index"],
        )
        raw_lookup[key] = row

    prefixes = sorted({
        (
            row["risk_mode"],
            row["flow_profile"],
            row["regime"],
            row["left_strategy"],
            row["right_strategy"],
        )
        for row in comparisons
    })
    seed_indexes = sorted({row["seed_index"] for row in raw_rows}, key=lambda value: int(value))

    deltas = []
    for risk_mode, flow_profile, regime, left_strategy, right_strategy in prefixes:
        for metric in PAIRED_DELTA_METRICS:
            for seed_index in seed_indexes:
                left_key = (risk_mode, flow_profile, regime, left_strategy, seed_index)
                right_key = (risk_mode, flow_profile, regime, right_strategy, seed_index)
                left = raw_lookup.get(left_key)
                right = raw_lookup.get(right_key)
                if left is None or right is None:
                    raise RuntimeError(
                        "missing paired seed row for "
                        f"{risk_mode} {flow_profile} {regime} {left_strategy} vs {right_strategy} seed {seed_index}"
                    )
                left_value = float(left[metric])
                right_value = float(right[metric])
                deltas.append(
                    {
                        "risk_mode": risk_mode,
                        "flow_profile": flow_profile,
                        "regime": regime,
                        "metric": metric,
                        "left_strategy": left_strategy,
                        "right_strategy": right_strategy,
                        "seed_index": seed_index,
                        "left_value": f"{left_value:.12g}",
                        "right_value": f"{right_value:.12g}",
                        "delta": f"{left_value - right_value:.12g}",
                    }
                )
    return deltas


def paired_delta_summary_rows(deltas):
    grouped = {}
    for row in deltas:
        key = (
            row["risk_mode"],
            row["flow_profile"],
            row["regime"],
            row["metric"],
            row["left_strategy"],
            row["right_strategy"],
        )
        grouped.setdefault(key, []).append(float(row["delta"]))

    summary = []
    for key in sorted(grouped):
        risk_mode, flow_profile, regime, metric, left_strategy, right_strategy = key
        values = grouped[key]
        mean, low, high = confidence_interval_95(values)
        excludes_zero = low > 0.0 or high < 0.0
        summary.append(
            {
                "risk_mode": risk_mode,
                "flow_profile": flow_profile,
                "regime": regime,
                "metric": metric,
                "left_strategy": left_strategy,
                "right_strategy": right_strategy,
                "sample_count": len(values),
                "mean_delta": f"{mean:.12g}",
                "stddev_delta": f"{sample_stddev(values):.12g}",
                "ci95_low": f"{low:.12g}",
                "ci95_high": f"{high:.12g}",
                "paired_ci95_excludes_zero": "true" if excludes_zero else "false",
            }
        )
    return summary


def paired_delta_claim_rows(summary, comparisons):
    unpaired_lookup = {}
    for row in comparisons:
        key = (
            row["risk_mode"],
            row["flow_profile"],
            row["regime"],
            row["metric"],
            row["left_strategy"],
            row["right_strategy"],
        )
        unpaired_lookup[key] = row

    claims = []
    for row in summary:
        key = (
            row["risk_mode"],
            row["flow_profile"],
            row["regime"],
            row["metric"],
            row["left_strategy"],
            row["right_strategy"],
        )
        previous = unpaired_lookup.get(key)
        mean_delta = float(row["mean_delta"])
        excludes_zero = row["paired_ci95_excludes_zero"] == "true"
        if not excludes_zero:
            conclusion = "not_separated"
        elif mean_delta > 0.0:
            conclusion = "left_higher"
        else:
            conclusion = "left_lower"

        previous_overlap = previous["ci95_overlap"] if previous else ""
        changed_from_unpaired = ""
        if previous is not None:
            changed_from_unpaired = "true" if (previous_overlap == "true") == excludes_zero else "false"

        claim = dict(row)
        claim["previous_unpaired_ci95_overlap"] = previous_overlap
        claim["changed_from_unpaired"] = changed_from_unpaired
        claim["paired_delta_conclusion"] = conclusion
        claims.append(claim)
    return claims


def read_raw_rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_run_config(path, args):
    rows = [
        ("events", args.events),
        ("seeds_per_regime", args.seeds),
        ("seed_formula", "regime base seed plus 1000 times seed index"),
        ("low_volatility_base_seed", REGIME_SEED_BASE["low-volatility"]),
        ("high_volatility_base_seed", REGIME_SEED_BASE["high-volatility"]),
        ("trending_base_seed", REGIME_SEED_BASE["trending"]),
        ("markout_horizon", args.markout_horizon),
        ("curve_sample_stride", args.curve_sample_stride),
        ("strategies", " ".join(args.strategies)),
        ("flow_profiles", " ".join(args.flow_profiles)),
        ("regimes", " ".join(args.regimes)),
        ("risk_modes", " ".join(args.risk_modes)),
        ("inventory_cap", args.inventory_cap),
        ("confidence_interval", "95 percent t interval"),
        ("t_critical_for_30_samples", T_CRITICAL_95[29]),
    ]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["field", "value"])
        writer.writerows(rows)


def main():
    args = parse_args()
    if args.seeds <= 0:
        raise RuntimeError("--seeds must be positive")

    root = Path(__file__).resolve().parents[1]
    build_dir = Path(args.build_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "raw_seed_results.csv"

    if not args.skip_runs:
        if not args.skip_build:
            configure_and_build(root, build_dir)
        executable = executable_path(root, build_dir)
        scratch_dir = output_dir / "_single_run"
        rows = []
        total = (
            len(args.risk_modes)
            * len(args.flow_profiles)
            * len(args.strategies)
            * len(args.regimes)
            * args.seeds
        )
        completed = 0
        for risk_mode in args.risk_modes:
            for flow_profile in args.flow_profiles:
                for strategy in args.strategies:
                    for regime in args.regimes:
                        for seed_index in range(args.seeds):
                            rows.append(run_one(root, executable, args, risk_mode, flow_profile, strategy, regime, seed_index, scratch_dir))
                            completed += 1
                            if completed % 25 == 0 or completed == total:
                                print(f"completed {completed} of {total}")
        if scratch_dir.exists():
            shutil.rmtree(scratch_dir)
        write_rows(raw_path, rows)
    else:
        rows = read_raw_rows(raw_path)

    aggregate = aggregate_rows(rows)
    comparisons = comparison_rows(aggregate)
    deltas = paired_delta_rows(rows, comparisons)
    delta_summary = paired_delta_summary_rows(deltas)
    delta_claims = paired_delta_claim_rows(delta_summary, comparisons)
    write_rows(output_dir / "aggregate_metrics.csv", aggregate)
    write_rows(output_dir / "comparison_claims.csv", comparisons)
    write_rows(output_dir / "paired_deltas.csv", deltas)
    write_rows(output_dir / "paired_delta_summary.csv", delta_summary)
    write_rows(output_dir / "paired_delta_claims.csv", delta_claims)
    write_run_config(output_dir / "run_config.csv", args)
    print(raw_path.resolve())
    print((output_dir / "aggregate_metrics.csv").resolve())
    print((output_dir / "comparison_claims.csv").resolve())
    print((output_dir / "paired_deltas.csv").resolve())
    print((output_dir / "paired_delta_summary.csv").resolve())
    print((output_dir / "paired_delta_claims.csv").resolve())


if __name__ == "__main__":
    main()
