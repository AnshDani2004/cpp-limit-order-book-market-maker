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
    double fill_rate{};
    double gross_spread_capture{};
    double inventory_pnl{};
    double adverse_selection_cost{};
    double fee_pnl{};
    double net_pnl_after_fees{};
    double maximum_drawdown{};
    double inventory_variance{};
    Quantity final_inventory{};
    std::size_t maker_fills{};
    std::size_t taker_fills{};
    Quantity market_maker_filled_quantity{};
    Quantity market_maker_posted_quantity{};
    std::size_t external_rejects{};
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
