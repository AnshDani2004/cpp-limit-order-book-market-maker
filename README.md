[![CI](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml/badge.svg)](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml)

# C++ Limit Order Book And Market Making Simulator

This is a systems-focused market microstructure project: a deterministic C++ limit order book, benchmark harness, ITCH replay path, and market-making simulator for comparing naive symmetric quoting with Avellaneda Stoikov-style inventory-aware quoting under controlled synthetic and ITCH-calibrated flow.

## What This Project Proves

The project is built around reproducible claims. Each stage adds measured behavior, limitations, tests where possible, and checked artifacts under `benchmarks/results`. The matching engine, benchmark harness, ITCH replay path, market-making simulator, Stage 5D queue-position diagnostic, follow-up fill-rate diagnostic extension, and artifact validator are complete on `main`; the full narrative is in [docs/research_note.md](docs/research_note.md).

## Headline Results

- Deterministic C++ matching engine with price-time priority, partial fills, cancel/replace, self-trade prevention, CSV replay, and direct `external_execute` support.
- Reproducible benchmark: `1,000,000` synthetic events at `3.7M` events/sec on Apple M3, with benchmark assumptions documented.
- Nasdaq ITCH replay: `12,423` bounded QQQ messages translated and replayed, including direct named resting order execution.
- Market-making simulations: naive versus Avellaneda Stoikov with attribution, risk controls, terminal liquidation, and paired same-seed statistics.
- Main strategy finding: robust claim is selected inventory-risk and risk-adjusted improvement under hand-chosen flow, not broad PnL dominance.
- Queue diagnostics: ITCH calibrated fill-rate collapse is dominated by sparse executions; in the focused ten-seed pass, physical first-in-queue ITCH-calibrated quotes still filled only around `1.6` to `1.9` percent.

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

Fill-rate diagnostic extension and artifact validation:

```bash
python3 scripts/generate_fill_rate_diagnostics.py --quick
python3 scripts/generate_fill_rate_diagnostics.py --full
python3 scripts/validate_fill_rate_artifacts.py
```

## Documentation

- [Research note](docs/research_note.md): full stage narrative, numbers, caveats, and interpretation changes.
- [Design](docs/design.md): matching engine structure and complexity notes.
- [Edge cases](docs/edge_cases.md): explicit behavior policy for matching, modify, self trade, and replay semantics.
- [Performance](docs/performance.md): Stage 2 benchmark methodology and latency analysis.
- [Stage 5C seed statistics](docs/stage5c_seed_statistics.md): 30-seed intervals and paired same-seed delta addendum.
- [Stage 5D queue position](docs/stage5d_queue_position.md): queue-depth and sparse-execution diagnostic.
- [Fill-rate and queue diagnostics](docs/fill_rate_queue_diagnostics.md): quote lifecycle tracking, execution-opportunity audit, fill decomposition, and controlled sparse-execution versus queue-position checks.

## Fill-Rate And Queue Diagnostics

The fill-rate diagnostic extension records market-maker quote lifecycles and per-market-event execution opportunities, then decomposes fills by flow profile, queue position, quote lifetime, and strategy. It compares hand-chosen and ITCH-calibrated flow with paired naive versus Avellaneda Stoikov runs plus controls for a derived zero-initial-queue subset, a physical first-in-queue scenario, increased execution intensity, and requote frequency.

The current result is technical and limited: under the checked ten-seed diagnostic, sparse execution flow dominates the ITCH-calibrated fill-rate collapse. Physical first-in-queue placement does not materially rescue fills, while increasing execution intensity and slowing requotes move fill rates in the expected direction. The artifact validator independently checks the generated fill-rate artifacts. Stage 5C remains the stronger 30-seed strategy-comparison pass.

## Limitations

- One-instrument simulator.
- Bounded ITCH sample, not full-day market reconstruction.
- Synthetic regimes are controlled experiments, not live trading evidence.
- Stage 5D queue diagnostic is one-seed, while the follow-up fill-rate extension is a focused ten-seed mechanism pass rather than a confidence-interval strategy result.

## Repository Map

- `include/lob`: public C++ headers.
- `src`: matching engine, order book, replay, and simulation implementation.
- `simulations`: market-maker simulation driver and comparison scripts.
- `tools`: ITCH replay, calibration, diagnostics, and utility scripts.
- `benchmarks/results`: checked result artifacts used by the docs.
- `docs`: detailed design notes, edge-case policy, performance notes, and stage reports.
