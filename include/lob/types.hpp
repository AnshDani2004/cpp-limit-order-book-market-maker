#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace lob {

using OrderId = std::uint64_t;
using Price = std::int64_t;
using Quantity = std::int64_t;
using Timestamp = std::int64_t;

enum class Side {
    Buy,
    Sell
};

enum class OrderType {
    Limit,
    Market
};

enum class OrderStatus {
    New,
    PartiallyFilled,
    Filled,
    Cancelled
};

struct Order {
    OrderId id{};
    std::string owner_id{};
    Side side{Side::Buy};
    OrderType type{OrderType::Limit};
    std::optional<Price> price{};
    Quantity quantity{};
    Quantity remaining_quantity{};
    Timestamp timestamp{};
    OrderStatus status{OrderStatus::New};

    static Order limit(OrderId id,
                       std::string owner_id,
                       Side side,
                       Price price,
                       Quantity quantity,
                       Timestamp timestamp);

    static Order market(OrderId id,
                        std::string owner_id,
                        Side side,
                        Quantity quantity,
                        Timestamp timestamp);
};

struct Trade {
    OrderId buy_order_id{};
    OrderId sell_order_id{};
    OrderId maker_order_id{};
    OrderId taker_order_id{};
    Price price{};
    Quantity quantity{};
    Timestamp timestamp{};
};

Side opposite(Side side);

std::string to_string(Side side);
std::string to_string(OrderType type);
std::string to_string(OrderStatus status);

}  // namespace lob
