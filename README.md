[![CI](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml/badge.svg)](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml)

# C++ Limit Order Book And Market Making Simulator

This repository is being built as a systems focused market microstructure project. Stage 1 implements a deterministic matching engine for one instrument with price time priority, partial fills across levels, cancellation, replacement, self trade prevention, and CSV replay.

No throughput, latency, or profit and loss claims are made yet. Those belong to later stages after the benchmark and strategy code exist and can be reproduced.

## What Stage 1 Proves

1. Modern C++ structure with RAII, value semantics, const correctness, and CMake.
2. A mutable order book using ordered price levels and FIFO queues.
3. Deterministic matching behavior covered by unit tests and a CSV integration test.
4. Explicit edge case policy documented in [docs/edge_cases.md](docs/edge_cases.md).

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

Stage 1 is intended to be complete when the local test suite and CI pass. Stage 2 performance numbers and Stage 3 market making results are intentionally absent until they are implemented and measured.
