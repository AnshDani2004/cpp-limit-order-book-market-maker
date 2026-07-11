#include "lob/matching_engine.hpp"

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

}  // namespace lob
