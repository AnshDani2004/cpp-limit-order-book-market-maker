[![CI](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml/badge.svg)](https://github.com/AnshDani2004/cpp-limit-order-book-market-maker/actions/workflows/ci.yml)

# C++ Limit Order Book And Market Making Simulator

This is a systems-focused market microstructure project: a deterministic C++ limit order book, benchmark harness, ITCH replay path, and market-making simulator for comparing naive symmetric quoting with Avellaneda Stoikov-style inventory-aware quoting under controlled synthetic and ITCH-calibrated flow.

## What This Project Proves

The project is built around reproducible claims. Each stage adds measured behavior, limitations, tests where possible, and checked artifacts under `benchmarks/results`. The matching engine, benchmark harness, ITCH replay path, market-making simulator, Stage 5D queue-position diagnostic, follow-up fill-rate diagnostic extension, and artifact validator are complete on `main`; the full narrative is in [docs/research_note.md](docs/research_note.md).

## Headline Results

- Deterministic, single-threaded C++20 matching engine with price-time priority, partial fills, cancel and modify (cancel/replace; a price change or size increase loses time priority), reject-incoming self-trade prevention, CSV replay, and direct `external_execute` support. Two price-level containers share one matching path: an ordered `std::map` book and a fixed tick range array book (`FlatOrderBook`); both pass the same matching test suite.
- Benchmark: `1,000,000` synthetic events (seed 42, 20,000 warmup events, map book) at `3,723,012` events/sec, p50 `125` ns, p99 `1,208` ns on an Apple M3 (`benchmarks/results/stage2_local/summary.csv`). The timed loop covers the matching engine call only: the event stream is generated before timing, and there is no I/O. Throughput is noise sensitive: same-machine reruns in the repo span `3.08M` to `4.64M` events/sec ([Stage 4D reconciliation](docs/stage4d_flat_order_book.md#map-baseline-reconciliation)), and the 2026-10-12 audit rerun on the same M3 model, with other jobs loading the machine, gave `1.44M` to `3.61M` events/sec (median `3.14M`), p50 `167` to `292` ns and p99 `1,084` to `2,583` ns over 15 map-book runs ([runs.txt](benchmarks/results/audit_2026-10-12_apple_m3/runs.txt), [runs.csv](benchmarks/results/audit_2026-10-12_apple_m3/runs.csv)). A low-load rerun the same day (no other benchmark or test jobs; load average 2.2 to 2.3) gave `4.63M` to `5.01M` events/sec (median `4.91M`), p50 `125` ns and p99 `750` to `958` ns over 5 map-book runs ([lowload_rerun](benchmarks/results/audit_2026-10-12_apple_m3/lowload_rerun/README.md)), so the `3.7M` figure is conservative. Per-event latencies are quantized by the macOS timer (about `41.7` ns per tick), so `125` ns is three ticks.
- Nasdaq ITCH replay: `12,423` bounded QQQ messages translated and replayed, including direct named resting order execution.
- Market-making simulations: naive versus Avellaneda Stoikov with attribution, risk controls, terminal liquidation, and paired same-seed statistics. Stage 5C runs `1,080` simulations (`30` seeds for each of `36` combinations: 3 strategies, 3 regimes, 2 flow profiles, 2 risk modes).
- Main strategy finding: robust claim is selected inventory-risk and risk-adjusted improvement under hand-chosen flow, not broad PnL dominance. Under hand-chosen high-volatility flow (uncontrolled), the paired Avellaneda Stoikov minus naive delta is `+1.06` risk-adjusted PnL (95 percent paired interval `[0.62, 1.50]`) and `-48.4M` inventory variance (`[-75.1M, -21.6M]`); net PnL does not separate. Under ITCH-calibrated flow there is no risk-adjusted PnL gain in any regime, though small inventory-variance reductions separate in high volatility and trending ([Stage 5C](docs/stage5c_seed_statistics.md)). "Risk-adjusted PnL" here is net PnL after fees, less any terminal inventory penalty, divided by maximum drawdown.
- Adverse selection: in the single-seed Stage 3 hand-chosen runs, inventory-reducing fills account for `87.3` to `94.6` percent of Avellaneda Stoikov's own adverse-selection cost (50-event markout against the reference mid), and AS adverse-selection cost is higher than naive in every regime (`benchmarks/results/stage3_comparison/avellaneda_stoikov_adverse_selection_split.csv`).
- Queue diagnostics: in the focused ten-seed, `2,500`-event pass, quote fill rates fall from `0.60` to `0.74` under hand-chosen flow to `0.015` to `0.019` under ITCH-calibrated flow. The collapse is dominated by sparse executions (about `10` external executions per run versus about `600`); physical first-in-queue ITCH-calibrated quotes still filled only around `1.6` to `1.9` percent.

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

The Nasdaq ITCH sample is not stored in this repository, and neither are the order-level files rebuilt
from it (`translated_orders.csv`, `translation_detail.csv`, `trades.csv`, `book_state.csv` in
`stage4a_itch_replay/` and `stage5a_itch_market_mode/`). `tools/fetch_itch_sample.sh` downloads the first
33,554,432 bytes of Nasdaq's public sample file `03272019.NASDAQ_ITCH50.gz`, checks its SHA-256, regenerates
those files in both execution modes and checks them against `benchmarks/results/itch_order_level_files.sha256`.
The derived results (summary, event-mix, size, lifetime and message-support tables, and everything in
Stage 5B onward) stay in the repository.

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
- Bounded ITCH sample, not full-day market reconstruction. "ITCH-calibrated" flow takes only the event mix and order-size distribution from `12,423` QQQ messages in a prefix of one public sample day (`57` executions); prices, regimes, and queue dynamics remain synthetic. There is no real queue-position or order-level fill data in this repo.
- Synthetic regimes are controlled experiments, not live trading evidence. Adverse selection is measured against the simulator's latent reference mid, which is not observable in real markets.
- The market-maker quote size (`10`) was not recalibrated to the ITCH order sizes (average external limit size roughly `1,300` units), so calibrated-flow fill rates also reflect deep queues ahead of small quotes.
- The `87.3` to `94.6` percent adverse-selection split comes from one seed per regime (Stage 3), not from the 30-seed Stage 5C pass. It is the share of Avellaneda Stoikov's own adverse-selection cost; naive quotes have no skew, so their fills are all classified as neutral and there is no like-for-like split of the AS minus naive difference.
- Stage 5D queue diagnostic is one-seed, while the follow-up fill-rate extension is a focused ten-seed mechanism pass rather than a confidence-interval strategy result.
- Performance numbers come from one laptop (Apple M3, macOS, Apple clang, `-O3`), one thread, and one synthetic event mix. They exclude network I/O, persistence, market data publication, and risk checks, and they vary run to run with host load. Per-event latency samples include one timer read and are quantized at about `41.7` ns. The flat book's speedup over the map book appeared in a one million event paired run but not in a five million event run, so it is not a stable estimate.
- The hot path still allocates (a `std::vector<Trade>` per order, `std::list` nodes per resting order, hash-map order index); it is not a lock-free or allocation-free production design.

## Repository Map

- `include/lob`: public C++ headers.
- `src`: matching engine, order book, replay, and simulation implementation.
- `simulations`: market-maker simulation driver and comparison scripts.
- `tools`: ITCH replay, calibration, diagnostics, and utility scripts.
- `benchmarks/results`: checked result artifacts used by the docs.
- `docs`: detailed design notes, edge-case policy, performance notes, and stage reports.
