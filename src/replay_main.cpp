#include "lob/csv_io.hpp"
#include "lob/matching_engine.hpp"

#include <exception>
#include <filesystem>
#include <iostream>

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: orderbook_replay input.csv output.csv\n";
        return 1;
    }

    try {
        lob::MatchingEngine engine;
        const auto events = lob::read_order_events_csv(std::filesystem::path(argv[1]));
        const auto trades = lob::replay_order_events(events, engine);
        lob::write_trades_csv(std::filesystem::path(argv[2]), trades);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }

    return 0;
}
