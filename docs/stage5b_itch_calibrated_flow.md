# Stage 5B ITCH Calibrated Synthetic Flow

Stage 5B keeps the original hand chosen synthetic generators and adds an `itch_calibrated` flow profile beside them. The calibrated profile is intentionally narrow: it uses the Stage 4A bounded QQQ replay statistics for event mix and order size distribution, while leaving the existing reference price regimes, seeds, quote offsets, and strategy parameters unchanged.

## Source Inputs

The calibrated event mix is taken from `benchmarks/results/stage4a_itch_replay/event_mix.csv`:

| Synthetic action | Stage 4A source | Count | Share |
| --- | --- | ---: | ---: |
| limit | new displayed orders | 5,910 | 47.5730499879 percent |
| market | `external_execute` events | 57 | 0.458826370442 percent |
| cancel | deletes | 5,864 | 47.2027690574 percent |
| modify | replace and partial cancel translations | 592 | 4.76535458424 percent |

The synthetic generator has no named external execution primitive, so Stage 4A `external_execute` events are mapped to synthetic market or taker flow. This preserves the measured execution scarcity without reverting to the older approximation that invented a taker order ID for ITCH replay. This is different from Stage 5A because replay data names the exact resting order that executed, while a forward generated stream has no captured exchange order reference to target. In the synthetic setting, a market event is a deliberate model of anonymous liquidity consumption, not a reconstruction of a named ITCH execution.

The calibrated quantity sampler uses the Stage 4A bucket counts from `benchmarks/results/stage4a_itch_replay/size_distribution.csv`: 45, 15, 34, 410, 5,799, and 6,120 observations in the `1_to_10`, `11_to_50`, `51_to_100`, `101_to_500`, `501_to_1000`, and `1001_plus` buckets. The `1001_plus` bucket is sampled uniformly from 1,001 to 3,000 shares because 3,000 is the maximum observed `quantity` in `benchmarks/results/stage4a_itch_replay/translated_orders.csv`.

The market maker quote size remains at the Stage 3 default of 10 units per side. It was not recalibrated with the external order size distribution, whose ITCH calibrated average external limit size is roughly 1,300 to 1,350 units in the checked runs. This means the fill rate collapse may come from both sparse execution events and deeper queue depth ahead of small market maker quotes. Stage 5D queue position tracking should separate those mechanisms directly.

Order lifetime percentiles from Stage 4A are not directly used as a survival model here. The bounded replay gives aggregate lifetimes, not a fitted per event hazard model, and the delete heavy event mix is the Stage 5B proxy for the observed cancellation pressure.

## Commands

```bash
/tmp/lob_cmake_venv/bin/cmake -S . -B build/stage5b -DCMAKE_BUILD_TYPE=Release
/tmp/lob_cmake_venv/bin/cmake --build build/stage5b --config Release --target lob_tests orderbook_benchmark market_maker_sim
/tmp/lob_cmake_venv/bin/ctest --test-dir build/stage5b --output-on-failure

CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 benchmarks/run_benchmark.py --events 1000000 --warmup 20000 --seed 42 --book map --flow-profile hand-chosen --build-dir build/stage5b --output-dir benchmarks/results/stage5b_stage2_hand_chosen --skip-build
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 benchmarks/run_benchmark.py --events 1000000 --warmup 20000 --seed 42 --book map --flow-profile itch-calibrated --build-dir build/stage5b --output-dir benchmarks/results/stage5b_stage2_itch_calibrated --skip-build

CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy naive --events 200000 --markout-horizon 50 --curve-sample-stride 100 --flow-profile hand-chosen --output-dir benchmarks/results/stage5b_hand_chosen_naive --build-dir build/stage5b --skip-build
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy avellaneda-stoikov --events 200000 --markout-horizon 50 --curve-sample-stride 100 --flow-profile hand-chosen --output-dir benchmarks/results/stage5b_hand_chosen_avellaneda_stoikov --build-dir build/stage5b --skip-build
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy naive --events 200000 --markout-horizon 50 --curve-sample-stride 100 --flow-profile itch-calibrated --output-dir benchmarks/results/stage5b_itch_calibrated_naive --build-dir build/stage5b --skip-build
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy avellaneda-stoikov --events 200000 --markout-horizon 50 --curve-sample-stride 100 --flow-profile itch-calibrated --output-dir benchmarks/results/stage5b_itch_calibrated_avellaneda_stoikov --build-dir build/stage5b --skip-build
```

## Stage 2 Benchmark Result

| Flow profile | Events per second | p50 ns | p95 ns | p99 ns | Max ns | Trades | Market events | Cancel events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hand chosen | 3,688,995.54185 | 166 | 667 | 1,167 | 2,229,667 | 350,663 | 100,566 | 199,619 |
| ITCH calibrated | 8,469,632.66144 | 84 | 166 | 250 | 968,792 | 31,066 | 4,486 | 470,520 |

The calibrated benchmark is faster because it performs far fewer executions and far more delete operations. The same seed produces roughly 100,000 market orders in the hand chosen benchmark and only 4,486 in the ITCH calibrated benchmark, matching the Stage 4A finding that the original synthetic stream overstated displayed liquidity consumption.

## Stage 3 Strategy Result

| Flow | Strategy | Regime | Fill rate | Maker fills | Final inventory | Net PnL after fees | Inventory variance | Reconciled |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| hand chosen | naive | low volatility | 0.4928 | 21,122 | 60,352 | 12,552,342.9813 | 611,910,819.983 | true |
| hand chosen | naive | high volatility | 0.432215 | 18,538 | 10,270 | 1,781,174.93578 | 38,674,268.7726 | true |
| hand chosen | naive | trending | 0.458575 | 19,590 | 22,260 | 719,512.770379 | 112,831,901.12 | true |
| hand chosen | Avellaneda Stoikov | low volatility | 0.497845 | 21,338 | 53,714 | 11,445,840.4199 | 520,649,751.809 | true |
| hand chosen | Avellaneda Stoikov | high volatility | 0.430605 | 18,542 | 1,178 | 4,914,171.49318 | 18,918,445.1248 | true |
| hand chosen | Avellaneda Stoikov | trending | 0.4644075 | 19,886 | 27,169 | 5,380,110.11378 | 114,699,721.514 | true |
| ITCH calibrated | naive | low volatility | 0.0169525 | 679 | 487 | 123,046.303144 | 51,440.4058599 | true |
| ITCH calibrated | naive | high volatility | 0.0173275 | 694 | 11 | -52,167.7134593 | 9,913.30170706 | true |
| ITCH calibrated | naive | trending | 0.0150075 | 604 | 573 | 143,013.930154 | 46,310.0277564 | true |
| ITCH calibrated | Avellaneda Stoikov | low volatility | 0.0175275 | 702 | 497 | 122,949.38329 | 48,355.5043599 | true |
| ITCH calibrated | Avellaneda Stoikov | high volatility | 0.0174775 | 700 | 11 | -53,846.5134593 | 9,122.35137203 | true |
| ITCH calibrated | Avellaneda Stoikov | trending | 0.0152325 | 613 | 583 | 143,271.921605 | 48,308.383999 | true |

The calibrated flow changes the interpretation of the Stage 3 PnL numbers materially. Under the hand chosen flow, both strategies get roughly 18,500 to 21,300 maker fills per regime; under the ITCH calibrated flow, they get roughly 600 to 702 maker fills. This is not a PnL accounting change. It is the direct result of changing only the external event generator from a 25 percent taker flow in Stage 3 to the Stage 4A execution share of 57 out of 12,423 translated events.

The Avellaneda Stoikov inventory control effect also becomes much weaker under the calibrated flow because there are fewer fills through which quote skew can actually flatten inventory. In high volatility, both strategies finish at inventory 11, and Avellaneda Stoikov slightly reduces inventory variance, 9,122.35137203 versus 9,913.30170706, but does not improve net PnL. That result is plausible for this sparse execution setting: the dominant change is fewer opportunities to trade, not a different reservation price formula.

## Reproducibility Artifacts

The compact comparison artifacts are:

```text
benchmarks/results/stage5b_flow_comparison/stage2_summary.csv
benchmarks/results/stage5b_flow_comparison/stage3_summary.csv
```

The raw run directories are:

```text
benchmarks/results/stage5b_stage2_hand_chosen
benchmarks/results/stage5b_stage2_itch_calibrated
benchmarks/results/stage5b_hand_chosen_naive
benchmarks/results/stage5b_hand_chosen_avellaneda_stoikov
benchmarks/results/stage5b_itch_calibrated_naive
benchmarks/results/stage5b_itch_calibrated_avellaneda_stoikov
benchmarks/results/stage5b_hand_chosen_stage3_comparison
benchmarks/results/stage5b_itch_calibrated_stage3_comparison
```
