[![CI](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml/badge.svg)](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml)

# C++ Limit Order Book And Market Making Simulator

This is a systems-focused market microstructure project: a deterministic C++ limit order book, benchmark harness, ITCH replay path, and market-making simulator for comparing naive symmetric quoting with Avellaneda Stoikov-style inventory-aware quoting under controlled synthetic and ITCH-calibrated flow.

## What This Project Proves

The project is built around reproducible claims. Each stage adds measured behavior, limitations, tests where possible, and checked artifacts under `benchmarks/results`. Stage 1 through Stage 5D are complete on `main`; the full narrative is in [docs/research_note.md](docs/research_note.md).

## Headline Results

- Deterministic C++ matching engine with price-time priority, partial fills, cancel/replace, self-trade prevention, CSV replay, and direct `external_execute` support.
- Reproducible benchmark: `1,000,000` synthetic events at `3.7M` events/sec on Apple M3, with benchmark assumptions documented.
- Nasdaq ITCH replay: `12,423` bounded QQQ messages translated and replayed, including direct named resting order execution.
- Market-making simulations: naive versus Avellaneda Stoikov with attribution, risk controls, terminal liquidation, and paired same-seed statistics.
- Main strategy finding: robust claim is selected inventory-risk and risk-adjusted improvement under hand-chosen flow, not broad PnL dominance.
- Queue diagnostic: ITCH calibrated fill-rate collapse is dominated by sparse executions; even zero-queue calibrated quotes filled around `1.8` to `2.0` percent versus roughly `72` to `74` percent for hand-chosen zero-queue quotes.

## How To Build And Test

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build --output-on-failure
```

## How To Reproduce The Major Results

Stage 2 benchmark:

```bash
python3 benchmarks/run_benchmark.py --events 1000000 --warmup 20000 --seed 42 --output-dir benchmarks/results/stage2_local --build-dir build/stage2_benchmark
```

Stage 3 and Stage 4C market-maker comparisons:

```bash
python3 simulations/run_market_maker.py --strategy naive --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage3_naive_checkpoint --build-dir build/stage3_market_maker
python3 simulations/run_market_maker.py --strategy avellaneda-stoikov --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage3_avellaneda_stoikov_checkpoint --build-dir build/stage3_market_maker
```

Stage 4A ITCH replay:

```bash
python3 tools/itch_replay.py --symbol QQQ --range-bytes 33554432 --output-dir benchmarks/results/stage4a_itch_replay --build-dir build/stage4a_itch_replay
```

Stage 5C paired statistics and Stage 5D queue diagnostics are checked in as reproducible artifacts; see the linked docs for exact commands, tables, and caveats.

## Documentation

- [Research note](docs/research_note.md): full stage narrative, numbers, caveats, and interpretation changes.
- [Design](docs/design.md): matching engine structure and complexity notes.
- [Edge cases](docs/edge_cases.md): explicit behavior policy for matching, modify, self trade, and replay semantics.
- [Performance](docs/performance.md): Stage 2 benchmark methodology and latency analysis.
- [Stage 5C seed statistics](docs/stage5c_seed_statistics.md): 30-seed intervals and paired same-seed delta addendum.
- [Stage 5D queue position](docs/stage5d_queue_position.md): queue-depth and sparse-execution diagnostic.

## Limitations

- One-instrument simulator.
- Bounded ITCH sample, not full-day market reconstruction.
- Synthetic regimes are controlled experiments, not live trading evidence.
- Stage 5D queue diagnostic is one-seed, not a confidence-interval result.

## Repository Map

- `include/lob`: public C++ headers.
- `src`: matching engine, order book, replay, and simulation implementation.
- `simulations`: market-maker simulation driver and comparison scripts.
- `tools`: ITCH replay, calibration, diagnostics, and utility scripts.
- `benchmarks/results`: checked result artifacts used by the docs.
- `docs`: detailed design notes, edge-case policy, performance notes, and stage reports.
