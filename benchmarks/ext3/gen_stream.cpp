// Extension 3(a): generate the shared synthetic order stream once (seed 42) and write it to CSV.
//
// This is a re-implementation of the hand-chosen FlowGenerator in benchmarks/orderbook_benchmark.cpp
// (same RNG, same event weights 60/10/20/10, same uniform 1..100 sizes, same passive price rule
// reference +/- U{5..200}, same bounded +/-1 reference random walk around 100000, same 20,000 limit-only
// warm-up events), with exactly two pre-registered changes (see PREREG.md section 3):
//   1. owner_id is empty for every order (self-trade prevention exists only in this repo's engine);
//   2. every modify is a cancel/replace to a NEW price (redrawn until it differs from the current price)
//      with a new random size. The repo's same-price size reduction keeps time priority, while
//      Liquibook's replace always re-queues the order, so same-price modifies are excluded.
// The repo's own MatchingEngine (map book) is used, as in the original, only to track which orders are
// live so that cancels and modifies always target a live order.
//
// Output CSV columns: phase,action,id,side,price,qty,ts
//   phase  W = warm-up, M = measured
//   action L = limit add, M = market (IOC), C = cancel, R = cancel/replace (price = new price, qty = new size)
//   side   B or S (blank for C and R; the engines know the side of a live order)
//   price  limit price for L, new price for R, 0 for M and C
//   qty    size for L and M, new size for R, 0 for C
#include "lob/matching_engine.hpp"

#include <cstdint>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

struct ActiveIndex {
    std::vector<lob::OrderId> ids{};
    std::unordered_map<lob::OrderId, std::size_t> positions{};

    bool empty() const { return ids.empty(); }

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
    }

    void upsert(lob::OrderId id) {
        if (positions.find(id) == positions.end()) {
            positions[id] = ids.size();
            ids.push_back(id);
        }
    }

    lob::OrderId random_id(std::mt19937_64& rng) const {
        std::uniform_int_distribution<std::size_t> distribution(0, ids.size() - 1);
        return ids[distribution(rng)];
    }
};

struct Row {
    char phase;
    char action;
    std::uint64_t id;
    char side;
    std::int64_t price;
    std::int64_t qty;
    std::int64_t ts;
};

class Generator {
public:
    Generator(std::uint64_t seed, bool original_modify) : rng_(seed), original_modify_(original_modify) {}

    std::vector<Row> run(std::size_t warmup, std::size_t measured) {
        std::vector<Row> rows;
        rows.reserve(warmup + measured);
        for (std::size_t i = 0; i < warmup; ++i) {
            rows.push_back(make_limit('W'));
        }
        for (std::size_t i = 0; i < measured; ++i) {
            rows.push_back(make_measured());
        }
        return rows;
    }

private:
    Row make_measured() {
        update_reference_price();
        std::uniform_int_distribution<int> distribution(1, 100);
        const auto draw = distribution(rng_);
        if (draw <= 60 || active_.empty()) {
            return make_limit('M');
        }
        if (draw <= 70) {
            return make_market();
        }
        if (draw <= 90) {
            return make_cancel();
        }
        return make_modify();
    }

    Row make_limit(char phase) {
        const auto ts = next_ts_++;
        const auto side = random_side();
        const auto price = passive_price(side);
        const auto qty = random_quantity();
        const auto id = next_id_++;
        apply(engine_.submit_order(lob::Order::limit(id, std::string{}, side, price, qty, ts)), id);
        return Row{phase, 'L', id, side == lob::Side::Buy ? 'B' : 'S', price, qty, ts};
    }

    Row make_market() {
        const auto ts = next_ts_++;
        const auto side = random_side();
        const auto qty = random_quantity();
        const auto id = next_id_++;
        apply(engine_.submit_order(lob::Order::market(id, std::string{}, side, qty, ts)), id);
        return Row{'M', 'M', id, side == lob::Side::Buy ? 'B' : 'S', 0, qty, ts};
    }

    Row make_cancel() {
        const auto ts = next_ts_++;
        const auto id = active_.random_id(rng_);
        apply(engine_.cancel_order(id, ts), id);
        active_.remove(id);
        return Row{'M', 'C', id, ' ', 0, 0, ts};
    }

    Row make_modify() {
        const auto ts = next_ts_++;
        const auto id = active_.random_id(rng_);
        const auto snapshot = engine_.book().snapshot_order(id);
        if (!snapshot.has_value()) {
            throw std::runtime_error("active index out of sync");
        }
        if (original_modify_) {
            // Negative control only (not the benchmark stream): the repo's original modify rule, 50% same-price
            // size reductions that keep time priority in this repo's engine but re-queue in Liquibook.
            std::uniform_int_distribution<int> mode_distribution(1, 100);
            if (mode_distribution(rng_) <= 50 && snapshot->remaining_quantity > 1) {
                std::uniform_int_distribution<lob::Quantity> reduce_distribution(1, snapshot->remaining_quantity - 1);
                const auto reduced = reduce_distribution(rng_);
                const auto same_price = snapshot->price.value();
                apply(engine_.modify_order(id, same_price, reduced, ts), id);
                return Row{'M', 'R', id, ' ', same_price, reduced, ts};
            }
        }
        lob::Price new_price = passive_price(snapshot->side);
        while (new_price == snapshot->price.value()) {
            new_price = passive_price(snapshot->side);
        }
        const auto new_qty = random_quantity();
        apply(engine_.modify_order(id, new_price, new_qty, ts), id);
        return Row{'M', 'R', id, ' ', new_price, new_qty, ts};
    }

    void apply(const lob::ExecutionResult& result, lob::OrderId id) {
        if (!result.accepted) {
            throw std::runtime_error("generated event rejected: " + result.reject_reason);
        }
        sync(id);
        for (const auto& trade : result.trades) {
            sync(trade.maker_order_id);
        }
    }

    void sync(lob::OrderId id) {
        if (engine_.book().contains(id)) {
            active_.upsert(id);
        } else {
            active_.remove(id);
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
    bool original_modify_{false};
    lob::MatchingEngine engine_{};
    ActiveIndex active_{};
    lob::OrderId next_id_{1};
    lob::Timestamp next_ts_{1};
    lob::Price reference_price_{100'000};
};

}  // namespace

int main(int argc, char** argv) {
    const bool original_modify = argc == 3 && std::string(argv[2]) == "--negative-control-original-modify";
    if (argc != 2 && !original_modify) {
        std::cerr << "usage: gen_stream <output.csv> [--negative-control-original-modify]\n";
        return 2;
    }
    try {
        Generator generator(42, original_modify);
        const auto rows = generator.run(20'000, 1'000'000);
        std::ofstream out(argv[1]);
        if (!out) {
            throw std::runtime_error("cannot open output");
        }
        out << "phase,action,id,side,price,qty,ts\n";
        std::size_t counts[4] = {0, 0, 0, 0};
        for (const auto& r : rows) {
            out << r.phase << ',' << r.action << ',' << r.id << ',';
            if (r.side != ' ') {
                out << r.side;
            }
            out << ',' << r.price << ',' << r.qty << ',' << r.ts << '\n';
            if (r.phase == 'M') {
                counts[r.action == 'L' ? 0 : r.action == 'M' ? 1 : r.action == 'C' ? 2 : 3]++;
            }
        }
        std::cout << "rows=" << rows.size() << " measured_limit=" << counts[0] << " measured_market=" << counts[1]
                  << " measured_cancel=" << counts[2] << " measured_replace=" << counts[3] << '\n';
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
