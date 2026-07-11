# Stage 3 Market Maker Results

This document reports the first naive symmetric versus Avellaneda Stoikov comparison. The numbers are measured outputs from the checked CSV artifacts, not target values.

Stage 5C reran this comparison across 30 seeds per regime. The single seed tables below remain useful mechanism probes, but the PnL winner labels should now be read through the multi seed confidence intervals in `docs/stage5c_seed_statistics.md`.

## Reproduction

```bash
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy naive --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage3_naive_checkpoint --build-dir build/stage3_market_maker
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy avellaneda-stoikov --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage3_avellaneda_stoikov_checkpoint --build-dir build/stage3_market_maker
python3 simulations/compare_market_makers.py --naive-dir benchmarks/results/stage3_naive_checkpoint --as-dir benchmarks/results/stage3_avellaneda_stoikov_checkpoint --output-dir benchmarks/results/stage3_comparison
```

If CMake is already on `PATH`, omit the `CMAKE=...` prefix. The exact side by side table is checked in at `benchmarks/results/stage3_comparison/metrics_table.csv`.

## Parameter Check

The Avellaneda Stoikov reservation price uses:

```text
reservation_price = reference_mid - inventory * risk_aversion * volatility^2 * time_remaining
```

With risk aversion `0.002`, the per unit inventory coefficient before `time_remaining` is:

| Regime | Volatility | Coefficient | Skew at 20000 inventory, time 1 |
| --- | ---: | ---: | ---: |
| Low volatility | 0.40 | 0.00032 | 6.4 ticks |
| High volatility | 1.60 | 0.00512 | 102.4 ticks |
| Trending | 0.80 | 0.00128 | 25.6 ticks |

Low volatility therefore gives the model a much weaker inventory correction than high volatility: high volatility is `16x` the low volatility coefficient, and trending is `4x` the low volatility coefficient. That matches the measured pattern: low volatility inventory control is real but modest, high volatility inventory control is much stronger, and the trending regime is dominated by the interaction between drift and the full-run time horizon.

## Trending Skew Diagnostic

The trending diagnostic CSV is checked in at `benchmarks/results/stage3_avellaneda_stoikov_checkpoint/avellaneda_stoikov_trending_skew.csv`, with the corresponding plot at `benchmarks/results/stage3_avellaneda_stoikov_checkpoint/avellaneda_stoikov_trending_skew.svg`.

| Event | Time remaining | Reference mid | Inventory | Reservation skew | Reservation price |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0.999995 | 99999.8872858 | 0 | 0 | 99999.8872858 |
| 50000 | 0.749995 | 99946.0507886 | -13413 | -12.8763941568 | 99958.9271827 |
| 100000 | 0.499995 | 100295.009572 | 5125 | 3.2799672 | 100291.729604 |
| 150000 | 0.249995 | 100176.871589 | 438 | 0.1401571968 | 100176.731432 |
| 199300 | 0.003495 | 100591.970963 | 27280 | 0.122039808 | 100591.848923 |
| 199999 | 0 | 100577.319145 | 27169 | 0 | 100577.319145 |

This confirms the full-run horizon concern. The largest sampled inventory appears near the end of the run, but `time_remaining` has almost decayed to zero, so the reservation skew is only `0.122039808` ticks at event `199300` and exactly `0` at the final event. The first implementation is therefore not a late-run inventory controller in the trending regime; it is an Avellaneda Stoikov quote center with a horizon that fades out before the final inventory buildup has finished.

## Full Metrics

| Regime | Metric | Naive symmetric | Avellaneda Stoikov | AS minus naive |
| --- | --- | ---: | ---: | ---: |
| Low volatility | Fill rate | 0.4928 | 0.497845 | 0.005045 |
| Low volatility | Gross spread capture | 3202319.00596 | 3150245.96371 | -52073.04225 |
| Low volatility | Inventory PnL | 9346081.57532 | 8291611.6962 | -1054469.87912 |
| Low volatility | Adverse selection cost | 6638.69576414 | 30111.2052548 | 23472.5094907 |
| Low volatility | Fee PnL | 3942.4 | 3982.76 | 40.36 |
| Low volatility | Net PnL after fees | 12552342.9813 | 11445840.4199 | -1106502.5614 |
| Low volatility | Maximum drawdown | 7624000.24593 | 6915228.42299 | -708771.82294 |
| Low volatility | Inventory variance | 611910819.983 | 520649751.809 | -91261068.174 |
| Low volatility | Final inventory | 60352 | 53714 | -6638 |
| Low volatility | Maker fills | 21122 | 21338 | 216 |
| Low volatility | Taker fills | 0 | 0 | 0 |
| High volatility | Fill rate | 0.432215 | 0.430605 | -0.00161 |
| High volatility | Gross spread capture | 4518812.65051 | 4171313.42866 | -347499.22185 |
| High volatility | Inventory PnL | -2741095.43473 | 739413.224525 | 3480508.65925 |
| High volatility | Adverse selection cost | 238640.967874 | 519452.931372 | 280811.963498 |
| High volatility | Fee PnL | 3457.72 | 3444.84 | -12.88 |
| High volatility | Net PnL after fees | 1781174.93578 | 4914171.49318 | 3132996.5574 |
| High volatility | Maximum drawdown | 10006722.7148 | 2251840.94166 | -7754881.77314 |
| High volatility | Inventory variance | 38674268.7726 | 18918445.1248 | -19755823.6478 |
| High volatility | Final inventory | 10270 | 1178 | -9092 |
| High volatility | Maker fills | 18538 | 18542 | 4 |
| High volatility | Taker fills | 0 | 0 | 0 |
| Trending | Fill rate | 0.458575 | 0.4644075 | 0.0058325 |
| Trending | Gross spread capture | 4957012.08171 | 4850955.92167 | -106056.16004 |
| Trending | Inventory PnL | -4241167.91133 | 525438.932106 | 4766606.84344 |
| Trending | Adverse selection cost | 69423.9757008 | 167077.049366 | 97653.0736652 |
| Trending | Fee PnL | 3668.6 | 3715.26 | 46.66 |
| Trending | Net PnL after fees | 719512.770379 | 5380110.11378 | 4660597.3434 |
| Trending | Maximum drawdown | 5188268.62244 | 2984356.4211 | -2203912.20134 |
| Trending | Inventory variance | 112831901.12 | 114699721.514 | 1867820.394 |
| Trending | Final inventory | 22260 | 27169 | 4909 |
| Trending | Maker fills | 19590 | 19886 | 296 |
| Trending | Taker fills | 0 | 0 | 0 |

## Avellaneda Stoikov Adverse Selection Split

AS adverse selection cost is higher than naive in every regime. To check whether this is an inventory control tradeoff rather than an unexplained artifact, AS maker fills are split by inventory effect at the fill:

```text
inventory_reducing: buy when inventory is negative, or sell when inventory is positive
inventory_increasing: buy when inventory is positive, or sell when inventory is negative
neutral: zero inventory or effectively zero reservation skew
```

The split uses the same 50 event markout horizon as the aggregate metrics. `Avg markout/unit` is signed and quantity weighted. `Adverse cost` is the negative markout tail only, matching the aggregate `adverse_selection_cost` definition.

| Regime | Group | Fills | Quantity | Avg markout/unit | Adverse cost | Share of AS adverse cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Low volatility | inventory_reducing | 7799 | 72962 | 3.62416807666 | 28497.5100367 | 94.6408813449% |
| Low volatility | inventory_increasing | 13534 | 126132 | 22.9485701344 | 1613.69521808 | 5.3591186551% |
| Low volatility | neutral | 5 | 44 | 5.11935811014 | 0 | 0% |
| High volatility | inventory_reducing | 9211 | 85614 | 12.7003031189 | 461292.521762 | 88.8035265377% |
| High volatility | inventory_increasing | 9326 | 86578 | 35.6248298329 | 58048.2375237 | 11.1748791888% |
| High volatility | neutral | 5 | 50 | 1.09920956747 | 112.172086694 | 0.0215942734981% |
| Trending | inventory_reducing | 8513 | 79520 | 14.4646712551 | 145926.202713 | 87.3406630454% |
| Trending | inventory_increasing | 11359 | 106112 | 35.0129500014 | 21081.7906192 | 12.6180051056% |
| Trending | neutral | 14 | 131 | 4.48534157291 | 69.0560338045 | 0.0413318490281% |

The split reconciles to the aggregate AS adverse selection costs in the metrics table: `30111.2052548` low volatility, `519452.931372` high volatility, and `167077.049366` trending. The checked artifact is `benchmarks/results/stage3_comparison/avellaneda_stoikov_adverse_selection_split.csv`.

This confirms the mechanism. AS pays most of its adverse selection cost on the side it is using to reduce inventory: `94.6%` in low volatility, `88.8%` in high volatility, and `87.3%` in trending. These fills still have positive signed average markout because many spread-capture fills remain profitable over the 50 event horizon, but the negative markout tail is concentrated in the inventory-reducing bucket. The strategy is trading inventory risk for adverse selection risk.

## Interpretation

Low volatility is not a flagship win for the inventory aware strategy. AS reduced final inventory from `60352` to `53714`, an `11.0%` reduction, and reduced inventory variance by `14.9%`, but net PnL fell by `1106502.5614` ticks. The weak inventory response is consistent with the low volatility coefficient of `0.00032`; the model is intentionally receiving little volatility signal to react to.

High volatility is the cleanest inventory control result. AS reduced final inventory from `10270` to `1178`, an `88.5%` reduction, and reduced inventory variance by `51.1%`. It also reduced maximum drawdown by `7754881.77314` ticks. AS captured less spread and had higher adverse selection cost, and the fill split shows that adverse selection cost came mostly from inventory-reducing fills. The inventory PnL improvement was large enough to raise net PnL anyway.

Trending is not an inventory control win. AS ended with higher final inventory (`27169` versus `22260`) and slightly higher inventory variance (`114699721.514` versus `112831901.12`). Its net PnL was higher because inventory PnL was better on this specific path, not because it carried less inventory. The skew diagnostic above shows why: the full-run horizon makes the reservation skew fade toward zero late in the run.

The large PnL numbers are a property of this toy environment allowing very large unhedged positions, not proof of deployable market making skill. In low volatility, both strategies earn most of their net PnL from inventory exposure rather than spread capture. In high volatility and trending, the spread and inventory components can offset each other by millions of ticks. Resume or README claims should therefore cite the attribution table and risk metrics, not net PnL alone.

## Stage 5C Statistical Update

The Stage 5C 30 seed pass narrows the conclusions above. In hand chosen high volatility, AS still has separated confidence intervals for risk adjusted PnL and inventory variance, so the risk control finding survives. In hand chosen trending, the single seed inventory result reverses across seeds: AS lowers final inventory and inventory variance with separated intervals, while net PnL and risk adjusted PnL intervals overlap. Under the ITCH calibrated flow, no AS versus naive winner claim separates for the displayed key metrics. See `benchmarks/results/stage5c_seed_statistics/aggregate_metrics.csv` and `docs/stage5c_seed_statistics.md`.
