#include "lob/csv_io.hpp"

#include <catch2/catch_test_macros.hpp>

#include <filesystem>
#include <fstream>
#include <sstream>

namespace {

std::string read_all(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

}  // namespace

TEST_CASE("csv replay produces the checked expected trades") {
    lob::MatchingEngine engine;
    const auto events = lob::read_order_events_csv("tests/fixtures/orders.csv");
    const auto trades = lob::replay_order_events(events, engine);

    const auto output_path = std::filesystem::temp_directory_path() / "lob_actual_trades.csv";
    lob::write_trades_csv(output_path, trades);

    CHECK(read_all(output_path) == read_all("tests/fixtures/expected_trades.csv"));
}
