#include "lob/csv_io.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

namespace lob {
namespace {

std::string trim(std::string value) {
    auto is_space = [](unsigned char character) {
        return std::isspace(character) != 0;
    };

    value.erase(value.begin(), std::find_if(value.begin(), value.end(), [&](unsigned char character) {
                    return !is_space(character);
                }));
    value.erase(std::find_if(value.rbegin(), value.rend(), [&](unsigned char character) {
                    return !is_space(character);
                }).base(),
                value.end());
    return value;
}

std::vector<std::string> split_csv_line(const std::string& line) {
    std::vector<std::string> fields;
    std::string field;
    std::stringstream stream(line);
    while (std::getline(stream, field, ',')) {
        fields.push_back(trim(field));
    }
    if (!line.empty() && line.back() == ',') {
        fields.emplace_back();
    }
    return fields;
}

std::uint64_t parse_u64(const std::string& value, const std::string& name, std::size_t line_number) {
    if (value.empty()) {
        throw std::runtime_error(name + " is missing on line " + std::to_string(line_number));
    }
    std::size_t consumed = 0;
    const auto parsed = std::stoull(value, &consumed);
    if (consumed != value.size()) {
        throw std::runtime_error(name + " is invalid on line " + std::to_string(line_number));
    }
    return parsed;
}

std::int64_t parse_i64(const std::string& value, const std::string& name, std::size_t line_number) {
    if (value.empty()) {
        throw std::runtime_error(name + " is missing on line " + std::to_string(line_number));
    }
    std::size_t consumed = 0;
    const auto parsed = std::stoll(value, &consumed);
    if (consumed != value.size()) {
        throw std::runtime_error(name + " is invalid on line " + std::to_string(line_number));
    }
    return parsed;
}

EventType parse_event_type(const std::string& value, std::size_t line_number) {
    if (value == "new") {
        return EventType::Submit;
    }
    if (value == "cancel") {
        return EventType::Cancel;
    }
    if (value == "modify") {
        return EventType::Modify;
    }
    if (value == "external_execute") {
        return EventType::ExternalExecute;
    }
    throw std::runtime_error("action is invalid on line " + std::to_string(line_number));
}

Side parse_side(const std::string& value, std::size_t line_number) {
    if (value == "buy") {
        return Side::Buy;
    }
    if (value == "sell") {
        return Side::Sell;
    }
    throw std::runtime_error("side is invalid on line " + std::to_string(line_number));
}

OrderType parse_order_type(const std::string& value, std::size_t line_number) {
    if (value == "limit") {
        return OrderType::Limit;
    }
    if (value == "market") {
        return OrderType::Market;
    }
    throw std::runtime_error("order type is invalid on line " + std::to_string(line_number));
}

std::optional<Price> parse_optional_price(const std::string& value, std::size_t line_number) {
    if (value.empty()) {
        return std::nullopt;
    }
    return parse_i64(value, "price", line_number);
}

std::optional<Quantity> parse_optional_quantity(const std::string& value, std::size_t line_number) {
    if (value.empty()) {
        return std::nullopt;
    }
    return parse_i64(value, "quantity", line_number);
}

Order make_order(const OrderEvent& event) {
    if (!event.side.has_value()) {
        throw std::runtime_error("side is missing on line " + std::to_string(event.line_number));
    }
    if (!event.order_type.has_value()) {
        throw std::runtime_error("order type is missing on line " + std::to_string(event.line_number));
    }
    if (!event.quantity.has_value()) {
        throw std::runtime_error("quantity is missing on line " + std::to_string(event.line_number));
    }

    if (*event.order_type == OrderType::Limit) {
        if (!event.price.has_value()) {
            throw std::runtime_error("price is missing on line " + std::to_string(event.line_number));
        }
        return Order::limit(event.order_id,
                            event.owner_id,
                            *event.side,
                            *event.price,
                            *event.quantity,
                            event.timestamp);
    }

    return Order::market(event.order_id, event.owner_id, *event.side, *event.quantity, event.timestamp);
}

}  // namespace

std::vector<OrderEvent> read_order_events_csv(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("could not open input csv");
    }

    std::string line;
    if (!std::getline(input, line)) {
        return {};
    }

    std::vector<OrderEvent> events;
    std::size_t line_number = 1;
    while (std::getline(input, line)) {
        ++line_number;
        if (trim(line).empty()) {
            continue;
        }

        const auto fields = split_csv_line(line);
        if (fields.size() != 8) {
            throw std::runtime_error("expected eight columns on line " + std::to_string(line_number));
        }

        OrderEvent event;
        event.timestamp = parse_i64(fields[0], "timestamp", line_number);
        event.event_type = parse_event_type(fields[1], line_number);
        event.order_id = parse_u64(fields[2], "order id", line_number);
        event.line_number = line_number;

        if (!fields[3].empty()) {
            event.side = parse_side(fields[3], line_number);
        }
        if (!fields[4].empty()) {
            event.order_type = parse_order_type(fields[4], line_number);
        }
        event.price = parse_optional_price(fields[5], line_number);
        event.quantity = parse_optional_quantity(fields[6], line_number);
        event.owner_id = fields[7];

        events.push_back(std::move(event));
    }

    return events;
}

std::vector<Trade> replay_order_events(const std::vector<OrderEvent>& events, MatchingEngine& engine) {
    std::vector<Trade> trades;
    for (const auto& event : events) {
        ExecutionResult result;

        switch (event.event_type) {
            case EventType::Submit:
                result = engine.submit_order(make_order(event));
                break;
            case EventType::Cancel:
                result = engine.cancel_order(event.order_id, event.timestamp);
                break;
            case EventType::Modify:
                if (!event.quantity.has_value()) {
                    throw std::runtime_error("quantity is missing on line " + std::to_string(event.line_number));
                }
                result = engine.modify_order(event.order_id, event.price, *event.quantity, event.timestamp);
                break;
            case EventType::ExternalExecute:
                if (!event.price.has_value()) {
                    throw std::runtime_error("price is missing on line " + std::to_string(event.line_number));
                }
                if (!event.quantity.has_value()) {
                    throw std::runtime_error("quantity is missing on line " + std::to_string(event.line_number));
                }
                result = engine.external_execute(event.order_id, *event.quantity, *event.price, event.timestamp);
                break;
        }

        if (!result.accepted) {
            throw std::runtime_error("event rejected on line " + std::to_string(event.line_number) + ": " + result.reject_reason);
        }

        trades.insert(trades.end(), result.trades.begin(), result.trades.end());
    }
    return trades;
}

void write_trades_csv(const std::filesystem::path& path, const std::vector<Trade>& trades) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not open output csv");
    }

    output << "timestamp,buy_order_id,sell_order_id,maker_order_id,taker_order_id,price,quantity\n";
    for (const auto& trade : trades) {
        output << trade.timestamp << ','
               << trade.buy_order_id << ','
               << trade.sell_order_id << ','
               << trade.maker_order_id << ','
               << trade.taker_order_id << ','
               << trade.price << ','
               << trade.quantity << '\n';
    }
}

void write_book_snapshot_csv(const std::filesystem::path& path, const MatchingEngine& engine) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not open output csv");
    }

    output << "side,price,order_id,remaining_quantity,owner_id,timestamp\n";
    for (const auto& [price, level] : engine.book().bid_levels()) {
        for (const auto& order : level) {
            output << "buy," << price << ',' << order.id << ',' << order.remaining_quantity << ','
                   << order.owner_id << ',' << order.timestamp << '\n';
        }
    }
    for (const auto& [price, level] : engine.book().ask_levels()) {
        for (const auto& order : level) {
            output << "sell," << price << ',' << order.id << ',' << order.remaining_quantity << ','
                   << order.owner_id << ',' << order.timestamp << '\n';
        }
    }
}

}  // namespace lob
