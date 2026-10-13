#!/usr/bin/env bash
# Adversarial timed runs. Holds ../ext3_timing.lock for the duration; records load and power per run.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOCK="$HERE/../ext3_timing.lock"
B="$HERE/build"
FROZEN="$HERE/../cpp-limit-order-book-market-maker/benchmarks/ext3/build/stream_seed42.csv"
OUT="$HERE/results_timed"; mkdir -p "$OUT"
CSV="$OUT/runs.csv"; LOG="$OUT/raw_stdout.txt"
load1() { sysctl -n vm.loadavg | awk '{print $2}'; }
below() { awk -v a="$1" 'BEGIN{exit !(a < 3.0)}'; }
if [ -e "$LOCK" ]; then echo "lock present: $(cat "$LOCK")"; exit 9; fi
echo "adversarial-fairness-reviewer $(date -u +%FT%TZ)" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
{ echo "start $(date -u +%FT%TZ)"; echo "power: $(pmset -g batt | head -1)"; pmset -g | grep -i lowpowermode; } > "$LOG"
echo "stream,config,mode,round,load1,flag,line" > "$CSV"
run() { # stream_name path engine mode round
  local w=0
  while ! below "$(load1)" && [ $w -lt 120 ]; do sleep 5; w=$((w+5)); done
  local l1; l1="$(load1)"; local flag=ok; below "$l1" || flag=LOADED
  local line; line="$("$B/adv_harness" time "$2" "$3" "$OUT/tmp_summary.csv" "$4")"
  echo "$1 $3 $4 r$5 load=$l1 $flag :: $line" >> "$LOG"
  echo "$1,$3,$4,$5,$l1,$flag,\"$line\"" >> "$CSV"
}
for r in 1 2 3 4 5; do
  for cfg in map lb_new lb_vec lb_pool noop; do run frozen "$FROZEN" "$cfg" clock "$r"; done
  for cfg in map lb_new lb_vec; do run frozen "$FROZEN" "$cfg" noclock "$r"; done
done
for r in 1 2 3; do
  for s in s5 s6 s1 s4; do
    for cfg in map lb_new lb_vec; do run "$s" "$B/$s.csv" "$cfg" clock "$r"; done
  done
done
echo "end $(date -u +%FT%TZ); power: $(pmset -g batt | head -1)" >> "$LOG"
echo done
