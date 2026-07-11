# Stage 5C Multi Seed Statistics

Stage 5C reruns the market maker comparison across 30 seeds per regime. It covers both external flow profiles, `hand_chosen` and `itch_calibrated`, and both modes used by the prior strategy docs:

```text
uncontrolled: Stage 3 style strategy comparison
risk controlled: Stage 4C style controls, terminal liquidation, inventory cap 20000
```

The goal is to separate real strategy effects from one random path. The confidence interval is a 95 percent t interval with 29 degrees of freedom. The raw per seed rows are checked in, so the aggregate table can be audited directly.

## Reproduction

```bash
/tmp/lob_cmake_venv/bin/cmake -S . -B build/stage5c -DCMAKE_BUILD_TYPE=Release
/tmp/lob_cmake_venv/bin/cmake --build build/stage5c --config Release --target lob_tests market_maker_sim
/tmp/lob_cmake_venv/bin/ctest --test-dir build/stage5c --output-on-failure

CMAKE=/tmp/lob_cmake_venv/bin/cmake python3 simulations/run_seed_statistics.py --events 200000 --seeds 30 --build-dir build/stage5c --output-dir benchmarks/results/stage5c_seed_statistics --skip-build
```

The seed formula is:

```text
low volatility seed = 3001 + 1000 * seed_index
high volatility seed = 3002 + 1000 * seed_index
trending seed = 3003 + 1000 * seed_index
seed_index from 0 to 29
```

The run produced:

```text
raw rows 1080
combinations 36
samples per combination 30
all reconciled true
```

## Checked Artifacts

```text
benchmarks/results/stage5c_seed_statistics/raw_seed_results.csv
benchmarks/results/stage5c_seed_statistics/aggregate_metrics.csv
benchmarks/results/stage5c_seed_statistics/comparison_claims.csv
benchmarks/results/stage5c_seed_statistics/run_config.csv
```

`aggregate_metrics.csv` reports every attribution metric used by the existing comparison table. `comparison_claims.csv` checks interval overlap for net PnL after fees, risk adjusted PnL, final inventory, inventory variance, and fill rate.

## Uncontrolled Results

These are the Stage 3 style runs, with no hard cap and no terminal liquidation.

| Flow | Regime | Metric | Naive mean and interval | AS mean and interval | AS delta | Interval overlap |
| --- | --- | --- | ---: | ---: | ---: | --- |
| hand chosen | low volatility | net PnL after fees | 3,660,781 [1,071,839, 6,249,723] | 3,412,293 [995,706, 5,828,880] | -248,488 | true |
| hand chosen | low volatility | risk adjusted PnL | 0.742493 [0.302412, 1.182574] | 0.758945 [0.315041, 1.202849] | 0.016451 | true |
| hand chosen | low volatility | inventory variance | 285,753,834 [198,238,017, 373,269,650] | 244,097,024 [169,436,979, 318,757,069] | -41,656,810 | true |
| hand chosen | high volatility | net PnL after fees | 3,861,929 [149,825, 7,574,034] | 4,734,521 [2,912,948, 6,556,094] | 872,592 | true |
| hand chosen | high volatility | risk adjusted PnL | 0.424649 [0.072012, 0.777287] | 1.482493 [0.944004, 2.020981] | 1.057843 | false |
| hand chosen | high volatility | inventory variance | 74,175,077 [45,925,738, 102,424,417] | 25,805,891 [20,592,320, 31,019,462] | -48,369,187 | false |
| hand chosen | trending | net PnL after fees | 19,373,317 [12,129,417, 26,617,217] | 13,573,359 [9,004,751, 18,141,966] | -5,799,958 | true |
| hand chosen | trending | risk adjusted PnL | 2.110486 [1.331857, 2.889114] | 2.374185 [1.599050, 3.149321] | 0.263700 | true |
| hand chosen | trending | final inventory | 46,289.7 [37,438.4, 55,141.0] | 30,087.2 [23,752.7, 36,421.6] | -16,202.5 | false |
| hand chosen | trending | inventory variance | 316,028,401 [234,025,421, 398,031,381] | 146,170,031 [115,820,611, 176,519,451] | -169,858,370 | false |
| ITCH calibrated | low volatility | net PnL after fees | 49,573.5 [28,108.6, 71,038.4] | 47,327.0 [26,614.8, 68,039.1] | -2,246.5 | true |
| ITCH calibrated | high volatility | net PnL after fees | 32,924.8 [-17,988.3, 83,837.8] | 30,968.5 [-11,238.8, 73,175.8] | -1,956.3 | true |
| ITCH calibrated | trending | net PnL after fees | 144,782.3 [75,598.8, 213,965.9] | 133,658.2 [69,138.1, 198,178.2] | -11,124.1 | true |
| ITCH calibrated | trending | inventory variance | 22,596.7 [14,071.4, 31,122.0] | 21,084.1 [13,419.1, 28,749.0] | -1,512.6 | true |

The hand chosen high volatility result remains the cleanest AS result. Net PnL does not separate, but risk adjusted PnL and inventory variance do separate. The old single seed statement that AS wins high volatility by net PnL should be narrowed to a risk result: AS lowers inventory variance and improves risk adjusted PnL under the hand chosen high volatility flow.

The hand chosen trending result changes materially. The old single seed run said trending was not an inventory control win because final inventory and inventory variance were worse for AS on that path. Across 30 seeds, AS has lower final inventory and lower inventory variance, and both intervals separate. Net PnL and risk adjusted PnL do not separate.

The ITCH calibrated flow shows no clear AS advantage across the checked strategy metrics. Every AS versus naive interval in `comparison_claims.csv` overlaps for the displayed key metrics. This matches the Stage 5B mechanism: sparse execution gives the strategy too few fills for quote skew to produce a statistically clear advantage.

## Risk Controlled Results

These are the Stage 4C style runs, with hard cap, soft skew, terminal liquidation, and inventory cap 20000.

| Flow | Regime | Metric | Naive mean and interval | AS mean and interval | AS delta | Interval overlap |
| --- | --- | --- | ---: | ---: | ---: | --- |
| hand chosen | low volatility | net PnL after fees | 1,531,637 [614,776, 2,448,497] | 1,475,974 [579,965, 2,371,984] | -55,662 | true |
| hand chosen | low volatility | risk adjusted PnL | 0.698511 [0.290232, 1.106790] | 0.686745 [0.283367, 1.090122] | -0.011766 | true |
| hand chosen | low volatility | inventory variance | 69,127,036 [55,919,572, 82,334,499] | 66,347,923 [54,283,512, 78,412,335] | -2,779,112 | true |
| hand chosen | high volatility | net PnL after fees | 2,616,744 [460,785, 4,772,702] | 3,598,527 [2,002,667, 5,194,388] | 981,784 | true |
| hand chosen | high volatility | risk adjusted PnL | 0.434981 [0.097375, 0.772587] | 0.998943 [0.547342, 1.450548] | 0.563963 | true |
| hand chosen | high volatility | inventory variance | 41,075,363 [35,360,705, 46,790,021] | 24,510,297 [19,902,887, 29,117,708] | -16,565,066 | false |
| hand chosen | trending | net PnL after fees | 9,486,231 [6,880,672, 12,091,790] | 8,825,862 [6,433,926, 11,217,798] | -660,369 | true |
| hand chosen | trending | risk adjusted PnL | 2.758216 [1.844492, 3.671940] | 2.713345 [1.876445, 3.550245] | -0.044872 | true |
| hand chosen | trending | inventory variance | 56,412,079 [47,181,534, 65,642,624] | 52,082,310 [45,608,709, 58,555,910] | -4,329,769 | true |
| ITCH calibrated | low volatility | net PnL after fees | 47,039.8 [26,275.5, 67,804.2] | 44,839.9 [24,786.0, 64,893.9] | -2,199.9 | true |
| ITCH calibrated | high volatility | net PnL after fees | 29,827.0 [-20,326.1, 79,980.2] | 28,297.3 [-13,079.6, 69,674.1] | -1,529.8 | true |
| ITCH calibrated | trending | net PnL after fees | 142,082.7 [73,296.4, 210,869.0] | 131,098.8 [66,933.1, 195,264.5] | -10,983.9 | true |
| ITCH calibrated | trending | inventory variance | 22,596.8 [14,071.5, 31,122.2] | 21,084.2 [13,419.2, 28,749.2] | -1,512.7 | true |

The Stage 4C single seed ranking was too strong. Across 30 seeds, hand chosen high volatility still shows a separated inventory variance reduction, but the risk adjusted PnL intervals overlap. Low volatility and trending do not have separated winner claims by net PnL or risk adjusted PnL.

Terminal liquidation makes final inventory exactly zero in every risk controlled row, so final inventory is not a useful comparison metric in that mode. Inventory variance and drawdown carry the risk comparison instead.

## Calibrated Avellaneda Stoikov

The calibrated Avellaneda Stoikov strategy is included in `raw_seed_results.csv` and `aggregate_metrics.csv`. It does not overturn the main finding. Under hand chosen flow it generally has a higher fill rate than original AS because its fitted decay changes quoted width, but the major net PnL and risk adjusted PnL interval comparisons still overlap in the regimes where the original AS comparisons overlap. Under ITCH calibrated flow, sparse fills dominate both AS variants.

## Interpretation Update

The strongest statistically supported conclusions after Stage 5C are narrower than the single seed story:

```text
hand chosen, uncontrolled, high volatility: AS improves risk adjusted PnL and lowers inventory variance
hand chosen, uncontrolled, trending: AS lowers final inventory and inventory variance, but PnL intervals overlap
hand chosen, risk controlled, high volatility: AS lowers inventory variance, but PnL intervals overlap
ITCH calibrated, all checked modes: no AS versus naive winner claim separates by the displayed confidence intervals
```

This is a useful correction, not a failure. The earlier single seed runs were good mechanism probes, but Stage 5C shows that most PnL rankings were path dependent at this sample size. The robust claim is about risk reduction in selected hand chosen regimes, not broad PnL dominance.

