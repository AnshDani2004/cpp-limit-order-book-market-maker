# Design

## Goal

Stage 1 builds the matching engine foundation for a one instrument order book. The priority is correctness, deterministic behavior, and a design that can be explained under interview questioning.

## Why C++

C++ is the right language for this project because the core problem is about explicit control over memory layout, ownership, latency, and data structure tradeoffs. The first stage still uses standard library containers, because correctness comes before hand tuned storage. Later benchmarks can compare this baseline against flatter storage.

## Core Components

`Order` carries side, type, integer tick price for limit orders, original quantity, remaining quantity, timestamp, order ID, owner ID, and status.

`Trade` records the two matched orders, the resting maker order, the incoming taker order, execution price, execution quantity, and execution timestamp.

`PriceLevel` owns the queue of resting orders at one price. It keeps price time priority inside the level by sorting first by timestamp and then by order ID.

`OrderBook` owns the bid and ask maps and an order ID index. Bids use descending price order and asks use ascending price order, so the best level is always at the beginning of the map.

`MatchingEngine` validates incoming events, applies self trade prevention, matches against the opposite side, produces trades, updates remaining quantities, and places any unfilled limit quantity onto the book.

## Data Structures

Bids are stored as `std::map<Price, PriceLevel, std::greater<Price>>`.

Asks are stored as `std::map<Price, PriceLevel, std::less<Price>>`.

Each `PriceLevel` stores orders in `std::list<Order>`. The list gives stable iterators, which lets the order ID index cancel or reduce an order without searching the full level. The tradeoff is poorer cache locality than a contiguous container. That is acceptable for Stage 1 because correctness and clean cancellation semantics matter more than raw speed.

The order index is an `std::unordered_map<OrderId, OrderLocation>`. It maps each active order ID to its side, price, and list iterator.

## Matching Rules

A buy order matches the lowest ask prices that are less than or equal to its limit price. A sell order matches the highest bid prices that are greater than or equal to its limit price. Market orders match available liquidity until their requested quantity is filled or the opposite side is empty.

Execution price is always the resting order price. This is the standard rule for price time priority books and makes maker versus taker economics explicit for later stages.

## Simplifying Assumptions

The engine handles one instrument and does not model trading sessions, auctions, hidden liquidity, pegged orders, minimum quantity, or venue specific order attributes.

Prices are integer ticks. Decimal price parsing is intentionally outside the engine boundary.

Self trade prevention uses owner ID. If an incoming order would execute against a resting order with the same non empty owner ID, the incoming order is rejected before any fill occurs.

## Larger Scale Changes

At larger scale, the ordered maps would be benchmarked against flat tick indexed storage for bounded price ranges. A real venue or trading system would also need sequence numbers from a gateway, persistence or recovery, replay logs, risk checks, symbol partitioning, market data publication, and much tighter control over allocation.
