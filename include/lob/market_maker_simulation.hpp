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

struct AvellanedaStoikovConfig {
    double risk_aversion{0.002};
    double fill_decay{0.25};
    Quantity quote_size{10};
    std::size_t refresh_cadence{10};
};

struct RiskControlConfig {
    bool enabled{false};
    Quantity inventory_cap{20000};
    double soft_start_fraction{0.50};
    double soft_penalty_max_skew_ticks{20.0};
    bool terminal_liquidation{false};
    double terminal_inventory_penalty_per_unit{0.50};
    double risk_denominator_floor{1.0};
};

struct MarketMakerSimulationConfig {
    RegimeConfig regime{};
    NaiveSymmetricConfig naive{};
    AvellanedaStoikovConfig avellaneda_stoikov{};
    AvellanedaStoikovConfig calibrated_avellaneda_stoikov{0.002, 0.63274456291, 10, 10};
    RiskControlConfig risk_controls{};
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
    double terminal_liquidation_cost{};
    double terminal_inventory_penalty{};
    double risk_adjusted_pnl{};
    double maximum_drawdown{};
    double inventory_variance{};
    Quantity pre_liquidation_inventory{};
    Quantity final_inventory{};
    Quantity terminal_liquidation_quantity{};
    Quantity terminal_liquidation_residual_inventory{};
    std::size_t maker_fills{};
    std::size_t taker_fills{};
    std::size_t passive_taker_fills{};
    std::size_t terminal_liquidation_trades{};
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
    std::size_t hard_cap_bid_blocks{};
    std::size_t hard_cap_ask_blocks{};
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
    double time_remaining{};
    double reference_mid{};
    double reservation_price{};
    double reservation_skew{};
    double cash{};
    Quantity inventory{};
    double net_pnl_after_fees{};
};

struct MarketMakerAdverseSelectionSplit {
    std::string strategy_name{};
    std::string regime_name{};
    std::string group_name{};
    std::size_t maker_fills{};
    Quantity maker_quantity{};
    double signed_markout{};
    double average_markout_per_unit{};
    double adverse_selection_cost{};
    double average_adverse_selection_cost_per_unit{};
    double adverse_selection_cost_share{};
    double total_adverse_selection_cost{};
};

struct TerminalLiquidationLevel {
    std::string strategy_name{};
    std::string regime_name{};
    std::size_t event_index{};
    FillSide side{FillSide::Sell};
    Price price{};
    Quantity displayed_quantity_before{};
    Quantity filled_quantity{};
    double liquidation_cost{};
};

struct TerminalLiquidationTrade {
    std::string strategy_name{};
    std::string regime_name{};
    std::size_t event_index{};
    FillSide side{FillSide::Sell};
    Price price{};
    Quantity quantity{};
    double liquidation_cost{};
};

struct MarketMakerRunResult {
    MarketMakerSummary summary{};
    std::vector<MarketMakerCurvePoint> curve{};
    std::vector<MarketMakerAdverseSelectionSplit> adverse_selection_split{};
    std::vector<TerminalLiquidationLevel> terminal_liquidation_levels{};
    std::vector<TerminalLiquidationTrade> terminal_liquidation_trades{};
};

double risk_control_soft_skew_ticks(const RiskControlConfig& risk_controls, Quantity inventory);
bool risk_control_allows_bid(const RiskControlConfig& risk_controls, Quantity inventory, Quantity quote_size);
bool risk_control_allows_ask(const RiskControlConfig& risk_controls, Quantity inventory, Quantity quote_size);
double terminal_liquidation_cost(FillSide side, double reference_mid, double fill_price, Quantity quantity);
double terminal_inventory_penalty(const RiskControlConfig& risk_controls, Quantity terminal_inventory);
double risk_adjusted_pnl(double net_pnl_after_fees,
                         double terminal_inventory_penalty,
                         double maximum_drawdown,
                         double denominator_floor);

MarketMakerRunResult run_naive_symmetric_strategy(const MarketMakerSimulationConfig& config);
MarketMakerRunResult run_avellaneda_stoikov_strategy(const MarketMakerSimulationConfig& config);
MarketMakerRunResult run_calibrated_avellaneda_stoikov_strategy(const MarketMakerSimulationConfig& config);

}  // namespace lob
