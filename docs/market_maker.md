# Market Maker Measurement Plan

This document fixes the Stage 3 measurement rules before any market maker implementation code is written. The goal is to prevent the strategy code from shaping the result definitions after the fact.

## Source Model

The inventory aware strategy will follow the Avellaneda and Stoikov market making framework from Marco Avellaneda and Sasha Stoikov, "High frequency trading in a limit order book," Quantitative Finance 8(3), pages 217 to 224, 2008. Reference links: [RePEc entry](https://ideas.repec.org/a/taf/quantf/v8y2008i3p217-224.html) and [author PDF](https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf).

The strategy will use the standard reservation price form:

```text
reservation_price = reference_mid - inventory * risk_aversion * volatility^2 * time_remaining
```

The symmetric optimal spread target will use:

```text
optimal_spread = risk_aversion * volatility^2 * time_remaining + (2 / risk_aversion) * log(1 + risk_aversion / fill_decay)
```

Bid and ask quotes will be centered around the reservation price, rounded to integer ticks, and clipped so bid is less than ask. A bid that would be greater than or equal to the current best ask is clipped to best ask minus one tick. An ask that would be less than or equal to the current best bid is clipped to best bid plus one tick. If the opposing side is empty, that side has no book based clip.

## Common Simulation Rules

All strategy comparisons must be apples to apples. For a given regime, the naive symmetric strategy and the inventory aware strategy will run on the same seed, the same reference price path, and the same exogenous order flow.

The simulator will use integer ticks. The initial reference mid is 100000 ticks. One contract has tick value 1. The default run length is 200000 events per regime unless a later benchmark explicitly states a different length.

The market maker starts with zero cash and zero inventory. Open inventory at the end is marked at the final reference mid. Results are reported after fees.

The market maker will submit passive limit quotes unless a strategy explicitly documents a taker action. If a computed quote would cross the book, it is clipped to a passive price. This keeps the baseline and inventory aware comparison focused on quoting behavior.

Maker and taker fees are signed per unit costs in ticks. The first implementation will use:

```text
maker_fee = -0.02 ticks per unit
taker_fee = 0.08 ticks per unit
```

A negative maker fee means a rebate. A positive taker fee means a cost. If these values change, the result table must state the replacement values.

## Regimes

Each regime specifies the reference price process and exogenous flow intensity. The same regime seed must be reused for both strategies.

| Regime | Seed | Drift Per Event | Volatility Per Event | Flow Notes |
| --- | --- | --- | --- | --- |
| Low volatility | 3001 | 0.00 ticks | 0.40 ticks | Narrower reference moves, normal order arrival |
| High volatility | 3002 | 0.00 ticks | 1.60 ticks | Wider reference moves, normal order arrival |
| Trending | 3003 | 0.004 ticks | 0.80 ticks | Upward drift with normal order arrival |

The reference path will be generated as:

```text
reference_mid_next = reference_mid + drift + volatility * normal_random_draw
```

The simulator may keep a double precision reference mid internally for path generation, but all book prices and submitted orders must be integer ticks.

Normal order arrival means the same base mix across regimes:

```text
external limit orders 55 percent
external market orders 25 percent
external cancels 10 percent
external modifies 10 percent
```

External order sizes will use a bounded distribution with support from 1 to 100 units. The exact distribution must be stated in the implementation. Every random source must take an explicit seed.

## Strategies To Compare

The naive strategy quotes symmetrically around the current reference mid with a fixed spread. It does not use inventory in quote placement.

The inventory aware strategy quotes around the Avellaneda and Stoikov reservation price and uses the optimal spread formula above. It must state risk aversion, fill decay, volatility estimate, time horizon, quote size, and refresh cadence before reporting any result.

For the first implementation, the strategy receives the regime volatility from the table above as an ex ante model input. It does not estimate volatility from a rolling window. This is an intentional simplifying assumption and must be named beside the results.

The time horizon is the full regime run. With the default 200000 event run, `time_remaining` is computed before event `event_index` as:

```text
time_remaining = (run_length - event_index) / run_length
```

The value counts down once from 1 toward 0 during the run and does not reset on quote refresh. Any late run quote behavior caused by this countdown must be discussed if visible in the plots.

Both strategies must use the same quote size and refresh cadence unless a difference is explicitly part of the experiment. The default quote size is 10 units per side. The default refresh cadence is every 10 events.

## PnL State

At every event, the accounting state is:

```text
cash
inventory
reference_mid
equity = cash + inventory * reference_mid
```

For a buy fill, cash decreases by fill_price * quantity. For a sell fill, cash increases by fill_price * quantity. Inventory increases on buys and decreases on sells.

Fees are applied per fill:

```text
fee_pnl = -fee_per_unit * quantity
```

With this sign convention, a maker rebate increases fee PnL and a taker fee decreases fee PnL. Each fill first adjusts cash by the fill price times quantity, then adjusts cash by `fee_pnl`. The running `fee_pnl` total is tracked for attribution only and is not an independent source of truth.

## PnL Attribution

The report must include a reconciliation table:

```text
net_pnl_after_fees = cash_final + inventory_final * final_reference_mid
gross_pnl_before_fees = net_pnl_after_fees - fee_pnl
gross_pnl_before_fees = spread_capture + inventory_pnl
net_pnl_after_fees = spread_capture + inventory_pnl + fee_pnl
```

Spread capture is recorded at each market maker fill using the reference mid at the fill event:

```text
buy spread capture = (reference_mid_at_fill - fill_price) * quantity
sell spread capture = (fill_price - reference_mid_at_fill) * quantity
```

Inventory PnL is the balancing price movement component:

```text
inventory_pnl = gross_pnl_before_fees - spread_capture
```

The implementation should also compute the equivalent event by event mark:

```text
inventory_pnl_increment = inventory_before_reference_move * reference_mid_change
```

The two inventory PnL calculations must reconcile within rounding error.

Adverse selection is reported as a markout diagnostic, not added a second time to net PnL. The default markout horizon is 50 events after the fill. For maker fills:

```text
buy markout = (future_reference_mid - fill_price) * quantity
sell markout = (fill_price - future_reference_mid) * quantity
adverse_selection_cost = max(0, -markout)
```

This captures fills that look profitable at the posted spread but are followed by a reference move through the fill price. The report must state the markout horizon.

## Required Metrics

For each regime and strategy, the result table must include:

```text
fill rate
gross spread capture
inventory PnL
adverse selection cost
fee PnL
net PnL after fees
maximum drawdown
inventory variance
final inventory
number of maker fills
number of taker fills
```

Fill rate is market maker filled quantity divided by market maker posted quantity that was live for at least one event.

Maximum drawdown is computed from the event level equity curve after fees.

Inventory variance is computed from event level inventory after each event.

## Required Plots

The Stage 3 result must include:

```text
inventory over time for both strategies in each regime
cumulative PnL after fees for both strategies in each regime
```

Plots must be generated by a reproducible script from checked result CSV files.

## Reporting Rules

The same seed and regime path must be used for both strategies in a comparison.

If the inventory aware strategy underperforms the naive strategy in any regime, the README must say so directly and explain the measured reason from the attribution table.

No resume bullet or README headline may use Stage 3 numbers until the result CSVs, plots, and reproduction command are checked in and CI is green.
