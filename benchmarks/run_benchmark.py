#!/usr/bin/env python3

import argparse
import csv
import os
import platform
import shutil
import subprocess
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=1_000_000)
    parser.add_argument("--warmup", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--book", choices=["map", "flat"], default="map")
    parser.add_argument("--flow-profile", choices=["hand-chosen", "itch-calibrated"], default="hand-chosen")
    parser.add_argument("--min-price", type=int, default=1)
    parser.add_argument("--max-price", type=int, default=200_000)
    parser.add_argument("--build-dir", default="build/stage2_benchmark")
    parser.add_argument("--output-dir", default="benchmarks/results/stage2_latest")
    parser.add_argument("--skip-build", action="store_true")
    return parser.parse_args()


def run(command, cwd):
    subprocess.run(command, cwd=cwd, check=True)


def command_output(command):
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def configure_and_build(root, build_dir):
    cmake = os.environ.get("CMAKE", "cmake")
    run([cmake, "-S", ".", "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF"], root)
    run([cmake, "--build", str(build_dir), "--config", "Release", "--target", "orderbook_benchmark"], root)


def read_metric_map(path):
    values = {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            values[row["metric"]] = row["value"]
    return values


def read_latencies(path):
    latencies = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            latencies.append(int(row["latency_ns"]))
    return latencies


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field", "value"])
        writer.writerows(rows)


def collect_hardware(root):
    rows = []
    rows.append(("system", platform.platform()))
    rows.append(("machine", platform.machine()))
    rows.append(("python", platform.python_version()))

    if platform.system() == "Darwin":
        rows.append(("cpu", command_output(["sysctl", "-n", "machdep.cpu.brand_string"])))
        rows.append(("logical_cores", command_output(["sysctl", "-n", "hw.ncpu"])))
        memory_bytes = command_output(["sysctl", "-n", "hw.memsize"])
        if memory_bytes:
            rows.append(("memory_gb", f"{int(memory_bytes) / (1024 ** 3):.2f}"))
        rows.append(("os", command_output(["sw_vers", "-productVersion"])))
    elif platform.system() == "Linux":
        cpu = ""
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            for line in cpuinfo.read_text().splitlines():
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
        rows.append(("cpu", cpu))
        rows.append(("logical_cores", str(os.cpu_count() or "")))
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text().splitlines():
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    rows.append(("memory_gb", f"{kb / (1024 ** 2):.2f}"))
                    break

    compiler = os.environ.get("CXX", "c++")
    compiler_version = command_output([compiler, "--version"]).splitlines()
    rows.append(("compiler", compiler_version[0] if compiler_version else compiler))

    cmake = os.environ.get("CMAKE", "cmake")
    cmake_version = command_output([cmake, "--version"]).splitlines()
    rows.append(("cmake", cmake_version[0] if cmake_version else cmake))
    return rows


def svg_escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_latency_cdf(path, latencies):
    sorted_latencies = sorted(latencies)
    width = 900
    height = 520
    left = 80
    right = 30
    top = 35
    bottom = 70
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_us = max(sorted_latencies) / 1000.0
    if max_us <= 0:
        max_us = 1.0

    points = []
    sample_count = min(1000, len(sorted_latencies))
    for index in range(sample_count):
        source_index = round(index * (len(sorted_latencies) - 1) / max(1, sample_count - 1))
        x_value = sorted_latencies[source_index] / 1000.0
        y_value = source_index / max(1, len(sorted_latencies) - 1)
        x = left + (x_value / max_us) * plot_width
        y = top + (1.0 - y_value) * plot_height
        points.append(f"{x:.2f},{y:.2f}")

    tick_values = [0.0, max_us * 0.25, max_us * 0.50, max_us * 0.75, max_us]
    cdf_ticks = [0.0, 0.25, 0.50, 0.75, 1.0]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="24" text-anchor="middle" font-family="Arial" font-size="18" fill="#111827">Order Processing Latency CDF</text>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#111827" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#111827" stroke-width="1"/>',
    ]

    for value in tick_values:
        x = left + (value / max_us) * plot_width
        lines.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_height}" stroke="#e5e7eb" stroke-width="1"/>')
        lines.append(f'<text x="{x:.2f}" y="{top + plot_height + 24}" text-anchor="middle" font-family="Arial" font-size="12" fill="#374151">{value:.2f}</text>')

    for value in cdf_ticks:
        y = top + (1.0 - value) * plot_height
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1"/>')
        lines.append(f'<text x="{left - 12}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="12" fill="#374151">{value:.2f}</text>')

    lines.append(f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{svg_escape(" ".join(points))}"/>')
    lines.append(f'<text x="{left + plot_width / 2}" y="{height - 22}" text-anchor="middle" font-family="Arial" font-size="14" fill="#111827">Latency microseconds</text>')
    lines.append(f'<text x="20" y="{top + plot_height / 2}" text-anchor="middle" transform="rotate(-90 20 {top + plot_height / 2})" font-family="Arial" font-size="14" fill="#111827">Cumulative share</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n")


def write_readme_snippet(path, summary):
    events = int(summary["measured_events"])
    eps = float(summary["events_per_second"])
    p50 = int(summary["p50_latency_ns"])
    p95 = int(summary["p95_latency_ns"])
    p99 = int(summary["p99_latency_ns"])
    max_latency = int(summary["max_latency_ns"])
    text = (
        "Stage 2 benchmark result\n\n"
        f"processed {events:,} synthetic order events at {eps:,.0f} events per second\n"
        f"p50 {p50} ns\n"
        f"p95 {p95} ns\n"
        f"p99 {p99} ns\n"
        f"max {max_latency} ns\n"
    )
    path.write_text(text)


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

    executable = root / build_dir / "orderbook_benchmark"
    if platform.system() == "Windows":
        executable = root / build_dir / "Release" / "orderbook_benchmark.exe"

    run([
        str(executable),
        "--events",
        str(args.events),
        "--warmup",
        str(args.warmup),
        "--seed",
        str(args.seed),
        "--book",
        args.book,
        "--flow-profile",
        args.flow_profile,
        "--min-price",
        str(args.min_price),
        "--max-price",
        str(args.max_price),
        "--output-dir",
        str(output_dir),
    ], root)

    summary = read_metric_map(output_dir / "summary.csv")
    latencies = read_latencies(output_dir / "latencies.csv")
    write_latency_cdf(output_dir / "latency_cdf.svg", latencies)
    write_csv(output_dir / "hardware.csv", collect_hardware(root))
    write_readme_snippet(output_dir / "readme_snippet.txt", summary)
    print((output_dir / "summary.csv").resolve())
    print((output_dir / "latency_cdf.svg").resolve())


if __name__ == "__main__":
    main()
