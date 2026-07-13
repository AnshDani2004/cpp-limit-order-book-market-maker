# Fill-Rate And Queue Diagnostics

This note documents the market maker fill-rate diagnostic extension. It is a controlled simulator diagnostic, not a profitability or production-readiness claim.

Two modes are available:

```bash
python3 scripts/generate_fill_rate_diagnostics.py --quick
python3 scripts/generate_fill_rate_diagnostics.py --full
```

`--quick` keeps the broad two-seed sweep used for fast mechanism checks. It runs `5000` events per run, `2` seeds, `3` regimes, `2` strategies, and `14` scenarios, including quote-size, risk-aversion, and inventory-cap controls.

`--full` is the checked focused pass. It runs `2500` events per run, `10` deterministic seeds, `3` regimes, `2` strategies, and these `8` scenarios:

```text
hand_chosen_flow
itch_calibrated_flow
physical_zero_queue_itch_calibrated_flow
increased_execution_intensity_2x
increased_execution_intensity_5x
increased_execution_intensity_10x
requote_frequency_fast_5
requote_frequency_slow_25
```

The full pass uses paired same-seed comparisons. The checked seeds are recorded in `artifacts/fill_diagnostics/run_config.csv`:

```text
low-volatility  3001 4001 5001 6001 7001 8001 9001 10001 11001 12001
high-volatility 3002 4002 5002 6002 7002 8002 9002 10002 11002 12002
trending        3003 4003 5003 6003 7003 8003 9003 10003 11003 12003
```

## Artifact Set

The full checked output is in `artifacts/fill_diagnostics`:

```text
quote_lifecycle.csv                 252000 rows
execution_opportunities.csv          50304 rows
fill_decomposition_by_seed.csv         540 rows
fill_decomposition_summary.csv         540 rows
strategy_comparison_by_seed.csv        480 rows
strategy_comparison_summary.csv        816 rows
statistical_summary.csv               1356 rows
paired_differences.csv                4500 rows
zero_queue_comparison.csv               60 rows
mechanism_summary.csv                   21 rows
mechanism_attribution_summary.csv        36 rows
run_config.csv                          19 rows
```

`quote_lifecycle.csv` records every market maker quote submitted by the diagnostic runs. It includes quote ID, strategy, seed, regime, flow type, scenario, side, price, size, submitted event index, first fill event if any, lifetime in events, initial displayed queue ahead, displayed depth at price, filled size, remaining size, final status, and no-fill reason.

`execution_opportunities.csv` records the book state immediately before each synthetic external market event. It captures the aggressive side, touched price, best bid/ask before the event, displayed depth at the touched level, whether a market maker quote was at that level, queue quantity ahead of the market maker, size executed before reaching the market maker, market maker fill size from the event, and the no-fill reason.

## Zero-Queue Controls

The diagnostic now separates two controls that should not be conflated.

`zero_initial_queue_subset` is a derived subset of the normal `itch_calibrated_flow` run. It keeps only quotes that happened to have zero displayed same-side queue ahead at placement. It is useful as a within-run diagnostic, but it is not a separate physical simulation.

`physical_zero_queue_itch_calibrated_flow` is a separate physical scenario. When a market maker quote would otherwise join behind same-side displayed quantity at its target price, the simulator shifts it to the nearest non-crossing empty same-side price level. If no such price can be found within the search bound, the run fails loudly. In the checked full artifact, all `30000` physical zero-queue quote rows have `initial_queue_ahead == 0`.

This scenario is intentionally artificial. It answers a narrow mechanism question: if the market maker is actually first in queue, do fills recover under sparse ITCH-calibrated executions?

## Main Fill-Rate Result

Mean quote-count fill rates in the ten-seed full pass:

| Scenario | Strategy | Low Vol | High Vol | Trending |
| --- | --- | ---: | ---: | ---: |
| hand_chosen_flow | naive | 0.7392 | 0.5964 | 0.7066 |
| hand_chosen_flow | Avellaneda Stoikov | 0.7392 | 0.6030 | 0.7106 |
| itch_calibrated_flow | naive | 0.0186 | 0.0154 | 0.0182 |
| itch_calibrated_flow | Avellaneda Stoikov | 0.0186 | 0.0160 | 0.0182 |

The hand-chosen to ITCH-calibrated mean fill-rate drops are:

```text
low volatility  -0.7206
high volatility -0.5840
trending        -0.6904
```

The confidence intervals in `mechanism_summary.csv` exclude zero for all three drops. This is the largest observed effect in the diagnostic.

## Sparse Executions Versus Queue Position

The full pass confirms the Stage 5D mechanism: sparse external execution flow dominates the calibrated fill-rate collapse, while queue position is a secondary filter in these runs.

For naive quotes, mean external execution-event counts per run are:

| Scenario | Low Vol | High Vol | Trending |
| --- | ---: | ---: | ---: |
| hand_chosen_flow | 639.7 | 604.3 | 611.5 |
| itch_calibrated_flow | 9.8 | 9.5 | 10.4 |
| increased_execution_intensity_10x | 108.8 | 101.2 | 107.4 |

The zero-queue comparison points the same way:

| Scenario | Strategy | Low Vol | High Vol | Trending |
| --- | --- | ---: | ---: | ---: |
| itch_calibrated_flow | naive | 0.0186 | 0.0154 | 0.0182 |
| zero_initial_queue_subset | naive | 0.0189 | 0.0157 | 0.0185 |
| physical_zero_queue_itch_calibrated_flow | naive | 0.0188 | 0.0162 | 0.0182 |

Physical first-in-queue placement does not materially rescue fill rates. The mean physical-zero minus normal-ITCH deltas are `0.0003`, `0.0006`, and `0.0000` in low volatility, high volatility, and trending. By contrast, moving from ITCH-calibrated flow to hand-chosen flow changes fill rate by roughly `0.58` to `0.72`.

## Execution Intensity Sweep

Increasing only the synthetic external execution intensity under ITCH-calibrated flow moves fill rates monotonically:

| Scenario | Naive Low Vol | Naive High Vol | Naive Trending |
| --- | ---: | ---: | ---: |
| itch_calibrated_flow | 0.0186 | 0.0154 | 0.0182 |
| increased_execution_intensity_2x | 0.0394 | 0.0350 | 0.0400 |
| increased_execution_intensity_5x | 0.0974 | 0.0882 | 0.0964 |
| increased_execution_intensity_10x | 0.1946 | 0.1810 | 0.1870 |

The paired mean deltas versus normal ITCH flow are positive in every regime and grow with the multiplier. This is the cleanest direct mechanism control in the extension.

## Quote Lifetime

Changing requote cadence also has the expected direction. Slower replacement gives sparse external executions more time to arrive:

| Scenario | Naive Low Vol | Naive High Vol | Naive Trending |
| --- | ---: | ---: | ---: |
| requote_frequency_fast_5 | 0.0094 | 0.0080 | 0.0092 |
| itch_calibrated_flow, cadence 10 | 0.0186 | 0.0154 | 0.0182 |
| requote_frequency_slow_25 | 0.0465 | 0.0435 | 0.0455 |

The slow-cadence paired mean deltas versus normal ITCH flow are about `0.0282`, `0.0286`, and `0.0273` in low volatility, high volatility, and trending.

## Strategy Comparison

The diagnostic does not show broad Avellaneda Stoikov dominance. Strategy effects are much smaller than flow-profile effects.

Across all full-pass hand-chosen rows, Avellaneda Stoikov minus naive has:

```text
mean net_pnl_after_fees delta    -1363.29
mean risk_adjusted_pnl delta        -2.10
mean inventory_variance delta     -520.08
mean fill_rate delta                 0.00332
```

Across all full-pass ITCH-calibrated baseline rows, Avellaneda Stoikov minus naive has:

```text
mean net_pnl_after_fees delta      -13.93
mean risk_adjusted_pnl delta        -0.06
mean inventory_variance delta       -1.59
mean fill_rate delta                 0.00020
```

These are mechanism-diagnostic numbers over `2500` event runs. Stage 5C remains the stronger strategy-comparison pass: it uses `30` seeds per regime and paired same-seed deltas. The fill-rate extension agrees with Stage 5C's narrowed interpretation: selected inventory-risk effects exist under some hand-chosen conditions, but ITCH-calibrated sparse flow does not support a broad AS PnL or fill-rate advantage.

## Robust Conclusions

1. ITCH-calibrated flow has far fewer external execution opportunities than hand-chosen flow.
2. Sparse execution flow remains the dominant observed fill-rate mechanism under the focused ten-seed pass.
3. Physical first-in-queue placement does not materially rescue ITCH-calibrated fill rates.
4. Increasing external execution intensity raises fill rates monotonically.
5. Slower requoting raises fill probability in sparse flow by increasing quote lifetime.
6. Naive versus Avellaneda Stoikov fill-rate differences are small relative to the flow-profile effect.

## Simulation-Design Limits

These diagnostics are still synthetic. The ITCH-calibrated flow uses a bounded QQQ sample to set event mix and size distribution, but the simulator does not reconstruct a full exchange session, participant identities, hidden liquidity, queue priority from real order entry timestamps, or venue-specific order attributes.

The physical zero-queue scenario is a controlled mechanism test, not an exchange condition. It deliberately changes quote placement to remove displayed same-price queue ahead while keeping the surrounding ITCH-calibrated flow mechanics fixed.

The full pass uses `10` seeds, not the `30` seed Stage 5C strategy pass. Its purpose is mechanism attribution, not broad strategy ranking.
