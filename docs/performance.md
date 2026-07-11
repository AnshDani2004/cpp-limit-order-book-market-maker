# Performance

## Benchmark Scope

Stage 2 measures the matching engine with a deterministic synthetic order stream. The benchmark excludes CSV parsing, synthetic event generation, and plot generation. It measures calls into `MatchingEngine` after a deterministic warmup has populated the book.

The result is a single process benchmark. It is not a claim about colocated production trading infrastructure.

## Reproduction Command

```bash
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 benchmarks/run_benchmark.py --events 1000000 --warmup 20000 --seed 42 --output-dir benchmarks/results/stage2_local --build-dir build/stage2_benchmark
```

If CMake is on `PATH`, run the same command without the `CMAKE=...` prefix.

## Synthetic Flow Assumptions

The event mix is an explicit assumption for this benchmark:

```text
limit 60 percent
market 10 percent
cancel 20 percent
modify 10 percent
```

The measured run used seed 42, 20,000 warmup events, and 1,000,000 measured events. The realized measured mix was:

```text
limit 599,535 events, 59.9535 percent
market 100,566 events, 10.0566 percent
cancel 199,619 events, 19.9619 percent
modify 100,280 events, 10.0280 percent
```

The generator keeps a reference price near 100,000 integer ticks with a small random walk and a weak pull back toward the anchor. Passive limit orders are placed 5 to 200 ticks away from the reference price. Order quantities are uniformly sampled from 1 to 100. Cancels and modifies select active resting orders from the synthetic book state. Market orders choose side randomly and walk available depth.

This is not calibrated to real exchange data. It is a deterministic stress stream intended to exercise limit, market, cancel, and modify paths under a repeatable mix.

## Measurement Method

The benchmark first generates the complete synthetic event stream with an internal engine so cancels and modifies target active orders. It then replays the same stream into a fresh engine.

Warmup events are applied before measurement. For measured events, the benchmark records one latency sample around the matching engine call for each event. Throughput is computed from wall time around the full measured replay loop. Latency percentiles are computed from the per event samples.

## Result

```text
processed 1,000,000 synthetic order events at 3,723,012 events per second
total measured time 0.26859975 seconds
p50 latency 125 ns
p95 latency 667 ns
p99 latency 1208 ns
max latency 2222959 ns
max event index 512822
trades 350,663
rejects 0
```

![Latency CDF](../benchmarks/results/stage2_local/latency_cdf.svg)

Raw result files are in [benchmarks/results/stage2_local](../benchmarks/results/stage2_local).

## Tail Latency Check

The max sample was event 512822, a buy limit order at price 99942 with quantity 36. The diagnostic replay shows that it rested in an existing level with depth 2, created no price level, recreated no price level, produced no trades, and did not perform an out of order insertion. The nearby samples were 292, 125, 83, 125, 125, 1416, 334, 541, 167, and 250 ns, so this run points to host scheduling or timer interruption rather than map allocation or an in level scan. The diagnostic record is in [tail_event.csv](../benchmarks/results/stage2_local/tail_event.csv).

## Hardware

```text
CPU Apple M3
logical cores 8
RAM 16 GB
OS macOS 26.5.1
compiler Apple clang 21.0.0
CMake 4.3.4
build type Release
```

## Memory Notes

On this platform, `sizeof(Order)` is 88 bytes and `sizeof(PriceLevel)` is 32 bytes.

A resting order stored in the current list based price level has a lower bound of about 104 bytes: 88 bytes for `Order` plus two list links. The active order index also stores the order ID, side, price, and list iterator in an unordered map entry, so actual memory per active resting order is higher and allocator dependent.

A price level has a lower bound of about 40 bytes for the map key and `PriceLevel` object, before tree node links and allocator bookkeeping. The current design favors clear cancellation semantics over compact memory layout.

At multi symbol scale, memory grows with active resting order count and active price level count. A production system would likely use custom allocators, tighter order records, and flatter price storage for bounded tick ranges.

## Limitations

Stage 2 only benchmarked the `std::map` price level container. Stage 4D adds the flat tick indexed comparison and reports it separately in [stage4d_flat_order_book.md](stage4d_flat_order_book.md).

The Stage 2 result is a single historical measurement, not a stable constant for the map book. During the Stage 4D baseline reconciliation, the same one million event map benchmark was rerun several times on the same machine and produced overlapping old and current ranges. Current code map reruns ranged from `3,927,907.83940` to `4,637,882.80650` events per second, while reruns of the old Stage 2 commit ranged from `3,077,933.27356` to `4,218,342.82512` events per second. The deterministic stream stayed fixed, but throughput and the max latency event moved with host timing noise. See [stage4d_flat_order_book.md](stage4d_flat_order_book.md).

The latency numbers include matching engine validation and state updates, but they do not include network I O, persistence, market data publication, risk checks, or CSV parsing.
