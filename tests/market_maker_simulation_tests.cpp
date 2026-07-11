#include "lob/market_maker_simulation.hpp"

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cstddef>
#include <cstdlib>
#include <stdexcept>
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
    CHECK(left.external_flow_profile == right.external_flow_profile);
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
    CHECK(left.terminal_liquidation_cost == Catch::Approx(right.terminal_liquidation_cost));
    CHECK(left.terminal_inventory_penalty == Catch::Approx(right.terminal_inventory_penalty));
    CHECK(left.risk_adjusted_pnl == Catch::Approx(right.risk_adjusted_pnl));
    CHECK(left.maximum_drawdown == Catch::Approx(right.maximum_drawdown));
    CHECK(left.inventory_variance == Catch::Approx(right.inventory_variance));
    CHECK(left.pre_liquidation_inventory == right.pre_liquidation_inventory);
    CHECK(left.final_inventory == right.final_inventory);
    CHECK(left.terminal_liquidation_quantity == right.terminal_liquidation_quantity);
    CHECK(left.terminal_liquidation_residual_inventory == right.terminal_liquidation_residual_inventory);
    CHECK(left.maker_fills == right.maker_fills);
    CHECK(left.taker_fills == right.taker_fills);
    CHECK(left.passive_taker_fills == right.passive_taker_fills);
    CHECK(left.terminal_liquidation_trades == right.terminal_liquidation_trades);
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
    CHECK(left.hard_cap_bid_blocks == right.hard_cap_bid_blocks);
    CHECK(left.hard_cap_ask_blocks == right.hard_cap_ask_blocks);
    CHECK(left.average_bid_distance == Catch::Approx(right.average_bid_distance));
    CHECK(left.average_ask_distance == Catch::Approx(right.average_ask_distance));
    CHECK(left.average_abs_quote_asymmetry == Catch::Approx(right.average_abs_quote_asymmetry));
    CHECK(left.max_abs_quote_asymmetry == Catch::Approx(right.max_abs_quote_asymmetry));
    CHECK(left.reconciliation_passed == right.reconciliation_passed);
}

void check_matching_adverse_selection_split(const std::vector<lob::MarketMakerAdverseSelectionSplit>& left,
                                            const std::vector<lob::MarketMakerAdverseSelectionSplit>& right) {
    REQUIRE(left.size() == right.size());
    for (std::size_t index = 0; index < left.size(); ++index) {
        CHECK(left[index].strategy_name == right[index].strategy_name);
        CHECK(left[index].regime_name == right[index].regime_name);
        CHECK(left[index].group_name == right[index].group_name);
        CHECK(left[index].maker_fills == right[index].maker_fills);
        CHECK(left[index].maker_quantity == right[index].maker_quantity);
        CHECK(left[index].signed_markout == Catch::Approx(right[index].signed_markout));
        CHECK(left[index].average_markout_per_unit == Catch::Approx(right[index].average_markout_per_unit));
        CHECK(left[index].adverse_selection_cost == Catch::Approx(right[index].adverse_selection_cost));
        CHECK(left[index].average_adverse_selection_cost_per_unit ==
              Catch::Approx(right[index].average_adverse_selection_cost_per_unit));
        CHECK(left[index].adverse_selection_cost_share == Catch::Approx(right[index].adverse_selection_cost_share));
        CHECK(left[index].total_adverse_selection_cost == Catch::Approx(right[index].total_adverse_selection_cost));
    }
}

}  // namespace

TEST_CASE("risk controls block only the side that would exceed the hard cap") {
    lob::RiskControlConfig controls;
    controls.enabled = true;
    controls.inventory_cap = 100;

    CHECK(lob::risk_control_allows_bid(controls, 90, 10));
    CHECK_FALSE(lob::risk_control_allows_bid(controls, 91, 10));
    CHECK(lob::risk_control_allows_ask(controls, -90, 10));
    CHECK_FALSE(lob::risk_control_allows_ask(controls, -91, 10));

    controls.enabled = false;
    CHECK(lob::risk_control_allows_bid(controls, 1000, 10));
    CHECK(lob::risk_control_allows_ask(controls, -1000, 10));
}

TEST_CASE("risk controls add soft quote skew before the hard cap") {
    lob::RiskControlConfig controls;
    controls.enabled = true;
    controls.inventory_cap = 100;
    controls.soft_start_fraction = 0.50;
    controls.soft_penalty_max_skew_ticks = 20.0;

    CHECK(lob::risk_control_soft_skew_ticks(controls, 50) == Catch::Approx(0.0));
    CHECK(lob::risk_control_soft_skew_ticks(controls, 75) == Catch::Approx(5.0));
    CHECK(lob::risk_control_soft_skew_ticks(controls, -75) == Catch::Approx(-5.0));
    CHECK(lob::risk_control_soft_skew_ticks(controls, 100) == Catch::Approx(20.0));
}

TEST_CASE("terminal liquidation cost penalty and risk adjusted PnL are explicit") {
    lob::RiskControlConfig controls;
    controls.enabled = true;
    controls.terminal_inventory_penalty_per_unit = 0.50;
    controls.risk_denominator_floor = 1.0;

    CHECK(lob::terminal_liquidation_cost(lob::FillSide::Sell, 100.0, 98.0, 10) == Catch::Approx(20.0));
    CHECK(lob::terminal_liquidation_cost(lob::FillSide::Buy, 100.0, 103.0, 10) == Catch::Approx(30.0));
    CHECK(lob::terminal_liquidation_cost(lob::FillSide::Sell, 100.0, 101.0, 10) == Catch::Approx(-10.0));
    CHECK(lob::terminal_inventory_penalty(controls, -30) == Catch::Approx(15.0));
    CHECK(lob::risk_adjusted_pnl(100.0, 15.0, 20.0, controls.risk_denominator_floor) == Catch::Approx(4.25));
    CHECK(lob::risk_adjusted_pnl(100.0, 15.0, 0.0, controls.risk_denominator_floor) == Catch::Approx(85.0));
}

TEST_CASE("risk controlled terminal liquidation closes residual inventory") {
    auto regime = lob::default_regimes(5000).front();
    auto config = make_config(regime);
    config.risk_controls.enabled = true;
    config.risk_controls.inventory_cap = 500;
    config.risk_controls.soft_start_fraction = 0.50;
    config.risk_controls.soft_penalty_max_skew_ticks = 20.0;
    config.risk_controls.terminal_liquidation = true;
    config.risk_controls.terminal_inventory_penalty_per_unit = 0.50;

    const auto result = lob::run_naive_symmetric_strategy(config);

    CHECK(result.summary.reconciliation_passed);
    CHECK(result.summary.pre_liquidation_inventory != 0);
    CHECK(result.summary.terminal_liquidation_quantity ==
          static_cast<lob::Quantity>(std::abs(result.summary.pre_liquidation_inventory)));
    CHECK(result.summary.final_inventory == 0);
    CHECK(result.summary.terminal_liquidation_residual_inventory == 0);
    CHECK(result.summary.taker_fills > 0);
    CHECK(result.summary.passive_taker_fills == 0);
    CHECK(result.summary.terminal_liquidation_trades == result.summary.taker_fills);
    CHECK(result.terminal_liquidation_trades.size() == result.summary.terminal_liquidation_trades);
    CHECK(result.summary.terminal_inventory_penalty ==
          Catch::Approx(0.50 * static_cast<double>(std::abs(result.summary.pre_liquidation_inventory))));

    lob::Quantity ladder_quantity = 0;
    double ladder_cost = 0.0;
    for (const auto& level : result.terminal_liquidation_levels) {
        CHECK(level.displayed_quantity_before >= level.filled_quantity);
        ladder_quantity += level.filled_quantity;
        ladder_cost += level.liquidation_cost;
    }
    CHECK_FALSE(result.terminal_liquidation_levels.empty());
    CHECK(ladder_quantity == result.summary.terminal_liquidation_quantity);
    CHECK(ladder_cost == Catch::Approx(result.summary.terminal_liquidation_cost));

    lob::Quantity trade_quantity = 0;
    double trade_cost = 0.0;
    for (const auto& trade : result.terminal_liquidation_trades) {
        trade_quantity += trade.quantity;
        trade_cost += trade.liquidation_cost;
    }
    CHECK(trade_quantity == result.summary.terminal_liquidation_quantity);
    CHECK(trade_cost == Catch::Approx(result.summary.terminal_liquidation_cost));
}

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
        CHECK(result.adverse_selection_split.size() == 3);
    }
}

TEST_CASE("avellaneda stoikov strategy reconciles in every Stage 3 regime") {
    const auto regimes = lob::default_regimes(2000);

    for (const auto& regime : regimes) {
        const auto result = lob::run_avellaneda_stoikov_strategy(make_config(regime));

        CHECK(result.summary.strategy_name == "avellaneda stoikov");
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
        CHECK(result.adverse_selection_split.size() == 3);
    }
}

TEST_CASE("calibrated avellaneda stoikov strategy reconciles in every Stage 4B regime") {
    const auto regimes = lob::default_regimes(2000);

    for (const auto& regime : regimes) {
        const auto result = lob::run_calibrated_avellaneda_stoikov_strategy(make_config(regime));

        CHECK(result.summary.strategy_name == "avellaneda stoikov calibrated");
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
        CHECK(result.adverse_selection_split.size() == 3);
    }
}

TEST_CASE("calibrated avellaneda stoikov validates its configured fill decay") {
    auto regime = lob::default_regimes(2000).front();
    auto config = make_config(regime);
    config.calibrated_avellaneda_stoikov.fill_decay = 0.0;

    CHECK_THROWS_AS(lob::run_calibrated_avellaneda_stoikov_strategy(config), std::invalid_argument);
}

TEST_CASE("ITCH calibrated external flow keeps Stage 4A mix beside the hand chosen profile") {
    auto regime = lob::default_regimes(8000).front();

    auto hand_config = make_config(regime);
    const auto hand = lob::run_naive_symmetric_strategy(hand_config);

    auto calibrated_config = make_config(regime);
    calibrated_config.external_flow_profile = lob::ExternalFlowProfile::ItchCalibrated;
    const auto calibrated = lob::run_naive_symmetric_strategy(calibrated_config);

    const auto hand_market_orders =
        hand.summary.external_market_buy_orders + hand.summary.external_market_sell_orders;
    const auto calibrated_market_orders =
        calibrated.summary.external_market_buy_orders + calibrated.summary.external_market_sell_orders;
    const auto hand_limit_orders =
        hand.summary.external_limit_buy_orders + hand.summary.external_limit_sell_orders;
    const auto calibrated_limit_orders =
        calibrated.summary.external_limit_buy_orders + calibrated.summary.external_limit_sell_orders;
    const auto hand_limit_quantity =
        hand.summary.external_limit_buy_quantity + hand.summary.external_limit_sell_quantity;
    const auto calibrated_limit_quantity =
        calibrated.summary.external_limit_buy_quantity + calibrated.summary.external_limit_sell_quantity;

    REQUIRE(hand_limit_orders > 0);
    REQUIRE(calibrated_limit_orders > 0);
    CHECK(hand.summary.external_flow_profile == "hand_chosen");
    CHECK(calibrated.summary.external_flow_profile == "itch_calibrated");
    CHECK(lob::external_flow_profile_name(lob::ExternalFlowProfile::ItchCalibrated) == "itch_calibrated");
    CHECK(calibrated.summary.reconciliation_passed);
    CHECK(calibrated_market_orders * 10 < hand_market_orders);
    CHECK(static_cast<double>(calibrated_limit_quantity) / static_cast<double>(calibrated_limit_orders) >
          10.0 * static_cast<double>(hand_limit_quantity) / static_cast<double>(hand_limit_orders));
}

TEST_CASE("avellaneda stoikov adverse selection split reconciles to maker fill totals") {
    auto regime = lob::default_regimes(2000).front();
    auto config = make_config(regime);
    const auto result = lob::run_avellaneda_stoikov_strategy(config);

    REQUIRE(result.adverse_selection_split.size() == 3);

    std::size_t maker_fills = 0;
    lob::Quantity maker_quantity = 0;
    double adverse_selection_cost = 0.0;
    for (const auto& split : result.adverse_selection_split) {
        maker_fills += split.maker_fills;
        maker_quantity += split.maker_quantity;
        adverse_selection_cost += split.adverse_selection_cost;
        if (split.maker_quantity > 0) {
            CHECK(split.average_markout_per_unit ==
                  Catch::Approx(split.signed_markout / static_cast<double>(split.maker_quantity)));
            CHECK(split.average_adverse_selection_cost_per_unit ==
                  Catch::Approx(split.adverse_selection_cost / static_cast<double>(split.maker_quantity)));
        }
    }

    CHECK(maker_fills == result.summary.maker_fills);
    CHECK(maker_quantity == result.summary.market_maker_filled_quantity);
    CHECK(adverse_selection_cost == Catch::Approx(result.summary.adverse_selection_cost));
}

TEST_CASE("naive symmetric strategy is deterministic for a fixed seed") {
    auto regime = lob::default_regimes(1500).front();
    auto config = make_config(regime);

    const auto first = lob::run_naive_symmetric_strategy(config);
    const auto second = lob::run_naive_symmetric_strategy(config);

    check_matching_summary(first.summary, second.summary);
    check_matching_adverse_selection_split(first.adverse_selection_split, second.adverse_selection_split);
    REQUIRE(first.curve.size() == second.curve.size());

    for (std::size_t index = 0; index < first.curve.size(); ++index) {
        CHECK(first.curve[index].strategy_name == second.curve[index].strategy_name);
        CHECK(first.curve[index].regime_name == second.curve[index].regime_name);
        CHECK(first.curve[index].event_index == second.curve[index].event_index);
        CHECK(first.curve[index].time_remaining == Catch::Approx(second.curve[index].time_remaining));
        CHECK(first.curve[index].reference_mid == Catch::Approx(second.curve[index].reference_mid));
        CHECK(first.curve[index].reservation_price == Catch::Approx(second.curve[index].reservation_price));
        CHECK(first.curve[index].reservation_skew == Catch::Approx(second.curve[index].reservation_skew));
        CHECK(first.curve[index].cash == Catch::Approx(second.curve[index].cash));
        CHECK(first.curve[index].inventory == second.curve[index].inventory);
        CHECK(first.curve[index].net_pnl_after_fees == Catch::Approx(second.curve[index].net_pnl_after_fees));
    }
}

TEST_CASE("avellaneda stoikov strategy is deterministic for a fixed seed") {
    auto regime = lob::default_regimes(1500).front();
    auto config = make_config(regime);

    const auto first = lob::run_avellaneda_stoikov_strategy(config);
    const auto second = lob::run_avellaneda_stoikov_strategy(config);

    check_matching_summary(first.summary, second.summary);
    check_matching_adverse_selection_split(first.adverse_selection_split, second.adverse_selection_split);
    REQUIRE(first.curve.size() == second.curve.size());

    for (std::size_t index = 0; index < first.curve.size(); ++index) {
        CHECK(first.curve[index].strategy_name == second.curve[index].strategy_name);
        CHECK(first.curve[index].regime_name == second.curve[index].regime_name);
        CHECK(first.curve[index].event_index == second.curve[index].event_index);
        CHECK(first.curve[index].time_remaining == Catch::Approx(second.curve[index].time_remaining));
        CHECK(first.curve[index].reference_mid == Catch::Approx(second.curve[index].reference_mid));
        CHECK(first.curve[index].reservation_price == Catch::Approx(second.curve[index].reservation_price));
        CHECK(first.curve[index].reservation_skew == Catch::Approx(second.curve[index].reservation_skew));
        CHECK(first.curve[index].cash == Catch::Approx(second.curve[index].cash));
        CHECK(first.curve[index].inventory == second.curve[index].inventory);
        CHECK(first.curve[index].net_pnl_after_fees == Catch::Approx(second.curve[index].net_pnl_after_fees));
    }
}
