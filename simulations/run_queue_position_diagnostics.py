#!/usr/bin/env python3

import argparse
import csv
import os
import platform
import shutil
import subprocess
from pathlib import Path
from statistics import median


STRATEGIES = ["naive", "avellaneda-stoikov"]
FLOW_PROFILES = ["hand-chosen", "itch-calibrated"]
REGIMES = ["low-volatility", "high-volatility", "trending"]
REGIME_SEED_BASE = {
    "low-volatility": 3001,
    "high-volatility": 3002,
    "trending": 3003,
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=200_000)
    parser.add_argument("--markout-horizon", type=int, default=50)
    parser.add_argument("--curve-sample-stride", type=int, default=100_000_000)
    parser.add_argument("--build-dir", default="build/stage5d")
    parser.add_argument("--output-dir", default="benchmarks/results/stage5d_queue_position")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-runs", action="store_true")
    return parser.parse_args()


def run(command, cwd):
    subprocess.run(command, cwd=cwd, check=True)


def configure_and_build(root, build_dir):
    cmake = os.environ.get("CMAKE", "cmake")
    run([cmake, "-S", ".", "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"], root)
    run([cmake, "--build", str(build_dir), "--config", "Release", "--target", "market_maker_sim"], root)


def executable_path(root, build_dir):
    if platform.system() == "Windows":
        return root / build_dir / "Release" / "market_maker_sim.exe"
    return root / build_dir / "market_maker_sim"


def seed_for(regime):
    return REGIME_SEED_BASE[regime]


def run_one(root, executable, args, flow_profile, strategy, regime, output_dir):
    run_dir = output_dir / "_runs" / flow_profile / strategy / regime
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
        flow_profile,
        "--regime",
        regime,
        "--seed",
        str(seed_for(regime)),
        "--output-dir",
        str(run_dir),
    ]
    run(command, root)
    return run_dir


def read_rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, rows, fieldnames=None):
    if fieldnames is None:
        if not rows:
            raise RuntimeError(f"no rows to write for {path}")
        fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def distance_bucket(distance):
    value = abs(float(distance))
    if value <= 5.0:
        return "0_to_5"
    if value <= 10.0:
        return "5_to_10"
    if value <= 20.0:
        return "10_to_20"
    if value <= 40.0:
        return "20_to_40"
    return "40_plus"


def queue_depth_bucket(quantity):
    value = int(float(quantity))
    if value == 0:
        return "0"
    if value <= 100:
        return "1_to_100"
    if value <= 500:
        return "101_to_500"
    if value <= 1000:
        return "501_to_1000"
    return "1001_plus"


def is_true(value):
    return str(value).lower() == "true"


def average(values):
    return 0.0 if not values else sum(values) / len(values)


def aggregate_group(rows, group_key):
    quote_count = len(rows)
    filled_rows = [row for row in rows if is_true(row["whether_the_quote_ever_filled"])]
    queue_quantities = [int(row["queue_quantity_ahead"]) for row in rows]
    queue_orders = [int(row["queue_orders_ahead"]) for row in rows]
    distances = [float(row["distance_from_mid"]) for row in rows]
    time_to_fill = [
        int(row["time_to_first_fill_if_any"])
        for row in filled_rows
        if row["time_to_first_fill_if_any"] != ""
    ]
    row = dict(group_key)
    row.update(
        {
            "quote_count": quote_count,
            "filled_quote_count": len(filled_rows),
            "fill_probability": f"{(len(filled_rows) / quote_count if quote_count else 0.0):.12g}",
            "posted_quantity": sum(int(item["quote_quantity"]) for item in rows),
            "filled_quantity": sum(int(item["filled_quantity"]) for item in rows),
            "average_queue_quantity_ahead": f"{average(queue_quantities):.12g}",
            "median_queue_quantity_ahead": f"{(median(queue_quantities) if queue_quantities else 0):.12g}",
            "average_queue_orders_ahead": f"{average(queue_orders):.12g}",
            "zero_queue_quantity_share": f"{(sum(1 for value in queue_quantities if value == 0) / quote_count if quote_count else 0.0):.12g}",
            "average_distance_from_mid": f"{average(distances):.12g}",
            "average_time_to_first_fill": f"{average(time_to_fill):.12g}",
            "canceled_unfilled_quotes": sum(1 for item in rows if is_true(item["whether_it_was_canceled_unfilled"])),
        }
    )
    return row


def aggregate_by(rows, fields):
    grouped = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        grouped.setdefault(key, []).append(row)

    output = []
    for key in sorted(grouped):
        group_key = {field: value for field, value in zip(fields, key)}
        output.append(aggregate_group(grouped[key], group_key))
    return output


def with_buckets(rows):
    enriched = []
    for row in rows:
        copied = dict(row)
        copied["distance_bucket"] = distance_bucket(row["distance_from_mid"])
        copied["queue_depth_bucket"] = queue_depth_bucket(row["queue_quantity_ahead"])
        enriched.append(copied)
    return enriched


def collect_run_dirs(output_dir):
    run_dirs = []
    for flow_profile in FLOW_PROFILES:
        for strategy in STRATEGIES:
            for regime in REGIMES:
                run_dirs.append(output_dir / "_runs" / flow_profile / strategy / regime)
    return run_dirs


def combine_outputs(output_dir):
    queue_rows = []
    outcome_rows = []
    summary_rows = []
    for run_dir in collect_run_dirs(output_dir):
        queue_rows.extend(read_rows(run_dir / "quote_queue_events.csv"))
        outcome_rows.extend(read_rows(run_dir / "quote_fill_outcomes.csv"))
        summary_rows.extend(read_rows(run_dir / "summary.csv"))

    write_rows(output_dir / "quote_queue_events.csv", queue_rows)
    write_rows(output_dir / "quote_fill_outcomes.csv", outcome_rows)
    write_rows(output_dir / "run_summaries.csv", summary_rows)

    enriched = with_buckets(queue_rows)
    summary = aggregate_by(enriched, ["flow_profile", "strategy", "regime"])
    by_distance = aggregate_by(enriched, ["flow_profile", "strategy", "regime", "distance_bucket"])
    by_queue = aggregate_by(enriched, ["flow_profile", "strategy", "regime", "queue_depth_bucket"])
    by_both = aggregate_by(
        enriched,
        ["flow_profile", "strategy", "regime", "distance_bucket", "queue_depth_bucket"],
    )

    write_rows(output_dir / "queue_position_summary.csv", summary)
    write_rows(output_dir / "fill_by_distance_bucket.csv", by_distance)
    write_rows(output_dir / "fill_by_queue_depth_bucket.csv", by_queue)
    write_rows(output_dir / "fill_by_distance_and_queue_bucket.csv", by_both)
    return queue_rows, summary, by_distance, by_queue, by_both


def write_run_config(path, args):
    rows = [
        {"field": "events", "value": args.events},
        {"field": "strategies", "value": " ".join(STRATEGIES)},
        {"field": "flow_profiles", "value": " ".join(FLOW_PROFILES)},
        {"field": "regimes", "value": " ".join(REGIMES)},
        {"field": "risk_mode", "value": "uncontrolled"},
        {"field": "seed_formula", "value": "Stage 5C base seed for each regime, seed_index 0"},
        {"field": "low_volatility_seed", "value": REGIME_SEED_BASE["low-volatility"]},
        {"field": "high_volatility_seed", "value": REGIME_SEED_BASE["high-volatility"]},
        {"field": "trending_seed", "value": REGIME_SEED_BASE["trending"]},
        {"field": "distance_buckets", "value": "0_to_5 5_to_10 10_to_20 20_to_40 40_plus"},
        {"field": "queue_depth_buckets", "value": "0 1_to_100 101_to_500 501_to_1000 1001_plus"},
    ]
    write_rows(path, rows, ["field", "value"])


def main():
    args = parse_args()
    if args.events <= 0:
        raise RuntimeError("--events must be positive")

    root = Path(__file__).resolve().parents[1]
    build_dir = Path(args.build_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_runs:
        if not args.skip_build:
            configure_and_build(root, build_dir)
        executable = executable_path(root, build_dir)
        total = len(FLOW_PROFILES) * len(STRATEGIES) * len(REGIMES)
        completed = 0
        for flow_profile in FLOW_PROFILES:
            for strategy in STRATEGIES:
                for regime in REGIMES:
                    run_one(root, executable, args, flow_profile, strategy, regime, output_dir)
                    completed += 1
                    print(f"completed {completed} of {total}")

    queue_rows, summary, by_distance, by_queue, by_both = combine_outputs(output_dir)
    write_run_config(output_dir / "run_config.csv", args)
    print((output_dir / "quote_queue_events.csv").resolve())
    print(f"quote_queue_events rows {len(queue_rows)}")
    print(f"queue_position_summary rows {len(summary)}")
    print(f"fill_by_distance_bucket rows {len(by_distance)}")
    print(f"fill_by_queue_depth_bucket rows {len(by_queue)}")
    print(f"fill_by_distance_and_queue_bucket rows {len(by_both)}")


if __name__ == "__main__":
    main()
