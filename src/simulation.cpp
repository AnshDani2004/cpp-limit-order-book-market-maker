#include "lob/simulation.hpp"

#include <cmath>
#include <random>
#include <sstream>
#include <utility>

namespace lob {
namespace {

PnlReconciliationFields fields_from_snapshot(const PnlSnapshot& state) {
    return PnlReconciliationFields{state.net_pnl_after_fees,
                                   state.gross_pnl_before_fees,
                                   state.spread_capture,
                                   state.inventory_pnl_balancing,
                                   state.fee_pnl,
                                   state.inventory_pnl_from_marks};
}

void add_compensated(double& sum, double& compensation, double value) {
    const auto adjusted = value - compensation;
    const auto next = sum + adjusted;
    compensation = (next - sum) - adjusted;
    sum = next;
}

std::string reconciliation_message(const std::string& regime_name,
                                   const std::string& strategy_name,
                                   double tolerance,
                                   double gross_identity_error,
                                   double net_identity_error,
                                   double inventory_mark_error) {
    std::ostringstream message;
    message << "PnL reconciliation failed"
            << " regime=" << regime_name
            << " strategy=" << strategy_name
            << " tolerance=" << tolerance
            << " gross_identity_error=" << gross_identity_error
            << " net_identity_error=" << net_identity_error
            << " inventory_pnl_mark_error=" << inventory_mark_error;
    return message.str();
}

}  // namespace

PnlReconciliationError::PnlReconciliationError(const std::string& message)
    : std::runtime_error(message) {}

PnlAccounting::PnlAccounting(std::string regime_name,
                             std::string strategy_name,
                             double initial_reference_mid,
                             FeeSchedule fees)
    : regime_name_(std::move(regime_name)),
      strategy_name_(std::move(strategy_name)),
      fees_(fees),
      reference_mid_(initial_reference_mid) {}

void PnlAccounting::record_reference_mid(double new_reference_mid) {
    add_compensated(inventory_pnl_from_marks_,
                    inventory_pnl_from_marks_compensation_,
                    static_cast<double>(inventory_) * (new_reference_mid - reference_mid_));
    reference_mid_ = new_reference_mid;
}

void PnlAccounting::record_fill(const FillEvent& fill) {
    if (fill.quantity <= 0) {
        throw std::invalid_argument("fill quantity must be positive");
    }
    if (fill.price <= 0.0) {
        throw std::invalid_argument("fill price must be positive");
    }

    const auto quantity = static_cast<double>(fill.quantity);
    if (fill.side == FillSide::Buy) {
        add_compensated(cash_, cash_compensation_, -fill.price * quantity);
        inventory_ += fill.quantity;
    } else {
        add_compensated(cash_, cash_compensation_, fill.price * quantity);
        inventory_ -= fill.quantity;
    }

    const auto fee = fee_delta(fill.role, fill.quantity);
    add_compensated(cash_, cash_compensation_, fee);
    add_compensated(fee_pnl_, fee_pnl_compensation_, fee);
    add_compensated(spread_capture_, spread_capture_compensation_, spread_capture_delta(fill));
}

PnlSnapshot PnlAccounting::snapshot() const {
    PnlSnapshot result;
    result.cash = cash_;
    result.inventory = inventory_;
    result.reference_mid = reference_mid_;
    result.fee_pnl = fee_pnl_;
    result.spread_capture = spread_capture_;
    result.inventory_pnl_from_marks = inventory_pnl_from_marks_;
    result.net_pnl_after_fees = cash_ + static_cast<double>(inventory_) * reference_mid_;
    result.gross_pnl_before_fees = result.net_pnl_after_fees - fee_pnl_;
    result.inventory_pnl_balancing = result.gross_pnl_before_fees - spread_capture_;
    return result;
}

bool PnlAccounting::reconciles(double tolerance) const {
    return pnl_reconciles(fields_from_snapshot(snapshot()), tolerance);
}

void PnlAccounting::assert_reconciles(double tolerance) const {
    assert_pnl_reconciles(fields_from_snapshot(snapshot()), regime_name_, strategy_name_, tolerance);
}

const std::string& PnlAccounting::regime_name() const noexcept {
    return regime_name_;
}

const std::string& PnlAccounting::strategy_name() const noexcept {
    return strategy_name_;
}

double PnlAccounting::fee_delta(LiquidityRole role, Quantity quantity) const {
    const auto fee_per_unit = role == LiquidityRole::Maker ? fees_.maker_fee_per_unit : fees_.taker_fee_per_unit;
    return -fee_per_unit * static_cast<double>(quantity);
}

double PnlAccounting::spread_capture_delta(const FillEvent& fill) const {
    const auto quantity = static_cast<double>(fill.quantity);
    if (fill.side == FillSide::Buy) {
        return (reference_mid_ - fill.price) * quantity;
    }
    return (fill.price - reference_mid_) * quantity;
}

bool pnl_reconciles(const PnlReconciliationFields& fields, double tolerance) {
    const auto gross_identity_error =
        fields.gross_pnl_before_fees - (fields.spread_capture + fields.inventory_pnl);
    const auto net_identity_error =
        fields.net_pnl_after_fees - (fields.spread_capture + fields.inventory_pnl + fields.fee_pnl);
    const auto inventory_mark_error = fields.inventory_pnl - fields.inventory_pnl_from_marks;
    return std::fabs(gross_identity_error) <= tolerance &&
           std::fabs(net_identity_error) <= tolerance &&
           std::fabs(inventory_mark_error) <= tolerance;
}

void assert_pnl_reconciles(const PnlReconciliationFields& fields,
                           const std::string& regime_name,
                           const std::string& strategy_name,
                           double tolerance) {
    const auto gross_identity_error =
        fields.gross_pnl_before_fees - (fields.spread_capture + fields.inventory_pnl);
    const auto net_identity_error =
        fields.net_pnl_after_fees - (fields.spread_capture + fields.inventory_pnl + fields.fee_pnl);
    const auto inventory_mark_error = fields.inventory_pnl - fields.inventory_pnl_from_marks;

    if (std::fabs(gross_identity_error) > tolerance ||
        std::fabs(net_identity_error) > tolerance ||
        std::fabs(inventory_mark_error) > tolerance) {
        throw PnlReconciliationError(reconciliation_message(regime_name,
                                                            strategy_name,
                                                            tolerance,
                                                            gross_identity_error,
                                                            net_identity_error,
                                                            inventory_mark_error));
    }
}

std::vector<RegimeConfig> default_regimes(std::size_t run_length) {
    return {
        RegimeConfig{RegimeKind::LowVolatility, "low volatility", 3001, 0.0, 0.40, run_length, 100000.0},
        RegimeConfig{RegimeKind::HighVolatility, "high volatility", 3002, 0.0, 1.60, run_length, 100000.0},
        RegimeConfig{RegimeKind::Trending, "trending", 3003, 0.004, 0.80, run_length, 100000.0},
    };
}

std::vector<double> generate_reference_path(const RegimeConfig& config) {
    std::mt19937_64 rng(config.seed);
    std::normal_distribution<double> innovations(0.0, 1.0);

    std::vector<double> path;
    path.reserve(config.run_length + 1);
    path.push_back(config.initial_reference_mid);

    auto current = config.initial_reference_mid;
    for (std::size_t index = 0; index < config.run_length; ++index) {
        current += config.drift_per_event + config.volatility_per_event * innovations(rng);
        path.push_back(current);
    }

    return path;
}

std::string to_string(RegimeKind kind) {
    switch (kind) {
        case RegimeKind::LowVolatility:
            return "low volatility";
        case RegimeKind::HighVolatility:
            return "high volatility";
        case RegimeKind::Trending:
            return "trending";
    }
    return "unknown";
}

std::string to_string(FillSide side) {
    return side == FillSide::Buy ? "buy" : "sell";
}

std::string to_string(LiquidityRole role) {
    return role == LiquidityRole::Maker ? "maker" : "taker";
}

}  // namespace lob
