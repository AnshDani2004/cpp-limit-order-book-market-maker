#!/usr/bin/env python3

import argparse
import csv
import os
import platform
import shutil
import subprocess
from pathlib import Path


COLORS = {
    "low volatility": "#2563eb",
    "high volatility": "#dc2626",
    "trending": "#059669",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="naive", choices=["naive", "avellaneda-stoikov"])
    parser.add_argument("--events", type=int, default=200_000)
    parser.add_argument("--markout-horizon", type=int, default=50)
    parser.add_argument("--curve-sample-stride", type=int, default=100)
    parser.add_argument("--regime", default="all", choices=["all", "low-volatility", "high-volatility", "trending"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--build-dir", default="build/stage3_market_maker")
    parser.add_argument("--output-dir", default="benchmarks/results/stage3_naive_latest")
    parser.add_argument("--skip-build", action="store_true")
    return parser.parse_args()


def strategy_label(strategy):
    if strategy == "naive":
        return "Naive"
    return "Avellaneda Stoikov"


def strategy_file_prefix(strategy):
    if strategy == "naive":
        return "naive"
    return "avellaneda_stoikov"


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


def read_curve(path):
    rows = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "strategy": row["strategy"],
                    "regime": row["regime"],
                    "event_index": int(row["event_index"]),
                    "inventory": float(row["inventory"]),
                    "net_pnl_after_fees": float(row["net_pnl_after_fees"]),
                }
            )
    return rows


def group_by_regime(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["regime"], []).append(row)
    return grouped


def svg_escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def scale(value, low, high, start, stop):
    if high == low:
        return (start + stop) / 2.0
    return start + (value - low) * (stop - start) / (high - low)


def write_line_plot(path, rows, metric, title, y_label):
    grouped = group_by_regime(rows)
    width = 940
    height = 540
    left = 85
    right = 155
    top = 42
    bottom = 70
    plot_width = width - left - right
    plot_height = height - top - bottom

    max_event = max(row["event_index"] for row in rows)
    values = [row[metric] for row in rows]
    low = min(values)
    high = max(values)
    padding = max(1.0, (high - low) * 0.08)
    low -= padding
    high += padding

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="26" text-anchor="middle" font-family="Arial" font-size="18" fill="#111827">{svg_escape(title)}</text>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#111827" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#111827" stroke-width="1"/>',
    ]

    for fraction in [0.0, 0.25, 0.5, 0.75, 1.0]:
        x = left + fraction * plot_width
        event_value = max_event * fraction
        lines.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_height}" stroke="#e5e7eb" stroke-width="1"/>')
        lines.append(f'<text x="{x:.2f}" y="{top + plot_height + 24}" text-anchor="middle" font-family="Arial" font-size="12" fill="#374151">{event_value:.0f}</text>')

    for fraction in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y = top + (1.0 - fraction) * plot_height
        value = low + (high - low) * fraction
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1"/>')
        lines.append(f'<text x="{left - 12}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="12" fill="#374151">{value:.0f}</text>')

    legend_y = top + 12
    for legend_index, (regime, regime_rows) in enumerate(grouped.items()):
        color = COLORS.get(regime, "#4b5563")
        points = []
        for row in regime_rows:
            x = scale(row["event_index"], 0, max_event, left, left + plot_width)
            y = scale(row[metric], low, high, top + plot_height, top)
            points.append(f"{x:.2f},{y:.2f}")
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{svg_escape(" ".join(points))}"/>')

        y = legend_y + legend_index * 24
        lines.append(f'<line x1="{left + plot_width + 28}" y1="{y}" x2="{left + plot_width + 54}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        lines.append(f'<text x="{left + plot_width + 62}" y="{y + 4}" font-family="Arial" font-size="13" fill="#111827">{svg_escape(regime)}</text>')

    lines.append(f'<text x="{left + plot_width / 2}" y="{height - 22}" text-anchor="middle" font-family="Arial" font-size="14" fill="#111827">Event index</text>')
    lines.append(f'<text x="22" y="{top + plot_height / 2}" text-anchor="middle" transform="rotate(-90 22 {top + plot_height / 2})" font-family="Arial" font-size="14" fill="#111827">{svg_escape(y_label)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n")


def main():
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    build_dir = Path(args.build_dir)
    output_dir = Path(args.output_dir)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    if not args.skip_build:
        configure_and_build(root, build_dir)

    executable = executable_path(root, build_dir)
    command = [
        str(executable),
        "--strategy",
        args.strategy,
        "--events",
        str(args.events),
        "--markout-horizon",
        str(args.markout_horizon),
        "--curve-sample-stride",
        str(args.curve_sample_stride),
        "--regime",
        args.regime,
        "--output-dir",
        str(output_dir),
    ]
    if args.seed is not None:
        command.extend(["--seed", str(args.seed)])
    run(command, root)

    curve = read_curve(output_dir / "equity_curve.csv")
    label = strategy_label(args.strategy)
    prefix = strategy_file_prefix(args.strategy)
    write_line_plot(output_dir / f"{prefix}_inventory.svg", curve, "inventory", f"{label} Inventory By Regime", "Inventory")
    write_line_plot(
        output_dir / f"{prefix}_pnl.svg",
        curve,
        "net_pnl_after_fees",
        f"{label} Cumulative PnL After Fees By Regime",
        "Net PnL after fees",
    )

    print((output_dir / "summary.csv").resolve())
    print((output_dir / f"{prefix}_inventory.svg").resolve())
    print((output_dir / f"{prefix}_pnl.svg").resolve())


if __name__ == "__main__":
    main()
