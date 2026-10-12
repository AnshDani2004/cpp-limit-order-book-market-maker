# Low-load rerun, 2026-10-12 (same Apple M3, same build/audit_release binary, repo commit 1c1451f code)

Run after the parallel audit jobs had finished. The machine was not idle in a strict sense (the
1-minute load average, recorded before each run, was 2.2 to 2.3 on 8 cores, from the desktop session
and other user processes), but no other benchmark or test job was running.

Commands:
  map:  ./build/audit_release/orderbook_benchmark --events 1000000 --warmup 20000 --seed 42 --output-dir <scratch>/map_runN
  flat: ./build/audit_release/orderbook_benchmark --events 1000000 --warmup 20000 --seed 42 --book flat --min-price 99000 --max-price 101000 --output-dir <scratch>/flat_runN
Every run: 350,663 trades, 0 rejects. Per-run summary.csv files are in this directory.

| run | book | events/s | p50 ns | p99 ns |
|---|---|---|---|---|
| map_run1 | map | 4628665 | 125 | 917 |
| map_run2 | map | 4965452 | 125 | 750 |
| map_run3 | map | 5008887 | 125 | 791 |
| map_run4 | map | 4667589 | 125 | 958 |
| map_run5 | map | 4912097 | 125 | 792 |
| flat_run1 | flat | 5623824 | 84 | 708 |
| flat_run2 | flat | 4867855 | 84 | 875 |
| flat_run3 | flat | 4834436 | 84 | 916 |

Map book, 5 runs: 4.63M to 5.01M events/s (median 4.91M), p50 125 ns in every run, p99 750 to 958 ns.
Flat book, 3 runs: 4.83M to 5.62M events/s, p50 84 ns, p99 708 to 916 ns.
The resume's ~3.7M events/s at 125 ns p50 / 1.2 us p99 (stage2_local) is therefore conservative on this machine at low load; the loaded-machine runs in runs.txt (median 3.14M) show how sensitive throughput is to other load.

## Raw stdout
### map run 1 | load: { 2.23 3.57 4.12 }
events_per_second=4628665.32435
p50_latency_ns=125
p95_latency_ns=500
p99_latency_ns=917
max_latency_ns=1352833
max_event_index=559699
max_event_action=limit
max_event_price_level_created=false
max_event_out_of_order_insert=false
rejects=0
### map run 2 | load: { 2.23 3.57 4.12 }
events_per_second=4965451.82617
p50_latency_ns=125
p95_latency_ns=459
p99_latency_ns=750
max_latency_ns=1285708
max_event_index=559699
max_event_action=limit
max_event_price_level_created=false
max_event_out_of_order_insert=false
rejects=0
### map run 3 | load: { 2.23 3.57 4.12 }
events_per_second=5008886.59128
p50_latency_ns=125
p95_latency_ns=459
p99_latency_ns=791
max_latency_ns=924125
max_event_index=512822
max_event_action=limit
max_event_price_level_created=false
max_event_out_of_order_insert=false
rejects=0
### map run 4 | load: { 2.23 3.57 4.12 }
events_per_second=4667588.90444
p50_latency_ns=125
p95_latency_ns=541
p99_latency_ns=958
max_latency_ns=1560625
max_event_index=512822
max_event_action=limit
max_event_price_level_created=false
max_event_out_of_order_insert=false
rejects=0
### map run 5 | load: { 2.23 3.57 4.12 }
events_per_second=4912097.0169
p50_latency_ns=125
p95_latency_ns=500
p99_latency_ns=792
max_latency_ns=1851708
max_event_index=512822
max_event_action=limit
max_event_price_level_created=false
max_event_out_of_order_insert=false
rejects=0
### flat run 1 | load: { 2.29 3.56 4.11 }
events_per_second=5623823.84051
p50_latency_ns=84
p95_latency_ns=458
p99_latency_ns=708
max_latency_ns=1280375
max_event_index=559699
max_event_action=limit
max_event_price_level_created=false
max_event_out_of_order_insert=false
rejects=0
### flat run 2 | load: { 2.29 3.56 4.11 }
events_per_second=4867854.99347
p50_latency_ns=84
p95_latency_ns=541
p99_latency_ns=875
max_latency_ns=1587417
max_event_index=512822
max_event_action=limit
max_event_price_level_created=false
max_event_out_of_order_insert=false
rejects=0
### flat run 3 | load: { 2.29 3.56 4.11 }
events_per_second=4834435.68539
p50_latency_ns=84
p95_latency_ns=541
p99_latency_ns=916
max_latency_ns=1671458
max_event_index=559699
max_event_action=limit
max_event_price_level_created=false
max_event_out_of_order_insert=false
rejects=0
