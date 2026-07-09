#pragma once

#include "lob/types.hpp"

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace lob {

enum class RegimeKind {
    LowVolatility,
    HighVolatility,
    Trending
};

enum class FillSide {
    Buy,
    Sell
};

enum class LiquidityRole {
    Maker,
    Taker
};

struct FeeSchedule {
    double maker_fee_per_unit{-0.02};
    double taker_fee_per_unit{0.08};
};

struct RegimeConfig {
    RegimeKind kind{RegimeKind::LowVolatility};
    std::string name{"low volatility"};
    std::uint64_t seed{3001};
    double drift_per_event{0.0};
    double volatility_per_event{0.40};
    std::size_t run_length{200000};
    double initial_reference_mid{100000.0};
};

struct FillEvent {
    FillSide side{FillSide::Buy};
    LiquidityRole role{LiquidityRole::Maker};
    double price{};
    Quantity quantity{};
    std::size_t event_index{};
};

struct PnlSnapshot {
    double cash{};
    Quantity inventory{};
    double reference_mid{};
    double fee_pnl{};
    double spread_capture{};
    double inventory_pnl_from_marks{};
    double net_pnl_after_fees{};
    double gross_pnl_before_fees{};
    double inventory_pnl_balancing{};
};

struct PnlReconciliationFields {
    double net_pnl_after_fees{};
    double gross_pnl_before_fees{};
    double spread_capture{};
    double inventory_pnl{};
    double fee_pnl{};
    double inventory_pnl_from_marks{};
};

class PnlReconciliationError : public std::runtime_error {
public:
    explicit PnlReconciliationError(const std::string& message);
};

class PnlAccounting {
public:
    PnlAccounting(std::string regime_name,
                  std::string strategy_name,
                  double initial_reference_mid,
                  FeeSchedule fees = {});

    void record_reference_mid(double new_reference_mid);
    void record_fill(const FillEvent& fill);

    PnlSnapshot snapshot() const;
    bool reconciles(double tolerance) const;
    void assert_reconciles(double tolerance) const;

    const std::string& regime_name() const noexcept;
    const std::string& strategy_name() const noexcept;

private:
    double fee_delta(LiquidityRole role, Quantity quantity) const;
    double spread_capture_delta(const FillEvent& fill) const;

    std::string regime_name_{};
    std::string strategy_name_{};
    FeeSchedule fees_{};
    double cash_{};
    Quantity inventory_{};
    double reference_mid_{};
    double fee_pnl_{};
    double spread_capture_{};
    double inventory_pnl_from_marks_{};
};

bool pnl_reconciles(const PnlReconciliationFields& fields, double tolerance);
void assert_pnl_reconciles(const PnlReconciliationFields& fields,
                           const std::string& regime_name,
                           const std::string& strategy_name,
                           double tolerance);

std::vector<RegimeConfig> default_regimes(std::size_t run_length = 200000);
std::vector<double> generate_reference_path(const RegimeConfig& config);

std::string to_string(RegimeKind kind);
std::string to_string(FillSide side);
std::string to_string(LiquidityRole role);

}  // namespace lob
