#include "lob/matching_engine.hpp"

#include <catch2/catch_template_test_macros.hpp>
#include <catch2/catch_test_macros.hpp>

using lob::Order;
using lob::OrderStatus;
using lob::Side;

TEMPLATE_TEST_CASE("limit orders rest and expose the top of book", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    auto ask = engine.submit_order(Order::limit(1, "seller", Side::Sell, 101, 10, 1));
    auto bid = engine.submit_order(Order::limit(2, "buyer", Side::Buy, 99, 5, 2));

    REQUIRE(ask.accepted);
    REQUIRE(bid.accepted);
    REQUIRE(ask.trades.empty());
    REQUIRE(bid.trades.empty());
    REQUIRE(engine.book().best_ask() == 101);
    REQUIRE(engine.book().best_bid() == 99);
    REQUIRE(engine.book().spread() == 2);
}

TEMPLATE_TEST_CASE("crossing limit orders execute at the resting price", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller", Side::Sell, 100, 10, 1)).accepted);
    auto result = engine.submit_order(Order::limit(2, "buyer", Side::Buy, 105, 4, 2));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 1);
    CHECK(result.trades[0].price == 100);
    CHECK(result.trades[0].quantity == 4);
    CHECK(result.order->status == OrderStatus::Filled);

    const auto* resting = engine.book().find_order(1);
    REQUIRE(resting != nullptr);
    CHECK(resting->remaining_quantity == 6);
    CHECK(resting->status == OrderStatus::PartiallyFilled);
}

TEMPLATE_TEST_CASE("aggressive limit order rests its unfilled remainder", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller", Side::Sell, 100, 5, 1)).accepted);
    auto result = engine.submit_order(Order::limit(2, "buyer", Side::Buy, 101, 8, 2));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 1);
    CHECK(result.trades[0].quantity == 5);
    CHECK(result.order->status == OrderStatus::PartiallyFilled);
    CHECK(result.order->remaining_quantity == 3);
    REQUIRE(engine.book().best_bid() == 101);
}

TEMPLATE_TEST_CASE("market order walks multiple price levels", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller a", Side::Sell, 100, 5, 1)).accepted);
    REQUIRE(engine.submit_order(Order::limit(2, "seller b", Side::Sell, 101, 7, 2)).accepted);

    auto result = engine.submit_order(Order::market(3, "buyer", Side::Buy, 9, 3));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 2);
    CHECK(result.trades[0].price == 100);
    CHECK(result.trades[0].quantity == 5);
    CHECK(result.trades[1].price == 101);
    CHECK(result.trades[1].quantity == 4);

    const auto* remaining = engine.book().find_order(2);
    REQUIRE(remaining != nullptr);
    CHECK(remaining->remaining_quantity == 3);
}

TEMPLATE_TEST_CASE("crossing limit order walks levels and rests remaining quantity", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller a", Side::Sell, 100, 5, 1)).accepted);
    REQUIRE(engine.submit_order(Order::limit(2, "seller b", Side::Sell, 101, 5, 2)).accepted);

    auto result = engine.submit_order(Order::limit(3, "buyer", Side::Buy, 102, 12, 3));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 2);
    CHECK(result.trades[0].quantity == 5);
    CHECK(result.trades[1].quantity == 5);
    CHECK(result.order->remaining_quantity == 2);
    REQUIRE(engine.book().best_bid() == 102);
}

TEMPLATE_TEST_CASE("cancel resting order removes it from the book", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "buyer", Side::Buy, 99, 10, 1)).accepted);
    auto result = engine.cancel_order(1, 2);

    REQUIRE(result.accepted);
    REQUIRE(result.order->status == OrderStatus::Cancelled);
    CHECK_FALSE(engine.book().best_bid().has_value());
    CHECK_FALSE(engine.cancel_order(1, 3).accepted);
}

TEMPLATE_TEST_CASE("cancel partially filled order removes only the remaining quantity", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller", Side::Sell, 100, 10, 1)).accepted);
    REQUIRE(engine.submit_order(Order::market(2, "buyer", Side::Buy, 4, 2)).accepted);

    auto result = engine.cancel_order(1, 3);

    REQUIRE(result.accepted);
    CHECK(result.order->remaining_quantity == 6);
    CHECK(result.order->status == OrderStatus::Cancelled);
    CHECK_FALSE(engine.book().best_ask().has_value());
}

TEMPLATE_TEST_CASE("modify price change loses time priority", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "buyer a", Side::Buy, 100, 1, 1)).accepted);
    REQUIRE(engine.submit_order(Order::limit(2, "buyer b", Side::Buy, 100, 1, 2)).accepted);
    REQUIRE(engine.modify_order(1, 99, 1, 3).accepted);
    REQUIRE(engine.modify_order(1, 100, 1, 4).accepted);

    auto result = engine.submit_order(Order::market(3, "seller", Side::Sell, 2, 5));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 2);
    CHECK(result.trades[0].buy_order_id == 2);
    CHECK(result.trades[1].buy_order_id == 1);
}

TEMPLATE_TEST_CASE("modify quantity reduction preserves time priority", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "buyer a", Side::Buy, 100, 5, 1)).accepted);
    REQUIRE(engine.submit_order(Order::limit(2, "buyer b", Side::Buy, 100, 5, 2)).accepted);
    REQUIRE(engine.modify_order(1, std::nullopt, 2, 3).accepted);

    auto result = engine.submit_order(Order::market(3, "seller", Side::Sell, 3, 4));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 2);
    CHECK(result.trades[0].buy_order_id == 1);
    CHECK(result.trades[0].quantity == 2);
    CHECK(result.trades[1].buy_order_id == 2);
    CHECK(result.trades[1].quantity == 1);
}

TEMPLATE_TEST_CASE("market order fills completely when liquidity is sufficient", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller", Side::Sell, 100, 5, 1)).accepted);
    auto result = engine.submit_order(Order::market(2, "buyer", Side::Buy, 5, 2));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 1);
    CHECK(result.order->status == OrderStatus::Filled);
    CHECK_FALSE(engine.book().best_ask().has_value());
}

TEMPLATE_TEST_CASE("external execute fully fills the named resting order", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller", Side::Sell, 100, 5, 1)).accepted);
    auto result = engine.external_execute(1, 5, 100, 2);

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 1);
    CHECK(result.trades[0].buy_order_id == 0);
    CHECK(result.trades[0].sell_order_id == 1);
    CHECK(result.trades[0].maker_order_id == 1);
    CHECK(result.trades[0].taker_order_id == 0);
    CHECK(result.trades[0].price == 100);
    CHECK(result.trades[0].quantity == 5);
    REQUIRE(result.order.has_value());
    CHECK(result.order->status == OrderStatus::Filled);
    CHECK(result.order->remaining_quantity == 0);
    CHECK_FALSE(engine.book().best_ask().has_value());
}

TEMPLATE_TEST_CASE("external execute partially fills the named resting order", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "buyer", Side::Buy, 99, 10, 1)).accepted);
    auto result = engine.external_execute(1, 4, 99, 2);

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 1);
    CHECK(result.trades[0].buy_order_id == 1);
    CHECK(result.trades[0].sell_order_id == 0);
    REQUIRE(result.order.has_value());
    CHECK(result.order->status == OrderStatus::PartiallyFilled);
    CHECK(result.order->remaining_quantity == 6);
    const auto* resting = engine.book().find_order(1);
    REQUIRE(resting != nullptr);
    CHECK(resting->remaining_quantity == 6);
    CHECK(resting->status == OrderStatus::PartiallyFilled);
}

TEMPLATE_TEST_CASE("external execute targets the named order inside a price level", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller a", Side::Sell, 100, 5, 1)).accepted);
    REQUIRE(engine.submit_order(Order::limit(2, "seller b", Side::Sell, 100, 7, 2)).accepted);
    auto result = engine.external_execute(2, 7, 100, 3);

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 1);
    CHECK(result.trades[0].sell_order_id == 2);
    CHECK(engine.book().find_order(2) == nullptr);
    const auto* front = engine.book().find_order(1);
    REQUIRE(front != nullptr);
    CHECK(front->remaining_quantity == 5);
    REQUIRE(engine.book().best_ask_level() != nullptr);
    CHECK(engine.book().best_ask_level()->front().id == 1);
}

TEMPLATE_TEST_CASE("external execute rejects missing or already closed orders", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    CHECK_FALSE(engine.external_execute(1, 1, 100, 1).accepted);
    REQUIRE(engine.submit_order(Order::limit(1, "seller", Side::Sell, 100, 3, 2)).accepted);
    REQUIRE(engine.external_execute(1, 3, 100, 3).accepted);

    auto result = engine.external_execute(1, 1, 100, 4);
    CHECK_FALSE(result.accepted);
    CHECK(result.reject_reason == "order is not active");
}

TEMPLATE_TEST_CASE("external execute rejects quantity mismatch without changing the book", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller", Side::Sell, 100, 3, 1)).accepted);
    auto result = engine.external_execute(1, 4, 100, 2);

    CHECK_FALSE(result.accepted);
    CHECK(result.reject_reason == "execution quantity exceeds remaining quantity");
    const auto* resting = engine.book().find_order(1);
    REQUIRE(resting != nullptr);
    CHECK(resting->remaining_quantity == 3);
    CHECK(resting->status == OrderStatus::New);
}

TEMPLATE_TEST_CASE("market order cancels unfilled remainder when liquidity is insufficient", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "seller", Side::Sell, 100, 5, 1)).accepted);
    auto result = engine.submit_order(Order::market(2, "buyer", Side::Buy, 8, 2));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 1);
    CHECK(result.order->status == OrderStatus::PartiallyFilled);
    CHECK(result.order->remaining_quantity == 3);
    CHECK_FALSE(engine.book().best_bid().has_value());
    CHECK_FALSE(engine.book().best_ask().has_value());
}

TEMPLATE_TEST_CASE("self trade prevention rejects the incoming order", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(1, "same owner", Side::Buy, 100, 5, 1)).accepted);
    auto result = engine.submit_order(Order::limit(2, "same owner", Side::Sell, 99, 5, 2));

    CHECK_FALSE(result.accepted);
    CHECK(result.trades.empty());
    REQUIRE(engine.book().best_bid() == 100);
}

TEMPLATE_TEST_CASE("orders with identical timestamp and price use order id as tie break", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    REQUIRE(engine.submit_order(Order::limit(20, "buyer b", Side::Buy, 100, 1, 1)).accepted);
    REQUIRE(engine.submit_order(Order::limit(10, "buyer a", Side::Buy, 100, 1, 1)).accepted);

    auto result = engine.submit_order(Order::market(30, "seller", Side::Sell, 2, 2));

    REQUIRE(result.accepted);
    REQUIRE(result.trades.size() == 2);
    CHECK(result.trades[0].buy_order_id == 10);
    CHECK(result.trades[1].buy_order_id == 20);
}

TEMPLATE_TEST_CASE("invalid order values are rejected deterministically", "", lob::MatchingEngine, lob::FlatMatchingEngine) {
    TestType engine;

    CHECK_FALSE(engine.submit_order(Order::limit(1, "buyer", Side::Buy, 100, 0, 1)).accepted);
    CHECK_FALSE(engine.submit_order(Order::limit(2, "buyer", Side::Buy, 0, 1, 1)).accepted);
    CHECK_FALSE(engine.submit_order(Order::market(3, "buyer", Side::Buy, 0, 1)).accepted);
}

TEST_CASE("flat order book rejects prices outside its configured range") {
    lob::FlatMatchingEngine engine(lob::FlatOrderBook(95, 105));

    CHECK(engine.submit_order(Order::limit(1, "buyer", Side::Buy, 100, 1, 1)).accepted);
    CHECK_FALSE(engine.submit_order(Order::limit(2, "buyer", Side::Buy, 94, 1, 2)).accepted);
    CHECK_FALSE(engine.submit_order(Order::limit(3, "seller", Side::Sell, 106, 1, 3)).accepted);

    REQUIRE(engine.book().best_bid() == 100);
}
