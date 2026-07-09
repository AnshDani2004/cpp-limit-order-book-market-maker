#pragma once

#include "lob/simulation.hpp"
#include "lob/types.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace lob {

struct NaiveSymmetricConfig {
    Price half_spread_ticks{5};
    Quantity quote_size{10};
    std::size_t refresh_cadence{10};
};

struct MarketMakerSimulationConfig {
    RegimeConfig regime{};
    NaiveSymmetricConfig naive{};
    std::size_t markout_horizon{50};
    std::size_t curve_sample_stride{100};
};

struct MarketMakerSummary {
    std::string strategy_name{};
    std::string regime_name{};
    std::uint64_t seed{};
    std::size_t events{};
    double initial_reference_mid{};
    double final_reference_mid{};
    double fill_rate{};
    double gross_spread_capture{};
    double inventory_pnl{};
    double inventory_pnl_from_marks{};
    double inventory_pnl_mark_error{};
    double gross_identity_error{};
    double net_identity_error{};
    double adverse_selection_cost{};
    double fee_pnl{};
    double net_pnl_after_fees{};
    double maximum_drawdown{};
    double inventory_variance{};
    Quantity final_inventory{};
    std::size_t maker_fills{};
    std::size_t taker_fills{};
    std::size_t market_maker_buy_fills{};
    std::size_t market_maker_sell_fills{};
    Quantity market_maker_filled_quantity{};
    Quantity market_maker_buy_quantity{};
    Quantity market_maker_sell_quantity{};
    Quantity market_maker_posted_quantity{};
    std::size_t external_limit_buy_orders{};
    std::size_t external_limit_sell_orders{};
    std::size_t external_market_buy_orders{};
    std::size_t external_market_sell_orders{};
    std::size_t external_price_modify_buy_orders{};
    std::size_t external_price_modify_sell_orders{};
    Quantity external_limit_buy_quantity{};
    Quantity external_limit_sell_quantity{};
    Quantity external_market_buy_quantity{};
    Quantity external_market_sell_quantity{};
    Quantity external_price_modify_buy_quantity{};
    Quantity external_price_modify_sell_quantity{};
    double average_external_limit_buy_offset{};
    double average_external_limit_sell_offset{};
    double average_external_price_modify_buy_offset{};
    double average_external_price_modify_sell_offset{};
    std::size_t external_rejects{};
    std::size_t quote_refreshes{};
    std::size_t symmetric_quote_refreshes{};
    std::size_t bid_clip_events{};
    std::size_t ask_clip_events{};
    double average_bid_distance{};
    double average_ask_distance{};
    double average_abs_quote_asymmetry{};
    double max_abs_quote_asymmetry{};
    bool reconciliation_passed{};
};

struct MarketMakerCurvePoint {
    std::string strategy_name{};
    std::string regime_name{};
    std::size_t event_index{};
    double reference_mid{};
    double cash{};
    Quantity inventory{};
    double net_pnl_after_fees{};
};

struct MarketMakerRunResult {
    MarketMakerSummary summary{};
    std::vector<MarketMakerCurvePoint> curve{};
};

MarketMakerRunResult run_naive_symmetric_strategy(const MarketMakerSimulationConfig& config);

}  // namespace lob
