#pragma once

#include "lob/price_level.hpp"
#include "lob/types.hpp"

#include <cstddef>
#include <iterator>
#include <optional>
#include <unordered_map>
#include <vector>

namespace lob {

struct FlatOrderLocation {
    Side side{Side::Buy};
    Price price{};
    PriceLevel::iterator iterator{};
};

class FlatOrderBook {
public:
    struct LevelView {
        Price price{};
        const PriceLevel* level{};
    };

    class LevelRange {
    public:
        class iterator {
        public:
            using iterator_category = std::forward_iterator_tag;
            using value_type = LevelView;
            using difference_type = std::ptrdiff_t;
            using pointer = const LevelView*;
            using reference = const LevelView&;

            iterator() = default;
            iterator(const FlatOrderBook* book, Side side, Price price, bool at_end);

            reference operator*() const;
            pointer operator->() const;
            iterator& operator++();
            bool operator==(const iterator& other) const;
            bool operator!=(const iterator& other) const;

        private:
            void advance_to_active();

            const FlatOrderBook* book_{};
            Side side_{Side::Buy};
            Price price_{};
            bool at_end_{true};
            LevelView view_{};
        };

        LevelRange() = default;
        LevelRange(const FlatOrderBook* book, Side side);

        iterator begin() const;
        iterator end() const;

    private:
        const FlatOrderBook* book_{};
        Side side_{Side::Buy};
    };

    explicit FlatOrderBook(Price min_price = 1, Price max_price = 200000);

    PriceLevel::iterator add_resting_order(Order order);

    bool cancel_order(OrderId id);
    bool contains(OrderId id) const;
    bool reduce_order(OrderId id, Quantity new_remaining_quantity);
    bool supports_price(Price price) const noexcept;

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

    LevelRange bid_levels() const;
    LevelRange ask_levels() const;

    Price min_price() const noexcept;
    Price max_price() const noexcept;

private:
    std::size_t index_for(Price price) const;
    PriceLevel& level_at(Side side, Price price);
    const PriceLevel& level_at(Side side, Price price) const;
    void refresh_best_after_remove(Side side, Price removed_price);

    Price min_price_{1};
    Price max_price_{200000};
    std::vector<PriceLevel> bids_{};
    std::vector<PriceLevel> asks_{};
    std::optional<Price> best_bid_{};
    std::optional<Price> best_ask_{};
    std::unordered_map<OrderId, FlatOrderLocation> locations_{};
};

}  // namespace lob
