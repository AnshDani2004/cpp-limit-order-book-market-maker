#include "lob/matching_engine.hpp"

#include <algorithm>
#include <utility>

namespace lob {

Order Order::limit(OrderId id,
                   std::string owner_id,
                   Side side,
                   Price price,
                   Quantity quantity,
                   Timestamp timestamp) {
    return Order{id,
                 std::move(owner_id),
                 side,
                 OrderType::Limit,
                 price,
                 quantity,
                 quantity,
                 timestamp,
                 OrderStatus::New};
}

Order Order::market(OrderId id,
                    std::string owner_id,
                    Side side,
                    Quantity quantity,
                    Timestamp timestamp) {
    return Order{id,
                 std::move(owner_id),
                 side,
                 OrderType::Market,
                 std::nullopt,
                 quantity,
                 quantity,
                 timestamp,
                 OrderStatus::New};
}

Side opposite(Side side) {
    return side == Side::Buy ? Side::Sell : Side::Buy;
}

std::string to_string(Side side) {
    return side == Side::Buy ? "buy" : "sell";
}

std::string to_string(OrderType type) {
    return type == OrderType::Limit ? "limit" : "market";
}

std::string to_string(OrderStatus status) {
    switch (status) {
        case OrderStatus::New:
            return "new";
        case OrderStatus::PartiallyFilled:
            return "partially filled";
        case OrderStatus::Filled:
            return "filled";
        case OrderStatus::Cancelled:
            return "cancelled";
    }
    return "unknown";
}

ExecutionResult MatchingEngine::submit_order(Order order) {
    return process_order(std::move(order), false);
}

ExecutionResult MatchingEngine::cancel_order(OrderId id, Timestamp timestamp) {
    (void)timestamp;
    auto snapshot = book_.snapshot_order(id);
    if (!snapshot.has_value()) {
        return ExecutionResult{false, "order is not active", std::nullopt, {}};
    }

    book_.cancel_order(id);
    snapshot->status = OrderStatus::Cancelled;
    return ExecutionResult{true, {}, snapshot, {}};
}

ExecutionResult MatchingEngine::modify_order(OrderId id,
                                             std::optional<Price> new_price,
                                             Quantity new_quantity,
                                             Timestamp timestamp) {
    auto snapshot = book_.snapshot_order(id);
    if (!snapshot.has_value()) {
        return ExecutionResult{false, "order is not active", std::nullopt, {}};
    }
    if (new_quantity <= 0) {
        return ExecutionResult{false, "quantity must be positive", snapshot, {}};
    }

    const auto current_price = snapshot->price.value();
    const auto target_price = new_price.value_or(current_price);
    if (target_price <= 0) {
        return ExecutionResult{false, "limit price must be positive", snapshot, {}};
    }

    if (target_price == current_price && new_quantity <= snapshot->remaining_quantity) {
        if (new_quantity < snapshot->remaining_quantity) {
            book_.reduce_order(id, new_quantity);
        }
        auto updated = book_.snapshot_order(id);
        return ExecutionResult{true, {}, updated, {}};
    }

    book_.cancel_order(id);
    auto replacement = *snapshot;
    replacement.price = target_price;
    replacement.quantity = new_quantity;
    replacement.remaining_quantity = new_quantity;
    replacement.timestamp = timestamp;
    replacement.status = OrderStatus::New;
    replacement.type = OrderType::Limit;
    return process_order(std::move(replacement), true);
}

const OrderBook& MatchingEngine::book() const noexcept {
    return book_;
}

ExecutionResult MatchingEngine::process_order(Order order, bool allow_seen_id) {
    if (order.id == 0) {
        return reject("order id must be positive", order);
    }
    if (!allow_seen_id && seen_order_ids_.find(order.id) != seen_order_ids_.end()) {
        return reject("order id already used", order);
    }
    if (book_.contains(order.id)) {
        return reject("order id is active", order);
    }
    if (order.quantity <= 0) {
        return reject("quantity must be positive", order);
    }
    if (order.remaining_quantity <= 0) {
        order.remaining_quantity = order.quantity;
    }
    if (order.type == OrderType::Limit) {
        if (!order.price.has_value() || *order.price <= 0) {
            return reject("limit price must be positive", order);
        }
    } else if (order.price.has_value()) {
        return reject("market order must not include price", order);
    }
    if (would_self_trade(order)) {
        return reject("self trade prevention rejected order", order);
    }

    seen_order_ids_.insert(order.id);
    std::vector<Trade> trades;

    while (order.remaining_quantity > 0 && can_cross(order)) {
        auto* level = order.side == Side::Buy ? book_.best_ask_level() : book_.best_bid_level();
        auto& resting = level->front();
        const auto resting_price = level->price();
        const auto resting_side = resting.side;
        const auto execution_quantity = std::min(order.remaining_quantity, resting.remaining_quantity);

        trades.push_back(Trade{order.side == Side::Buy ? order.id : resting.id,
                               order.side == Side::Buy ? resting.id : order.id,
                               resting.id,
                               order.id,
                               resting_price,
                               execution_quantity,
                               order.timestamp});

        order.remaining_quantity -= execution_quantity;
        resting.remaining_quantity -= execution_quantity;
        order.status = order.remaining_quantity == 0 ? OrderStatus::Filled : OrderStatus::PartiallyFilled;
        resting.status = resting.remaining_quantity == 0 ? OrderStatus::Filled : OrderStatus::PartiallyFilled;

        if (resting.remaining_quantity == 0) {
            book_.remove_front(resting_side, resting_price);
        }
    }

    if (order.remaining_quantity == 0) {
        order.status = OrderStatus::Filled;
    } else if (order.type == OrderType::Limit) {
        order.status = trades.empty() ? OrderStatus::New : OrderStatus::PartiallyFilled;
        book_.add_resting_order(order);
    } else {
        order.status = trades.empty() ? OrderStatus::Cancelled : OrderStatus::PartiallyFilled;
    }

    return ExecutionResult{true, {}, order, std::move(trades)};
}

ExecutionResult MatchingEngine::reject(std::string reason, Order order) const {
    return ExecutionResult{false, std::move(reason), std::move(order), {}};
}

bool MatchingEngine::can_cross(const Order& incoming) const {
    const auto* level = incoming.side == Side::Buy ? book_.best_ask_level() : book_.best_bid_level();
    if (level == nullptr) {
        return false;
    }
    return price_allows_match(incoming, level->price());
}

bool MatchingEngine::would_self_trade(const Order& incoming) const {
    if (incoming.owner_id.empty()) {
        return false;
    }

    auto remaining_to_check = incoming.remaining_quantity > 0 ? incoming.remaining_quantity : incoming.quantity;

    if (incoming.side == Side::Buy) {
        for (const auto& [price, level] : book_.ask_levels()) {
            if (!price_allows_match(incoming, price)) {
                break;
            }
            for (const auto& resting : level) {
                if (remaining_to_check <= 0) {
                    return false;
                }
                if (resting.owner_id == incoming.owner_id) {
                    return true;
                }
                remaining_to_check -= resting.remaining_quantity;
            }
        }
        return false;
    }

    for (const auto& [price, level] : book_.bid_levels()) {
        if (!price_allows_match(incoming, price)) {
            break;
        }
        for (const auto& resting : level) {
            if (remaining_to_check <= 0) {
                return false;
            }
            if (resting.owner_id == incoming.owner_id) {
                return true;
            }
            remaining_to_check -= resting.remaining_quantity;
        }
    }
    return false;
}

bool MatchingEngine::price_allows_match(const Order& incoming, Price resting_price) const {
    if (incoming.type == OrderType::Market) {
        return true;
    }
    if (incoming.side == Side::Buy) {
        return resting_price <= incoming.price.value();
    }
    return resting_price >= incoming.price.value();
}

}  // namespace lob
