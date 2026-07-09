#!/usr/bin/env python3

import argparse
import csv
import shutil
from pathlib import Path


STRATEGY_LABELS = {
    "naive symmetric": "Naive",
    "avellaneda stoikov": "Avellaneda Stoikov",
}

STRATEGY_COLORS = {
    "naive symmetric": "#2563eb",
    "avellaneda stoikov": "#dc2626",
}

METRICS = [
    ("fill_rate", "Fill rate"),
    ("gross_spread_capture", "Gross spread capture"),
    ("inventory_pnl", "Inventory PnL"),
    ("adverse_selection_cost", "Adverse selection cost"),
    ("fee_pnl", "Fee PnL"),
    ("net_pnl_after_fees", "Net PnL after fees"),
    ("maximum_drawdown", "Maximum drawdown"),
    ("inventory_variance", "Inventory variance"),
    ("final_inventory", "Final inventory"),
    ("maker_fills", "Maker fills"),
    ("taker_fills", "Taker fills"),
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--naive-dir", default="benchmarks/results/stage3_naive_checkpoint")
    parser.add_argument("--as-dir", default="benchmarks/results/stage3_avellaneda_stoikov_checkpoint")
    parser.add_argument("--output-dir", default="benchmarks/results/stage3_comparison")
    return parser.parse_args()


def read_summary(path):
    rows = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)
    return rows


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


def numeric(value):
    return float(value)


def write_side_by_side(path, summaries):
    fieldnames = [
        "regime",
        "metric",
        "naive_symmetric",
        "avellaneda_stoikov",
        "as_minus_naive",
        "as_percent_change",
    ]
    by_regime = {}
    for row in summaries:
        by_regime.setdefault(row["regime"], {})[row["strategy"]] = row

    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for regime, strategies in by_regime.items():
            naive = strategies["naive symmetric"]
            avellaneda = strategies["avellaneda stoikov"]
            for metric, _label in METRICS:
                naive_value = numeric(naive[metric])
                as_value = numeric(avellaneda[metric])
                delta = as_value - naive_value
                percent_change = "" if naive_value == 0 else delta / abs(naive_value)
                writer.writerow(
                    {
                        "regime": regime,
                        "metric": metric,
                        "naive_symmetric": f"{naive_value:.12g}",
                        "avellaneda_stoikov": f"{as_value:.12g}",
                        "as_minus_naive": f"{delta:.12g}",
                        "as_percent_change": "" if percent_change == "" else f"{percent_change:.12g}",
                    }
                )


def write_regime_summary(path, summaries):
    with path.open("w", newline="") as handle:
        fieldnames = list(summaries[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)


def svg_escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def scale(value, low, high, start, stop):
    if high == low:
        return (start + stop) / 2.0
    return start + (value - low) * (stop - start) / (high - low)


def write_comparison_plot(path, rows, regime, metric, title, y_label):
    regime_rows = [row for row in rows if row["regime"] == regime]
    width = 940
    height = 540
    left = 85
    right = 185
    top = 42
    bottom = 70
    plot_width = width - left - right
    plot_height = height - top - bottom

    max_event = max(row["event_index"] for row in regime_rows)
    values = [row[metric] for row in regime_rows]
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

    for legend_index, strategy in enumerate(STRATEGY_LABELS):
        strategy_rows = [row for row in regime_rows if row["strategy"] == strategy]
        points = []
        for row in strategy_rows:
            x = scale(row["event_index"], 0, max_event, left, left + plot_width)
            y = scale(row[metric], low, high, top + plot_height, top)
            points.append(f"{x:.2f},{y:.2f}")

        color = STRATEGY_COLORS[strategy]
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{svg_escape(" ".join(points))}"/>')
        legend_y = top + 16 + legend_index * 24
        lines.append(f'<line x1="{left + plot_width + 28}" y1="{legend_y}" x2="{left + plot_width + 54}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>')
        lines.append(f'<text x="{left + plot_width + 62}" y="{legend_y + 4}" font-family="Arial" font-size="13" fill="#111827">{svg_escape(STRATEGY_LABELS[strategy])}</text>')

    lines.append(f'<text x="{left + plot_width / 2}" y="{height - 22}" text-anchor="middle" font-family="Arial" font-size="14" fill="#111827">Event index</text>')
    lines.append(f'<text x="22" y="{top + plot_height / 2}" text-anchor="middle" transform="rotate(-90 22 {top + plot_height / 2})" font-family="Arial" font-size="14" fill="#111827">{svg_escape(y_label)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n")


def main():
    args = parse_args()
    naive_dir = Path(args.naive_dir)
    as_dir = Path(args.as_dir)
    output_dir = Path(args.output_dir)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    summaries = read_summary(naive_dir / "summary.csv") + read_summary(as_dir / "summary.csv")
    write_side_by_side(output_dir / "metrics_table.csv", summaries)
    write_regime_summary(output_dir / "summary_by_strategy.csv", summaries)
    as_adverse_split = as_dir / "adverse_selection_split.csv"
    if as_adverse_split.exists():
        shutil.copyfile(as_adverse_split, output_dir / "avellaneda_stoikov_adverse_selection_split.csv")

    curves = read_curve(naive_dir / "equity_curve.csv") + read_curve(as_dir / "equity_curve.csv")
    for regime in ["low volatility", "high volatility", "trending"]:
        slug = regime.replace(" ", "_")
        write_comparison_plot(
            output_dir / f"{slug}_inventory.svg",
            curves,
            regime,
            "inventory",
            f"{regime.title()} Inventory",
            "Inventory",
        )
        write_comparison_plot(
            output_dir / f"{slug}_pnl.svg",
            curves,
            regime,
            "net_pnl_after_fees",
            f"{regime.title()} Cumulative PnL After Fees",
            "Net PnL after fees",
        )

    print((output_dir / "metrics_table.csv").resolve())
    print((output_dir / "summary_by_strategy.csv").resolve())
    copied_split = output_dir / "avellaneda_stoikov_adverse_selection_split.csv"
    if copied_split.exists():
        print(copied_split.resolve())


if __name__ == "__main__":
    main()
