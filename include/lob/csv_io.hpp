#pragma once

#include "lob/matching_engine.hpp"
#include "lob/types.hpp"

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace lob {

enum class EventType {
    Submit,
    Cancel,
    Modify,
    ExternalExecute
};

struct OrderEvent {
    EventType event_type{EventType::Submit};
    Timestamp timestamp{};
    OrderId order_id{};
    std::optional<Side> side{};
    std::optional<OrderType> order_type{};
    std::optional<Price> price{};
    std::optional<Quantity> quantity{};
    std::string owner_id{};
    std::size_t line_number{};
};

std::vector<OrderEvent> read_order_events_csv(const std::filesystem::path& path);
std::vector<Trade> replay_order_events(const std::vector<OrderEvent>& events, MatchingEngine& engine);
void write_trades_csv(const std::filesystem::path& path, const std::vector<Trade>& trades);
void write_book_snapshot_csv(const std::filesystem::path& path, const MatchingEngine& engine);

}  // namespace lob
