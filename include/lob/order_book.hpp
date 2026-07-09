#pragma once

#include "lob/price_level.hpp"
#include "lob/types.hpp"

#include <functional>
#include <map>
#include <optional>
#include <unordered_map>

namespace lob {

struct OrderLocation {
    Side side{Side::Buy};
    Price price{};
    PriceLevel::iterator iterator{};
};

class OrderBook {
public:
    using BidLevels = std::map<Price, PriceLevel, std::greater<Price>>;
    using AskLevels = std::map<Price, PriceLevel, std::less<Price>>;

    PriceLevel::iterator add_resting_order(Order order);

    bool cancel_order(OrderId id);
    bool contains(OrderId id) const;
    bool reduce_order(OrderId id, Quantity new_remaining_quantity);

    Order* find_order(OrderId id);
    const Order* find_order(OrderId id) const;
    std::optional<Order> snapshot_order(OrderId id) const;

    std::optional<Price> best_bid() const;
    std::optional<Price> best_ask() const;
    std::optional<Price> spread() const;

    PriceLevel* best_bid_level();
    PriceLevel* best_ask_level();
    const PriceLevel* best_bid_level() const;
    const PriceLevel* best_ask_level() const;

    void remove_front(Side resting_side, Price price);

    const BidLevels& bid_levels() const noexcept;
    const AskLevels& ask_levels() const noexcept;

private:
    BidLevels bids_{};
    AskLevels asks_{};
    std::unordered_map<OrderId, OrderLocation> locations_{};
};

}  // namespace lob
