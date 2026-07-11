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
    parser.add_argument(
        "--strategy",
        default="naive",
        choices=["naive", "avellaneda-stoikov", "avellaneda-stoikov-calibrated"],
    )
    parser.add_argument("--events", type=int, default=200_000)
    parser.add_argument("--markout-horizon", type=int, default=50)
    parser.add_argument("--curve-sample-stride", type=int, default=100)
    parser.add_argument("--regime", default="all", choices=["all", "low-volatility", "high-volatility", "trending"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--fill-decay", type=float)
    parser.add_argument("--flow-profile", default="hand-chosen", choices=["hand-chosen", "itch-calibrated"])
    parser.add_argument("--risk-controls", action="store_true")
    parser.add_argument("--inventory-cap", type=int, default=20_000)
    parser.add_argument("--soft-start-fraction", type=float, default=0.50)
    parser.add_argument("--soft-penalty-max-skew-ticks", type=float, default=20.0)
    parser.add_argument("--terminal-liquidation", action="store_true")
    parser.add_argument("--terminal-inventory-penalty-per-unit", type=float, default=0.50)
    parser.add_argument("--risk-denominator-floor", type=float, default=1.0)
    parser.add_argument("--build-dir", default="build/stage3_market_maker")
    parser.add_argument("--output-dir", default="benchmarks/results/stage3_naive_latest")
    parser.add_argument("--skip-build", action="store_true")
    return parser.parse_args()


def strategy_label(strategy):
    if strategy == "naive":
        return "Naive"
    if strategy == "avellaneda-stoikov":
        return "Avellaneda Stoikov"
    return "Calibrated Avellaneda Stoikov"


def strategy_file_prefix(strategy):
    if strategy == "naive":
        return "naive"
    if strategy == "avellaneda-stoikov":
        return "avellaneda_stoikov"
    return "avellaneda_stoikov_calibrated"


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
                    "time_remaining": float(row["time_remaining"]),
                    "reference_mid": float(row["reference_mid"]),
                    "reservation_price": float(row["reservation_price"]),
                    "reservation_skew": float(row["reservation_skew"]),
                    "cash": float(row["cash"]),
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


def write_trending_skew_csv(path, rows):
    trending = [row for row in rows if row["regime"] == "trending"]
    if not trending:
        return

    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "event_index",
                "time_remaining",
                "reference_mid",
                "inventory",
                "reservation_price",
                "reservation_skew",
                "net_pnl_after_fees",
            ]
        )
        for row in trending:
            writer.writerow(
                [
                    row["event_index"],
                    row["time_remaining"],
                    row["reference_mid"],
                    row["inventory"],
                    row["reservation_price"],
                    row["reservation_skew"],
                    row["net_pnl_after_fees"],
                ]
            )


def write_trending_skew_plot(path, rows):
    trending = [row for row in rows if row["regime"] == "trending"]
    if not trending:
        return

    width = 940
    height = 720
    left = 85
    right = 40
    top = 46
    bottom = 58
    gap = 34
    panel_height = (height - top - bottom - 2 * gap) / 3.0
    plot_width = width - left - right
    max_event = max(row["event_index"] for row in trending)

    panels = [
        ("inventory", "Inventory", "#2563eb"),
        ("reservation_skew", "Reservation skew ticks", "#dc2626"),
        ("reference_mid", "Reference mid", "#059669"),
    ]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="26" text-anchor="middle" font-family="Arial" font-size="18" fill="#111827">Avellaneda Stoikov Trending Inventory And Reservation Skew</text>',
    ]

    for panel_index, (metric, label, color) in enumerate(panels):
        panel_top = top + panel_index * (panel_height + gap)
        values = [row[metric] for row in trending]
        low = min(values)
        high = max(values)
        padding = max(1.0, (high - low) * 0.08)
        low -= padding
        high += padding

        lines.append(f'<line x1="{left}" y1="{panel_top + panel_height:.2f}" x2="{left + plot_width}" y2="{panel_top + panel_height:.2f}" stroke="#111827" stroke-width="1"/>')
        lines.append(f'<line x1="{left}" y1="{panel_top:.2f}" x2="{left}" y2="{panel_top + panel_height:.2f}" stroke="#111827" stroke-width="1"/>')
        lines.append(f'<text x="{left - 12}" y="{panel_top + 14:.2f}" text-anchor="end" font-family="Arial" font-size="12" fill="#111827">{svg_escape(label)}</text>')

        for fraction in [0.0, 0.5, 1.0]:
            y = panel_top + (1.0 - fraction) * panel_height
            value = low + (high - low) * fraction
            lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1"/>')
            lines.append(f'<text x="{left - 12}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#374151">{value:.0f}</text>')

        points = []
        for row in trending:
            x = scale(row["event_index"], 0, max_event, left, left + plot_width)
            y = scale(row[metric], low, high, panel_top + panel_height, panel_top)
            points.append(f"{x:.2f},{y:.2f}")
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{svg_escape(" ".join(points))}"/>')

    x_axis_y = height - 24
    for fraction in [0.0, 0.25, 0.5, 0.75, 1.0]:
        x = left + fraction * plot_width
        event_value = max_event * fraction
        lines.append(f'<text x="{x:.2f}" y="{x_axis_y}" text-anchor="middle" font-family="Arial" font-size="12" fill="#374151">{event_value:.0f}</text>')
    lines.append(f'<text x="{left + plot_width / 2}" y="{height - 4}" text-anchor="middle" font-family="Arial" font-size="14" fill="#111827">Event index</text>')
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
        "--flow-profile",
        args.flow_profile,
        "--regime",
        args.regime,
        "--output-dir",
        str(output_dir),
    ]
    if args.seed is not None:
        command.extend(["--seed", str(args.seed)])
    if args.fill_decay is not None:
        command.extend(["--fill-decay", f"{args.fill_decay:.12g}"])
    if args.risk_controls:
        command.append("--risk-controls")
    command.extend(["--inventory-cap", str(args.inventory_cap)])
    command.extend(["--soft-start-fraction", f"{args.soft_start_fraction:.12g}"])
    command.extend(["--soft-penalty-max-skew-ticks", f"{args.soft_penalty_max_skew_ticks:.12g}"])
    if args.terminal_liquidation:
        command.append("--terminal-liquidation")
    command.extend(["--terminal-inventory-penalty-per-unit", f"{args.terminal_inventory_penalty_per_unit:.12g}"])
    command.extend(["--risk-denominator-floor", f"{args.risk_denominator_floor:.12g}"])
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
    if args.strategy in {"avellaneda-stoikov", "avellaneda-stoikov-calibrated"}:
        write_trending_skew_csv(output_dir / f"{prefix}_trending_skew.csv", curve)
        write_trending_skew_plot(output_dir / f"{prefix}_trending_skew.svg", curve)

    print((output_dir / "summary.csv").resolve())
    print((output_dir / f"{prefix}_inventory.svg").resolve())
    print((output_dir / f"{prefix}_pnl.svg").resolve())


if __name__ == "__main__":
    main()
