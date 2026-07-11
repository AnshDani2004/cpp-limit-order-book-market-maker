# Stage 4C Risk Control Results

Stage 4C adds hard inventory caps, soft quote skew, explicit terminal liquidation, terminal inventory penalty, and risk adjusted PnL. The controls are applied to both naive symmetric and Avellaneda Stoikov so the comparison uses the same risk machinery for both strategies.

Stage 5C reran the controlled comparison across 30 seeds per regime. The single seed production table below remains the mechanics checkpoint, but the winner labels in this document are now narrowed by the confidence interval results in `docs/stage5c_seed_statistics.md`.

## Reproduction

```bash
python3 simulations/run_market_maker.py --strategy naive --events 200000 --markout-horizon 50 --curve-sample-stride 100 --risk-controls --terminal-liquidation --inventory-cap 20000 --output-dir benchmarks/results/stage4c_naive_risk_controlled --build-dir build/stage4c --skip-build
python3 simulations/run_market_maker.py --strategy avellaneda-stoikov --events 200000 --markout-horizon 50 --curve-sample-stride 100 --risk-controls --terminal-liquidation --inventory-cap 20000 --output-dir benchmarks/results/stage4c_avellaneda_stoikov_risk_controlled --build-dir build/stage4c --skip-build
python3 simulations/compare_market_makers.py --naive-dir benchmarks/results/stage4c_naive_risk_controlled --as-dir benchmarks/results/stage4c_avellaneda_stoikov_risk_controlled --output-dir benchmarks/results/stage4c_risk_controlled_comparison
```

The local validation command was:

```bash
/tmp/lob_cmake_venv/bin/cmake --build build/stage4c --config Release --target lob_tests market_maker_sim
/tmp/lob_cmake_venv/bin/ctest --test-dir build/stage4c --output-on-failure
```

The result was:

```text
100% tests passed, 0 tests failed out of 33
```

## Parameters

```text
inventory_cap 20000 units
soft_start_fraction 0.50
soft_penalty_max_skew_ticks 20
terminal_liquidation true
terminal_inventory_penalty_per_unit 0.50 ticks
risk_adjusted_pnl (net_pnl_after_fees - terminal_inventory_penalty) / max(maximum_drawdown, 1)
```

## Liquidation Ladder Sanity Check

The first 5000 event smoke run used a smaller cap of `500` only to force the mechanics to activate quickly. The large per unit liquidation costs in that smoke run came from the terminal book, not from overfilling or walking beyond the required depth. Each liquidation order stopped part way through its last displayed level.

```text
regime,pre_inventory,quantity,liquidation_cost,per_unit_cost,levels_walked
low volatility,-265,265,7325.41395295,27.6430715206,4
high volatility,51,51,-2554.14893372,-50.0813516416,2
trending,445,445,11963.7550603,26.8848428321,7
```

The level detail was:

```text
regime,price,displayed_quantity_before,filled_quantity,liquidation_cost
low volatility,100045,13,13,302.258042975
low volatility,100048,21,21,551.262992498
low volatility,100049,54,54,1471.53340928
low volatility,100050,215,177,5000.3595082
high volatility,99917,11,11,-559.522319038
high volatility,99916,152,40,-1994.62661468
trending,100117,52,52,683.683737383
trending,100111,108,108,2067.95853149
trending,100100,51,51,1537.5359732
trending,100099,27,27,840.989632872
trending,100098,93,93,2989.74206878
trending,100097,49,49,1624.24044484
trending,100096,93,65,2219.60467173
```

This confirms that the smoke slippage is a small sample terminal book artifact. The production runs below use the stated `200000` events and `20000` unit cap.

## Production Results

Checked artifacts:

```text
benchmarks/results/stage4c_naive_risk_controlled
benchmarks/results/stage4c_avellaneda_stoikov_risk_controlled
benchmarks/results/stage4c_risk_controlled_comparison
```

Key controlled metrics:

```text
strategy,regime,net_pnl_after_fees,risk_adjusted_pnl,pre_liquidation_inventory,terminal_liquidation_quantity,terminal_liquidation_cost,liquidation_cost_per_unit,terminal_inventory_penalty,maximum_drawdown,hard_cap_bid_blocks,hard_cap_ask_blocks,passive_taker_fills,terminal_liquidation_trades,reconciliation
naive,low volatility,6648070.36,3.79145721962,7452,7452,135105.605311,18.1301134341,3726,1752451.35976,5008,0,0,144,true
naive,high volatility,3162630.12,0.448401096106,6076,6076,-13896.736214,-2.28715210895,3038,7046352.35604,0,0,0,130,true
naive,trending,3266771.32,0.8467416267,17386,17386,523350.657063,30.1018438435,8693,3847783.33468,0,0,0,324,true
avellaneda stoikov,low volatility,6440295.44,3.65709628448,7416,7416,134138.476783,18.0877126191,3708,1760026.79156,4470,0,0,145,true
avellaneda stoikov,high volatility,4923699.5,2.18741584269,1179,1179,-9310.01349511,-7.89653392291,589.5,2250651.15829,0,0,0,28,true
avellaneda stoikov,trending,5156102.14,1.9505626349,17311,17311,519931.721179,30.0347594696,8655.5,2638954.80611,0,0,0,322,true
```

The new `taker_fills` count in Stage 4C is entirely terminal liquidation. Ordinary quote submission remains passive:

```text
strategy,regime,taker_fills,passive_taker_fills,terminal_liquidation_trades
naive,low volatility,144,0,144
naive,high volatility,130,0,130
naive,trending,324,0,324
avellaneda stoikov,low volatility,145,0,145
avellaneda stoikov,high volatility,28,0,28
avellaneda stoikov,trending,322,0,322
```

The terminal liquidation trace confirms those taker trades happen at `event_index 200000`, after the strategy horizon, not during normal quote refresh. Sample rows:

```text
strategy,regime,event_index,side,price,quantity,liquidation_cost
naive,low volatility,200000,sell,100444,72,1292.25705614
naive,high volatility,200000,sell,100441,8,-85.3334249032
naive,trending,200000,sell,100555,38,848.127514575
avellaneda stoikov,low volatility,200000,sell,100444,21,376.908308041
avellaneda stoikov,high volatility,200000,sell,100440,16,-154.666849806
avellaneda stoikov,trending,200000,sell,100555,11,245.510596324
```

Terminal ladder counts in the production runs:

```text
strategy,regime,levels_walked,first_price,last_price,last_level_displayed,last_level_filled
naive,low volatility,2,100444,100443,6398,1357
naive,high volatility,18,100441,100424,189,175
naive,trending,15,100555,100541,1286,934
avellaneda stoikov,low volatility,2,100444,100443,6434,1036
avellaneda stoikov,high volatility,4,100440,100437,490,420
avellaneda stoikov,trending,15,100555,100541,1149,822
```

The production ladder behavior is more stable than the small smoke run. Low volatility closes in two levels for both strategies. Trending closes in fifteen levels because both strategies finish with roughly `17000` units of long inventory and must sell into the bid stack. High volatility is the sharpest strategy contrast: naive walks eighteen levels for `6076` units, while Avellaneda Stoikov walks four levels for `1179` units.

## Ranking Change Versus Stage 3

The uncontrolled Stage 3 raw net PnL ranking was:

```text
regime,winner_by_net_pnl
low volatility,naive
high volatility,avellaneda stoikov
trending,avellaneda stoikov
```

The Stage 4C controlled raw net PnL ranking is the same:

```text
regime,winner_by_net_pnl
low volatility,naive
high volatility,avellaneda stoikov
trending,avellaneda stoikov
```

The risk adjusted PnL ranking is also the same in this run:

```text
regime,winner_by_risk_adjusted_pnl
low volatility,naive
high volatility,avellaneda stoikov
trending,avellaneda stoikov
```

The Stage 5C multi seed pass narrows this ranking. Across 30 seeds, the controlled hand chosen high volatility run still shows a separated inventory variance reduction for Avellaneda Stoikov. The paired same-seed delta addendum also separates risk adjusted PnL in favor of Avellaneda Stoikov, while net PnL still does not separate. Low volatility and trending show lower AS net PnL under paired deltas, while risk adjusted PnL does not separate for original AS versus naive in either regime. The interpretation changes even though the single seed winner labels did not. Low volatility raw PnL drops sharply for both strategies because the hard cap blocks thousands of bids and prevents the very large long inventory that drove the uncontrolled low volatility PnL. High volatility remains the cleanest Avellaneda Stoikov risk reduction result, not a proven PnL dominance result. Trending should be treated as path dependent for PnL at this sample size.

## Mechanism Notes

The cap block pattern is informative:

```text
strategy,regime,hard_cap_bid_blocks,hard_cap_ask_blocks
naive,low volatility,5008,0
naive,high volatility,0,0
naive,trending,0,0
avellaneda stoikov,low volatility,4470,0
avellaneda stoikov,high volatility,0,0
avellaneda stoikov,trending,0,0
```

At this production cap, low volatility is the only regime where the hard cap binds. That is not the same pattern as the 5000 event smoke run. The smoke run was a forced mechanics check with a tiny cap. In the production run, low volatility is the path where the uncontrolled strategies accumulated the largest long inventories, so bid blocking is expected there. Trending remains below the cap after the soft skew adjustment, so the absence of hard cap blocks is a result, not a missed trigger.

The final inventory invariant holds in every controlled production run:

```text
strategy,regime,final_inventory,terminal_liquidation_residual_inventory,reconciliation
naive,low volatility,0,0,true
naive,high volatility,0,0,true
naive,trending,0,0,true
avellaneda stoikov,low volatility,0,0,true
avellaneda stoikov,high volatility,0,0,true
avellaneda stoikov,trending,0,0,true
```
