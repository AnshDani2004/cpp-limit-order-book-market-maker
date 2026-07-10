# Stage 4B Calibrated Strategy Comparison

This checkpoint compares the Stage 3 naive baseline, the original hand chosen Avellaneda Stoikov strategy, and a calibrated Avellaneda Stoikov strategy that uses the Stage 4B fitted fill decay.

## Reproduction

```bash
CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_market_maker.py --strategy naive --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage4b_naive_comparison --build-dir build/stage4b_market_maker
python3 simulations/run_market_maker.py --strategy avellaneda-stoikov --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage4b_avellaneda_stoikov_comparison --build-dir build/stage4b_market_maker --skip-build
python3 simulations/run_market_maker.py --strategy avellaneda-stoikov-calibrated --events 200000 --markout-horizon 50 --curve-sample-stride 100 --output-dir benchmarks/results/stage4b_calibrated_avellaneda_stoikov_comparison --build-dir build/stage4b_market_maker --skip-build
python3 simulations/compare_market_makers.py --naive-dir benchmarks/results/stage4b_naive_comparison --as-dir benchmarks/results/stage4b_avellaneda_stoikov_comparison --calibrated-as-dir benchmarks/results/stage4b_calibrated_avellaneda_stoikov_comparison --output-dir benchmarks/results/stage4b_strategy_comparison
```

If CMake is already on `PATH`, omit the `CMAKE=...` prefix.

## Parameters

The original Avellaneda Stoikov run uses:

```text
risk_aversion 0.002
fill_decay 0.25
quote_size 10
refresh_cadence 10
```

The calibrated Avellaneda Stoikov run changes only:

```text
fill_decay 0.63274456291
fill_decay_source Stage 4B QQQ regular session exponential fit
```

The fitted decay is larger than the hand chosen value. In the AS spread formula, that lowers the spread term. At time remaining near `1`, the original full spread is about `7.97` ticks across the three regimes, while the calibrated full spread is about `3.16` ticks. The calibrated strategy therefore quotes more aggressively by construction.

## Full Attribution Table

The checked CSV artifact is `benchmarks/results/stage4b_strategy_comparison/metrics_table.csv`.

```text
regime,metric,naive,original_as,calibrated_as,calibrated_minus_original_as
low volatility,fill_rate,0.4928,0.497845,0.51504,0.017195
low volatility,gross_spread_capture,3202319.00596,3150245.96371,2864211.19289,-286034.77082
low volatility,inventory_pnl,9346081.57532,8291611.6962,8109779.52187,-181832.17433
low volatility,adverse_selection_cost,6638.69576414,30111.2052548,93693.2307408,63582.025486
low volatility,fee_pnl,3942.4,3982.76,4120.32,137.56
low volatility,net_pnl_after_fees,12552342.9813,11445840.4199,10978111.0348,-467729.3851
low volatility,maximum_drawdown,7624000.24593,6915228.42299,6901051.57384,-14176.84915
low volatility,inventory_variance,611910819.983,520649751.809,525169757.445,4520005.636
low volatility,final_inventory,60352,53714,53636,-78
low volatility,maker_fills,21122,21338,22063,725
low volatility,taker_fills,0,0,0,0
high volatility,fill_rate,0.432215,0.430605,0.448705,0.0181
high volatility,gross_spread_capture,4518812.65051,4171313.42866,4020855.62833,-150457.80033
high volatility,inventory_pnl,-2741095.43473,739413.224525,692765.359587,-46647.864938
high volatility,adverse_selection_cost,238640.967874,519452.931372,637130.917924,117677.986552
high volatility,fee_pnl,3457.72,3444.84,3589.64,144.8
high volatility,net_pnl_after_fees,1781174.93578,4914171.49318,4717210.62791,-196960.86527
high volatility,maximum_drawdown,10006722.7148,2251840.94166,2216335.69471,-35505.24695
high volatility,inventory_variance,38674268.7726,18918445.1248,18909166.3211,-9278.8037
high volatility,final_inventory,10270,1178,1056,-122
high volatility,maker_fills,18538,18542,19285,743
high volatility,taker_fills,0,0,0,0
trending,fill_rate,0.458575,0.4644075,0.48209,0.0176825
trending,gross_spread_capture,4957012.08171,4850955.92167,4635041.98283,-215913.93884
trending,inventory_pnl,-4241167.91133,525438.932106,436682.660635,-88756.271471
trending,adverse_selection_cost,69423.9757008,167077.049366,268119.118439,101042.069073
trending,fee_pnl,3668.6,3715.26,3856.72,141.46
trending,net_pnl_after_fees,719512.770379,5380110.11378,5075581.36346,-304528.75032
trending,maximum_drawdown,5188268.62244,2984356.4211,3006666.44261,22310.02151
trending,inventory_variance,112831901.12,114699721.514,112439457.561,-2260263.953
trending,final_inventory,22260,27169,26526,-643
trending,maker_fills,19590,19886,20594,708
trending,taker_fills,0,0,0,0
```

## Interpretation

The calibrated strategy does not uniformly outperform the original hand chosen AS strategy. It underperforms original AS on net PnL in every regime:

```text
low volatility calibrated minus original AS net PnL -467729.3851
high volatility calibrated minus original AS net PnL -196960.86527
trending calibrated minus original AS net PnL -304528.75032
```

The mechanism is consistent across regimes. The calibrated decay creates tighter AS quotes, which raises fill rate and maker fills. That gives slightly lower final inventory than original AS in all three regimes, and slightly lower high volatility inventory variance. The cost is lower spread capture and higher adverse selection cost:

```text
low volatility adverse selection cost rises by 63582.025486 versus original AS
high volatility adverse selection cost rises by 117677.986552 versus original AS
trending adverse selection cost rises by 101042.069073 versus original AS
```

This is not a bug in the fitted decay. It is a scope mismatch between the Stage 4B real data calibration and the Stage 3 synthetic environment. The real ITCH fit estimates how fill probability decays with distance in an observed QQQ regular session slice. Using that larger decay inside the toy AS formula tells the synthetic strategy that fills remain viable closer to the touch, so it quotes tighter. In this synthetic flow, tighter quotes buy more fills but give up too much spread and markout quality.

The calibrated run is still useful. It turns the arrival model from an arbitrary parameter into a measured input, and the result is honestly negative for net PnL versus the hand chosen value. The comparison also makes the tradeoff visible: calibrated AS is more active and slightly flatter, but pays for that with adverse selection and lower spread capture.

## Artifacts

```text
benchmarks/results/stage4b_naive_comparison
benchmarks/results/stage4b_avellaneda_stoikov_comparison
benchmarks/results/stage4b_calibrated_avellaneda_stoikov_comparison
benchmarks/results/stage4b_strategy_comparison
```
