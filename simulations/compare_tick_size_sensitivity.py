#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path


CASES = [
    ("1", "0.63274456291", "calibrated-one-cent-dir"),
    ("5", "0.126548912582", "calibrated-five-cent-dir"),
    ("20", "0.0316372281455", "calibrated-twenty-cent-dir"),
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-as-dir", default="benchmarks/results/stage4b_avellaneda_stoikov_comparison")
    parser.add_argument(
        "--calibrated-one-cent-dir",
        default="benchmarks/results/stage4b_calibrated_avellaneda_stoikov_comparison",
    )
    parser.add_argument(
        "--calibrated-five-cent-dir",
        default="benchmarks/results/stage4b_calibrated_tick_5c_comparison",
    )
    parser.add_argument(
        "--calibrated-twenty-cent-dir",
        default="benchmarks/results/stage4b_calibrated_tick_20c_comparison",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/results/stage4b_strategy_comparison/tick_size_sensitivity.csv",
    )
    return parser.parse_args()


def read_summary(directory):
    with (Path(directory) / "summary.csv").open(newline="") as handle:
        return {row["regime"]: row for row in csv.DictReader(handle)}


def main():
    args = parse_args()
    original = read_summary(args.original_as_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "tick_size_cents",
        "fill_decay",
        "regime",
        "original_as_net_pnl",
        "calibrated_net_pnl",
        "net_pnl_minus_original_as",
        "original_as_final_inventory",
        "calibrated_final_inventory",
        "final_inventory_minus_original_as",
        "calibrated_fill_rate",
        "calibrated_maker_fills",
        "calibrated_gross_spread_capture",
        "calibrated_adverse_selection_cost",
    ]

    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for tick_size, fill_decay, attr_name in CASES:
            current = read_summary(getattr(args, attr_name.replace("-", "_")))
            for regime in ["low volatility", "high volatility", "trending"]:
                base = original[regime]
                row = current[regime]
                net_delta = float(row["net_pnl_after_fees"]) - float(base["net_pnl_after_fees"])
                inventory_delta = int(row["final_inventory"]) - int(base["final_inventory"])
                writer.writerow(
                    {
                        "tick_size_cents": tick_size,
                        "fill_decay": fill_decay,
                        "regime": regime,
                        "original_as_net_pnl": f"{float(base['net_pnl_after_fees']):.12g}",
                        "calibrated_net_pnl": f"{float(row['net_pnl_after_fees']):.12g}",
                        "net_pnl_minus_original_as": f"{net_delta:.12g}",
                        "original_as_final_inventory": base["final_inventory"],
                        "calibrated_final_inventory": row["final_inventory"],
                        "final_inventory_minus_original_as": inventory_delta,
                        "calibrated_fill_rate": f"{float(row['fill_rate']):.12g}",
                        "calibrated_maker_fills": row["maker_fills"],
                        "calibrated_gross_spread_capture": f"{float(row['gross_spread_capture']):.12g}",
                        "calibrated_adverse_selection_cost": f"{float(row['adverse_selection_cost']):.12g}",
                    }
                )

    print(output.resolve())


if __name__ == "__main__":
    main()
