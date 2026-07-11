[![CI](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml/badge.svg)](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml)

# C++ Limit Order Book And Market Making Simulator

This repository is being built as a systems focused market microstructure project. Stage 1 implements a deterministic matching engine for one instrument with price time priority, partial fills across levels, cancellation, replacement, self trade prevention, and CSV replay.

Stage 2 adds a reproducible benchmark harness for deterministic synthetic order flow. On the hardware listed below, the engine processed 1,000,000 synthetic order events at 3,723,012 events per second. This is a measured result, not a target.

Stage 3 adds naive symmetric and Avellaneda Stoikov market maker simulations with PnL attribution, reconciliation checks, and regime comparisons. Stage 5C later reruns these comparisons across 30 seeds per regime and narrows the claim: the strongest result is risk reduction in selected hand chosen flow regimes, not broad PnL dominance. The AS runs also show a measured tradeoff: inventory reducing fills account for most AS adverse selection cost. See [docs/stage3_results.md](docs/stage3_results.md) and [docs/stage5c_seed_statistics.md](docs/stage5c_seed_statistics.md).

Stage 4A replays a bounded public Nasdaq TotalView ITCH sample through the matching engine, including direct `external_execute` handling for named resting order executions. Stage 4B fits a regular session QQQ fill decay curve, validates that the decay effect is statistically robust, and compares the calibrated AS parameter against the original hand chosen AS value. The calibrated result depends on the tick to cent bridge between real QQQ data and the synthetic simulator. See [docs/stage4b_strategy_comparison.md](docs/stage4b_strategy_comparison.md).

Stage 4C adds inventory caps, soft quote skew, explicit terminal liquidation, terminal inventory penalty, and risk adjusted PnL. With a 20000 unit cap, terminal liquidation closes all controlled runs to zero final inventory. Stage 5C shows that controlled high volatility still has a separated AS inventory variance reduction, while net PnL and risk adjusted PnL intervals overlap. See [docs/stage4c_results.md](docs/stage4c_results.md).

Stage 4D adds a fixed range `FlatOrderBook` behind the same matching logic as the map book. The Stage 1 matching tests now run against both engines. On one paired one million event Stage 2 benchmark stream, the flat book processed 5,332,518 events per second versus 4,618,931 for the map book. Follow up reconciliation showed the exact speedup is run length and host noise sensitive, so this is evidence that the flat book can outperform the map book on this stream, not a universal array book speedup claim. See [docs/stage4d_flat_order_book.md](docs/stage4d_flat_order_book.md).

Stage 5A corrects ITCH execution replay semantics by using direct named order execution instead of synthetic market orders for unknown aggressors. Stage 5B adds an ITCH calibrated synthetic flow profile beside the original hand chosen flow. Under the calibrated profile, the market maker fill rate drops from roughly 43 to 50 percent to roughly 1.5 to 1.8 percent because the Stage 4A input had only 57 external executions across 12,423 translated events. See [docs/stage5b_itch_calibrated_flow.md](docs/stage5b_itch_calibrated_flow.md).

Stage 5C adds a 30 seed statistical pass for hand chosen and ITCH calibrated flow, uncontrolled and risk controlled modes. It checks both separate confidence interval overlap and paired same-seed strategy deltas. All 1,080 raw seed rows reconcile true. See [docs/stage5c_seed_statistics.md](docs/stage5c_seed_statistics.md).

## What Stage 1 Proves

1. Modern C++ structure with RAII, value semantics, const correctness, and CMake.
2. A mutable order book using ordered price levels and FIFO queues.
3. Deterministic matching behavior covered by unit tests and a CSV integration test.
4. Explicit edge case policy documented in [docs/edge_cases.md](docs/edge_cases.md).

## Stage 2 Benchmark Result

Measured command:

```bash
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 benchmarks/run_benchmark.py --events 1000000 --warmup 20000 --seed 42 --output-dir benchmarks/results/stage2_local --build-dir build/stage2_benchmark
```

If CMake is already on `PATH`, omit the `CMAKE=...` prefix.

Measured output:

```text
processed 1,000,000 synthetic order events at 3,723,012 events per second
p50 latency 125 ns
p95 latency 667 ns
p99 latency 1208 ns
max latency 2222959 ns
rejects 0
```

Hardware and toolchain:

```text
CPU Apple M3
logical cores 8
RAM 16 GB
OS macOS 26.5.1
compiler Apple clang 21.0.0
CMake 4.3.4
build type Release
```

The synthetic event mix is an explicit benchmark assumption, not a claim about any specific exchange venue:

```text
limit 599,535 events, 59.9535 percent
market 100,566 events, 10.0566 percent
cancel 199,619 events, 19.9619 percent
modify 100,280 events, 10.0280 percent
```

![Latency CDF](benchmarks/results/stage2_local/latency_cdf.svg)

See [docs/performance.md](docs/performance.md) for the benchmark method, memory notes, and limitations.

## Stage 3 Market Maker Result

Measured command:

```bash
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy naive --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage3_naive_checkpoint --build-dir build/stage3_market_maker
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy avellaneda-stoikov --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage3_avellaneda_stoikov_checkpoint --build-dir build/stage3_market_maker
python3 simulations/compare_market_makers.py --naive-dir benchmarks/results/stage3_naive_checkpoint --as-dir benchmarks/results/stage3_avellaneda_stoikov_checkpoint --output-dir benchmarks/results/stage3_comparison
```

Key inventory results:

```text
low volatility: final inventory 60352 naive, 53714 Avellaneda Stoikov
high volatility: final inventory 10270 naive, 1178 Avellaneda Stoikov
trending: final inventory 22260 naive, 27169 Avellaneda Stoikov
```

The full attribution table is checked in at `benchmarks/results/stage3_comparison/metrics_table.csv`. Net PnL is not reported as a standalone success metric because this toy environment permits large unhedged inventory exposure.

## Stage 4A ITCH Replay Result

Measured command:

```bash
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 tools/itch_replay.py --symbol QQQ --range-bytes 33554432 --output-dir benchmarks/results/stage4a_itch_replay --build-dir build/stage4a_itch_replay
```

The replay translated `12423` QQQ messages from a bounded prefix of the public Nasdaq TotalView ITCH sample file `03272019.NASDAQ_ITCH50.gz` and replayed them through the existing matching engine. The observed event mix was `47.5730499879` percent limit, `0` percent market, `0.458826370442` percent external execution, `47.2027690574` percent cancel, and `4.76535458424` percent modify.

See [docs/stage4a_replay.md](docs/stage4a_replay.md) for the source, limitations, translation rules, and comparison against the Stage 3 synthetic assumptions.

## Stage 4B Calibrated Strategy Result

The default Stage 4B calibrated AS run assumes one synthetic tick equals one real cent and uses the fitted QQQ regular session decay:

```text
fill_decay 0.63274456291
```

The original hand chosen AS value was:

```text
fill_decay 0.25
```

Measured comparison against original AS:

```text
low volatility net PnL change -467729.3851, final inventory change -78
high volatility net PnL change -196960.86527, final inventory change -122
trending net PnL change -304528.75032, final inventory change -643
```

Under that direct mapping, the calibrated strategy improves final inventory slightly in all three regimes, but it lowers spread capture and raises adverse selection cost enough to reduce net PnL.

The tick size sensitivity check changes the broader conclusion:

```text
one tick equals 5 cents: calibrated AS net PnL beats original AS in all three regimes
one tick equals 20 cents: calibrated AS loses in low and high volatility, wins in trending
```

The full attribution table is checked in at `benchmarks/results/stage4b_strategy_comparison/metrics_table.csv`, and the unit sensitivity table is checked in at `benchmarks/results/stage4b_strategy_comparison/tick_size_sensitivity.csv`.

## Stage 4C Risk Control Result

Measured comparison:

```text
low volatility risk adjusted PnL 3.79145721962 naive, 3.65709628448 Avellaneda Stoikov
high volatility risk adjusted PnL 0.448401096106 naive, 2.18741584269 Avellaneda Stoikov
trending risk adjusted PnL 0.8467416267 naive, 1.9505626349 Avellaneda Stoikov
```

The full table is checked in at `benchmarks/results/stage4c_risk_controlled_comparison/metrics_table.csv`. The terminal liquidation price level evidence is checked in at `benchmarks/results/stage4c_risk_controlled_comparison/naive_terminal_liquidation_levels.csv` and `benchmarks/results/stage4c_risk_controlled_comparison/avellaneda_stoikov_terminal_liquidation_levels.csv`.
The per trade terminal liquidation trace is checked in beside those files, and the controlled runs report `passive_taker_fills` as zero in every regime.

## Stage 4D Flat Book Result

Measured comparison:

```text
map book throughput 4618931.43599 events per second
flat book throughput 5332518.0411 events per second
flat throughput improvement 15.449170766 percent
map p99 875 ns
flat p99 791 ns
```

This is the checked paired one million event artifact. A reconciliation rerun found overlapping map throughput between the old Stage 2 commit and current code, and a five million event diagnostic gave map `3265328.77983` events per second versus flat `3202855.57994`. Treat the one million event improvement as workload and run dependent. The full comparison table is checked in at `benchmarks/results/stage4d_comparison/metrics_table.csv`, and the reconciliation table is checked in at `benchmarks/results/stage4d_comparison/baseline_reconciliation.csv`.

## Build And Test

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build --output-on-failure
```

## CSV Replay

Input CSV columns:

```text
timestamp,action,order_id,side,order_type,price,quantity,owner_id
```

For `new`, provide side, order type, quantity, and price for limit orders. For `cancel`, only timestamp, action, and order ID are required. For `modify`, quantity means the desired remaining open quantity, and price may be empty to keep the current price. For `external_execute`, provide timestamp, action, order ID, execution price, and execution quantity.

Run the sample replay:

```bash
./build/orderbook_replay data/sample_orders.csv build/sample_trades.csv
diff -u data/sample_expected_trades.csv build/sample_trades.csv
```

Output CSV columns:

```text
timestamp,buy_order_id,sell_order_id,maker_order_id,taker_order_id,price,quantity
```

## Design Summary

Prices are integer ticks. This avoids floating point rounding in matching and makes tick size validation the caller responsibility. Bids are stored in a descending `std::map`; asks are stored in an ascending `std::map`. Each price level stores a `std::list<Order>` so cancellation and modification can remove a resting order through an index without scanning the whole book.

Orders at the same price are prioritized by timestamp, then order ID. The order ID tie break makes identical timestamp handling deterministic across test runs and CSV replays.

Market orders never rest. If liquidity is insufficient, the executed part is reported and the unfilled remainder is cancelled immediately.

See [docs/design.md](docs/design.md) for the detailed design rationale.

## Current Stage Status

Stage 1, Stage 2, Stage 3, Stage 4A, Stage 4B, Stage 4C, Stage 4D, Stage 5A, Stage 5B, and Stage 5C are complete once local tests pass and CI is green on `main`.
