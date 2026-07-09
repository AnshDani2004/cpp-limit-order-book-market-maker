#include "lob/market_maker_simulation.hpp"

#include "lob/matching_engine.hpp"

#include <algorithm>
#include <cmath>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace lob {
namespace {

constexpr const char* kNaiveStrategyName = "naive symmetric";
constexpr const char* kAvellanedaStoikovStrategyName = "avellaneda stoikov";
constexpr const char* kMarketMakerOwner = "market_maker";
constexpr OrderId kMarketMakerOrderIdStart = 1'000'000'000'000ULL;
constexpr double kRunReconciliationTolerance = 1e-5;

enum class StrategyKind {
    NaiveSymmetric,
    AvellanedaStoikov
};

enum class ExternalAction {
    Limit,
    Market,
    Cancel,
    Modify
};

struct ExternalEvent {
    ExternalAction action{ExternalAction::Limit};
    Timestamp timestamp{};
    Order order{};
    OrderId order_id{};
    std::optional<Price> new_price{};
    Quantity new_quantity{};
};

struct ActiveExternalOrder {
    Side side{Side::Buy};
    Price price{};
    Quantity remaining_quantity{};
};

struct ActiveExternalIndex {
    std::vector<OrderId> ids{};
    std::unordered_map<OrderId, std::size_t> positions{};
    std::unordered_map<OrderId, ActiveExternalOrder> orders{};

    bool empty() const {
        return ids.empty();
    }

    void remove(OrderId id) {
        const auto position = positions.find(id);
        if (position == positions.end()) {
            return;
        }

        const auto index = position->second;
        const auto back_id = ids.back();
        ids[index] = back_id;
        positions[back_id] = index;
        ids.pop_back();
        positions.erase(position);
        orders.erase(id);
    }

    void upsert(const Order& order) {
        if (positions.find(order.id) == positions.end()) {
            positions[order.id] = ids.size();
            ids.push_back(order.id);
        }
        orders[order.id] = ActiveExternalOrder{order.side, order.price.value(), order.remaining_quantity};
    }

    OrderId random_id(std::mt19937_64& rng) const {
        std::uniform_int_distribution<std::size_t> distribution(0, ids.size() - 1);
        return ids[distribution(rng)];
    }
};

struct ExternalFlowDiagnostics {
    std::size_t limit_buy_orders{};
    std::size_t limit_sell_orders{};
    std::size_t market_buy_orders{};
    std::size_t market_sell_orders{};
    std::size_t price_modify_buy_orders{};
    std::size_t price_modify_sell_orders{};
    Quantity limit_buy_quantity{};
    Quantity limit_sell_quantity{};
    Quantity market_buy_quantity{};
    Quantity market_sell_quantity{};
    Quantity price_modify_buy_quantity{};
    Quantity price_modify_sell_quantity{};
    double limit_buy_offset_sum{};
    double limit_sell_offset_sum{};
    double price_modify_buy_offset_sum{};
    double price_modify_sell_offset_sum{};
};

struct GeneratedExternalFlow {
    std::vector<ExternalEvent> events{};
    ExternalFlowDiagnostics diagnostics{};
};

struct QuoteIds {
    std::optional<OrderId> bid{};
    std::optional<OrderId> ask{};
};

struct QuotePrices {
    Price reference{};
    Price proposed_bid{};
    Price proposed_ask{};
    Price bid{};
    Price ask{};
};

class RunningMoments {
public:
    void add(double value) {
        ++count_;
        sum_ += value;
        sum_squares_ += value * value;
    }

    double variance() const {
        if (count_ == 0) {
            return 0.0;
        }
        const auto mean = sum_ / static_cast<double>(count_);
        return sum_squares_ / static_cast<double>(count_) - mean * mean;
    }

private:
    std::size_t count_{};
    double sum_{};
    double sum_squares_{};
};

bool is_market_maker_order(OrderId id) {
    return id >= kMarketMakerOrderIdStart;
}

Price rounded_reference(double reference_mid) {
    return static_cast<Price>(std::llround(reference_mid));
}

void sync_active_id(MatchingEngine& engine, ActiveExternalIndex& active, OrderId id) {
    const auto snapshot = engine.book().snapshot_order(id);
    if (snapshot.has_value()) {
        active.upsert(*snapshot);
    } else {
        active.remove(id);
    }
}

ExecutionResult apply_external_event(MatchingEngine& engine, const ExternalEvent& event) {
    switch (event.action) {
        case ExternalAction::Limit:
        case ExternalAction::Market:
            return engine.submit_order(event.order);
        case ExternalAction::Cancel:
            return engine.cancel_order(event.order_id, event.timestamp);
        case ExternalAction::Modify:
            return engine.modify_order(event.order_id, event.new_price, event.new_quantity, event.timestamp);
    }
    throw std::runtime_error("unknown external action");
}

void sync_after_external_result(MatchingEngine& engine,
                                ActiveExternalIndex& active,
                                const ExternalEvent& event,
                                const ExecutionResult& result) {
    if (event.action == ExternalAction::Cancel) {
        active.remove(event.order_id);
    } else if (event.action == ExternalAction::Modify) {
        sync_active_id(engine, active, event.order_id);
    } else {
        sync_active_id(engine, active, event.order.id);
    }

    for (const auto& trade : result.trades) {
        sync_active_id(engine, active, trade.maker_order_id);
    }
}

class ExternalFlowGenerator {
public:
    ExternalFlowGenerator(const RegimeConfig& regime, const std::vector<double>& reference_path)
        : regime_(regime), reference_path_(reference_path), rng_(regime.seed ^ 0x9e3779b97f4a7c15ULL) {}

    GeneratedExternalFlow generate() {
        GeneratedExternalFlow flow;
        flow.events.reserve(regime_.run_length);

        for (std::size_t index = 0; index < regime_.run_length; ++index) {
            auto event = make_event(index);
            apply_generated_event(event);
            flow.events.push_back(std::move(event));
        }

        flow.diagnostics = diagnostics_;
        return flow;
    }

private:
    ExternalEvent make_event(std::size_t event_index) {
        std::uniform_int_distribution<int> distribution(1, 100);
        const auto draw = distribution(rng_);

        if (draw <= 55 || active_.empty()) {
            return make_limit_event(event_index);
        }
        if (draw <= 80) {
            return make_market_event();
        }
        if (draw <= 90) {
            return make_cancel_event();
        }
        return make_modify_event(event_index);
    }

    ExternalEvent make_limit_event(std::size_t event_index) {
        ExternalEvent event;
        event.action = ExternalAction::Limit;
        event.timestamp = next_timestamp_++;

        const auto side = random_side();
        const auto [price, offset] = passive_external_price(side, event_index);
        const auto quantity = random_quantity();
        const auto order_id = next_order_id_++;
        event.order = Order::limit(order_id,
                                   "external_" + std::to_string(order_id),
                                   side,
                                   price,
                                   quantity,
                                   event.timestamp);
        event.order_id = event.order.id;
        if (side == Side::Buy) {
            ++diagnostics_.limit_buy_orders;
            diagnostics_.limit_buy_quantity += quantity;
            diagnostics_.limit_buy_offset_sum += static_cast<double>(offset);
        } else {
            ++diagnostics_.limit_sell_orders;
            diagnostics_.limit_sell_quantity += quantity;
            diagnostics_.limit_sell_offset_sum += static_cast<double>(offset);
        }
        return event;
    }

    ExternalEvent make_market_event() {
        ExternalEvent event;
        event.action = ExternalAction::Market;
        event.timestamp = next_timestamp_++;

        const auto side = random_side();
        const auto quantity = random_quantity();
        event.order = Order::market(next_order_id_++, "external_taker", side, quantity, event.timestamp);
        event.order_id = event.order.id;
        if (side == Side::Buy) {
            ++diagnostics_.market_buy_orders;
            diagnostics_.market_buy_quantity += quantity;
        } else {
            ++diagnostics_.market_sell_orders;
            diagnostics_.market_sell_quantity += quantity;
        }
        return event;
    }

    ExternalEvent make_cancel_event() {
        ExternalEvent event;
        event.action = ExternalAction::Cancel;
        event.timestamp = next_timestamp_++;
        event.order_id = active_.random_id(rng_);
        return event;
    }

    ExternalEvent make_modify_event(std::size_t event_index) {
        ExternalEvent event;
        event.action = ExternalAction::Modify;
        event.timestamp = next_timestamp_++;
        event.order_id = active_.random_id(rng_);

        const auto snapshot = generation_engine_.book().snapshot_order(event.order_id);
        if (!snapshot.has_value()) {
            return make_limit_event(event_index);
        }

        std::uniform_int_distribution<int> mode_distribution(1, 100);
        if (mode_distribution(rng_) <= 50 && snapshot->remaining_quantity > 1) {
            event.new_price = std::nullopt;
            std::uniform_int_distribution<Quantity> reduce_distribution(1, snapshot->remaining_quantity - 1);
            event.new_quantity = reduce_distribution(rng_);
            return event;
        }

        const auto [price, offset] = passive_external_price(snapshot->side, event_index);
        event.new_price = price;
        event.new_quantity = random_quantity();
        if (snapshot->side == Side::Buy) {
            ++diagnostics_.price_modify_buy_orders;
            diagnostics_.price_modify_buy_quantity += event.new_quantity;
            diagnostics_.price_modify_buy_offset_sum += static_cast<double>(offset);
        } else {
            ++diagnostics_.price_modify_sell_orders;
            diagnostics_.price_modify_sell_quantity += event.new_quantity;
            diagnostics_.price_modify_sell_offset_sum += static_cast<double>(offset);
        }
        return event;
    }

    void apply_generated_event(const ExternalEvent& event) {
        auto result = apply_external_event(generation_engine_, event);
        if (!result.accepted) {
            throw std::runtime_error("generated external event rejected: " + result.reject_reason);
        }
        sync_after_external_result(generation_engine_, active_, event, result);
    }

    Side random_side() {
        std::uniform_int_distribution<int> distribution(0, 1);
        return distribution(rng_) == 0 ? Side::Buy : Side::Sell;
    }

    Quantity random_quantity() {
        std::uniform_int_distribution<Quantity> distribution(1, 100);
        return distribution(rng_);
    }

    std::pair<Price, Price> passive_external_price(Side side, std::size_t event_index) {
        std::uniform_int_distribution<Price> offset_distribution(8, 80);
        const auto reference = rounded_reference(reference_path_[event_index]);
        const auto offset = offset_distribution(rng_);
        return {side == Side::Buy ? reference - offset : reference + offset, offset};
    }

    const RegimeConfig& regime_;
    const std::vector<double>& reference_path_;
    std::mt19937_64 rng_;
    MatchingEngine generation_engine_{};
    ActiveExternalIndex active_{};
    ExternalFlowDiagnostics diagnostics_{};
    OrderId next_order_id_{1};
    Timestamp next_timestamp_{1};
};

FillSide market_maker_fill_side(const Trade& trade) {
    return is_market_maker_order(trade.buy_order_id) ? FillSide::Buy : FillSide::Sell;
}

LiquidityRole market_maker_liquidity_role(const Trade& trade) {
    return is_market_maker_order(trade.maker_order_id) ? LiquidityRole::Maker : LiquidityRole::Taker;
}

void record_market_maker_trades(PnlAccounting& accounting,
                                MarketMakerSummary& summary,
                                const std::vector<double>& reference_path,
                                std::size_t event_index,
                                std::size_t markout_horizon,
                                const ExecutionResult& result) {
    for (const auto& trade : result.trades) {
        const auto maker_is_market_maker = is_market_maker_order(trade.maker_order_id);
        const auto taker_is_market_maker = is_market_maker_order(trade.taker_order_id);
        if (!maker_is_market_maker && !taker_is_market_maker) {
            continue;
        }

        const auto side = market_maker_fill_side(trade);
        const auto role = market_maker_liquidity_role(trade);
        accounting.record_fill(FillEvent{side, role, static_cast<double>(trade.price), trade.quantity, event_index});

        summary.market_maker_filled_quantity += trade.quantity;
        if (side == FillSide::Buy) {
            ++summary.market_maker_buy_fills;
            summary.market_maker_buy_quantity += trade.quantity;
        } else {
            ++summary.market_maker_sell_fills;
            summary.market_maker_sell_quantity += trade.quantity;
        }
        if (role == LiquidityRole::Maker) {
            ++summary.maker_fills;

            const auto future_index = std::min(event_index + markout_horizon, reference_path.size() - 1);
            const auto future_mid = reference_path[future_index];
            const auto quantity = static_cast<double>(trade.quantity);
            const auto markout = side == FillSide::Buy
                                     ? (future_mid - static_cast<double>(trade.price)) * quantity
                                     : (static_cast<double>(trade.price) - future_mid) * quantity;
            summary.adverse_selection_cost += std::max(0.0, -markout);
        } else {
            ++summary.taker_fills;
        }
    }
}

void sync_quote_ids(const MatchingEngine& engine, QuoteIds& quotes) {
    if (quotes.bid.has_value() && !engine.book().contains(*quotes.bid)) {
        quotes.bid.reset();
    }
    if (quotes.ask.has_value() && !engine.book().contains(*quotes.ask)) {
        quotes.ask.reset();
    }
}

void cancel_quote(MatchingEngine& engine, std::optional<OrderId>& id, Timestamp timestamp) {
    if (!id.has_value()) {
        return;
    }
    if (engine.book().contains(*id)) {
        const auto result = engine.cancel_order(*id, timestamp);
        if (!result.accepted) {
            throw std::runtime_error("market maker quote cancel rejected: " + result.reject_reason);
        }
    }
    id.reset();
}

Price clipped_bid_price(const MatchingEngine& engine, Price proposed_bid) {
    const auto best_ask = engine.book().best_ask();
    if (best_ask.has_value() && proposed_bid >= *best_ask) {
        return *best_ask - 1;
    }
    return proposed_bid;
}

Price clipped_ask_price(const MatchingEngine& engine, Price proposed_ask) {
    const auto best_bid = engine.book().best_bid();
    if (best_bid.has_value() && proposed_ask <= *best_bid) {
        return *best_bid + 1;
    }
    return proposed_ask;
}

void record_quote_diagnostics(MarketMakerSummary& summary,
                              Price reference,
                              Price proposed_bid,
                              Price proposed_ask,
                              Price bid,
                              Price ask) {
    ++summary.quote_refreshes;
    if (bid != proposed_bid) {
        ++summary.bid_clip_events;
    }
    if (ask != proposed_ask) {
        ++summary.ask_clip_events;
    }

    const auto bid_distance = static_cast<double>(reference - bid);
    const auto ask_distance = static_cast<double>(ask - reference);
    const auto abs_asymmetry = std::fabs(ask_distance - bid_distance);

    if (bid_distance == ask_distance) {
        ++summary.symmetric_quote_refreshes;
    }
    summary.average_bid_distance += bid_distance;
    summary.average_ask_distance += ask_distance;
    summary.average_abs_quote_asymmetry += abs_asymmetry;
    summary.max_abs_quote_asymmetry = std::max(summary.max_abs_quote_asymmetry, abs_asymmetry);
}

void submit_quote(MatchingEngine& engine,
                  PnlAccounting& accounting,
                  MarketMakerSummary& summary,
                  QuoteIds& quotes,
                  const std::vector<double>& reference_path,
                  std::size_t event_index,
                  std::size_t markout_horizon,
                  OrderId order_id,
                  Side side,
                  Price price,
                  Quantity quantity,
                  Timestamp timestamp) {
    const auto order = Order::limit(order_id, kMarketMakerOwner, side, price, quantity, timestamp);
    const auto result = engine.submit_order(order);
    if (!result.accepted) {
        throw std::runtime_error("market maker quote rejected: " + result.reject_reason);
    }

    record_market_maker_trades(accounting, summary, reference_path, event_index, markout_horizon, result);

    if (engine.book().contains(order_id)) {
        if (side == Side::Buy) {
            quotes.bid = order_id;
        } else {
            quotes.ask = order_id;
        }
        summary.market_maker_posted_quantity += result.order->remaining_quantity;
    }
}

double drawdown_after_equity(double equity, double& peak_equity, double current_max_drawdown) {
    peak_equity = std::max(peak_equity, equity);
    return std::max(current_max_drawdown, peak_equity - equity);
}

bool should_store_curve_point(std::size_t event_index, std::size_t run_length, std::size_t stride) {
    const auto effective_stride = std::max<std::size_t>(1, stride);
    return event_index == 0 || event_index + 1 == run_length || event_index % effective_stride == 0;
}

const char* strategy_name(StrategyKind kind) {
    switch (kind) {
        case StrategyKind::NaiveSymmetric:
            return kNaiveStrategyName;
        case StrategyKind::AvellanedaStoikov:
            return kAvellanedaStoikovStrategyName;
    }
    return "unknown";
}

void validate_common_config(const MarketMakerSimulationConfig& config) {
    if (config.regime.run_length == 0) {
        throw std::invalid_argument("run length must be positive");
    }
    if (config.curve_sample_stride == 0) {
        throw std::invalid_argument("curve sample stride must be positive");
    }
}

void validate_naive_config(const NaiveSymmetricConfig& strategy) {
    if (strategy.half_spread_ticks <= 0) {
        throw std::invalid_argument("naive half spread must be positive");
    }
    if (strategy.quote_size <= 0) {
        throw std::invalid_argument("naive quote size must be positive");
    }
    if (strategy.refresh_cadence == 0) {
        throw std::invalid_argument("naive refresh cadence must be positive");
    }
}

void validate_avellaneda_stoikov_config(const AvellanedaStoikovConfig& strategy) {
    if (strategy.risk_aversion <= 0.0) {
        throw std::invalid_argument("risk aversion must be positive");
    }
    if (strategy.fill_decay <= 0.0) {
        throw std::invalid_argument("fill decay must be positive");
    }
    if (strategy.quote_size <= 0) {
        throw std::invalid_argument("avellaneda stoikov quote size must be positive");
    }
    if (strategy.refresh_cadence == 0) {
        throw std::invalid_argument("avellaneda stoikov refresh cadence must be positive");
    }
}

std::size_t refresh_cadence(const MarketMakerSimulationConfig& config, StrategyKind kind) {
    return kind == StrategyKind::NaiveSymmetric ? config.naive.refresh_cadence
                                                : config.avellaneda_stoikov.refresh_cadence;
}

QuotePrices make_naive_quote_prices(const MatchingEngine& engine,
                                    const NaiveSymmetricConfig& strategy,
                                    double reference_mid) {
    QuotePrices prices;
    prices.reference = rounded_reference(reference_mid);
    prices.proposed_bid = prices.reference - strategy.half_spread_ticks;
    prices.proposed_ask = prices.reference + strategy.half_spread_ticks;
    prices.bid = clipped_bid_price(engine, prices.proposed_bid);
    prices.ask = clipped_ask_price(engine, prices.proposed_ask);
    if (prices.bid >= prices.ask) {
        prices.bid = prices.ask - 1;
    }
    return prices;
}

QuotePrices make_avellaneda_stoikov_quote_prices(const MatchingEngine& engine,
                                                 const AvellanedaStoikovConfig& strategy,
                                                 const RegimeConfig& regime,
                                                 double reference_mid,
                                                 Quantity inventory,
                                                 std::size_t event_index) {
    const auto time_remaining =
        static_cast<double>(regime.run_length - event_index) / static_cast<double>(regime.run_length);
    const auto variance = regime.volatility_per_event * regime.volatility_per_event;
    const auto reservation_price =
        reference_mid - static_cast<double>(inventory) * strategy.risk_aversion * variance * time_remaining;
    const auto optimal_spread =
        strategy.risk_aversion * variance * time_remaining +
        (2.0 / strategy.risk_aversion) * std::log(1.0 + strategy.risk_aversion / strategy.fill_decay);
    const auto half_spread = std::max(0.5, optimal_spread / 2.0);

    QuotePrices prices;
    prices.reference = rounded_reference(reference_mid);
    prices.proposed_bid = static_cast<Price>(std::floor(reservation_price - half_spread));
    prices.proposed_ask = static_cast<Price>(std::ceil(reservation_price + half_spread));
    if (prices.proposed_bid >= prices.proposed_ask) {
        prices.proposed_ask = prices.proposed_bid + 1;
    }
    prices.bid = clipped_bid_price(engine, prices.proposed_bid);
    prices.ask = clipped_ask_price(engine, prices.proposed_ask);
    if (prices.bid >= prices.ask) {
        prices.bid = prices.ask - 1;
    }
    return prices;
}

QuotePrices make_quote_prices(const MatchingEngine& engine,
                              const MarketMakerSimulationConfig& config,
                              StrategyKind kind,
                              double reference_mid,
                              Quantity inventory,
                              std::size_t event_index) {
    if (kind == StrategyKind::NaiveSymmetric) {
        return make_naive_quote_prices(engine, config.naive, reference_mid);
    }
    return make_avellaneda_stoikov_quote_prices(engine,
                                                config.avellaneda_stoikov,
                                                config.regime,
                                                reference_mid,
                                                inventory,
                                                event_index);
}

Quantity quote_size(const MarketMakerSimulationConfig& config, StrategyKind kind) {
    return kind == StrategyKind::NaiveSymmetric ? config.naive.quote_size : config.avellaneda_stoikov.quote_size;
}

double time_remaining_after_event(const RegimeConfig& regime, std::size_t event_index) {
    const auto next_index = std::min(event_index + 1, regime.run_length);
    return static_cast<double>(regime.run_length - next_index) / static_cast<double>(regime.run_length);
}

double reservation_skew(const MarketMakerSimulationConfig& config,
                        StrategyKind kind,
                        Quantity inventory,
                        double time_remaining) {
    if (kind == StrategyKind::NaiveSymmetric) {
        return 0.0;
    }
    const auto variance = config.regime.volatility_per_event * config.regime.volatility_per_event;
    return static_cast<double>(inventory) * config.avellaneda_stoikov.risk_aversion * variance * time_remaining;
}

void refresh_quotes(MatchingEngine& engine,
                    PnlAccounting& accounting,
                    MarketMakerSummary& summary,
                    QuoteIds& quotes,
                    const MarketMakerSimulationConfig& config,
                    StrategyKind kind,
                    const std::vector<double>& reference_path,
                    std::size_t event_index,
                    OrderId& next_market_maker_order_id,
                    Timestamp& next_market_maker_timestamp) {
    cancel_quote(engine, quotes.bid, next_market_maker_timestamp++);
    cancel_quote(engine, quotes.ask, next_market_maker_timestamp++);

    const auto inventory = accounting.snapshot().inventory;
    const auto prices = make_quote_prices(engine, config, kind, reference_path[event_index], inventory, event_index);
    if (prices.bid <= 0 || prices.ask <= 0) {
        throw std::runtime_error("market maker quote price must be positive");
    }
    record_quote_diagnostics(summary, prices.reference, prices.proposed_bid, prices.proposed_ask, prices.bid, prices.ask);

    submit_quote(engine,
                 accounting,
                 summary,
                 quotes,
                 reference_path,
                 event_index,
                 config.markout_horizon,
                 next_market_maker_order_id++,
                 Side::Buy,
                 prices.bid,
                 quote_size(config, kind),
                 next_market_maker_timestamp++);
    submit_quote(engine,
                 accounting,
                 summary,
                 quotes,
                 reference_path,
                 event_index,
                 config.markout_horizon,
                 next_market_maker_order_id++,
                 Side::Sell,
                 prices.ask,
                 quote_size(config, kind),
                 next_market_maker_timestamp++);
}

MarketMakerRunResult run_strategy(const MarketMakerSimulationConfig& config, StrategyKind kind) {
    validate_common_config(config);
    if (kind == StrategyKind::NaiveSymmetric) {
        validate_naive_config(config.naive);
    } else {
        validate_avellaneda_stoikov_config(config.avellaneda_stoikov);
    }

    const auto reference_path = generate_reference_path(config.regime);
    auto external_flow = ExternalFlowGenerator(config.regime, reference_path).generate();
    const auto& external_events = external_flow.events;

    MatchingEngine engine;
    PnlAccounting accounting(config.regime.name, strategy_name(kind), reference_path.front());
    QuoteIds quotes;
    OrderId next_market_maker_order_id = kMarketMakerOrderIdStart;
    Timestamp next_market_maker_timestamp = 1'000'000'000;

    MarketMakerRunResult result;
    result.summary.strategy_name = strategy_name(kind);
    result.summary.regime_name = config.regime.name;
    result.summary.seed = config.regime.seed;
    result.summary.events = config.regime.run_length;
    result.summary.initial_reference_mid = reference_path.front();
    result.summary.final_reference_mid = reference_path.back();
    result.summary.external_limit_buy_orders = external_flow.diagnostics.limit_buy_orders;
    result.summary.external_limit_sell_orders = external_flow.diagnostics.limit_sell_orders;
    result.summary.external_market_buy_orders = external_flow.diagnostics.market_buy_orders;
    result.summary.external_market_sell_orders = external_flow.diagnostics.market_sell_orders;
    result.summary.external_price_modify_buy_orders = external_flow.diagnostics.price_modify_buy_orders;
    result.summary.external_price_modify_sell_orders = external_flow.diagnostics.price_modify_sell_orders;
    result.summary.external_limit_buy_quantity = external_flow.diagnostics.limit_buy_quantity;
    result.summary.external_limit_sell_quantity = external_flow.diagnostics.limit_sell_quantity;
    result.summary.external_market_buy_quantity = external_flow.diagnostics.market_buy_quantity;
    result.summary.external_market_sell_quantity = external_flow.diagnostics.market_sell_quantity;
    result.summary.external_price_modify_buy_quantity = external_flow.diagnostics.price_modify_buy_quantity;
    result.summary.external_price_modify_sell_quantity = external_flow.diagnostics.price_modify_sell_quantity;
    result.summary.average_external_limit_buy_offset =
        result.summary.external_limit_buy_orders == 0
            ? 0.0
            : external_flow.diagnostics.limit_buy_offset_sum /
                  static_cast<double>(result.summary.external_limit_buy_orders);
    result.summary.average_external_limit_sell_offset =
        result.summary.external_limit_sell_orders == 0
            ? 0.0
            : external_flow.diagnostics.limit_sell_offset_sum /
                  static_cast<double>(result.summary.external_limit_sell_orders);
    result.summary.average_external_price_modify_buy_offset =
        result.summary.external_price_modify_buy_orders == 0
            ? 0.0
            : external_flow.diagnostics.price_modify_buy_offset_sum /
                  static_cast<double>(result.summary.external_price_modify_buy_orders);
    result.summary.average_external_price_modify_sell_offset =
        result.summary.external_price_modify_sell_orders == 0
            ? 0.0
            : external_flow.diagnostics.price_modify_sell_offset_sum /
                  static_cast<double>(result.summary.external_price_modify_sell_orders);

    double peak_equity = 0.0;
    RunningMoments inventory_moments;

    for (std::size_t event_index = 0; event_index < external_events.size(); ++event_index) {
        if (event_index % refresh_cadence(config, kind) == 0) {
            refresh_quotes(engine,
                           accounting,
                           result.summary,
                           quotes,
                           config,
                           kind,
                           reference_path,
                           event_index,
                           next_market_maker_order_id,
                           next_market_maker_timestamp);
        }

        const auto external_result = apply_external_event(engine, external_events[event_index]);
        if (!external_result.accepted) {
            ++result.summary.external_rejects;
        }
        record_market_maker_trades(accounting,
                                   result.summary,
                                   reference_path,
                                   event_index,
                                   config.markout_horizon,
                                   external_result);
        sync_quote_ids(engine, quotes);

        accounting.record_reference_mid(reference_path[event_index + 1]);
        const auto state = accounting.snapshot();
        result.summary.maximum_drawdown =
            drawdown_after_equity(state.net_pnl_after_fees, peak_equity, result.summary.maximum_drawdown);
        inventory_moments.add(static_cast<double>(state.inventory));

        if (should_store_curve_point(event_index, config.regime.run_length, config.curve_sample_stride)) {
            const auto time_remaining = time_remaining_after_event(config.regime, event_index);
            const auto skew = reservation_skew(config, kind, state.inventory, time_remaining);
            result.curve.push_back(MarketMakerCurvePoint{strategy_name(kind),
                                                         config.regime.name,
                                                         event_index,
                                                         time_remaining,
                                                         state.reference_mid,
                                                         state.reference_mid - skew,
                                                         skew,
                                                         state.cash,
                                                         state.inventory,
                                                         state.net_pnl_after_fees});
        }
    }

    const auto final_state = accounting.snapshot();
    result.summary.fill_rate = result.summary.market_maker_posted_quantity == 0
                                   ? 0.0
                                   : static_cast<double>(result.summary.market_maker_filled_quantity) /
                                         static_cast<double>(result.summary.market_maker_posted_quantity);
    result.summary.gross_spread_capture = final_state.spread_capture;
    result.summary.inventory_pnl = final_state.inventory_pnl_balancing;
    result.summary.inventory_pnl_from_marks = final_state.inventory_pnl_from_marks;
    result.summary.inventory_pnl_mark_error =
        final_state.inventory_pnl_balancing - final_state.inventory_pnl_from_marks;
    result.summary.gross_identity_error =
        final_state.gross_pnl_before_fees -
        (final_state.spread_capture + final_state.inventory_pnl_balancing);
    result.summary.net_identity_error =
        final_state.net_pnl_after_fees -
        (final_state.spread_capture + final_state.inventory_pnl_balancing + final_state.fee_pnl);
    result.summary.fee_pnl = final_state.fee_pnl;
    result.summary.net_pnl_after_fees = final_state.net_pnl_after_fees;
    result.summary.inventory_variance = inventory_moments.variance();
    result.summary.final_inventory = final_state.inventory;
    if (result.summary.quote_refreshes > 0) {
        const auto refreshes = static_cast<double>(result.summary.quote_refreshes);
        result.summary.average_bid_distance /= refreshes;
        result.summary.average_ask_distance /= refreshes;
        result.summary.average_abs_quote_asymmetry /= refreshes;
    }
    result.summary.reconciliation_passed = accounting.reconciles(kRunReconciliationTolerance);
    accounting.assert_reconciles(kRunReconciliationTolerance);

    return result;
}

}  // namespace

MarketMakerRunResult run_naive_symmetric_strategy(const MarketMakerSimulationConfig& config) {
    return run_strategy(config, StrategyKind::NaiveSymmetric);
}

MarketMakerRunResult run_avellaneda_stoikov_strategy(const MarketMakerSimulationConfig& config) {
    return run_strategy(config, StrategyKind::AvellanedaStoikov);
}

}  // namespace lob
