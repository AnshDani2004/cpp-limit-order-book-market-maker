# Stage 5D Queue Position Diagnostics

Stage 5D instruments market maker quote placement to separate two mechanisms behind a fill:

```text
distance from the reference mid
displayed FIFO queue depth ahead at the same price
```

The specific Stage 5B question was whether the ITCH calibrated fill-rate collapse came mainly from sparse execution events or from market maker quotes being buried behind much larger calibrated external order sizes.

## Reproduction

```bash
/tmp/lob_cmake_venv/bin/cmake -S . -B build/stage5d -DCMAKE_BUILD_TYPE=Release
/tmp/lob_cmake_venv/bin/cmake --build build/stage5d --config Release --target lob_tests market_maker_sim
/tmp/lob_cmake_venv/bin/ctest --test-dir build/stage5d --output-on-failure

python3 simulations/run_queue_position_diagnostics.py --events 200000 --build-dir build/stage5d --output-dir benchmarks/results/stage5d_queue_position --skip-build
```

The diagnostic run uses one deterministic seed per regime, matching Stage 5C seed index `0`:

```text
low volatility seed 3001
high volatility seed 3002
trending seed 3003
```

It runs uncontrolled `naive` and original `avellaneda-stoikov` strategies across `hand_chosen` and `itch_calibrated` flow profiles.

## Checked Artifacts

```text
benchmarks/results/stage5d_queue_position/quote_queue_events.csv
benchmarks/results/stage5d_queue_position/quote_fill_outcomes.csv
benchmarks/results/stage5d_queue_position/queue_position_summary.csv
benchmarks/results/stage5d_queue_position/fill_by_distance_bucket.csv
benchmarks/results/stage5d_queue_position/fill_by_queue_depth_bucket.csv
benchmarks/results/stage5d_queue_position/fill_by_distance_and_queue_bucket.csv
benchmarks/results/stage5d_queue_position/run_summaries.csv
benchmarks/results/stage5d_queue_position/run_config.csv
```

The run produced:

```text
quote_queue_events rows 480000
queue_position_summary rows 12
fill_by_distance_bucket rows 58
fill_by_queue_depth_bucket rows 60
fill_by_distance_and_queue_bucket rows 230
```

Each quote placement records event index, quote order ID, strategy, regime, risk mode, flow profile, seed, side, price, reference mid, distance from mid, quote quantity, queue orders ahead, queue quantity ahead, total same-side level quantity before quote, fill outcome, filled quantity, time to first fill, and whether the quote was canceled unfilled.

## FIFO Gate

Market maker quotes already enter the same FIFO path as external limit orders. `submit_quote` builds an ordinary `Order::limit` with owner `market_maker` and sends it through `MatchingEngine::submit_order`. The book stores it in the same `PriceLevel` `std::list<Order>` as external orders, sorted by timestamp and then order ID.

Stage 5D adds two deterministic queue priority tests, each run against both `lob::MatchingEngine` and `lob::FlatMatchingEngine`:

```text
market maker quote behind external queue waits for displayed depth ahead
market maker quote first at a price level fills before later external liquidity
```

No matching fix was needed. The existing FIFO behavior was correct; Stage 5D only adds explicit tests and diagnostics.

## Summary

The one-seed diagnostic reproduces the Stage 5B fill-rate scale:

| Flow | Strategy | Regime | Market events | Maker fills | Fill probability |
| --- | --- | --- | ---: | ---: | ---: |
| hand chosen | naive | low volatility | 50,109 | 21,122 | 0.504325 |
| hand chosen | naive | high volatility | 49,834 | 18,538 | 0.443025 |
| hand chosen | naive | trending | 49,996 | 19,590 | 0.469250 |
| hand chosen | Avellaneda Stoikov | low volatility | 50,109 | 21,338 | 0.509600 |
| hand chosen | Avellaneda Stoikov | high volatility | 49,834 | 18,542 | 0.441850 |
| hand chosen | Avellaneda Stoikov | trending | 49,996 | 19,886 | 0.475950 |
| ITCH calibrated | naive | low volatility | 913 | 679 | 0.016975 |
| ITCH calibrated | naive | high volatility | 882 | 694 | 0.017350 |
| ITCH calibrated | naive | trending | 898 | 604 | 0.015075 |
| ITCH calibrated | Avellaneda Stoikov | low volatility | 913 | 702 | 0.017550 |
| ITCH calibrated | Avellaneda Stoikov | high volatility | 882 | 700 | 0.017500 |
| ITCH calibrated | Avellaneda Stoikov | trending | 898 | 613 | 0.015300 |

The first surprise is that ITCH calibrated quotes are not generally more buried at placement:

| Flow | Strategy | Regime | Average queue quantity ahead | Zero queue share | Fill probability |
| --- | --- | --- | ---: | ---: | ---: |
| hand chosen | naive | low volatility | 968.735650 | 0.676775 | 0.504325 |
| hand chosen | naive | high volatility | 221.113425 | 0.597900 | 0.443025 |
| hand chosen | naive | trending | 546.606350 | 0.627475 | 0.469250 |
| ITCH calibrated | naive | low volatility | 335.520050 | 0.809725 | 0.016975 |
| ITCH calibrated | naive | high volatility | 137.905525 | 0.905050 | 0.017350 |
| ITCH calibrated | naive | trending | 331.441200 | 0.807300 | 0.015075 |

The calibrated external order sizes are much larger, but market maker quotes are often closer to the reference mid than the calibrated passive external order placement range. In this diagnostic they frequently join an empty same-price level. The large order size effect appears when there is queue ahead, not as a general increase in average queue depth for every quote.

## Queue Depth

Queue depth strongly affects fills within a flow. For naive hand chosen flow:

| Regime | Queue depth bucket | Quote count | Fill probability |
| --- | --- | ---: | ---: |
| low volatility | 0 | 27,071 | 0.734808 |
| low volatility | 1 to 100 | 527 | 0.518027 |
| low volatility | 101 to 500 | 131 | 0.061069 |
| low volatility | 501 to 1000 | 419 | 0 |
| low volatility | 1001 plus | 11,852 | 0 |
| high volatility | 0 | 23,916 | 0.722278 |
| high volatility | 1 to 100 | 1,858 | 0.236276 |
| high volatility | 101 to 500 | 6,473 | 0.001236 |
| high volatility | 501 to 1000 | 5,613 | 0 |
| high volatility | 1001 plus | 2,140 | 0 |
| trending | 0 | 25,099 | 0.735009 |
| trending | 1 to 100 | 698 | 0.457020 |
| trending | 101 to 500 | 1,957 | 0.001533 |
| trending | 501 to 1000 | 2,849 | 0 |
| trending | 1001 plus | 9,397 | 0 |

For naive ITCH calibrated flow, even front-of-queue quotes fill rarely:

| Regime | Queue depth bucket | Quote count | Fill probability |
| --- | --- | ---: | ---: |
| low volatility | 0 | 32,389 | 0.019760 |
| low volatility | 1 to 100 | 108 | 0.009259 |
| low volatility | 101 to 500 | 537 | 0.016760 |
| low volatility | 501 to 1000 | 2,308 | 0.009532 |
| low volatility | 1001 plus | 4,658 | 0.001503 |
| high volatility | 0 | 36,202 | 0.018507 |
| high volatility | 1 to 100 | 46 | 0 |
| high volatility | 101 to 500 | 204 | 0.019608 |
| high volatility | 501 to 1000 | 1,529 | 0.007194 |
| high volatility | 1001 plus | 2,019 | 0.004458 |
| trending | 0 | 32,292 | 0.017620 |
| trending | 1 to 100 | 120 | 0.016667 |
| trending | 101 to 500 | 450 | 0.015556 |
| trending | 501 to 1000 | 2,426 | 0.006595 |
| trending | 1001 plus | 4,712 | 0.001910 |

This is the key mechanism split. Queue depth matters, especially once queue ahead exceeds a few hundred units, but the ITCH calibrated collapse remains even when queue depth ahead is zero.

## Distance Versus Queue

Distance-only buckets are misleading in the hand chosen flow because distance and queue depth are correlated. Naive hand chosen low volatility quotes in the `0_to_5` bucket fill with probability `0.440705`, but the same flow's `40_plus` bucket fills with probability `0.730515`. That does not mean farther quotes are intrinsically better; it means many far-distance quotes are first at their price level, while close quotes often have displayed queue ahead.

Conditioning on zero queue removes most of that artifact. For naive hand chosen zero-queue quotes, fill probability is roughly flat across distance:

```text
low volatility zero queue by distance: 0.717190 to 0.740342
high volatility zero queue by distance: 0.709300 to 0.737089
trending zero queue by distance: 0.726276 to 0.743433
```

For naive ITCH calibrated zero-queue quotes, fill probability remains low across distance:

```text
low volatility zero queue by distance: 0.019325 to 0.020257 in populated buckets
high volatility zero queue by distance: 0.016645 to 0.024818 in populated buckets
trending zero queue by distance: 0.016647 to 0.032164 in populated buckets
```

The diagnostic therefore does not support a clean "distance decay after queue depth" claim inside this synthetic market maker setup. Queue position dominates the hand chosen bucket shape, and sparse executions dominate the ITCH calibrated bucket shape.

## Stage 5B Question

Stage 5B said the fill-rate collapse was mainly caused by sparse execution flow, while queue depth from larger external orders remained an open question. Stage 5D narrows that:

```text
Sparse execution is still the dominant cause.
Queue depth is a real secondary filter when a quote has depth ahead.
The calibrated flow does not bury most market maker quotes at placement; zero-queue share is higher under ITCH calibrated flow than under hand chosen flow.
```

The strongest evidence is the front-of-queue comparison. Naive hand chosen zero-queue fill probability is about `0.72` to `0.74`; naive ITCH calibrated zero-queue fill probability is about `0.018` to `0.020` in the main populated buckets. A quote at the front of the queue still needs incoming liquidity to arrive. The calibrated flow has only about `882` to `913` market events per 200,000 event run, compared with about `49,834` to `50,109` under hand chosen flow.

## Limitations

This is a one-seed diagnostic, not a 30-seed statistical pass. It is enough to answer the Stage 5B mechanism question at the checked seed, but it should not be read as a confidence interval result.

The diagnostic uses uncontrolled runs because Stage 5B's open question came from the uncontrolled flow comparison. Risk controlled queue diagnostics would be a separate extension.

Queue depth is measured at quote placement. The fill outcome captures whether the quote eventually filled, but the artifact does not reconstruct every intermediate queue depletion event ahead of the quote.

Distance buckets are simple explanatory buckets, not a fitted intensity model. Stage 4B remains the calibrated real-data distance fit; Stage 5D is a simulator queue-position diagnostic.
