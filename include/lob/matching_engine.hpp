#pragma once

#include "lob/order_book.hpp"
#include "lob/types.hpp"

#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

namespace lob {

struct ExecutionResult {
    bool accepted{false};
    std::string reject_reason{};
    std::optional<Order> order{};
    std::vector<Trade> trades{};
};

class MatchingEngine {
public:
    ExecutionResult submit_order(Order order);
    ExecutionResult cancel_order(OrderId id, Timestamp timestamp);
    ExecutionResult modify_order(OrderId id,
                                 std::optional<Price> new_price,
                                 Quantity new_quantity,
                                 Timestamp timestamp);

    const OrderBook& book() const noexcept;

private:
    ExecutionResult process_order(Order order, bool allow_seen_id);
    ExecutionResult reject(std::string reason, Order order) const;

    bool can_cross(const Order& incoming) const;
    bool would_self_trade(const Order& incoming) const;
    bool price_allows_match(const Order& incoming, Price resting_price) const;

    OrderBook book_{};
    std::unordered_set<OrderId> seen_order_ids_{};
};

}  // namespace lob
