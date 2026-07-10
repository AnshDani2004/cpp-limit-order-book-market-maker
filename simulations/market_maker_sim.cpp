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
    return args;
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
    output << "markout_horizon," << args.markout_horizon << '\n';
    output << "curve_sample_stride," << args.curve_sample_stride << '\n';
    output << "quote_size,10\n";
    output << "refresh_cadence,10\n";
    if (args.strategy == "naive") {
        output << "naive_half_spread_ticks,5\n";
        output << "naive_full_spread_ticks,10\n";
    } else {
        output << "risk_aversion,0.002\n";
        output << "fill_decay," << (args.strategy == "avellaneda-stoikov" ? 0.25 : kCalibratedFillDecay) << '\n';
        output << "volatility_source,regime volatility per event\n";
        output << "time_horizon,full regime run\n";
        if (args.strategy == "avellaneda-stoikov-calibrated") {
            output << "fill_decay_source,Stage 4B QQQ regular session exponential fit\n";
        }
    }
    output << "reconciliation_tolerance_ticks,0.00001\n";
    output << "external_limit_order_share,0.55\n";
    output << "external_market_order_share,0.25\n";
    output << "external_cancel_share,0.10\n";
    output << "external_modify_share,0.10\n";
    output << "external_quantity_distribution,uniform integer 1 to 100\n";
    output << "external_limit_offset_distribution,uniform integer 8 to 80 ticks from reference mid\n";
}

void write_summary(const std::filesystem::path& path, const std::vector<lob::MarketMakerRunResult>& results) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write summary");
    }

    output << std::setprecision(12);
    output << "strategy,regime,seed,events,initial_reference_mid,final_reference_mid,"
           << "fill_rate,gross_spread_capture,inventory_pnl,"
           << "inventory_pnl_from_marks,inventory_pnl_mark_error,gross_identity_error,"
           << "net_identity_error,adverse_selection_cost,fee_pnl,net_pnl_after_fees,maximum_drawdown,"
           << "inventory_variance,final_inventory,maker_fills,taker_fills,"
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
           << "ask_clip_events,average_bid_distance,average_ask_distance,"
           << "average_abs_quote_asymmetry,max_abs_quote_asymmetry,"
           << "reconciliation_passed\n";
    for (const auto& result : results) {
        const auto& summary = result.summary;
        output << summary.strategy_name << ','
               << summary.regime_name << ','
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
               << summary.inventory_variance << ','
               << summary.final_inventory << ','
               << summary.maker_fills << ','
               << summary.taker_fills << ','
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

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto args = parse_args(argc, argv);
        std::filesystem::create_directories(args.output_dir);

        std::vector<lob::MarketMakerRunResult> results;
        for (const auto& regime : selected_regimes(args)) {
            lob::MarketMakerSimulationConfig config;
            config.regime = regime;
            config.markout_horizon = args.markout_horizon;
            config.curve_sample_stride = args.curve_sample_stride;
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
