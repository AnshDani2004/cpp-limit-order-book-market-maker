#pragma once

#include "lob/types.hpp"

#include <cstddef>
#include <list>

namespace lob {

class PriceLevel {
public:
    using Orders = std::list<Order>;
    using iterator = Orders::iterator;
    using const_iterator = Orders::const_iterator;

    PriceLevel() = default;
    explicit PriceLevel(Price price);

    iterator add_order(Order order);
    void erase(iterator position);
    void pop_front();

    Order& front();
    const Order& front() const;

    bool empty() const noexcept;
    std::size_t size() const noexcept;
    Price price() const noexcept;

    iterator begin() noexcept;
    iterator end() noexcept;
    const_iterator begin() const noexcept;
    const_iterator end() const noexcept;

private:
    static bool has_higher_priority(const Order& left, const Order& right);

    Price price_{};
    Orders orders_{};
};

}  // namespace lob
