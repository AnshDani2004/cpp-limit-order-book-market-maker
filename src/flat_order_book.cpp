#include "lob/flat_order_book.hpp"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace lob {

FlatOrderBook::LevelRange::iterator::iterator(const FlatOrderBook* book, Side side, Price price, bool at_end)
    : book_(book), side_(side), price_(price), at_end_(at_end) {
    advance_to_active();
}

FlatOrderBook::LevelRange::iterator::reference FlatOrderBook::LevelRange::iterator::operator*() const {
    return view_;
}

FlatOrderBook::LevelRange::iterator::pointer FlatOrderBook::LevelRange::iterator::operator->() const {
    return std::addressof(view_);
}

FlatOrderBook::LevelRange::iterator& FlatOrderBook::LevelRange::iterator::operator++() {
    if (at_end_) {
        return *this;
    }
    if (side_ == Side::Buy) {
        if (price_ == book_->min_price_) {
            at_end_ = true;
            return *this;
        }
        --price_;
    } else {
        if (price_ == book_->max_price_) {
            at_end_ = true;
            return *this;
        }
        ++price_;
    }
    advance_to_active();
    return *this;
}

bool FlatOrderBook::LevelRange::iterator::operator==(const iterator& other) const {
    if (at_end_ && other.at_end_) {
        return true;
    }
    return book_ == other.book_ && side_ == other.side_ && price_ == other.price_ && at_end_ == other.at_end_;
}

bool FlatOrderBook::LevelRange::iterator::operator!=(const iterator& other) const {
    return !(*this == other);
}

void FlatOrderBook::LevelRange::iterator::advance_to_active() {
    if (book_ == nullptr || at_end_) {
        at_end_ = true;
        return;
    }

    while (book_->supports_price(price_)) {
        const auto& level = book_->level_at(side_, price_);
        if (!level.empty()) {
            view_ = LevelView{price_, std::addressof(level)};
            return;
        }
        if (side_ == Side::Buy) {
            if (price_ == book_->min_price_) {
                break;
            }
            --price_;
        } else {
            if (price_ == book_->max_price_) {
                break;
            }
            ++price_;
        }
    }
    at_end_ = true;
}

FlatOrderBook::LevelRange::LevelRange(const FlatOrderBook* book, Side side) : book_(book), side_(side) {}

FlatOrderBook::LevelRange::iterator FlatOrderBook::LevelRange::begin() const {
    if (book_ == nullptr) {
        return iterator{};
    }
    const auto best = side_ == Side::Buy ? book_->best_bid_ : book_->best_ask_;
    if (!best.has_value()) {
        return end();
    }
    return iterator(book_, side_, *best, false);
}

FlatOrderBook::LevelRange::iterator FlatOrderBook::LevelRange::end() const {
    return iterator(book_, side_, 0, true);
}

FlatOrderBook::FlatOrderBook(Price min_price, Price max_price)
    : min_price_(min_price), max_price_(max_price) {
    if (min_price_ <= 0 || max_price_ < min_price_) {
        throw std::invalid_argument("flat order book price range is invalid");
    }

    const auto count = static_cast<std::size_t>(max_price_ - min_price_ + 1);
    bids_.reserve(count);
    asks_.reserve(count);
    for (Price price = min_price_; price <= max_price_; ++price) {
        bids_.emplace_back(price);
        asks_.emplace_back(price);
    }
}

PriceLevel::iterator FlatOrderBook::add_resting_order(Order order) {
    const auto side = order.side;
    const auto price = order.price.value();
    if (!supports_price(price)) {
        throw std::out_of_range("flat order book price is outside configured range");
    }

    auto& level = level_at(side, price);
    auto order_position = level.add_order(std::move(order));
    locations_[order_position->id] = FlatOrderLocation{side, price, order_position};
    if (side == Side::Buy) {
        if (!best_bid_.has_value() || price > *best_bid_) {
            best_bid_ = price;
        }
    } else if (!best_ask_.has_value() || price < *best_ask_) {
        best_ask_ = price;
    }
    return order_position;
}

bool FlatOrderBook::cancel_order(OrderId id) {
    auto location_position = locations_.find(id);
    if (location_position == locations_.end()) {
        return false;
    }

    const auto location = location_position->second;
    auto& level = level_at(location.side, location.price);
    level.erase(location.iterator);
    locations_.erase(location_position);
    if (level.empty()) {
        refresh_best_after_remove(location.side, location.price);
    }
    return true;
}

bool FlatOrderBook::contains(OrderId id) const {
    return locations_.find(id) != locations_.end();
}

bool FlatOrderBook::reduce_order(OrderId id, Quantity new_remaining_quantity) {
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

bool FlatOrderBook::supports_price(Price price) const noexcept {
    return price >= min_price_ && price <= max_price_;
}

Order* FlatOrderBook::find_order(OrderId id) {
    auto location_position = locations_.find(id);
    if (location_position == locations_.end()) {
        return nullptr;
    }
    return std::addressof(*location_position->second.iterator);
}

const Order* FlatOrderBook::find_order(OrderId id) const {
    auto location_position = locations_.find(id);
    if (location_position == locations_.end()) {
        return nullptr;
    }
    return std::addressof(*location_position->second.iterator);
}

std::optional<Order> FlatOrderBook::snapshot_order(OrderId id) const {
    const auto* order = find_order(id);
    if (order == nullptr) {
        return std::nullopt;
    }
    return *order;
}

std::optional<Price> FlatOrderBook::best_bid() const {
    return best_bid_;
}

std::optional<Price> FlatOrderBook::best_ask() const {
    return best_ask_;
}

std::optional<Price> FlatOrderBook::spread() const {
    if (!best_bid_.has_value() || !best_ask_.has_value()) {
        return std::nullopt;
    }
    return *best_ask_ - *best_bid_;
}

PriceLevel* FlatOrderBook::best_bid_level() {
    if (!best_bid_.has_value()) {
        return nullptr;
    }
    return std::addressof(level_at(Side::Buy, *best_bid_));
}

PriceLevel* FlatOrderBook::best_ask_level() {
    if (!best_ask_.has_value()) {
        return nullptr;
    }
    return std::addressof(level_at(Side::Sell, *best_ask_));
}

const PriceLevel* FlatOrderBook::best_bid_level() const {
    if (!best_bid_.has_value()) {
        return nullptr;
    }
    return std::addressof(level_at(Side::Buy, *best_bid_));
}

const PriceLevel* FlatOrderBook::best_ask_level() const {
    if (!best_ask_.has_value()) {
        return nullptr;
    }
    return std::addressof(level_at(Side::Sell, *best_ask_));
}

void FlatOrderBook::remove_front(Side resting_side, Price price) {
    auto& level = level_at(resting_side, price);
    if (level.empty()) {
        throw std::logic_error("flat price level missing for front removal");
    }
    locations_.erase(level.front().id);
    level.pop_front();
    if (level.empty()) {
        refresh_best_after_remove(resting_side, price);
    }
}

FlatOrderBook::LevelRange FlatOrderBook::bid_levels() const {
    return LevelRange(this, Side::Buy);
}

FlatOrderBook::LevelRange FlatOrderBook::ask_levels() const {
    return LevelRange(this, Side::Sell);
}

Price FlatOrderBook::min_price() const noexcept {
    return min_price_;
}

Price FlatOrderBook::max_price() const noexcept {
    return max_price_;
}

std::size_t FlatOrderBook::index_for(Price price) const {
    return static_cast<std::size_t>(price - min_price_);
}

PriceLevel& FlatOrderBook::level_at(Side side, Price price) {
    return side == Side::Buy ? bids_[index_for(price)] : asks_[index_for(price)];
}

const PriceLevel& FlatOrderBook::level_at(Side side, Price price) const {
    return side == Side::Buy ? bids_[index_for(price)] : asks_[index_for(price)];
}

void FlatOrderBook::refresh_best_after_remove(Side side, Price removed_price) {
    if (side == Side::Buy) {
        if (!best_bid_.has_value() || *best_bid_ != removed_price) {
            return;
        }
        for (Price price = removed_price; price >= min_price_; --price) {
            if (!level_at(Side::Buy, price).empty()) {
                best_bid_ = price;
                return;
            }
            if (price == min_price_) {
                break;
            }
        }
        best_bid_.reset();
        return;
    }

    if (!best_ask_.has_value() || *best_ask_ != removed_price) {
        return;
    }
    for (Price price = removed_price; price <= max_price_; ++price) {
        if (!level_at(Side::Sell, price).empty()) {
            best_ask_ = price;
            return;
        }
        if (price == max_price_) {
            break;
        }
    }
    best_ask_.reset();
}

}  // namespace lob
