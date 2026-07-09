#include "lob/simulation.hpp"

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <string>

namespace {

lob::PnlAccounting make_multi_fill_accounting_run() {
    lob::PnlAccounting accounting("low volatility", "accounting smoke", 100.0);

    accounting.record_fill(lob::FillEvent{lob::FillSide::Buy, lob::LiquidityRole::Maker, 99.0, 10, 1});
    accounting.record_reference_mid(101.5);
    accounting.record_fill(lob::FillEvent{lob::FillSide::Sell, lob::LiquidityRole::Taker, 102.0, 4, 2});
    accounting.record_reference_mid(100.5);
    accounting.record_fill(lob::FillEvent{lob::FillSide::Buy, lob::LiquidityRole::Maker, 100.0, 3, 3});
    accounting.record_reference_mid(103.0);

    return accounting;
}

lob::PnlReconciliationFields fields_from_snapshot(const lob::PnlSnapshot& state) {
    return lob::PnlReconciliationFields{state.net_pnl_after_fees,
                                        state.gross_pnl_before_fees,
                                        state.spread_capture,
                                        state.inventory_pnl_balancing,
                                        state.fee_pnl,
                                        state.inventory_pnl_from_marks};
}

}  // namespace

TEST_CASE("default regimes match the Stage 3 measurement plan") {
    const auto regimes = lob::default_regimes(200000);

    REQUIRE(regimes.size() == 3);
    CHECK(regimes[0].name == "low volatility");
    CHECK(regimes[0].seed == 3001);
    CHECK(regimes[0].drift_per_event == 0.0);
    CHECK(regimes[0].volatility_per_event == 0.40);

    CHECK(regimes[1].name == "high volatility");
    CHECK(regimes[1].seed == 3002);
    CHECK(regimes[1].drift_per_event == 0.0);
    CHECK(regimes[1].volatility_per_event == 1.60);

    CHECK(regimes[2].name == "trending");
    CHECK(regimes[2].seed == 3003);
    CHECK(regimes[2].drift_per_event == 0.004);
    CHECK(regimes[2].volatility_per_event == 0.80);
}

TEST_CASE("reference path generation is deterministic for a fixed regime seed") {
    const lob::RegimeConfig config{lob::RegimeKind::LowVolatility,
                                   "low volatility",
                                   3001,
                                   0.0,
                                   0.40,
                                   8,
                                   100000.0};

    const auto first = lob::generate_reference_path(config);
    const auto second = lob::generate_reference_path(config);

    REQUIRE(first.size() == 9);
    CHECK(first == second);
}

TEST_CASE("PnL accounting reconciles spread capture inventory marks and fees") {
    const auto accounting = make_multi_fill_accounting_run();

    const auto state = accounting.snapshot();

    CHECK(state.cash == Catch::Approx(-882.06));
    CHECK(state.inventory == 9);
    CHECK(state.reference_mid == Catch::Approx(103.0));
    CHECK(state.fee_pnl == Catch::Approx(-0.06));
    CHECK(state.spread_capture == Catch::Approx(13.5));
    CHECK(state.inventory_pnl_from_marks == Catch::Approx(31.5));
    CHECK(state.inventory_pnl_balancing == Catch::Approx(31.5));
    CHECK(state.gross_pnl_before_fees == Catch::Approx(45.0));
    CHECK(state.net_pnl_after_fees == Catch::Approx(44.94));
    CHECK(accounting.reconciles(1e-9));
    CHECK_NOTHROW(accounting.assert_reconciles(1e-9));
}

TEST_CASE("PnL reconciliation fails loudly for deliberately broken fields") {
    const auto accounting = make_multi_fill_accounting_run();
    const auto state = accounting.snapshot();
    const auto valid = fields_from_snapshot(state);
    auto broken = valid;
    broken.inventory_pnl += 7.25;

    CHECK(lob::pnl_reconciles(valid, 1e-9));
    CHECK_FALSE(lob::pnl_reconciles(broken, 1e-9));

    try {
        lob::assert_pnl_reconciles(broken, "high volatility", "broken reconciliation", 1e-9);
        FAIL("expected reconciliation failure");
    } catch (const lob::PnlReconciliationError& error) {
        const std::string message = error.what();
        CHECK(message.find("regime=high volatility") != std::string::npos);
        CHECK(message.find("strategy=broken reconciliation") != std::string::npos);
        CHECK(message.find("gross_identity_error=-7.25") != std::string::npos);
        CHECK(message.find("net_identity_error=-7.25") != std::string::npos);
        CHECK(message.find("inventory_pnl_mark_error=7.25") != std::string::npos);
    }
}
