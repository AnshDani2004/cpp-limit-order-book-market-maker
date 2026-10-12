#!/usr/bin/env bash
# Extension 3(a): the pre-registered timed runs (PREREG.md section 7). Usage: run_timed.sh <output_dir>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
B="$HERE/build"
OUT="${1:?output dir}"
STREAM="$B/stream_seed42.csv"
EXPECTED_SHA=e1e9535a678b5c581ebb461b5d78a5307674203258e8ea24e98f93f30a8c3394
CONFIGS=(map lb_new flat lb_pool map_unity lb_shared)
ROUNDS=5
THRESH=3.0
GATE_MAX_S=2700   # 45 minutes
GATE_POLL_S=60
RUN_WAIT_MAX_S=300
RUN_POLL_S=15

mkdir -p "$OUT"
LOG="$OUT/raw_stdout.txt"
CSV="$OUT/runs.csv"
load1() { sysctl -n vm.loadavg | awk '{print $2}'; }
below() { awk -v a="$1" -v t="$THRESH" 'BEGIN{exit !(a < t)}'; }

actual_sha="$(shasum -a 256 "$STREAM" | awk '{print $1}')"
[ "$actual_sha" = "$EXPECTED_SHA" ] || { echo "stream hash mismatch: $actual_sha" >&2; exit 1; }

{
  echo "# ext3a timed runs"
  echo "start_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "repo_commit: $(git -C "$HERE" rev-parse HEAD)"
  echo "liquibook_commit: $(git -C "$HERE/third_party/liquibook" rev-parse HEAD)"
  echo "stream_sha256: $actual_sha"
  echo "cpu: $(sysctl -n machdep.cpu.brand_string) ncpu=$(sysctl -n hw.ncpu) perf=$(sysctl -n hw.perflevel0.physicalcpu) eff=$(sysctl -n hw.perflevel1.physicalcpu) mem_bytes=$(sysctl -n hw.memsize)"
  echo "os: $(sw_vers -productVersion) ($(sw_vers -buildVersion)), $(uname -sr)"
  echo "compiler: $(clang++ --version | head -1)"
  echo "power: $(pmset -g batt | head -1)"
} > "$LOG"

# Global gate: wait for 1-minute load < 3.0, polling every 60 s, for up to 45 minutes.
gate_start=$(date +%s)
GATE=passed
while ! below "$(load1)"; do
  now=$(date +%s)
  echo "gate_poll $(date -u +%H:%M:%SZ) load: $(sysctl -n vm.loadavg)" >> "$LOG"
  if [ $((now - gate_start)) -ge $GATE_MAX_S ]; then GATE=failed; break; fi
  sleep $GATE_POLL_S
done
echo "gate: $GATE after $(( $(date +%s) - gate_start )) s; load: $(sysctl -n vm.loadavg)" >> "$LOG"

echo "config,round,binary,load1,load5,load15,loaded_flag,events_per_second,p50_ns,p95_ns,p99_ns,max_ns,trades,volume,rejects" > "$CSV"
for r in $(seq 1 $ROUNDS); do
  for cfg in "${CONFIGS[@]}"; do
    if [ "$GATE" = passed ]; then
      waited=0
      while ! below "$(load1)" && [ $waited -lt $RUN_WAIT_MAX_S ]; do sleep $RUN_POLL_S; waited=$((waited + RUN_POLL_S)); done
    fi
    read -r _ l1 l5 l15 _ <<< "$(sysctl -n vm.loadavg)"
    flag=ok
    below "$l1" || flag=LOADED
    [ "$GATE" = passed ] || flag=LOADED
    if [ "$cfg" = map_unity ]; then bin="$B/ext3_harness_unity"; eng=map; else bin="$B/ext3_harness"; eng="$cfg"; fi
    summary="$OUT/${cfg}_run${r}_summary.csv"
    echo "### $cfg run $r | load: { $l1 $l5 $l15 } | $flag" >> "$LOG"
    "$bin" time "$STREAM" "$eng" "$summary" >> "$LOG"
    get() { awk -F, -v k="$1" '$1==k{print $2}' "$summary"; }
    echo "$cfg,$r,$(basename "$bin"),$l1,$l5,$l15,$flag,$(get events_per_second),$(get p50_latency_ns),$(get p95_latency_ns),$(get p99_latency_ns),$(get max_latency_ns),$(get measured_trades),$(get measured_volume),$(get measured_rejects)" >> "$CSV"
  done
done
echo "end_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
echo "done: $CSV"
