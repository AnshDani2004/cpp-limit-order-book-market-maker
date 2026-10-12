#!/usr/bin/env python3
"""Extension 3(a): summary table and the pre-registered decision rule (PREREG.md section 8).
Usage: python3 -I summarize.py <runs.csv>  (writes summary.md next to runs.csv)"""
import csv
import statistics
import sys
from pathlib import Path

EXPECTED = {"trades": "372120", "volume": "9486560", "rejects": "0"}
PRIMARY = ("map", "lb_new")
SECONDARY = [("flat", "lb_new"), ("map_unity", "lb_new"), ("map", "lb_pool"), ("map", "lb_shared"),
             ("map", "flat"), ("map", "map_unity")]
METRICS = [("events_per_second", "events/s", True), ("p50_ns", "p50 ns", False), ("p99_ns", "p99 ns", False)]


def decide(a, b, values, metric, higher_better):
    va, vb = values[a][metric], values[b][metric]
    ma, mb = statistics.median(va), statistics.median(vb)
    if higher_better:
        if ma > mb and min(va) > max(vb):
            return f"{a} faster"
        if mb > ma and min(vb) > max(va):
            return f"{b} faster"
    else:
        if ma < mb and max(va) < min(vb):
            return f"{a} lower"
        if mb < ma and max(vb) < min(va):
            return f"{b} lower"
    return "no clear difference"


def main():
    path = Path(sys.argv[1])
    rows = list(csv.DictReader(path.open()))
    invalid = [r for r in rows if any(r[k] != v for k, v in EXPECTED.items())]
    loaded = [r for r in rows if r["loaded_flag"] != "ok"]
    values = {}
    for r in rows:
        if r in invalid:
            continue
        d = values.setdefault(r["config"], {m: [] for m, _, _ in METRICS} | {"load1": []})
        for m, _, _ in METRICS:
            d[m].append(float(r[m]))
        d["load1"].append(float(r["load1"]))
    out = [f"# ext3a summary (computed by summarize.py from {path.name})", ""]
    out.append(f"runs: {len(rows)}; invalid (trade count, volume or rejects differ from expected): {len(invalid)}; "
               f"runs with pre-run 1-min load >= 3.0 or failed gate (LOADED): {len(loaded)}")
    out.append("")
    out.append("| config | n | events/s median | events/s min to max | p50 ns median (min to max) | p99 ns median (min to max) | 1-min load (min to max) |")
    out.append("|---|---|---|---|---|---|---|")
    for cfg, d in values.items():
        e, p50, p99, ld = d["events_per_second"], d["p50_ns"], d["p99_ns"], d["load1"]
        out.append(f"| {cfg} | {len(e)} | {statistics.median(e):,.0f} | {min(e):,.0f} to {max(e):,.0f} | "
                   f"{statistics.median(p50):.0f} ({min(p50):.0f} to {max(p50):.0f}) | "
                   f"{statistics.median(p99):.0f} ({min(p99):.0f} to {max(p99):.0f}) | {min(ld):.2f} to {max(ld):.2f} |")
    out.append("")
    out.append("## Decision rule (pre-registered)")
    for label, pairs in (("PRIMARY", [PRIMARY]), ("secondary (descriptive)", SECONDARY)):
        for a, b in pairs:
            if a not in values or b not in values:
                continue
            ratio = statistics.median(values[a]["events_per_second"]) / statistics.median(values[b]["events_per_second"])
            parts = [f"{name}: {decide(a, b, values, m, hb)}" for m, name, hb in METRICS]
            out.append(f"- {label} {a} vs {b}: " + "; ".join(parts) + f"; median events/s ratio {a}/{b} = {ratio:.3f}")
    text = "\n".join(out) + "\n"
    (path.parent / "summary.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
