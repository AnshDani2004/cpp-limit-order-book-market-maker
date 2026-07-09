#include "lob/market_maker_simulation.hpp"

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cstddef>
#include <utility>

namespace {

lob::MarketMakerSimulationConfig make_config(lob::RegimeConfig regime) {
    lob::MarketMakerSimulationConfig config;
    config.regime = std::move(regime);
    config.curve_sample_stride = 25;
    return config;
}

void check_matching_summary(const lob::MarketMakerSummary& left, const lob::MarketMakerSummary& right) {
    CHECK(left.strategy_name == right.strategy_name);
    CHECK(left.regime_name == right.regime_name);
    CHECK(left.seed == right.seed);
    CHECK(left.events == right.events);
    CHECK(left.initial_reference_mid == Catch::Approx(right.initial_reference_mid));
    CHECK(left.final_reference_mid == Catch::Approx(right.final_reference_mid));
    CHECK(left.fill_rate == Catch::Approx(right.fill_rate));
    CHECK(left.gross_spread_capture == Catch::Approx(right.gross_spread_capture));
    CHECK(left.inventory_pnl == Catch::Approx(right.inventory_pnl));
    CHECK(left.inventory_pnl_from_marks == Catch::Approx(right.inventory_pnl_from_marks));
    CHECK(left.inventory_pnl_mark_error == Catch::Approx(right.inventory_pnl_mark_error));
    CHECK(left.gross_identity_error == Catch::Approx(right.gross_identity_error));
    CHECK(left.net_identity_error == Catch::Approx(right.net_identity_error));
    CHECK(left.adverse_selection_cost == Catch::Approx(right.adverse_selection_cost));
    CHECK(left.fee_pnl == Catch::Approx(right.fee_pnl));
    CHECK(left.net_pnl_after_fees == Catch::Approx(right.net_pnl_after_fees));
    CHECK(left.maximum_drawdown == Catch::Approx(right.maximum_drawdown));
    CHECK(left.inventory_variance == Catch::Approx(right.inventory_variance));
    CHECK(left.final_inventory == right.final_inventory);
    CHECK(left.maker_fills == right.maker_fills);
    CHECK(left.taker_fills == right.taker_fills);
    CHECK(left.market_maker_buy_fills == right.market_maker_buy_fills);
    CHECK(left.market_maker_sell_fills == right.market_maker_sell_fills);
    CHECK(left.market_maker_filled_quantity == right.market_maker_filled_quantity);
    CHECK(left.market_maker_buy_quantity == right.market_maker_buy_quantity);
    CHECK(left.market_maker_sell_quantity == right.market_maker_sell_quantity);
    CHECK(left.market_maker_posted_quantity == right.market_maker_posted_quantity);
    CHECK(left.external_limit_buy_orders == right.external_limit_buy_orders);
    CHECK(left.external_limit_sell_orders == right.external_limit_sell_orders);
    CHECK(left.external_market_buy_orders == right.external_market_buy_orders);
    CHECK(left.external_market_sell_orders == right.external_market_sell_orders);
    CHECK(left.external_price_modify_buy_orders == right.external_price_modify_buy_orders);
    CHECK(left.external_price_modify_sell_orders == right.external_price_modify_sell_orders);
    CHECK(left.external_limit_buy_quantity == right.external_limit_buy_quantity);
    CHECK(left.external_limit_sell_quantity == right.external_limit_sell_quantity);
    CHECK(left.external_market_buy_quantity == right.external_market_buy_quantity);
    CHECK(left.external_market_sell_quantity == right.external_market_sell_quantity);
    CHECK(left.external_price_modify_buy_quantity == right.external_price_modify_buy_quantity);
    CHECK(left.external_price_modify_sell_quantity == right.external_price_modify_sell_quantity);
    CHECK(left.average_external_limit_buy_offset == Catch::Approx(right.average_external_limit_buy_offset));
    CHECK(left.average_external_limit_sell_offset == Catch::Approx(right.average_external_limit_sell_offset));
    CHECK(left.average_external_price_modify_buy_offset ==
          Catch::Approx(right.average_external_price_modify_buy_offset));
    CHECK(left.average_external_price_modify_sell_offset ==
          Catch::Approx(right.average_external_price_modify_sell_offset));
    CHECK(left.external_rejects == right.external_rejects);
    CHECK(left.quote_refreshes == right.quote_refreshes);
    CHECK(left.symmetric_quote_refreshes == right.symmetric_quote_refreshes);
    CHECK(left.bid_clip_events == right.bid_clip_events);
    CHECK(left.ask_clip_events == right.ask_clip_events);
    CHECK(left.average_bid_distance == Catch::Approx(right.average_bid_distance));
    CHECK(left.average_ask_distance == Catch::Approx(right.average_ask_distance));
    CHECK(left.average_abs_quote_asymmetry == Catch::Approx(right.average_abs_quote_asymmetry));
    CHECK(left.max_abs_quote_asymmetry == Catch::Approx(right.max_abs_quote_asymmetry));
    CHECK(left.reconciliation_passed == right.reconciliation_passed);
}

}  // namespace

TEST_CASE("naive symmetric strategy reconciles in every Stage 3 regime") {
    const auto regimes = lob::default_regimes(2000);

    for (const auto& regime : regimes) {
        const auto result = lob::run_naive_symmetric_strategy(make_config(regime));

        CHECK(result.summary.strategy_name == "naive symmetric");
        CHECK(result.summary.regime_name == regime.name);
        CHECK(result.summary.reconciliation_passed);
        CHECK(result.summary.market_maker_posted_quantity > 0);
        CHECK(result.summary.market_maker_filled_quantity > 0);
        CHECK(result.summary.market_maker_buy_quantity + result.summary.market_maker_sell_quantity ==
              result.summary.market_maker_filled_quantity);
        CHECK(result.summary.fill_rate > 0.0);
        CHECK(result.summary.maker_fills > 0);
        CHECK(result.summary.taker_fills == 0);
        CHECK(result.summary.quote_refreshes > 0);
        CHECK_FALSE(result.curve.empty());
    }
}

TEST_CASE("naive symmetric strategy is deterministic for a fixed seed") {
    auto regime = lob::default_regimes(1500).front();
    auto config = make_config(regime);

    const auto first = lob::run_naive_symmetric_strategy(config);
    const auto second = lob::run_naive_symmetric_strategy(config);

    check_matching_summary(first.summary, second.summary);
    REQUIRE(first.curve.size() == second.curve.size());

    for (std::size_t index = 0; index < first.curve.size(); ++index) {
        CHECK(first.curve[index].strategy_name == second.curve[index].strategy_name);
        CHECK(first.curve[index].regime_name == second.curve[index].regime_name);
        CHECK(first.curve[index].event_index == second.curve[index].event_index);
        CHECK(first.curve[index].reference_mid == Catch::Approx(second.curve[index].reference_mid));
        CHECK(first.curve[index].cash == Catch::Approx(second.curve[index].cash));
        CHECK(first.curve[index].inventory == second.curve[index].inventory);
        CHECK(first.curve[index].net_pnl_after_fees == Catch::Approx(second.curve[index].net_pnl_after_fees));
    }
}
