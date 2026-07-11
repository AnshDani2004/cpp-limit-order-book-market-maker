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

## One Million Event Result

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

In this paired run, the flat book is faster on throughput and the main latency percentiles:

```text
throughput improvement 15.449170766 percent
p50 improvement 32.8 percent
p95 improvement 8.4 percent
p99 improvement 9.6 percent
```

The result is useful but not a sweeping claim that arrays always win. The flat book still stores each price level as a `PriceLevel` list, so cancellation and within level priority behavior remain the same as the map book. The main change is price level lookup and best level maintenance.

## Map Baseline Reconciliation

The Stage 4D map run should not be read as a silent replacement for the Stage 2 map benchmark. The Stage 2 checked result reports `3,723,011.65582` events per second, while the Stage 4D paired map run reports `4,618,931.43599` events per second. The event stream itself did not change: seed, warmup, measured event count, event mix, trade count, and reject count match.

The lazy `bid_levels()` and `ask_levels()` iterator change is flat book only. `OrderBook::bid_levels()` and `OrderBook::ask_levels()` still return references to the map containers. The shared change is that `MatchingEngine` became `BasicMatchingEngine<Book>` in a header so the same matching path can compile for both books. That changes the compiler boundary for the map book, but rerunning the old Stage 2 commit and current code on the same machine shows overlapping throughput ranges rather than a clean 24 percent code speedup.

Current code, one million event map reruns:

```text
4220681.13242 eps, max event 512822, p99 1000 ns
3963030.20693 eps, max event 559699, p99 1125 ns
4637882.80650 eps, max event 559699, p99 916 ns
4321395.11920 eps, max event 512822, p99 1000 ns
3927907.83940 eps, max event 559699, p99 1041 ns
```

Old Stage 2 commit `e8da074`, rerun on the same machine:

```text
4090497.47902 eps, p99 1083 ns
4088684.93365 eps, p99 1083 ns
3077933.27356 eps, p99 1208 ns
4218342.82512 eps, p99 958 ns
```

The max latency event index also moved between `512822` and `559699` under identical current map inputs, so the max sample is not stable enough to identify a unique slow event across runs. The two candidate events were both diagnosed as non allocating, non out of order cases.

A longer five million event diagnostic using the same current binary gave:

```text
map  3265328.77983 eps, p99 1209 ns, max event 3056481
flat 3202855.57994 eps, p99 1250 ns, max event 3056481
```

That longer run does not reproduce the one million event flat throughput advantage. The Stage 4D performance conclusion is therefore narrower: the flat book is behaviorally equivalent under the Stage 1 suite, rejects unsupported ranges explicitly, and can outperform the map book on the one million event Stage 2 stream, but the measured speedup is run length and host noise sensitive. The checked `15.449170766` percent improvement is the result of one paired artifact, not a stable universal speedup estimate.

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
