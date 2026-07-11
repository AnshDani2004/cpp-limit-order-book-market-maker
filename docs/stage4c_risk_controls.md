# Stage 4C Risk Controls

This checkpoint adds inventory limits, terminal liquidation, and a risk adjusted PnL view to the market maker simulator. The intent is to measure whether a strategy that looks good on raw PnL still looks good after inventory exposure and terminal closing cost are made explicit.

## Parameters

The controlled runs use the same seeds, regimes, quote size, refresh cadence, maker fees, taker fees, and markout horizon as Stage 3 unless a command states otherwise.

```text
inventory_cap 20000 units
soft_start_fraction 0.50
soft_penalty_max_skew_ticks 20
terminal_liquidation true
terminal_inventory_penalty_per_unit 0.50 ticks
risk_denominator_floor 1 tick
```

The cap is set at `20000` units because it is below the largest uncontrolled Stage 3 terminal inventories, so it can change behavior in the low volatility and trending paths, but it is still high enough to let the strategy quote through ordinary inventory swings. This makes the cap a risk control rather than a tiny position target.

## Hard Cap

At every quote refresh, the simulator cancels any active market maker quotes, reads current inventory, and checks each side independently.

```text
bid allowed if inventory + quote_size <= inventory_cap
ask allowed if inventory - quote_size >= -inventory_cap
```

If the bid is blocked, the strategy stops quoting the side that would increase a long position. If the ask is blocked, the strategy stops quoting the side that would increase a short position. The opposite side can still quote, so the control leans toward flattening instead of stopping the strategy entirely.

The summary reports:

```text
hard_cap_bid_blocks
hard_cap_ask_blocks
```

## Soft Penalty

The soft penalty starts before the hard cap and shifts the quote center against inventory. It applies to both naive symmetric and Avellaneda Stoikov runs so the controlled comparison does not give one strategy a different risk tool.

```text
soft_start = inventory_cap * soft_start_fraction
ratio = clamp((abs(inventory) - soft_start) / (inventory_cap - soft_start), 0, 1)
soft_skew = sign(inventory) * soft_penalty_max_skew_ticks * ratio^2
adjusted_center = reference_mid - soft_skew
```

For positive inventory, the center moves down. That lowers the ask and bid together, making sell fills easier and buy fills harder. For negative inventory, the center moves up, making buy fills easier and sell fills harder. The quadratic shape keeps the penalty quiet near the start zone and makes it visible as inventory approaches the cap.

For Avellaneda Stoikov, this soft skew is added to the existing reservation price skew:

```text
total_skew = AS_inventory_skew + soft_skew
reservation_price = reference_mid - total_skew
```

## Terminal Liquidation

At the end of the trading horizon, if terminal liquidation is enabled, the simulator cancels any active quotes and submits one explicit market order to close the remaining inventory.

```text
long inventory closes with a market sell
short inventory closes with a market buy
```

The liquidation fill is recorded through the same accounting path as all other fills and therefore includes taker fees. The simulator fails loudly if the market order leaves residual inventory.

Liquidation cost is reported relative to the final reference mid:

```text
sell liquidation cost = (final_reference_mid - fill_price) * quantity
buy liquidation cost = (fill_price - final_reference_mid) * quantity
```

The value is signed. A positive value means the liquidation price was worse than the final reference mid. A negative value means the liquidation price was better than the final reference mid.

The summary reports:

```text
pre_liquidation_inventory
terminal_liquidation_quantity
terminal_liquidation_cost
terminal_liquidation_residual_inventory
final_inventory
```

With terminal liquidation enabled, `final_inventory` should be zero. The `pre_liquidation_inventory` field preserves the exposure that existed at the end of the strategy run before the forced close.

## Terminal Inventory Penalty

The terminal inventory penalty is applied to the inventory held at the end of the trading horizon before forced liquidation.

```text
terminal_inventory_penalty = terminal_inventory_penalty_per_unit * abs(pre_liquidation_inventory)
```

This is intentionally separate from realized liquidation cost. Liquidation cost measures the actual close price. The terminal inventory penalty measures the risk of reaching the end of the horizon with a large position.

## Risk Adjusted PnL

Risk adjusted PnL uses net PnL after fees, after any liquidation fills have been recorded, minus the terminal inventory penalty, divided by maximum drawdown.

```text
risk_adjusted_pnl = (net_pnl_after_fees - terminal_inventory_penalty) / max(maximum_drawdown, risk_denominator_floor)
```

The denominator floor prevents division by zero in very small diagnostic runs. The production comparison uses the realized maximum drawdown unless it is below one tick.

## Test Gate

The first Stage 4C checkpoint adds deterministic tests before the full regime comparison:

```text
risk controls block only the side that would exceed the hard cap
risk controls add soft quote skew before the hard cap
terminal liquidation cost penalty and risk adjusted PnL are explicit
risk controlled terminal liquidation closes residual inventory
```

The full comparison should not start until these mechanics pass locally and remain green in CI.
