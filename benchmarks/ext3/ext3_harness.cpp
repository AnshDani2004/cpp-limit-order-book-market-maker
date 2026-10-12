// Extension 3(a) harness: replay one pre-generated stream into this repo's engine or into Liquibook,
// with the same event structs, the same timing loop and the same timer for every engine.
//
//   ext3_harness check <stream.csv>                         equivalence check (all engines, untimed)
//   ext3_harness time <stream.csv> <engine> <summary.csv>   one timed run of one engine
//
// Engines: map, flat (this repo, BasicMatchingEngine over OrderBook / FlatOrderBook),
//          lb_new, lb_pool, lb_shared (Liquibook liquibook::book::OrderBook, three order-ownership styles).
// Built twice by build.sh: ext3_harness links lob_core as a separate static library (as the repo ships
// it); ext3_harness_unity is compiled with -DEXT3_UNITY, which pulls the repo's engine sources into this
// translation unit (sensitivity check for cross-TU inlining; Liquibook is header-only either way).
#include "lob/matching_engine.hpp"

#include <book/order.h>
#include <book/order_book.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#ifdef EXT3_UNITY
#include "../../src/flat_order_book.cpp"
#include "../../src/matching_engine.cpp"
#include "../../src/order_book.cpp"
#include "../../src/price_level.cpp"
#endif

namespace {

using Clock = std::chrono::steady_clock;

enum class Action : std::uint8_t { Limit, Market, Cancel, Replace };

struct Event {
    Action action{Action::Limit};
    bool buy{true};
    std::uint64_t id{};
    std::int64_t price{};
    std::int64_t qty{};
    std::int64_t ts{};
};

struct Stream {
    std::vector<Event> warmup{};
    std::vector<Event> measured{};
};

Stream load_stream(const std::string& path) {
    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error("cannot open stream " + path);
    }
    Stream stream;
    stream.warmup.reserve(20'000);
    stream.measured.reserve(1'000'000);
    std::string line;
    std::getline(in, line);
    if (line != "phase,action,id,side,price,qty,ts") {
        throw std::runtime_error("unexpected stream header");
    }
    while (std::getline(in, line)) {
        // phase,action,id,side,price,qty,ts
        const char phase = line[0];
        Event e;
        switch (line[2]) {
            case 'L': e.action = Action::Limit; break;
            case 'M': e.action = Action::Market; break;
            case 'C': e.action = Action::Cancel; break;
            case 'R': e.action = Action::Replace; break;
            default: throw std::runtime_error("bad action");
        }
        std::size_t pos = 4;
        auto next_field = [&]() {
            const auto comma = line.find(',', pos);
            std::string field = line.substr(pos, comma == std::string::npos ? std::string::npos : comma - pos);
            pos = comma == std::string::npos ? line.size() : comma + 1;
            return field;
        };
        e.id = std::stoull(next_field());
        const auto side = next_field();
        e.buy = side == "B";
        e.price = std::stoll(next_field());
        e.qty = std::stoll(next_field());
        e.ts = std::stoll(next_field());
        (phase == 'W' ? stream.warmup : stream.measured).push_back(e);
    }
    return stream;
}

// ---------------------------------------------------------------------------------------------
// Shared bookkeeping. Counting trades and volume happens inside the timed window for every engine.
// The trade-sequence hash is only computed when kCheck is true (equivalence mode, untimed).
struct Counters {
    std::uint64_t trades{};
    std::uint64_t volume{};
    std::uint64_t rejects{};
    std::uint64_t trade_hash{1469598103934665603ULL};
    std::uint64_t event_index{};
};

inline void fnv(std::uint64_t& h, std::uint64_t v) {
    for (int i = 0; i < 8; ++i) {
        h ^= (v >> (8 * i)) & 0xffU;
        h *= 1099511628211ULL;
    }
}

template <bool kCheck>
inline void record_trade(Counters& c, std::uint64_t maker, std::uint64_t taker, std::uint64_t price, std::uint64_t qty) {
    ++c.trades;
    c.volume += qty;
    if constexpr (kCheck) {
        fnv(c.trade_hash, c.event_index);
        fnv(c.trade_hash, maker);
        fnv(c.trade_hash, taker);
        fnv(c.trade_hash, price);
        fnv(c.trade_hash, qty);
    }
}

struct LevelAgg {
    std::int64_t price{};
    std::uint64_t qty{};
    std::uint64_t orders{};
};

struct BookState {
    std::vector<LevelAgg> bids{};  // best first
    std::vector<LevelAgg> asks{};  // best first

    std::uint64_t hash() const {
        std::uint64_t h = 1469598103934665603ULL;
        for (const auto& l : bids) { fnv(h, 1); fnv(h, l.price); fnv(h, l.qty); fnv(h, l.orders); }
        for (const auto& l : asks) { fnv(h, 2); fnv(h, l.price); fnv(h, l.qty); fnv(h, l.orders); }
        return h;
    }
    static std::uint64_t total(const std::vector<LevelAgg>& v, bool orders) {
        std::uint64_t t = 0;
        for (const auto& l : v) t += orders ? l.orders : l.qty;
        return t;
    }
};

// ---------------------------------------------------------------------------------------------
// This repo's engine. Each event builds an lob::Order (empty owner_id, so no heap allocation for the
// string) and calls the engine's public API, exactly as benchmarks/orderbook_benchmark.cpp does.
template <typename Engine, bool kCheck>
class RepoAdapter {
public:
    explicit RepoAdapter(Engine engine) : engine_(std::move(engine)) {}

    void apply(const Event& e) {
        lob::ExecutionResult r;
        switch (e.action) {
            case Action::Limit:
                r = engine_.submit_order(lob::Order::limit(e.id, std::string{}, e.buy ? lob::Side::Buy : lob::Side::Sell,
                                                           e.price, e.qty, e.ts));
                break;
            case Action::Market:
                r = engine_.submit_order(lob::Order::market(e.id, std::string{}, e.buy ? lob::Side::Buy : lob::Side::Sell,
                                                            e.qty, e.ts));
                break;
            case Action::Cancel:
                r = engine_.cancel_order(e.id, e.ts);
                break;
            case Action::Replace:
                r = engine_.modify_order(e.id, e.price, e.qty, e.ts);
                break;
        }
        if (!r.accepted) {
            ++c.rejects;
        }
        for (const auto& t : r.trades) {
            record_trade<kCheck>(c, t.maker_order_id, t.taker_order_id, static_cast<std::uint64_t>(t.price),
                                 static_cast<std::uint64_t>(t.quantity));
        }
        ++c.event_index;
    }

    BookState state() const {
        BookState s;
        for (const auto& entry : engine_.book().bid_levels()) {
            s.bids.push_back(agg(lob::detail::level_entry_price(entry), lob::detail::level_entry_level(entry)));
        }
        for (const auto& entry : engine_.book().ask_levels()) {
            s.asks.push_back(agg(lob::detail::level_entry_price(entry), lob::detail::level_entry_level(entry)));
        }
        return s;
    }

    Counters c{};

private:
    static LevelAgg agg(lob::Price price, const lob::PriceLevel& level) {
        LevelAgg a{price, 0, 0};
        for (const auto& o : level) {
            a.qty += static_cast<std::uint64_t>(o.remaining_quantity);
            ++a.orders;
        }
        return a;
    }

    Engine engine_;
};

// ---------------------------------------------------------------------------------------------
// Liquibook. The application order class implements Liquibook's Order interface; the adapter keeps an
// id -> order map (std::unordered_map, the same container this repo's engine uses internally) because the
// stream addresses cancels and replaces by order id while Liquibook addresses them by order pointer.
struct LbOrder final : public liquibook::book::Order {
    LbOrder() = default;
    LbOrder(std::uint64_t id_, bool buy_, liquibook::book::Price price_, liquibook::book::Quantity qty_)
        : id(id_), buy(buy_), px(price_), qty(qty_), open(qty_) {}
    bool is_buy() const override { return buy; }
    liquibook::book::Price price() const override { return px; }
    liquibook::book::Quantity order_qty() const override { return qty; }

    std::uint64_t id{};
    bool buy{true};
    liquibook::book::Price px{};
    liquibook::book::Quantity qty{};
    liquibook::book::Quantity open{};
};

// Ownership policies. lb_new: new/delete inside the timed event. lb_pool: slots preallocated before timing
// (Liquibook's own test/perf/pt_order_book.cpp style). lb_shared: std::make_shared (the style of Liquibook's
// examples/mt_order_entry).
struct NewPolicy {
    using Ptr = LbOrder*;
    explicit NewPolicy(std::size_t) {}
    Ptr make(std::uint64_t id, bool buy, std::uint64_t price, std::uint64_t qty) { return new LbOrder(id, buy, price, qty); }
    void release(Ptr p) { delete p; }
    static LbOrder* raw(const Ptr& p) { return p; }
};

struct PoolPolicy {
    using Ptr = LbOrder*;
    explicit PoolPolicy(std::size_t max_id) : slots(max_id + 1) {}
    Ptr make(std::uint64_t id, bool buy, std::uint64_t price, std::uint64_t qty) {
        LbOrder* p = &slots[id];
        p->id = id; p->buy = buy; p->px = price; p->qty = qty; p->open = qty;
        return p;
    }
    void release(Ptr) {}
    static LbOrder* raw(const Ptr& p) { return p; }
    std::vector<LbOrder> slots;
};

struct SharedPolicy {
    using Ptr = std::shared_ptr<LbOrder>;
    explicit SharedPolicy(std::size_t) {}
    Ptr make(std::uint64_t id, bool buy, std::uint64_t price, std::uint64_t qty) {
        return std::make_shared<LbOrder>(id, buy, price, qty);
    }
    void release(const Ptr&) {}
    static LbOrder* raw(const Ptr& p) { return p.get(); }
};

template <typename Policy, bool kCheck>
class LbAdapter final : public liquibook::book::OrderListener<typename Policy::Ptr> {
public:
    using Ptr = typename Policy::Ptr;

    explicit LbAdapter(std::size_t max_id) : policy_(max_id) {
        book_.set_order_listener(this);
        dead_.reserve(64);
    }

    ~LbAdapter() {
        for (auto& kv : live_) {
            policy_.release(kv.second);
        }
    }

    void apply(const Event& e) {
        switch (e.action) {
            case Action::Limit: {
                Ptr o = policy_.make(e.id, e.buy, static_cast<std::uint64_t>(e.price), static_cast<std::uint64_t>(e.qty));
                live_.emplace(e.id, o);
                book_.add(o);
                reap();
                finish_if_filled(e.id);
                break;
            }
            case Action::Market: {
                Ptr o = policy_.make(e.id, e.buy, liquibook::book::MARKET_ORDER_PRICE, static_cast<std::uint64_t>(e.qty));
                book_.add(o, liquibook::book::oc_immediate_or_cancel);
                reap();
                policy_.release(o);
                break;
            }
            case Action::Cancel: {
                auto it = live_.find(e.id);
                if (it == live_.end()) {
                    ++c.rejects;
                    break;
                }
                Ptr o = it->second;
                live_.erase(it);
                book_.cancel(o);
                policy_.release(o);
                break;
            }
            case Action::Replace: {
                auto it = live_.find(e.id);
                if (it == live_.end()) {
                    ++c.rejects;
                    break;
                }
                Ptr o = it->second;
                const auto delta = e.qty - static_cast<std::int64_t>(Policy::raw(o)->open);
                book_.replace(o, delta, static_cast<std::uint64_t>(e.price));
                reap();
                finish_if_filled(e.id);
                break;
            }
        }
        ++c.event_index;
    }

    // Liquibook OrderListener interface: minimal bookkeeping only.
    void on_accept(const Ptr&) override {}
    void on_reject(const Ptr&, const char*) override { ++c.rejects; }
    void on_fill(const Ptr& order, const Ptr& matched, liquibook::book::Quantity qty, liquibook::book::Price price) override {
        LbOrder* in = Policy::raw(order);
        LbOrder* rest = Policy::raw(matched);
        in->open -= qty;
        rest->open -= qty;
        record_trade<kCheck>(c, rest->id, in->id, price, qty);
        if (rest->open == 0) {
            dead_.push_back(rest->id);
        }
    }
    void on_cancel(const Ptr&) override {}
    void on_cancel_reject(const Ptr&, const char*) override { ++c.rejects; }
    void on_replace(const Ptr& order, const int64_t& size_delta, liquibook::book::Price new_price) override {
        LbOrder* o = Policy::raw(order);
        o->px = new_price;
        o->open = static_cast<liquibook::book::Quantity>(static_cast<std::int64_t>(o->open) + size_delta);
    }
    void on_replace_reject(const Ptr&, const char*) override { ++c.rejects; }

    BookState state() const {
        BookState s;
        collect(book_.bids(), s.bids);
        collect(book_.asks(), s.asks);
        return s;
    }

    Counters c{};

private:
    void reap() {
        for (const auto id : dead_) {
            auto it = live_.find(id);
            if (it != live_.end()) {
                Ptr o = it->second;
                live_.erase(it);
                policy_.release(o);
            }
        }
        dead_.clear();
    }

    void finish_if_filled(std::uint64_t id) {
        auto it = live_.find(id);
        if (it != live_.end() && Policy::raw(it->second)->open == 0) {
            Ptr o = it->second;
            live_.erase(it);
            policy_.release(o);
        }
    }

    template <typename Map>
    static void collect(const Map& side, std::vector<LevelAgg>& out) {
        for (const auto& kv : side) {
            const auto price = static_cast<std::int64_t>(kv.first.price());
            if (out.empty() || out.back().price != price) {
                out.push_back(LevelAgg{price, 0, 0});
            }
            out.back().qty += kv.second.open_qty();
            ++out.back().orders;
        }
    }

    Policy policy_;
    liquibook::book::OrderBook<Ptr> book_{"EXT3"};
    std::unordered_map<std::uint64_t, Ptr> live_{};
    std::vector<std::uint64_t> dead_{};
};

// ---------------------------------------------------------------------------------------------
constexpr lob::Price kFlatMin = 99'000;
constexpr lob::Price kFlatMax = 101'000;

std::uint64_t max_id(const Stream& s) {
    std::uint64_t m = 0;
    for (const auto& e : s.warmup) m = std::max(m, e.id);
    for (const auto& e : s.measured) m = std::max(m, e.id);
    return m;
}

template <bool kCheck>
struct Factory {
    const Stream& s;
    auto map() const { return RepoAdapter<lob::MatchingEngine, kCheck>(lob::MatchingEngine{}); }
    auto flat() const {
        return RepoAdapter<lob::FlatMatchingEngine, kCheck>(lob::FlatMatchingEngine(lob::FlatOrderBook(kFlatMin, kFlatMax)));
    }
};

struct CheckRow {
    std::string engine;
    std::uint64_t measured_trades{}, measured_volume{}, total_trades{}, total_volume{}, rejects{}, trade_hash{};
    BookState state;
};

template <typename Adapter>
CheckRow run_check(const std::string& name, Adapter& a, const Stream& s) {
    for (const auto& e : s.warmup) a.apply(e);
    const auto warm_trades = a.c.trades;
    const auto warm_volume = a.c.volume;
    for (const auto& e : s.measured) a.apply(e);
    CheckRow row;
    row.engine = name;
    row.measured_trades = a.c.trades - warm_trades;
    row.measured_volume = a.c.volume - warm_volume;
    row.total_trades = a.c.trades;
    row.total_volume = a.c.volume;
    row.rejects = a.c.rejects;
    row.trade_hash = a.c.trade_hash;
    row.state = a.state();
    return row;
}

int do_check(const Stream& s) {
    std::vector<CheckRow> rows;
    const auto mid = max_id(s);
    { auto a = Factory<true>{s}.map(); rows.push_back(run_check("map", a, s)); }
    { auto a = Factory<true>{s}.flat(); rows.push_back(run_check("flat", a, s)); }
    { auto a = std::make_unique<LbAdapter<NewPolicy, true>>(mid); rows.push_back(run_check("lb_new", *a, s)); }
    { auto a = std::make_unique<LbAdapter<PoolPolicy, true>>(mid); rows.push_back(run_check("lb_pool", *a, s)); }
    { auto a = std::make_unique<LbAdapter<SharedPolicy, true>>(mid); rows.push_back(run_check("lb_shared", *a, s)); }

    std::cout << "engine,measured_trades,measured_volume,total_trades,total_volume,rejects,trade_seq_hash,"
                 "best_bid,best_bid_qty,best_ask,best_ask_qty,bid_levels,ask_levels,bid_orders,ask_orders,"
                 "bid_qty,ask_qty,final_book_hash\n";
    bool ok = true;
    for (const auto& r : rows) {
        const auto& st = r.state;
        std::cout << r.engine << ',' << r.measured_trades << ',' << r.measured_volume << ',' << r.total_trades << ','
                  << r.total_volume << ',' << r.rejects << ',' << std::hex << r.trade_hash << std::dec << ','
                  << (st.bids.empty() ? 0 : st.bids.front().price) << ',' << (st.bids.empty() ? 0 : st.bids.front().qty) << ','
                  << (st.asks.empty() ? 0 : st.asks.front().price) << ',' << (st.asks.empty() ? 0 : st.asks.front().qty) << ','
                  << st.bids.size() << ',' << st.asks.size() << ',' << BookState::total(st.bids, true) << ','
                  << BookState::total(st.asks, true) << ',' << BookState::total(st.bids, false) << ','
                  << BookState::total(st.asks, false) << ',' << std::hex << st.hash() << std::dec << '\n';
        const auto& ref = rows.front();
        if (r.measured_trades != ref.measured_trades || r.measured_volume != ref.measured_volume ||
            r.total_trades != ref.total_trades || r.total_volume != ref.total_volume || r.rejects != 0 ||
            r.trade_hash != ref.trade_hash || st.hash() != ref.state.hash()) {
            ok = false;
        }
    }
    std::cout << "EQUIVALENCE=" << (ok ? "PASS" : "FAIL") << '\n';
    return ok ? 0 : 3;
}

// ---------------------------------------------------------------------------------------------
// The timing loop: identical for every engine (same as replay_flow in orderbook_benchmark.cpp).
std::uint64_t percentile(const std::vector<std::uint64_t>& sorted, double p) {
    return sorted[static_cast<std::size_t>(p * static_cast<double>(sorted.size() - 1))];
}

template <typename Adapter>
int run_timed(const std::string& engine, Adapter& a, const Stream& s, const std::string& out_path) {
    for (const auto& e : s.warmup) a.apply(e);
    const auto warm_trades = a.c.trades;
    const auto warm_volume = a.c.volume;
    const auto warm_rejects = a.c.rejects;

    std::vector<std::uint64_t> lat;
    lat.reserve(s.measured.size());
    const auto total_start = Clock::now();
    for (const auto& e : s.measured) {
        const auto t0 = Clock::now();
        a.apply(e);
        const auto t1 = Clock::now();
        lat.push_back(static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count()));
    }
    const auto total_stop = Clock::now();
    const auto total_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(total_stop - total_start).count());
    const double eps = static_cast<double>(s.measured.size()) / (static_cast<double>(total_ns) / 1e9);
    std::vector<std::uint64_t> sorted = lat;
    std::sort(sorted.begin(), sorted.end());

    std::ofstream out(out_path);
    out << std::setprecision(12);
    out << "metric,value\n";
    out << "engine," << engine << '\n';
#ifdef EXT3_UNITY
    out << "binary,ext3_harness_unity\n";
#else
    out << "binary,ext3_harness\n";
#endif
    out << "warmup_events," << s.warmup.size() << '\n';
    out << "measured_events," << s.measured.size() << '\n';
    out << "events_per_second," << eps << '\n';
    out << "total_seconds," << static_cast<double>(total_ns) / 1e9 << '\n';
    out << "p50_latency_ns," << percentile(sorted, 0.50) << '\n';
    out << "p95_latency_ns," << percentile(sorted, 0.95) << '\n';
    out << "p99_latency_ns," << percentile(sorted, 0.99) << '\n';
    out << "max_latency_ns," << sorted.back() << '\n';
    out << "measured_trades," << a.c.trades - warm_trades << '\n';
    out << "measured_volume," << a.c.volume - warm_volume << '\n';
    out << "measured_rejects," << a.c.rejects - warm_rejects << '\n';
    std::cout << std::setprecision(12) << "engine=" << engine << " events_per_second=" << eps
              << " p50_ns=" << percentile(sorted, 0.50) << " p99_ns=" << percentile(sorted, 0.99)
              << " trades=" << a.c.trades - warm_trades << " volume=" << a.c.volume - warm_volume
              << " rejects=" << a.c.rejects - warm_rejects << '\n';
    return 0;
}

int do_time(const Stream& s, const std::string& engine, const std::string& out) {
    const auto mid = max_id(s);
    if (engine == "map") { auto a = Factory<false>{s}.map(); return run_timed(engine, a, s, out); }
    if (engine == "flat") { auto a = Factory<false>{s}.flat(); return run_timed(engine, a, s, out); }
    if (engine == "lb_new") { auto a = std::make_unique<LbAdapter<NewPolicy, false>>(mid); return run_timed(engine, *a, s, out); }
    if (engine == "lb_pool") { auto a = std::make_unique<LbAdapter<PoolPolicy, false>>(mid); return run_timed(engine, *a, s, out); }
    if (engine == "lb_shared") { auto a = std::make_unique<LbAdapter<SharedPolicy, false>>(mid); return run_timed(engine, *a, s, out); }
    throw std::runtime_error("unknown engine " + engine);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 3 && std::string(argv[1]) == "check") {
            return do_check(load_stream(argv[2]));
        }
        if (argc == 5 && std::string(argv[1]) == "time") {
            return do_time(load_stream(argv[2]), argv[3], argv[4]);
        }
        std::cerr << "usage: ext3_harness check <stream.csv> | time <stream.csv> <engine> <summary.csv>\n";
        return 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
