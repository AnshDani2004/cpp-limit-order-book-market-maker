#include "lob/order_book.hpp"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace lob {

PriceLevel::iterator OrderBook::add_resting_order(Order order) {
    const auto side = order.side;
    const auto price = order.price.value();

    if (side == Side::Buy) {
        auto [level_position, inserted] = bids_.try_emplace(price, PriceLevel(price));
        (void)inserted;
        auto order_position = level_position->second.add_order(std::move(order));
        locations_[order_position->id] = OrderLocation{side, price, order_position};
        return order_position;
    }

    auto [level_position, inserted] = asks_.try_emplace(price, PriceLevel(price));
    (void)inserted;
    auto order_position = level_position->second.add_order(std::move(order));
    locations_[order_position->id] = OrderLocation{side, price, order_position};
    return order_position;
}

bool OrderBook::cancel_order(OrderId id) {
    auto location_position = locations_.find(id);
    if (location_position == locations_.end()) {
        return false;
    }

    const auto location = location_position->second;

    if (location.side == Side::Buy) {
        auto level_position = bids_.find(location.price);
        if (level_position == bids_.end()) {
            throw std::logic_error("bid level missing for active order");
        }
        level_position->second.erase(location.iterator);
        if (level_position->second.empty()) {
            bids_.erase(level_position);
        }
    } else {
        auto level_position = asks_.find(location.price);
        if (level_position == asks_.end()) {
            throw std::logic_error("ask level missing for active order");
        }
        level_position->second.erase(location.iterator);
        if (level_position->second.empty()) {
            asks_.erase(level_position);
        }
    }

    locations_.erase(location_position);
    return true;
}

bool OrderBook::contains(OrderId id) const {
    return locations_.find(id) != locations_.end();
}

bool OrderBook::reduce_order(OrderId id, Quantity new_remaining_quantity) {
    auto* order = find_order(id);
    if (order == nullptr || new_remaining_quantity <= 0 || new_remaining_quantity > order->remaining_quantity) {
        return false;
    }

    const auto executed_quantity = order->quantity - order->remaining_quantity;
    order->remaining_quantity = new_remaining_quantity;
    order->quantity = executed_quantity + new_remaining_quantity;
    order->status = executed_quantity > 0 ? OrderStatus::PartiallyFilled : OrderStatus::New;
    return true;
}

Order* OrderBook::find_order(OrderId id) {
    auto location_position = locations_.find(id);
    if (location_position == locations_.end()) {
        return nullptr;
    }
    return std::addressof(*location_position->second.iterator);
}

const Order* OrderBook::find_order(OrderId id) const {
    auto location_position = locations_.find(id);
    if (location_position == locations_.end()) {
        return nullptr;
    }
    return std::addressof(*location_position->second.iterator);
}

std::optional<Order> OrderBook::snapshot_order(OrderId id) const {
    const auto* order = find_order(id);
    if (order == nullptr) {
        return std::nullopt;
    }
    return *order;
}

std::optional<Price> OrderBook::best_bid() const {
    if (bids_.empty()) {
        return std::nullopt;
    }
    return bids_.begin()->first;
}

std::optional<Price> OrderBook::best_ask() const {
    if (asks_.empty()) {
        return std::nullopt;
    }
    return asks_.begin()->first;
}

std::optional<Price> OrderBook::spread() const {
    const auto bid = best_bid();
    const auto ask = best_ask();
    if (!bid.has_value() || !ask.has_value()) {
        return std::nullopt;
    }
    return *ask - *bid;
}

PriceLevel* OrderBook::best_bid_level() {
    if (bids_.empty()) {
        return nullptr;
    }
    return std::addressof(bids_.begin()->second);
}

PriceLevel* OrderBook::best_ask_level() {
    if (asks_.empty()) {
        return nullptr;
    }
    return std::addressof(asks_.begin()->second);
}

const PriceLevel* OrderBook::best_bid_level() const {
    if (bids_.empty()) {
        return nullptr;
    }
    return std::addressof(bids_.begin()->second);
}

const PriceLevel* OrderBook::best_ask_level() const {
    if (asks_.empty()) {
        return nullptr;
    }
    return std::addressof(asks_.begin()->second);
}

void OrderBook::remove_front(Side resting_side, Price price) {
    if (resting_side == Side::Buy) {
        auto level_position = bids_.find(price);
        if (level_position == bids_.end() || level_position->second.empty()) {
            throw std::logic_error("bid level missing for front removal");
        }
        locations_.erase(level_position->second.front().id);
        level_position->second.pop_front();
        if (level_position->second.empty()) {
            bids_.erase(level_position);
        }
        return;
    }

    auto level_position = asks_.find(price);
    if (level_position == asks_.end() || level_position->second.empty()) {
        throw std::logic_error("ask level missing for front removal");
    }
    locations_.erase(level_position->second.front().id);
    level_position->second.pop_front();
    if (level_position->second.empty()) {
        asks_.erase(level_position);
    }
}

const OrderBook::BidLevels& OrderBook::bid_levels() const noexcept {
    return bids_;
}

const OrderBook::AskLevels& OrderBook::ask_levels() const noexcept {
    return asks_;
}

}  // namespace lob
