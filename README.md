[![CI](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml/badge.svg)](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml)

# C++ Limit Order Book And Market Making Simulator

This repository is being built as a systems focused market microstructure project. Stage 1 implements a deterministic matching engine for one instrument with price time priority, partial fills across levels, cancellation, replacement, self trade prevention, and CSV replay.

Stage 2 adds a reproducible benchmark harness for deterministic synthetic order flow. On the hardware listed below, the engine processed 1,000,000 synthetic order events at 3,723,012 events per second. This is a measured result, not a target.

Stage 3 adds naive symmetric and Avellaneda Stoikov market maker simulations with PnL attribution, reconciliation checks, and regime comparisons. The results are regime dependent: inventory aware quoting materially reduced inventory risk in the high volatility run, helped only modestly in the low volatility run, and did not reduce inventory in the trending run because the full-run time horizon decayed before the late inventory buildup. The AS runs also show a measured tradeoff: inventory-reducing fills account for most of AS adverse selection cost. See [docs/stage3_results.md](docs/stage3_results.md).

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

For `new`, provide side, order type, quantity, and price for limit orders. For `cancel`, only timestamp, action, and order ID are required. For `modify`, quantity means the desired remaining open quantity, and price may be empty to keep the current price.

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

Stage 1, Stage 2, and the first Stage 3 comparison are complete once local tests pass and CI is green on `main`.
