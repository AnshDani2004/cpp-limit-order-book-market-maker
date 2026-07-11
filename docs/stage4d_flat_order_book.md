# Stage 4D Flat Order Book

Stage 4D adds `FlatOrderBook`, a fixed tick range book that uses direct price indexing instead of ordered maps for price level lookup. The public matching path is shared with the existing map book through `BasicMatchingEngine<Book>`.

## Behavioral Gate

The Stage 1 matching tests now run against both engines:

```text
lob::MatchingEngine
lob::FlatMatchingEngine
```

The local validation command was:

```bash
/tmp/lob_cmake_venv/bin/cmake --build build/stage4d --config Release --target orderbook_benchmark lob_tests
/tmp/lob_cmake_venv/bin/ctest --test-dir build/stage4d --output-on-failure
```

The result was:

```text
100% tests passed, 0 tests failed out of 48
```

The added flat range test is:

```text
flat order book rejects prices outside its configured range
```

This test proves that the flat book does not silently wrap or clamp out of range prices.

## Benchmark Reproduction

Both runs use the same synthetic event stream, seed, warmup count, measured event count, hardware, and benchmark method as Stage 2.

```bash
python3 benchmarks/run_benchmark.py --events 1000000 --warmup 20000 --seed 42 --book map --output-dir benchmarks/results/stage4d_map_book --build-dir build/stage4d --skip-build
python3 benchmarks/run_benchmark.py --events 1000000 --warmup 20000 --seed 42 --book flat --min-price 99000 --max-price 101000 --output-dir benchmarks/results/stage4d_flat_book --build-dir build/stage4d --skip-build
```

The flat range `99000` to `101000` was chosen because the Stage 2 generator anchors around `100000`, uses passive offsets up to `200` ticks, and pulls the reference back inside a `250` tick band. The checked run reports:

```text
unsupported_flat_range_events 0
rejects 0
```

## Result

The checked comparison artifact is `benchmarks/results/stage4d_comparison/metrics_table.csv`.

```text
metric,map,flat,flat_minus_map,flat_percent_change_vs_map
events_per_second,4618931.43599,5332518.0411,713586.60511,0.15449170766
total_seconds,0.216500291,0.187528667,-0.028971624,-0.133817944845
p50_latency_ns,125,84,-41,-0.328
p95_latency_ns,500,458,-42,-0.084
p99_latency_ns,875,791,-84,-0.096
max_latency_ns,1481666,3883209,2401543,1.62083964942
trades,350663,350663,0,0
rejects,0,0,0,
unsupported_flat_range_events,0,0,0,
```

The flat book is faster on throughput and the main latency percentiles:

```text
throughput improvement 15.449170766 percent
p50 improvement 32.8 percent
p95 improvement 8.4 percent
p99 improvement 9.6 percent
```

The result is useful but not a sweeping claim that arrays always win. The flat book still stores each price level as a `PriceLevel` list, so cancellation and within level priority behavior remain the same as the map book. The main change is price level lookup and best level maintenance.

## Tail Latency Check

The maximum latency event was the same event index in both runs:

```text
event_index 559699
action limit
side buy
price 100137
quantity 23
trades 1
rested_after_event false
target_level_existed_before false
price_level_created false
out_of_order_insert false
```

Nearby samples:

```text
map 208, 167, 541, 167, 250, 1481666, 4708, 375, 5625, 1833, 166
flat 250, 167, 542, 84, 209, 3883209, 13625, 2416, 9750, 1666, 1333
```

Because the same event was the max in both runs and the event did not create a level, recreate a level, rest an order, or insert out of order, this points to host scheduling or timer interruption rather than a flat book mechanism. The flat run has the higher single max, but its p50, p95, p99, and throughput are better.

## Bounded Range Edge

The flat book has an explicit configured tick range. It rejects limit prices outside that range. The benchmark adds a preflight check for flat runs:

```text
generated event stream contains prices outside flat book range
```

The preflight runs after the synthetic stream is generated and before measured replay begins. This prevents a too narrow flat range from becoming a misleading benchmark with rejects that the map book would not have.

A deliberate narrow range check used:

```bash
build/stage4d/orderbook_benchmark --events 1000 --warmup 100 --seed 42 --book flat --min-price 99990 --max-price 100010 --output-dir /tmp/stage4d_narrow_range_check
```

It failed before replay with:

```text
generated event stream contains prices outside flat book range
```

## Implementation Note

The first flat book smoke run was slower than the map book because `bid_levels()` and `ask_levels()` originally materialized vectors of active levels for self trade checks. That was an implementation artifact, not an array book property. Replacing those vectors with a lazy level iterator changed the 100000 event smoke result from slower than map to faster than map, and the full result above uses the lazy iterator.
