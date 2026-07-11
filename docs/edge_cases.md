# Edge Cases

## Empty Book

A limit order that does not cross rests on its side of the book. A market order sent to an empty opposite side is accepted, produces no trades, and ends with cancelled status because it cannot rest.

## Zero Size Order

Any order with quantity less than or equal to zero is rejected. The engine never creates a resting order with non positive remaining quantity.

## Tick Size Mismatch

The engine accepts prices only as integer ticks. Decimal conversion and tick size validation belong at the boundary before `Order::limit` is called or before a CSV row is produced.

## Duplicate Order ID

Every new order ID can be used once. A new order with an ID already seen by the engine is rejected. A replacement keeps the same ID because it is an update to an active order, not a new client order.

## Zero Order ID

Order ID `0` is reserved and is never accepted as a real incoming order ID. The benchmark generator starts synthetic order IDs at `1`, market maker quote IDs start at `1000000000000`, and the ITCH translator maps source order references directly into engine order IDs, where any zero source ID would be rejected by the replay rather than admitted as an active order.

Stage 5A uses `0` in trade records as a sentinel for the unknown aggressor on an `external_execute` event. This is unambiguous because the engine will not accept a real order with ID `0`.

## Immediate Crossing

An aggressive limit order executes against the opposite side while the best opposite price satisfies the limit. Any unfilled limit quantity rests at its limit price.

## Partial Fill Within One Level

If the best resting order has more quantity than the incoming order needs, the resting order remains at the front of its level with reduced remaining quantity and partially filled status.

## Partial Fill Across Multiple Levels

Market orders and aggressive limit orders continue walking price levels until the incoming quantity is filled, the opposite side is empty, or the next price no longer satisfies the limit.

## Market Order With Insufficient Liquidity

Market orders never rest. If a market order is partly filled and the opposite side runs out, the remainder is cancelled immediately. The result keeps partially filled status and the remaining quantity records the amount not executed.

## Cancel Resting Order

Cancelling an active resting order removes only its unfilled quantity. If that order was already partially filled, the executed quantity remains represented by prior trades.

## Cancel Filled Or Missing Order

Filled orders are no longer active in the book. A cancel request for a filled or unknown order is rejected with no state change.

## External Execute

An `external_execute` event reduces a named resting order by the supplied quantity at the supplied execution price. The named order remains the maker in the trade record. The aggressor side is unknown at this schema boundary, so the missing taker order ID is recorded as the reserved sentinel `0`.

If the named order is missing or already closed, the event is rejected with no state change. If the supplied quantity is less than or equal to zero, the event is rejected. If the supplied execution price is less than or equal to zero, the event is rejected. If the supplied quantity is larger than the named order's remaining quantity, the event is rejected with no state change.

A partial external execution leaves the order resting with reduced remaining quantity and partially filled status. A full external execution removes the order from the book and returns filled status for the event result.

## Modify Price

A price change is implemented as cancel and reinsert with the supplied timestamp. The order loses time priority because changing price is economically a new quote at that price.

## Modify Quantity Down

Reducing quantity at the same price preserves time priority. The order keeps its original timestamp because it did not gain queue advantage by increasing displayed size or changing price.

## Modify Quantity Up

Increasing quantity at the same price is treated as cancel and reinsert with a new timestamp. This avoids letting a participant add displayed size while keeping an older queue position.

## Modify To Zero

A modify request with quantity less than or equal to zero is rejected. Cancellation is the explicit operation for removing an order.

## Self Trade

Orders carry an owner ID. If the incoming order would execute against a resting order with the same non empty owner ID, the incoming order is rejected before any trade is produced. This conservative rule avoids partial execution followed by a self trade later in the sweep.

## Same Price And Same Timestamp

Orders at the same price are ordered first by timestamp and then by order ID. The order ID rule gives a deterministic secondary priority for replay and testing.

## Resting Market Maker Quote During Later Stages

The same cancel and replace rules will apply to market maker quotes. A quote cancelled before a fill leaves the book with no trade. A quote replaced at a new price loses time priority. A quote reduced at the same price keeps priority.
