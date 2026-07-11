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

TEST_CASE("csv replay supports external execute events") {
    const auto input_path = std::filesystem::temp_directory_path() / "lob_external_execute_orders.csv";
    const auto output_path = std::filesystem::temp_directory_path() / "lob_external_execute_trades.csv";

    {
        std::ofstream input(input_path);
        input << "timestamp,action,order_id,side,order_type,price,quantity,owner_id\n";
        input << "1,new,1,sell,limit,101,10,alpha\n";
        input << "2,external_execute,1,,,101,4,\n";
    }

    lob::MatchingEngine engine;
    const auto events = lob::read_order_events_csv(input_path);
    const auto trades = lob::replay_order_events(events, engine);
    lob::write_trades_csv(output_path, trades);

    CHECK(read_all(output_path) ==
          "timestamp,buy_order_id,sell_order_id,maker_order_id,taker_order_id,price,quantity\n"
          "2,0,1,1,0,101,4\n");
    const auto* resting = engine.book().find_order(1);
    REQUIRE(resting != nullptr);
    CHECK(resting->remaining_quantity == 6);
}
