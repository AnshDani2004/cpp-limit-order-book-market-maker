"""Replication summary per PREREG section 8: median and min-max per config, decision rule on pairs."""
import csv, json, statistics, sys

rows = list(csv.DictReader(open(sys.argv[1])))
cfgs = ["map", "lb_new", "flat", "lb_pool", "map_unity", "lb_shared"]
S = {}
for c in cfgs:
    rr = [r for r in rows if r["config"] == c]
    if not rr:
        continue
    d = {"n": len(rr), "all_valid": all(r["valid"] == "1" for r in rr),
         "loaded_runs": sum(r["loaded_flag"] != "ok" for r in rr),
         "load_min": min(float(r["load1_before"]) for r in rr), "load_max": max(float(r["load1_before"]) for r in rr),
         "power": sorted({r["power"] for r in rr})}
    for m in ["events_per_s", "p50_ns", "p99_ns"]:
        v = [float(r[m]) for r in rr]
        d[m] = {"median": statistics.median(v), "min": min(v), "max": max(v), "runs": v}
    S[c] = d

def faster(x, y):  # events/s: higher is better
    a, b = S[x]["events_per_s"], S[y]["events_per_s"]
    if a["median"] > b["median"] and a["min"] > b["max"]:
        return f"{x} faster"
    if b["median"] > a["median"] and b["min"] > a["max"]:
        return f"{y} faster"
    return "no clear difference"

def lower(x, y, m):
    a, b = S[x][m], S[y][m]
    if a["median"] < b["median"] and a["max"] < b["min"]:
        return f"{x} lower"
    if b["median"] < a["median"] and b["max"] < a["min"]:
        return f"{y} lower"
    return "no clear difference"

pairs = [("map", "lb_new", "PRIMARY"), ("flat", "lb_new", "secondary"), ("map", "lb_pool", "secondary"),
         ("map_unity", "lb_new", "secondary"), ("map", "lb_shared", "secondary"), ("flat", "lb_pool", "secondary"),
         ("map_unity", "lb_pool", "secondary"), ("map", "flat", "secondary"), ("map", "map_unity", "secondary")]
dec = []
for x, y, role in pairs:
    if x in S and y in S:
        dec.append({"pair": f"{x} vs {y}", "role": role, "events_per_s": faster(x, y),
                    "ratio_of_medians": S[x]["events_per_s"]["median"] / S[y]["events_per_s"]["median"],
                    "p50": lower(x, y, "p50_ns"), "p99": lower(x, y, "p99_ns")})
out = {"configs": S, "decisions": dec}
print(json.dumps(out, indent=1))
