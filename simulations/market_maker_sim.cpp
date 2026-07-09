#include "lob/market_maker_simulation.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Args {
    std::size_t events{200'000};
    std::size_t markout_horizon{50};
    std::size_t curve_sample_stride{100};
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
            const auto strategy = require_value();
            if (strategy != "naive") {
                throw std::runtime_error("only --strategy naive is implemented in this checkpoint");
            }
        } else if (argument == "--events") {
            args.events = static_cast<std::size_t>(parse_u64(require_value()));
        } else if (argument == "--markout-horizon") {
            args.markout_horizon = static_cast<std::size_t>(parse_u64(require_value()));
        } else if (argument == "--curve-sample-stride") {
            args.curve_sample_stride = static_cast<std::size_t>(parse_u64(require_value()));
        } else if (argument == "--output-dir") {
            args.output_dir = require_value();
        } else {
            throw std::runtime_error("unknown argument: " + argument);
        }
    }

    if (args.events == 0) {
        throw std::runtime_error("events must be positive");
    }
    return args;
}

void write_run_config(const std::filesystem::path& path, const Args& args) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write run config");
    }

    output << "field,value\n";
    output << "strategy,naive symmetric\n";
    output << "events," << args.events << '\n';
    output << "markout_horizon," << args.markout_horizon << '\n';
    output << "curve_sample_stride," << args.curve_sample_stride << '\n';
    output << "naive_half_spread_ticks,5\n";
    output << "naive_full_spread_ticks,10\n";
    output << "quote_size,10\n";
    output << "refresh_cadence,10\n";
    output << "reconciliation_tolerance_ticks,0.01\n";
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
    output << "strategy,regime,seed,events,fill_rate,gross_spread_capture,inventory_pnl,"
           << "adverse_selection_cost,fee_pnl,net_pnl_after_fees,maximum_drawdown,"
           << "inventory_variance,final_inventory,maker_fills,taker_fills,"
           << "market_maker_filled_quantity,market_maker_posted_quantity,external_rejects,"
           << "reconciliation_passed\n";
    for (const auto& result : results) {
        const auto& summary = result.summary;
        output << summary.strategy_name << ','
               << summary.regime_name << ','
               << summary.seed << ','
               << summary.events << ','
               << summary.fill_rate << ','
               << summary.gross_spread_capture << ','
               << summary.inventory_pnl << ','
               << summary.adverse_selection_cost << ','
               << summary.fee_pnl << ','
               << summary.net_pnl_after_fees << ','
               << summary.maximum_drawdown << ','
               << summary.inventory_variance << ','
               << summary.final_inventory << ','
               << summary.maker_fills << ','
               << summary.taker_fills << ','
               << summary.market_maker_filled_quantity << ','
               << summary.market_maker_posted_quantity << ','
               << summary.external_rejects << ','
               << (summary.reconciliation_passed ? "true" : "false") << '\n';
    }
}

void write_curve(const std::filesystem::path& path, const std::vector<lob::MarketMakerRunResult>& results) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write equity curve");
    }

    output << std::setprecision(12);
    output << "strategy,regime,event_index,reference_mid,cash,inventory,net_pnl_after_fees\n";
    for (const auto& result : results) {
        for (const auto& point : result.curve) {
            output << point.strategy_name << ','
                   << point.regime_name << ','
                   << point.event_index << ','
                   << point.reference_mid << ','
                   << point.cash << ','
                   << point.inventory << ','
                   << point.net_pnl_after_fees << '\n';
        }
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto args = parse_args(argc, argv);
        std::filesystem::create_directories(args.output_dir);

        std::vector<lob::MarketMakerRunResult> results;
        for (const auto& regime : lob::default_regimes(args.events)) {
            lob::MarketMakerSimulationConfig config;
            config.regime = regime;
            config.markout_horizon = args.markout_horizon;
            config.curve_sample_stride = args.curve_sample_stride;
            results.push_back(lob::run_naive_symmetric_strategy(config));
        }

        write_run_config(args.output_dir / "run_config.csv", args);
        write_summary(args.output_dir / "summary.csv", results);
        write_curve(args.output_dir / "equity_curve.csv", results);

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
