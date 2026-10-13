#!/bin/bash
# Replication timed sequence per PREREG section 7 (5 rounds x 6 configs, fixed order, fresh process each),
# with the shared-machine lock and load rules from the replication brief.
set -uo pipefail
cd "$(dirname "$0")"
OUT=${1:?usage: run_timed.sh results/<run_dir>}
STREAM=build/stream_a.csv
EXPECT_SHA=9993edaeb2c2a2e7a74c49994133f158a1e0682ddeb4537bd75c0eaa621b59b9
LOCK=/Users/ansh/quant-projects-audit/existing/ext3_timing.lock
mkdir -p "$OUT"
LOG="$OUT/raw_stdout.txt"; RUNS="$OUT/runs.csv"
load1() { sysctl -n vm.loadavg | awk '{print $2}'; }
lt3() { awk -v l="$1" 'BEGIN{exit !(l<3.0)}'; }
log() { echo "$*" | tee -a "$LOG"; }
: > "$LOG"
log "machine: $(sysctl -n machdep.cpu.brand_string) $(sw_vers -productVersion)"
log "compiler: $(clang++ --version | head -1)"
log "repo HEAD: $(git -C ../cpp-limit-order-book-market-maker rev-parse HEAD) liquibook: $(git -C third_party/liquibook rev-parse HEAD)"
SHA=$(shasum -a 256 "$STREAM" | awk '{print $1}')
log "stream sha256: $SHA"
[ "$SHA" = "$EXPECT_SHA" ] || { log "STREAM SHA MISMATCH"; exit 1; }
# Gate: lock absent and load < 3.0, poll every 60 s up to 45 min.
GATE=FAIL
for i in $(seq 0 45); do
  L=$(load1)
  if [ ! -e "$LOCK" ] && lt3 "$L"; then
    if ( set -o noclobber; echo "replication-agent ext3a $(date '+%F %T')" > "$LOCK" ) 2>/dev/null; then GATE=PASS; log "gate poll $i: load=$L lock=acquired"; break; fi
  fi
  log "gate poll $i: load=$L lock=$([ -e "$LOCK" ] && cat "$LOCK" || echo absent)"
  [ $i -lt 45 ] && sleep 60
done
if [ "$GATE" != PASS ]; then
  log "GATE FAILED after 45 min: not running (replication brief requires load < 3.0 and no lock)"; exit 2
fi
trap 'rm -f "$LOCK"' EXIT
log "gate: PASS"
echo "round,config,order,load1_before,loaded_flag,power,events_per_s,p50_ns,p99_ns,max_ns,total_ns,trades,volume,rejects,valid" > "$RUNS"
CONFIGS="map lb_new flat lb_pool map_unity lb_shared"
k=0
for r in 1 2 3 4 5; do
  for c in $CONFIGS; do
    k=$((k+1))
    for w in $(seq 0 20); do L=$(load1); lt3 "$L" && break; log "  wait $w before $c r$r: load=$L"; sleep 15; done
    L=$(load1); FLAG=ok; lt3 "$L" || FLAG=LOADED
    PWR=$(pmset -g batt | head -1 | sed "s/Now drawing from //; s/'//g")
    BIN=build/rep_harness; [ "$c" = map_unity ] && BIN=build/rep_harness_unity
    LINE=$($BIN run $c $STREAM)
    log "round=$r config=$c load1=$L flag=$FLAG power=$PWR :: $LINE"
    g() { echo "$LINE" | tr ' ' '\n' | awk -F= -v k="$1" '$1==k{print $2}'; }
    echo "$r,$c,$k,$L,$FLAG,$PWR,$(g events_per_s),$(g p50_ns),$(g p99_ns),$(g max_ns),$(g total_ns),$(g trades),$(g volume),$(g rejects),$(g valid)" >> "$RUNS"
  done
done
log "done $(date '+%F %T')"
