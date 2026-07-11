#include "lob/market_maker_simulation.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr double kCalibratedFillDecay = 0.63274456291;

struct Args {
    std::string strategy{"naive"};
    std::size_t events{200'000};
    std::size_t markout_horizon{50};
    std::size_t curve_sample_stride{100};
    std::string regime{"all"};
    std::optional<std::uint64_t> seed_override{};
    std::optional<double> fill_decay_override{};
    lob::ExternalFlowProfile flow_profile{lob::ExternalFlowProfile::HandChosen};
    bool risk_controls{false};
    lob::Quantity inventory_cap{20000};
    double soft_start_fraction{0.50};
    double soft_penalty_max_skew_ticks{20.0};
    bool terminal_liquidation{false};
    double terminal_inventory_penalty_per_unit{0.50};
    double risk_denominator_floor{1.0};
    std::filesystem::path output_dir{"benchmarks/results/stage3_naive_latest"};
};

std::uint64_t parse_u64(const std::string& value) {
    std::size_t consumed = 0;
    const auto parsed = std::stoull(value, &consumed);
    if (consumed != value.size()) {
        throw std::runtime_error("invalid numeric argument: " + value);
    }
    return parsed;
}

double parse_double(const std::string& value) {
    std::size_t consumed = 0;
    const auto parsed = std::stod(value, &consumed);
    if (consumed != value.size()) {
        throw std::runtime_error("invalid decimal argument: " + value);
    }
    return parsed;
}

Args parse_args(int argc, char** argv) {
    Args args;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        auto require_value = [&]() -> std::string {
            if (index + 1 >= argc) {
                throw std::runtime_error("missing value for " + argument);
            }
            ++index;
            return argv[index];
        };

        if (argument == "--strategy") {
            args.strategy = require_value();
            if (args.strategy != "naive" && args.strategy != "avellaneda-stoikov" &&
                args.strategy != "avellaneda-stoikov-calibrated") {
                throw std::runtime_error("unknown strategy: " + args.strategy);
            }
        } else if (argument == "--events") {
            args.events = static_cast<std::size_t>(parse_u64(require_value()));
        } else if (argument == "--markout-horizon") {
            args.markout_horizon = static_cast<std::size_t>(parse_u64(require_value()));
        } else if (argument == "--curve-sample-stride") {
            args.curve_sample_stride = static_cast<std::size_t>(parse_u64(require_value()));
        } else if (argument == "--regime") {
            args.regime = require_value();
            if (args.regime != "all" && args.regime != "low-volatility" &&
                args.regime != "high-volatility" && args.regime != "trending") {
                throw std::runtime_error("unknown regime: " + args.regime);
            }
        } else if (argument == "--seed") {
            args.seed_override = parse_u64(require_value());
        } else if (argument == "--fill-decay") {
            args.fill_decay_override = parse_double(require_value());
        } else if (argument == "--flow-profile") {
            const auto value = require_value();
            if (value == "hand-chosen") {
                args.flow_profile = lob::ExternalFlowProfile::HandChosen;
            } else if (value == "itch-calibrated") {
                args.flow_profile = lob::ExternalFlowProfile::ItchCalibrated;
            } else {
                throw std::runtime_error("unknown flow profile: " + value);
            }
        } else if (argument == "--risk-controls") {
            args.risk_controls = true;
        } else if (argument == "--inventory-cap") {
            args.inventory_cap = static_cast<lob::Quantity>(parse_u64(require_value()));
        } else if (argument == "--soft-start-fraction") {
            args.soft_start_fraction = parse_double(require_value());
        } else if (argument == "--soft-penalty-max-skew-ticks") {
            args.soft_penalty_max_skew_ticks = parse_double(require_value());
        } else if (argument == "--terminal-liquidation") {
            args.terminal_liquidation = true;
        } else if (argument == "--terminal-inventory-penalty-per-unit") {
            args.terminal_inventory_penalty_per_unit = parse_double(require_value());
        } else if (argument == "--risk-denominator-floor") {
            args.risk_denominator_floor = parse_double(require_value());
        } else if (argument == "--output-dir") {
            args.output_dir = require_value();
        } else {
            throw std::runtime_error("unknown argument: " + argument);
        }
    }

    if (args.events == 0) {
        throw std::runtime_error("events must be positive");
    }
    if (args.seed_override.has_value() && args.regime == "all") {
        throw std::runtime_error("--seed requires a single --regime");
    }
    if (args.fill_decay_override.has_value() && args.strategy == "naive") {
        throw std::runtime_error("--fill-decay requires an Avellaneda Stoikov strategy");
    }
    if (args.inventory_cap <= 0) {
        throw std::runtime_error("--inventory-cap must be positive");
    }
    if (args.soft_start_fraction < 0.0 || args.soft_start_fraction >= 1.0) {
        throw std::runtime_error("--soft-start-fraction must be in [0, 1)");
    }
    if (args.soft_penalty_max_skew_ticks < 0.0) {
        throw std::runtime_error("--soft-penalty-max-skew-ticks must be nonnegative");
    }
    if (args.terminal_inventory_penalty_per_unit < 0.0) {
        throw std::runtime_error("--terminal-inventory-penalty-per-unit must be nonnegative");
    }
    if (args.risk_denominator_floor <= 0.0) {
        throw std::runtime_error("--risk-denominator-floor must be positive");
    }
    return args;
}

double selected_fill_decay(const Args& args) {
    if (args.strategy == "avellaneda-stoikov") {
        return args.fill_decay_override.value_or(0.25);
    }
    if (args.strategy == "avellaneda-stoikov-calibrated") {
        return args.fill_decay_override.value_or(kCalibratedFillDecay);
    }
    return 0.0;
}

std::vector<lob::RegimeConfig> selected_regimes(const Args& args) {
    auto regimes = lob::default_regimes(args.events);
    if (args.regime == "all") {
        return regimes;
    }

    std::vector<lob::RegimeConfig> selected;
    for (auto& regime : regimes) {
        const auto matches = (args.regime == "low-volatility" &&
                              regime.kind == lob::RegimeKind::LowVolatility) ||
                             (args.regime == "high-volatility" &&
                              regime.kind == lob::RegimeKind::HighVolatility) ||
                             (args.regime == "trending" &&
                              regime.kind == lob::RegimeKind::Trending);
        if (matches) {
            if (args.seed_override.has_value()) {
                regime.seed = *args.seed_override;
            }
            selected.push_back(regime);
        }
    }
    return selected;
}

void write_run_config(const std::filesystem::path& path, const Args& args) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write run config");
    }

    output << std::setprecision(12);
    output << "field,value\n";
    if (args.strategy == "naive") {
        output << "strategy,naive symmetric\n";
    } else if (args.strategy == "avellaneda-stoikov") {
        output << "strategy,avellaneda stoikov\n";
    } else {
        output << "strategy,avellaneda stoikov calibrated\n";
    }
    output << "regime," << args.regime << '\n';
    if (args.seed_override.has_value()) {
        output << "seed_override," << *args.seed_override << '\n';
    }
    output << "events," << args.events << '\n';
    output << "flow_profile," << lob::external_flow_profile_name(args.flow_profile) << '\n';
    output << "markout_horizon," << args.markout_horizon << '\n';
    output << "curve_sample_stride," << args.curve_sample_stride << '\n';
    output << "quote_size,10\n";
    output << "refresh_cadence,10\n";
    output << "risk_controls_enabled," << (args.risk_controls ? "true" : "false") << '\n';
    output << "inventory_cap," << args.inventory_cap << '\n';
    output << "soft_start_fraction," << args.soft_start_fraction << '\n';
    output << "soft_penalty_max_skew_ticks," << args.soft_penalty_max_skew_ticks << '\n';
    output << "terminal_liquidation," << (args.terminal_liquidation ? "true" : "false") << '\n';
    output << "terminal_inventory_penalty_per_unit," << args.terminal_inventory_penalty_per_unit << '\n';
    output << "risk_adjusted_pnl_formula,(net_pnl_after_fees - terminal_inventory_penalty) / max(maximum_drawdown, risk_denominator_floor)\n";
    output << "risk_denominator_floor," << args.risk_denominator_floor << '\n';
    if (args.strategy == "naive") {
        output << "naive_half_spread_ticks,5\n";
        output << "naive_full_spread_ticks,10\n";
    } else {
        output << "risk_aversion,0.002\n";
        output << "fill_decay," << selected_fill_decay(args) << '\n';
        output << "volatility_source,regime volatility per event\n";
        output << "time_horizon,full regime run\n";
        if (args.strategy == "avellaneda-stoikov-calibrated") {
            output << "fill_decay_source,Stage 4B QQQ regular session exponential fit\n";
        }
    }
    output << "reconciliation_tolerance_ticks,0.00001\n";
    if (args.flow_profile == lob::ExternalFlowProfile::HandChosen) {
        output << "external_limit_order_share,0.55\n";
        output << "external_market_order_share,0.25\n";
        output << "external_cancel_share,0.10\n";
        output << "external_modify_share,0.10\n";
        output << "external_quantity_distribution,uniform integer 1 to 100\n";
    } else {
        output << "external_limit_order_share,5910 / 12423\n";
        output << "external_market_order_share,57 / 12423\n";
        output << "external_cancel_share,5864 / 12423\n";
        output << "external_modify_share,592 / 12423\n";
        output << "external_quantity_distribution,Stage 4A QQQ bounded prefix bucket counts 45 15 34 410 5799 6120 with 1001 plus sampled 1001 to observed max 3000\n";
        output << "external_market_order_source,Stage 4A external_execute events mapped to synthetic taker flow\n";
    }
    output << "external_limit_offset_distribution,uniform integer 8 to 80 ticks from reference mid\n";
}

void write_summary(const std::filesystem::path& path, const std::vector<lob::MarketMakerRunResult>& results) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write summary");
    }

    output << std::setprecision(12);
    output << "strategy,regime,external_flow_profile,seed,events,initial_reference_mid,final_reference_mid,"
           << "fill_rate,gross_spread_capture,inventory_pnl,"
           << "inventory_pnl_from_marks,inventory_pnl_mark_error,gross_identity_error,"
           << "net_identity_error,adverse_selection_cost,fee_pnl,net_pnl_after_fees,maximum_drawdown,"
           << "terminal_liquidation_cost,terminal_inventory_penalty,risk_adjusted_pnl,"
           << "inventory_variance,pre_liquidation_inventory,final_inventory,"
           << "terminal_liquidation_quantity,terminal_liquidation_residual_inventory,"
           << "maker_fills,taker_fills,passive_taker_fills,terminal_liquidation_trades,"
           << "market_maker_buy_fills,market_maker_sell_fills,market_maker_filled_quantity,"
           << "market_maker_buy_quantity,market_maker_sell_quantity,market_maker_posted_quantity,"
           << "external_limit_buy_orders,external_limit_sell_orders,external_market_buy_orders,"
           << "external_market_sell_orders,external_price_modify_buy_orders,"
           << "external_price_modify_sell_orders,external_limit_buy_quantity,external_limit_sell_quantity,"
           << "external_market_buy_quantity,external_market_sell_quantity,"
           << "external_price_modify_buy_quantity,external_price_modify_sell_quantity,"
           << "average_external_limit_buy_offset,average_external_limit_sell_offset,"
           << "average_external_price_modify_buy_offset,average_external_price_modify_sell_offset,"
           << "external_rejects,quote_refreshes,symmetric_quote_refreshes,bid_clip_events,"
           << "ask_clip_events,hard_cap_bid_blocks,hard_cap_ask_blocks,"
           << "average_bid_distance,average_ask_distance,"
           << "average_abs_quote_asymmetry,max_abs_quote_asymmetry,"
           << "reconciliation_passed\n";
    for (const auto& result : results) {
        const auto& summary = result.summary;
        output << summary.strategy_name << ','
               << summary.regime_name << ','
               << summary.external_flow_profile << ','
               << summary.seed << ','
               << summary.events << ','
               << summary.initial_reference_mid << ','
               << summary.final_reference_mid << ','
               << summary.fill_rate << ','
               << summary.gross_spread_capture << ','
               << summary.inventory_pnl << ','
               << summary.inventory_pnl_from_marks << ','
               << summary.inventory_pnl_mark_error << ','
               << summary.gross_identity_error << ','
               << summary.net_identity_error << ','
               << summary.adverse_selection_cost << ','
               << summary.fee_pnl << ','
               << summary.net_pnl_after_fees << ','
               << summary.maximum_drawdown << ','
               << summary.terminal_liquidation_cost << ','
               << summary.terminal_inventory_penalty << ','
               << summary.risk_adjusted_pnl << ','
               << summary.inventory_variance << ','
               << summary.pre_liquidation_inventory << ','
               << summary.final_inventory << ','
               << summary.terminal_liquidation_quantity << ','
               << summary.terminal_liquidation_residual_inventory << ','
               << summary.maker_fills << ','
               << summary.taker_fills << ','
               << summary.passive_taker_fills << ','
               << summary.terminal_liquidation_trades << ','
               << summary.market_maker_buy_fills << ','
               << summary.market_maker_sell_fills << ','
               << summary.market_maker_filled_quantity << ','
               << summary.market_maker_buy_quantity << ','
               << summary.market_maker_sell_quantity << ','
               << summary.market_maker_posted_quantity << ','
               << summary.external_limit_buy_orders << ','
               << summary.external_limit_sell_orders << ','
               << summary.external_market_buy_orders << ','
               << summary.external_market_sell_orders << ','
               << summary.external_price_modify_buy_orders << ','
               << summary.external_price_modify_sell_orders << ','
               << summary.external_limit_buy_quantity << ','
               << summary.external_limit_sell_quantity << ','
               << summary.external_market_buy_quantity << ','
               << summary.external_market_sell_quantity << ','
               << summary.external_price_modify_buy_quantity << ','
               << summary.external_price_modify_sell_quantity << ','
               << summary.average_external_limit_buy_offset << ','
               << summary.average_external_limit_sell_offset << ','
               << summary.average_external_price_modify_buy_offset << ','
               << summary.average_external_price_modify_sell_offset << ','
               << summary.external_rejects << ','
               << summary.quote_refreshes << ','
               << summary.symmetric_quote_refreshes << ','
               << summary.bid_clip_events << ','
               << summary.ask_clip_events << ','
               << summary.hard_cap_bid_blocks << ','
               << summary.hard_cap_ask_blocks << ','
               << summary.average_bid_distance << ','
               << summary.average_ask_distance << ','
               << summary.average_abs_quote_asymmetry << ','
               << summary.max_abs_quote_asymmetry << ','
               << (summary.reconciliation_passed ? "true" : "false") << '\n';
    }
}

void write_curve(const std::filesystem::path& path, const std::vector<lob::MarketMakerRunResult>& results) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write equity curve");
    }

    output << std::setprecision(12);
    output << "strategy,regime,event_index,time_remaining,reference_mid,reservation_price,"
           << "reservation_skew,cash,inventory,net_pnl_after_fees\n";
    for (const auto& result : results) {
        for (const auto& point : result.curve) {
            output << point.strategy_name << ','
                   << point.regime_name << ','
                   << point.event_index << ','
                   << point.time_remaining << ','
                   << point.reference_mid << ','
                   << point.reservation_price << ','
                   << point.reservation_skew << ','
                   << point.cash << ','
                   << point.inventory << ','
                   << point.net_pnl_after_fees << '\n';
        }
    }
}

void write_adverse_selection_split(const std::filesystem::path& path,
                                   const std::vector<lob::MarketMakerRunResult>& results) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write adverse selection split");
    }

    output << std::setprecision(12);
    output << "strategy,regime,group,maker_fills,maker_quantity,signed_markout,"
           << "average_markout_per_unit,adverse_selection_cost,"
           << "average_adverse_selection_cost_per_unit,adverse_selection_cost_share,"
           << "total_adverse_selection_cost\n";
    for (const auto& result : results) {
        for (const auto& split : result.adverse_selection_split) {
            output << split.strategy_name << ','
                   << split.regime_name << ','
                   << split.group_name << ','
                   << split.maker_fills << ','
                   << split.maker_quantity << ','
                   << split.signed_markout << ','
                   << split.average_markout_per_unit << ','
                   << split.adverse_selection_cost << ','
                   << split.average_adverse_selection_cost_per_unit << ','
                   << split.adverse_selection_cost_share << ','
                   << split.total_adverse_selection_cost << '\n';
        }
    }
}

void write_terminal_liquidation_levels(const std::filesystem::path& path,
                                       const std::vector<lob::MarketMakerRunResult>& results) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write terminal liquidation levels");
    }

    output << std::setprecision(12);
    output << "strategy,regime,event_index,side,price,displayed_quantity_before,"
           << "filled_quantity,liquidation_cost\n";
    for (const auto& result : results) {
        for (const auto& level : result.terminal_liquidation_levels) {
            output << level.strategy_name << ','
                   << level.regime_name << ','
                   << level.event_index << ','
                   << lob::to_string(level.side) << ','
                   << level.price << ','
                   << level.displayed_quantity_before << ','
                   << level.filled_quantity << ','
                   << level.liquidation_cost << '\n';
        }
    }
}

void write_terminal_liquidation_trades(const std::filesystem::path& path,
                                       const std::vector<lob::MarketMakerRunResult>& results) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write terminal liquidation trades");
    }

    output << std::setprecision(12);
    output << "strategy,regime,event_index,side,price,quantity,liquidation_cost\n";
    for (const auto& result : results) {
        for (const auto& trade : result.terminal_liquidation_trades) {
            output << trade.strategy_name << ','
                   << trade.regime_name << ','
                   << trade.event_index << ','
                   << lob::to_string(trade.side) << ','
                   << trade.price << ','
                   << trade.quantity << ','
                   << trade.liquidation_cost << '\n';
        }
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto args = parse_args(argc, argv);
        std::filesystem::create_directories(args.output_dir);

        std::vector<lob::MarketMakerRunResult> results;
        for (const auto& regime : selected_regimes(args)) {
            lob::MarketMakerSimulationConfig config;
            config.regime = regime;
            config.external_flow_profile = args.flow_profile;
            config.markout_horizon = args.markout_horizon;
            config.curve_sample_stride = args.curve_sample_stride;
            config.risk_controls.enabled = args.risk_controls;
            config.risk_controls.inventory_cap = args.inventory_cap;
            config.risk_controls.soft_start_fraction = args.soft_start_fraction;
            config.risk_controls.soft_penalty_max_skew_ticks = args.soft_penalty_max_skew_ticks;
            config.risk_controls.terminal_liquidation = args.terminal_liquidation;
            config.risk_controls.terminal_inventory_penalty_per_unit =
                args.terminal_inventory_penalty_per_unit;
            config.risk_controls.risk_denominator_floor = args.risk_denominator_floor;
            if (args.strategy == "avellaneda-stoikov" && args.fill_decay_override.has_value()) {
                config.avellaneda_stoikov.fill_decay = *args.fill_decay_override;
            }
            if (args.strategy == "avellaneda-stoikov-calibrated" && args.fill_decay_override.has_value()) {
                config.calibrated_avellaneda_stoikov.fill_decay = *args.fill_decay_override;
            }
            if (args.strategy == "naive") {
                results.push_back(lob::run_naive_symmetric_strategy(config));
            } else if (args.strategy == "avellaneda-stoikov") {
                results.push_back(lob::run_avellaneda_stoikov_strategy(config));
            } else {
                results.push_back(lob::run_calibrated_avellaneda_stoikov_strategy(config));
            }
        }

        write_run_config(args.output_dir / "run_config.csv", args);
        write_summary(args.output_dir / "summary.csv", results);
        write_curve(args.output_dir / "equity_curve.csv", results);
        write_adverse_selection_split(args.output_dir / "adverse_selection_split.csv", results);
        write_terminal_liquidation_levels(args.output_dir / "terminal_liquidation_levels.csv", results);
        write_terminal_liquidation_trades(args.output_dir / "terminal_liquidation_trades.csv", results);

        std::cout << (args.output_dir / "summary.csv") << '\n';
        for (const auto& result : results) {
            const auto& summary = result.summary;
            std::cout << summary.regime_name
                      << " net_pnl_after_fees=" << summary.net_pnl_after_fees
                      << " final_inventory=" << summary.final_inventory
                      << " maker_fills=" << summary.maker_fills
                      << " reconciliation=" << (summary.reconciliation_passed ? "true" : "false")
                      << '\n';
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }
}
