#include "lob/matching_engine.hpp"
#include "lob/price_level.hpp"

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

enum class BenchmarkAction {
    Limit,
    Market,
    Cancel,
    Modify
};

struct BenchmarkEvent {
    BenchmarkAction action{BenchmarkAction::Limit};
    lob::Timestamp timestamp{};
    lob::Order order{};
    lob::OrderId order_id{};
    std::optional<lob::Price> new_price{};
    lob::Quantity new_quantity{};
};

struct ActiveOrder {
    lob::Side side{lob::Side::Buy};
    lob::Price price{};
};

struct ActiveIndex {
    std::vector<lob::OrderId> ids{};
    std::unordered_map<lob::OrderId, std::size_t> positions{};
    std::unordered_map<lob::OrderId, ActiveOrder> orders{};

    bool empty() const {
        return ids.empty();
    }

    void remove(lob::OrderId id) {
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

    void upsert(const lob::Order& order) {
        if (positions.find(order.id) == positions.end()) {
            positions[order.id] = ids.size();
            ids.push_back(order.id);
        }
        orders[order.id] = ActiveOrder{order.side, order.price.value()};
    }

    lob::OrderId random_id(std::mt19937_64& rng) const {
        std::uniform_int_distribution<std::size_t> distribution(0, ids.size() - 1);
        return ids[distribution(rng)];
    }
};

struct Config {
    std::size_t events{1'000'000};
    std::size_t warmup{20'000};
    std::uint64_t seed{42};
    std::filesystem::path output_dir{"build/benchmark_results"};
};

struct EventCounts {
    std::size_t limit{};
    std::size_t market{};
    std::size_t cancel{};
    std::size_t modify{};
};

struct GeneratedFlow {
    std::vector<BenchmarkEvent> warmup_events{};
    std::vector<BenchmarkEvent> measured_events{};
    EventCounts measured_counts{};
};

std::uint64_t parse_u64(const std::string& value) {
    std::size_t consumed = 0;
    const auto parsed = std::stoull(value, &consumed);
    if (consumed != value.size()) {
        throw std::runtime_error("invalid numeric argument");
    }
    return parsed;
}

Config parse_args(int argc, char** argv) {
    Config config;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        auto require_value = [&]() -> std::string {
            if (index + 1 >= argc) {
                throw std::runtime_error("missing argument value");
            }
            ++index;
            return argv[index];
        };

        if (argument == "--events") {
            config.events = static_cast<std::size_t>(parse_u64(require_value()));
        } else if (argument == "--warmup") {
            config.warmup = static_cast<std::size_t>(parse_u64(require_value()));
        } else if (argument == "--seed") {
            config.seed = parse_u64(require_value());
        } else if (argument == "--output-dir") {
            config.output_dir = require_value();
        } else {
            throw std::runtime_error("unknown argument: " + argument);
        }
    }

    if (config.events == 0) {
        throw std::runtime_error("events must be positive");
    }
    return config;
}

void sync_active_id(lob::MatchingEngine& engine, ActiveIndex& active, lob::OrderId id) {
    const auto snapshot = engine.book().snapshot_order(id);
    if (snapshot.has_value()) {
        active.upsert(*snapshot);
    } else {
        active.remove(id);
    }
}

void sync_after_result(lob::MatchingEngine& engine,
                       ActiveIndex& active,
                       const BenchmarkEvent& event,
                       const lob::ExecutionResult& result) {
    if (event.action == BenchmarkAction::Cancel) {
        active.remove(event.order_id);
    } else if (event.action == BenchmarkAction::Modify) {
        sync_active_id(engine, active, event.order_id);
    } else if (event.action == BenchmarkAction::Limit || event.action == BenchmarkAction::Market) {
        sync_active_id(engine, active, event.order.id);
    }

    for (const auto& trade : result.trades) {
        sync_active_id(engine, active, trade.maker_order_id);
    }
}

lob::ExecutionResult apply_event(lob::MatchingEngine& engine, const BenchmarkEvent& event) {
    switch (event.action) {
        case BenchmarkAction::Limit:
        case BenchmarkAction::Market:
            return engine.submit_order(event.order);
        case BenchmarkAction::Cancel:
            return engine.cancel_order(event.order_id, event.timestamp);
        case BenchmarkAction::Modify:
            return engine.modify_order(event.order_id, event.new_price, event.new_quantity, event.timestamp);
    }
    throw std::runtime_error("unknown benchmark action");
}

class FlowGenerator {
public:
    explicit FlowGenerator(std::uint64_t seed) : rng_(seed) {}

    GeneratedFlow generate(std::size_t warmup_count, std::size_t measured_count) {
        GeneratedFlow flow;
        flow.warmup_events.reserve(warmup_count);
        flow.measured_events.reserve(measured_count);

        for (std::size_t index = 0; index < warmup_count; ++index) {
            auto event = make_limit_event();
            apply_generated_event(event);
            flow.warmup_events.push_back(std::move(event));
        }

        for (std::size_t index = 0; index < measured_count; ++index) {
            auto event = make_measured_event();
            apply_generated_event(event);
            increment_count(flow.measured_counts, event.action);
            flow.measured_events.push_back(std::move(event));
        }

        return flow;
    }

private:
    BenchmarkEvent make_measured_event() {
        update_reference_price();

        std::uniform_int_distribution<int> distribution(1, 100);
        const auto draw = distribution(rng_);

        if (draw <= 60 || active_.empty()) {
            return make_limit_event();
        }
        if (draw <= 70) {
            return make_market_event();
        }
        if (draw <= 90) {
            return make_cancel_event();
        }
        return make_modify_event();
    }

    BenchmarkEvent make_limit_event() {
        BenchmarkEvent event;
        event.action = BenchmarkAction::Limit;
        event.timestamp = next_timestamp_++;

        const auto side = random_side();
        const auto price = passive_price(side);
        const auto quantity = random_quantity();
        const auto order_id = next_order_id_++;
        event.order = lob::Order::limit(order_id, "resting_" + std::to_string(order_id), side, price, quantity, event.timestamp);
        event.order_id = event.order.id;
        return event;
    }

    BenchmarkEvent make_market_event() {
        BenchmarkEvent event;
        event.action = BenchmarkAction::Market;
        event.timestamp = next_timestamp_++;

        const auto side = random_side();
        const auto quantity = random_quantity();
        event.order = lob::Order::market(next_order_id_++, "aggressor", side, quantity, event.timestamp);
        event.order_id = event.order.id;
        return event;
    }

    BenchmarkEvent make_cancel_event() {
        BenchmarkEvent event;
        event.action = BenchmarkAction::Cancel;
        event.timestamp = next_timestamp_++;
        event.order_id = active_.random_id(rng_);
        return event;
    }

    BenchmarkEvent make_modify_event() {
        BenchmarkEvent event;
        event.action = BenchmarkAction::Modify;
        event.timestamp = next_timestamp_++;
        event.order_id = active_.random_id(rng_);

        const auto snapshot = simulation_engine_.book().snapshot_order(event.order_id);
        if (!snapshot.has_value()) {
            return make_limit_event();
        }

        std::uniform_int_distribution<int> mode_distribution(1, 100);
        if (mode_distribution(rng_) <= 50 && snapshot->remaining_quantity > 1) {
            event.new_price = std::nullopt;
            std::uniform_int_distribution<lob::Quantity> reduce_distribution(1, snapshot->remaining_quantity - 1);
            event.new_quantity = reduce_distribution(rng_);
            return event;
        }

        event.new_price = passive_price(snapshot->side);
        event.new_quantity = random_quantity();
        return event;
    }

    void apply_generated_event(const BenchmarkEvent& event) {
        auto result = apply_event(simulation_engine_, event);
        if (!result.accepted) {
            throw std::runtime_error("generated event was rejected: " + result.reject_reason);
        }
        sync_after_result(simulation_engine_, active_, event, result);
    }

    static void increment_count(EventCounts& counts, BenchmarkAction action) {
        switch (action) {
            case BenchmarkAction::Limit:
                ++counts.limit;
                break;
            case BenchmarkAction::Market:
                ++counts.market;
                break;
            case BenchmarkAction::Cancel:
                ++counts.cancel;
                break;
            case BenchmarkAction::Modify:
                ++counts.modify;
                break;
        }
    }

    lob::Side random_side() {
        std::uniform_int_distribution<int> distribution(0, 1);
        return distribution(rng_) == 0 ? lob::Side::Buy : lob::Side::Sell;
    }

    lob::Quantity random_quantity() {
        std::uniform_int_distribution<lob::Quantity> distribution(1, 100);
        return distribution(rng_);
    }

    lob::Price passive_price(lob::Side side) {
        std::uniform_int_distribution<lob::Price> offset_distribution(5, 200);
        const auto offset = offset_distribution(rng_);
        return side == lob::Side::Buy ? reference_price_ - offset : reference_price_ + offset;
    }

    void update_reference_price() {
        std::uniform_int_distribution<int> step_distribution(-1, 1);
        reference_price_ += step_distribution(rng_);

        const auto anchor = 100'000;
        if (reference_price_ > anchor + 250) {
            --reference_price_;
        } else if (reference_price_ < anchor - 250) {
            ++reference_price_;
        }
    }

    std::mt19937_64 rng_;
    lob::MatchingEngine simulation_engine_{};
    ActiveIndex active_{};
    lob::OrderId next_order_id_{1};
    lob::Timestamp next_timestamp_{1};
    lob::Price reference_price_{100'000};
};

struct ReplaySummary {
    std::size_t rejects{};
    std::size_t trades{};
    std::uint64_t total_ns{};
    double events_per_second{};
    std::uint64_t p50_ns{};
    std::uint64_t p95_ns{};
    std::uint64_t p99_ns{};
    std::uint64_t max_ns{};
};

std::uint64_t percentile(const std::vector<std::uint64_t>& sorted, double probability) {
    const auto raw_index = static_cast<std::size_t>(probability * static_cast<double>(sorted.size() - 1));
    return sorted[raw_index];
}

ReplaySummary replay_flow(const GeneratedFlow& flow,
                          const std::filesystem::path& latency_path,
                          std::vector<std::uint64_t>& latencies) {
    lob::MatchingEngine engine;

    for (const auto& event : flow.warmup_events) {
        const auto result = apply_event(engine, event);
        if (!result.accepted) {
            throw std::runtime_error("warmup replay event was rejected");
        }
    }

    latencies.clear();
    latencies.reserve(flow.measured_events.size());

    ReplaySummary summary;
    const auto total_start = Clock::now();
    for (const auto& event : flow.measured_events) {
        const auto start = Clock::now();
        const auto result = apply_event(engine, event);
        const auto stop = Clock::now();

        if (!result.accepted) {
            ++summary.rejects;
        }
        summary.trades += result.trades.size();
        latencies.push_back(static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count()));
    }
    const auto total_stop = Clock::now();

    summary.total_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(total_stop - total_start).count());
    summary.events_per_second = static_cast<double>(flow.measured_events.size()) /
                                (static_cast<double>(summary.total_ns) / 1'000'000'000.0);

    std::vector<std::uint64_t> sorted = latencies;
    std::sort(sorted.begin(), sorted.end());
    summary.p50_ns = percentile(sorted, 0.50);
    summary.p95_ns = percentile(sorted, 0.95);
    summary.p99_ns = percentile(sorted, 0.99);
    summary.max_ns = sorted.back();

    std::ofstream latency_output(latency_path);
    if (!latency_output) {
        throw std::runtime_error("could not write latency csv");
    }
    latency_output << "event_index,latency_ns\n";
    for (std::size_t index = 0; index < latencies.size(); ++index) {
        latency_output << index << ',' << latencies[index] << '\n';
    }

    return summary;
}

void write_summary(const std::filesystem::path& path,
                   const Config& config,
                   const GeneratedFlow& flow,
                   const ReplaySummary& summary) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write summary csv");
    }

    output << std::setprecision(12);
    output << "metric,value\n";
    output << "seed," << config.seed << '\n';
    output << "warmup_events," << config.warmup << '\n';
    output << "measured_events," << config.events << '\n';
    output << "events_per_second," << summary.events_per_second << '\n';
    output << "total_seconds," << static_cast<double>(summary.total_ns) / 1'000'000'000.0 << '\n';
    output << "p50_latency_ns," << summary.p50_ns << '\n';
    output << "p95_latency_ns," << summary.p95_ns << '\n';
    output << "p99_latency_ns," << summary.p99_ns << '\n';
    output << "max_latency_ns," << summary.max_ns << '\n';
    output << "trades," << summary.trades << '\n';
    output << "rejects," << summary.rejects << '\n';
    output << "limit_events," << flow.measured_counts.limit << '\n';
    output << "market_events," << flow.measured_counts.market << '\n';
    output << "cancel_events," << flow.measured_counts.cancel << '\n';
    output << "modify_events," << flow.measured_counts.modify << '\n';
    output << "sizeof_order_bytes," << sizeof(lob::Order) << '\n';
    output << "sizeof_price_level_bytes," << sizeof(lob::PriceLevel) << '\n';
    output << "estimated_resting_order_bytes," << sizeof(lob::Order) + 2 * sizeof(void*) << '\n';
}

void write_event_mix(const std::filesystem::path& path, const EventCounts& counts) {
    const auto total = counts.limit + counts.market + counts.cancel + counts.modify;
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write event mix csv");
    }
    output << std::setprecision(12);
    output << "action,count,share\n";
    output << "limit," << counts.limit << ',' << static_cast<double>(counts.limit) / static_cast<double>(total) << '\n';
    output << "market," << counts.market << ',' << static_cast<double>(counts.market) / static_cast<double>(total) << '\n';
    output << "cancel," << counts.cancel << ',' << static_cast<double>(counts.cancel) / static_cast<double>(total) << '\n';
    output << "modify," << counts.modify << ',' << static_cast<double>(counts.modify) / static_cast<double>(total) << '\n';
}

void write_run_config(const std::filesystem::path& path, const Config& config) {
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("could not write config csv");
    }
    output << "field,value\n";
    output << "benchmark,orderbook_benchmark\n";
    output << "seed," << config.seed << '\n';
    output << "warmup_events," << config.warmup << '\n';
    output << "measured_events," << config.events << '\n';
    output << "requested_limit_share,0.60\n";
    output << "requested_market_share,0.10\n";
    output << "requested_cancel_share,0.20\n";
    output << "requested_modify_share,0.10\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto config = parse_args(argc, argv);
        std::filesystem::create_directories(config.output_dir);

        FlowGenerator generator(config.seed);
        const auto flow = generator.generate(config.warmup, config.events);

        std::vector<std::uint64_t> latencies;
        const auto summary = replay_flow(flow, config.output_dir / "latencies.csv", latencies);

        write_summary(config.output_dir / "summary.csv", config, flow, summary);
        write_event_mix(config.output_dir / "event_mix.csv", flow.measured_counts);
        write_run_config(config.output_dir / "run_config.csv", config);

        std::cout << std::setprecision(12);
        std::cout << "events_per_second=" << summary.events_per_second << '\n';
        std::cout << "p50_latency_ns=" << summary.p50_ns << '\n';
        std::cout << "p95_latency_ns=" << summary.p95_ns << '\n';
        std::cout << "p99_latency_ns=" << summary.p99_ns << '\n';
        std::cout << "max_latency_ns=" << summary.max_ns << '\n';
        std::cout << "rejects=" << summary.rejects << '\n';
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }

    return 0;
}
