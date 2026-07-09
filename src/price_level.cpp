#include "lob/price_level.hpp"

#include <algorithm>
#include <utility>

namespace lob {

PriceLevel::PriceLevel(Price price) : price_(price) {}

PriceLevel::iterator PriceLevel::add_order(Order order) {
    auto position = std::find_if(orders_.begin(), orders_.end(), [&](const Order& resting) {
        return has_higher_priority(order, resting);
    });
    return orders_.insert(position, std::move(order));
}

void PriceLevel::erase(iterator position) {
    orders_.erase(position);
}

void PriceLevel::pop_front() {
    orders_.pop_front();
}

Order& PriceLevel::front() {
    return orders_.front();
}

const Order& PriceLevel::front() const {
    return orders_.front();
}

bool PriceLevel::empty() const noexcept {
    return orders_.empty();
}

std::size_t PriceLevel::size() const noexcept {
    return orders_.size();
}

Price PriceLevel::price() const noexcept {
    return price_;
}

PriceLevel::iterator PriceLevel::begin() noexcept {
    return orders_.begin();
}

PriceLevel::iterator PriceLevel::end() noexcept {
    return orders_.end();
}

PriceLevel::const_iterator PriceLevel::begin() const noexcept {
    return orders_.begin();
}

PriceLevel::const_iterator PriceLevel::end() const noexcept {
    return orders_.end();
}

bool PriceLevel::has_higher_priority(const Order& left, const Order& right) {
    if (left.timestamp != right.timestamp) {
        return left.timestamp < right.timestamp;
    }
    return left.id < right.id;
}

}  // namespace lob
