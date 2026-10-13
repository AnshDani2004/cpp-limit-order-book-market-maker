// Independent replication harness for ext3a, written from PREREG.md sections 3 to 7 only.
// Usage:
//   rep_harness check <stream.csv>            untimed equivalence over all configs in this binary
//   rep_harness run <config> <stream.csv>      one timed run (fresh process), prints one result line
// Configs: map, flat, lb_new, lb_pool, lb_shared (rep_harness); map_unity (rep_harness_unity).
#ifdef REP_UNITY
#include "../../cpp-limit-order-book-market-maker/src/flat_order_book.cpp"
#include "../../cpp-limit-order-book-market-maker/src/matching_engine.cpp"
#include "../../cpp-limit-order-book-market-maker/src/order_book.cpp"
#include "../../cpp-limit-order-book-market-maker/src/price_level.cpp"
#endif
#include "lob/matching_engine.hpp"

#include <book/order_book.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

enum : std::uint8_t { A_LIMIT = 0, A_MARKET = 1, A_CANCEL = 2, A_REPLACE = 3 };

struct Event {
    std::uint8_t action;
    bool buy;
    std::uint64_t id;
    std::int64_t price;
    std::int64_t qty;
    std::int64_t ts;
};

struct Stream {
    std::vector<Event> warm, meas;
    std::uint64_t max_id = 0;
};

Stream load(const char* path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open stream");
    std::string line;
    std::getline(in, line);  // header
    Stream s;
    s.warm.reserve(20000);
    s.meas.reserve(1000000);
    while (std::getline(in, line)) {
        char ph[16], ac[16], sd[8];
        unsigned long long id;
        long long px, q, ts;
        // fields: phase,action,id,side,price,qty,ts
        for (auto& c : line) if (c == ',') c = ' ';
        if (std::sscanf(line.c_str(), "%15s %15s %llu %7s %lld %lld %lld", ph, ac, &id, sd, &px, &q, &ts) != 7)
            throw std::runtime_error("bad row");
        Event e{};
        if (!std::strcmp(ac, "limit")) e.action = A_LIMIT;
        else if (!std::strcmp(ac, "market")) e.action = A_MARKET;
        else if (!std::strcmp(ac, "cancel")) e.action = A_CANCEL;
        else if (!std::strcmp(ac, "replace") || !std::strcmp(ac, "reduce")) e.action = A_REPLACE;  // reduce: negative control only
        else throw std::runtime_error(std::string("unknown action ") + ac);
        e.buy = sd[0] == 'b';
        e.id = id; e.price = px; e.qty = q; e.ts = ts;
        s.max_id = std::max<std::uint64_t>(s.max_id, id);
        (ph[0] == 'w' ? s.warm : s.meas).push_back(e);
    }
    return s;
}

// FNV-1a 64 over 8-byte little-endian words.
struct Fnv {
    std::uint64_t h = 1469598103934665603ULL;
    void add(std::uint64_t v) {
        for (int i = 0; i < 8; ++i) { h ^= (v >> (8 * i)) & 0xff; h *= 1099511628211ULL; }
    }
};

struct Counters {
    std::uint64_t trades = 0, volume = 0, rejects = 0;
};

struct BookState {
    std::int64_t best_bid = 0, best_bid_size = 0, best_ask = 0, best_ask_size = 0;
    std::uint64_t levels_bid = 0, levels_ask = 0, orders_bid = 0, orders_ask = 0;
    std::int64_t size_bid = 0, size_ask = 0;
    std::uint64_t hash = 0;
};

// Accumulates a book side given (price, size, count) per level in priority order.
struct SideAcc {
    std::uint64_t levels = 0, orders = 0;
    std::int64_t size = 0, best = 0, best_size = 0;
    void level(Fnv& f, std::int64_t px, std::int64_t sz, std::uint64_t n) {
        if (levels == 0) { best = px; best_size = sz; }
        ++levels; orders += n; size += sz;
        f.add(static_cast<std::uint64_t>(px)); f.add(static_cast<std::uint64_t>(sz)); f.add(n);
    }
};

// ---------------- this repo ----------------
template <typename Engine, bool HASH>
struct RepoAdapter {
    Engine eng;
    Counters c;
    Fnv th;
    explicit RepoAdapter(Engine e) : eng(std::move(e)) {}
    void apply(const Event& e, std::uint64_t idx) {
        const auto side = e.buy ? lob::Side::Buy : lob::Side::Sell;
        lob::ExecutionResult r;
        switch (e.action) {
            case A_LIMIT: r = eng.submit_order(lob::Order::limit(e.id, "", side, e.price, e.qty, e.ts)); break;
            case A_MARKET: r = eng.submit_order(lob::Order::market(e.id, "", side, e.qty, e.ts)); break;
            case A_CANCEL: r = eng.cancel_order(e.id, e.ts); break;
            default: r = eng.modify_order(e.id, e.price, e.qty, e.ts); break;
        }
        if (!r.accepted) ++c.rejects;
        for (const auto& t : r.trades) {
            ++c.trades;
            c.volume += static_cast<std::uint64_t>(t.quantity);
            if constexpr (HASH) {
                th.add(idx); th.add(t.maker_order_id); th.add(t.taker_order_id);
                th.add(static_cast<std::uint64_t>(t.price)); th.add(static_cast<std::uint64_t>(t.quantity));
            }
        }
    }
    BookState state() const {
        Fnv f; SideAcc b, a;
        for (const auto& entry : eng.book().bid_levels()) {
            const auto& lvl = lob::detail::level_entry_level(entry);
            std::int64_t sz = 0; std::uint64_t n = 0;
            for (const auto& o : lvl) { sz += o.remaining_quantity; ++n; }
            b.level(f, lob::detail::level_entry_price(entry), sz, n);
        }
        for (const auto& entry : eng.book().ask_levels()) {
            const auto& lvl = lob::detail::level_entry_level(entry);
            std::int64_t sz = 0; std::uint64_t n = 0;
            for (const auto& o : lvl) { sz += o.remaining_quantity; ++n; }
            a.level(f, lob::detail::level_entry_price(entry), sz, n);
        }
        return BookState{b.best, b.best_size, a.best, a.best_size, b.levels, a.levels, b.orders, a.orders, b.size, a.size, f.h};
    }
};

// ---------------- Liquibook ----------------
struct LbOrder {
    std::uint64_t id = 0;
    bool buy = false;
    liquibook::book::Price px = 0;
    liquibook::book::Quantity qty = 0;
    liquibook::book::Quantity open = 0;
    bool is_buy() const { return buy; }
    liquibook::book::Price price() const { return px; }
    liquibook::book::Quantity order_qty() const { return qty; }
    liquibook::book::Price stop_price() const { return 0; }
    bool all_or_none() const { return false; }
    bool immediate_or_cancel() const { return false; }
};

enum class Own { New, Pool, Shared };

template <Own O> struct PtrOf { using type = LbOrder*; };
template <> struct PtrOf<Own::Shared> { using type = std::shared_ptr<LbOrder>; };

template <Own O, bool HASH>
struct LbAdapter final : liquibook::book::OrderListener<typename PtrOf<O>::type> {
    using Ptr = typename PtrOf<O>::type;
    liquibook::book::OrderBook<Ptr> book;
    std::unordered_map<std::uint64_t, Ptr> live;
    std::vector<std::uint64_t> filled;  // fully filled resting ids, removed after the call
    std::vector<LbOrder> pool;
    Counters c;
    Fnv th;
    std::uint64_t cur_idx = 0;

    explicit LbAdapter(std::uint64_t max_id) {
        book.set_order_listener(this);
        if constexpr (O == Own::Pool) pool.resize(max_id + 1);
        filled.reserve(64);
    }
    ~LbAdapter() {
        if constexpr (O == Own::New) for (auto& kv : live) delete kv.second;
    }

    Ptr make(const Event& e, liquibook::book::Price px) {
        if constexpr (O == Own::New) {
            return new LbOrder{e.id, e.buy, px, static_cast<liquibook::book::Quantity>(e.qty), static_cast<liquibook::book::Quantity>(e.qty)};
        } else if constexpr (O == Own::Pool) {
            LbOrder& o = pool[e.id];
            o = LbOrder{e.id, e.buy, px, static_cast<liquibook::book::Quantity>(e.qty), static_cast<liquibook::book::Quantity>(e.qty)};
            return &o;
        } else {
            return std::make_shared<LbOrder>(LbOrder{e.id, e.buy, px, static_cast<liquibook::book::Quantity>(e.qty), static_cast<liquibook::book::Quantity>(e.qty)});
        }
    }
    void release(Ptr& p) {
        if constexpr (O == Own::New) delete p;
        (void)p;
    }
    void erase_id(std::uint64_t id) {
        auto it = live.find(id);
        if (it == live.end()) return;
        release(it->second);
        live.erase(it);
    }
    void flush_filled() {
        for (auto id : filled) erase_id(id);
        filled.clear();
    }

    void apply(const Event& e, std::uint64_t idx) {
        cur_idx = idx;
        switch (e.action) {
            case A_LIMIT: {
                Ptr p = make(e, static_cast<liquibook::book::Price>(e.price));
                live[e.id] = p;
                book.add(p);
                flush_filled();
                if (p->open == 0) erase_id(e.id);
                break;
            }
            case A_MARKET: {
                Ptr p = make(e, liquibook::book::MARKET_ORDER_PRICE);
                book.add(p, liquibook::book::oc_immediate_or_cancel);
                flush_filled();
                release(p);
                break;
            }
            case A_CANCEL: {
                auto it = live.find(e.id);
                if (it == live.end()) { ++c.rejects; break; }
                book.cancel(it->second);
                erase_id(e.id);
                break;
            }
            default: {
                auto it = live.find(e.id);
                if (it == live.end()) { ++c.rejects; break; }
                Ptr p = it->second;
                const std::int64_t delta = e.qty - static_cast<std::int64_t>(p->open);
                book.replace(p, delta, static_cast<liquibook::book::Price>(e.price));
                flush_filled();
                if (p->open == 0) erase_id(e.id);
                break;
            }
        }
    }

    // listener
    void on_accept(const Ptr&) override {}
    void on_reject(const Ptr&, const char*) override { ++c.rejects; }
    void on_fill(const Ptr& order, const Ptr& matched, liquibook::book::Quantity q, liquibook::book::Price px) override {
        ++c.trades;
        c.volume += q;
        order->open -= q;
        matched->open -= q;
        if (matched->open == 0) filled.push_back(matched->id);
        if constexpr (HASH) {
            th.add(cur_idx); th.add(matched->id); th.add(order->id); th.add(px); th.add(q);
        }
    }
    void on_cancel(const Ptr&) override {}
    void on_cancel_reject(const Ptr&, const char*) override { ++c.rejects; }
    void on_replace(const Ptr& order, const int64_t& size_delta, liquibook::book::Price new_price) override {
        order->px = new_price;
        order->open = static_cast<liquibook::book::Quantity>(static_cast<std::int64_t>(order->open) + size_delta);
    }
    void on_replace_reject(const Ptr&, const char*) override { ++c.rejects; }

    BookState state() const {
        Fnv f; SideAcc b, a;
        auto walk = [&](const auto& m, SideAcc& acc) {
            auto it = m.begin();
            while (it != m.end()) {
                const auto px = it->first.price();
                std::int64_t sz = 0; std::uint64_t n = 0;
                while (it != m.end() && it->first.price() == px) { sz += static_cast<std::int64_t>(it->second.open_qty()); ++n; ++it; }
                acc.level(f, static_cast<std::int64_t>(px), sz, n);
            }
        };
        walk(book.bids(), b);
        walk(book.asks(), a);
        return BookState{b.best, b.best_size, a.best, a.best_size, b.levels, a.levels, b.orders, a.orders, b.size, a.size, f.h};
    }
};

template <typename Adapter>
void replay_untimed(Adapter& ad, const Stream& s) {
    for (std::size_t i = 0; i < s.warm.size(); ++i) ad.apply(s.warm[i], 0);
    const auto warm_trades = ad.c.trades, warm_rej = ad.c.rejects;
    if (warm_trades != 0 || warm_rej != 0) std::fprintf(stderr, "warning: warm-up trades=%llu rejects=%llu\n",
                                                          (unsigned long long)warm_trades, (unsigned long long)warm_rej);
    ad.c = Counters{};
    for (std::size_t i = 0; i < s.meas.size(); ++i) ad.apply(s.meas[i], i);
}

struct CheckRow {
    std::string name;
    Counters c;
    std::uint64_t trade_hash;
    BookState b;
};

template <typename Adapter>
CheckRow check_one(const char* name, Adapter& ad, const Stream& s) {
    replay_untimed(ad, s);
    return CheckRow{name, ad.c, ad.th.h, ad.state()};
}

void print_row(const CheckRow& r) {
    std::printf("%-10s trades=%llu volume=%llu rejects=%llu trade_hash=%016llx best_bid=%lld(%lld) best_ask=%lld(%lld) "
                "levels=%llu/%llu orders=%llu/%llu size=%lld/%lld book_hash=%016llx\n",
                r.name.c_str(), (unsigned long long)r.c.trades, (unsigned long long)r.c.volume, (unsigned long long)r.c.rejects,
                (unsigned long long)r.trade_hash, (long long)r.b.best_bid, (long long)r.b.best_bid_size, (long long)r.b.best_ask,
                (long long)r.b.best_ask_size, (unsigned long long)r.b.levels_bid, (unsigned long long)r.b.levels_ask,
                (unsigned long long)r.b.orders_bid, (unsigned long long)r.b.orders_ask, (long long)r.b.size_bid,
                (long long)r.b.size_ask, (unsigned long long)r.b.hash);
}

bool same(const CheckRow& a, const CheckRow& b) {
    return a.c.trades == b.c.trades && a.c.volume == b.c.volume && a.c.rejects == b.c.rejects && a.trade_hash == b.trade_hash &&
           std::memcmp(&a.b, &b.b, sizeof(BookState)) == 0;
}

std::uint64_t pct(const std::vector<std::uint64_t>& v, double p) {
    return v[static_cast<std::size_t>(p * static_cast<double>(v.size() - 1))];
}

template <typename Adapter>
int timed(const char* name, Adapter& ad, const Stream& s) {
    for (std::size_t i = 0; i < s.warm.size(); ++i) ad.apply(s.warm[i], 0);
    ad.c = Counters{};
    std::vector<std::uint64_t> lat;
    lat.reserve(s.meas.size());
    const auto T0 = Clock::now();
    for (std::size_t i = 0; i < s.meas.size(); ++i) {
        const auto t0 = Clock::now();
        ad.apply(s.meas[i], i);
        const auto t1 = Clock::now();
        lat.push_back(static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count()));
    }
    const auto T1 = Clock::now();
    const double total_ns = static_cast<double>(std::chrono::duration_cast<std::chrono::nanoseconds>(T1 - T0).count());
    std::sort(lat.begin(), lat.end());
    const double eps = static_cast<double>(s.meas.size()) / (total_ns / 1e9);
    const bool valid = ad.c.trades == 372120 && ad.c.volume == 9486560 && ad.c.rejects == 0;
    std::printf("RESULT config=%s events=%zu total_ns=%.0f events_per_s=%.1f p50_ns=%llu p99_ns=%llu max_ns=%llu trades=%llu volume=%llu rejects=%llu valid=%d\n",
                name, s.meas.size(), total_ns, eps, (unsigned long long)pct(lat, 0.50), (unsigned long long)pct(lat, 0.99),
                (unsigned long long)lat.back(), (unsigned long long)ad.c.trades, (unsigned long long)ad.c.volume,
                (unsigned long long)ad.c.rejects, valid ? 1 : 0);
    return valid ? 0 : 3;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) { std::fprintf(stderr, "usage: check <csv> | run <config> <csv>\n"); return 2; }
    const std::string mode = argv[1];
    if (mode == "check") {
        const Stream s = load(argv[2]);
        std::vector<CheckRow> rows;
#ifdef REP_UNITY
        { RepoAdapter<lob::MatchingEngine, true> a{lob::MatchingEngine{}}; rows.push_back(check_one("map_unity", a, s)); }
#else
        { RepoAdapter<lob::MatchingEngine, true> a{lob::MatchingEngine{}}; rows.push_back(check_one("map", a, s)); }
        { RepoAdapter<lob::FlatMatchingEngine, true> a{lob::FlatMatchingEngine{lob::FlatOrderBook(99000, 101000)}}; rows.push_back(check_one("flat", a, s)); }
        { auto a = std::make_unique<LbAdapter<Own::New, true>>(s.max_id); rows.push_back(check_one("lb_new", *a, s)); }
        { auto a = std::make_unique<LbAdapter<Own::Pool, true>>(s.max_id); rows.push_back(check_one("lb_pool", *a, s)); }
        { auto a = std::make_unique<LbAdapter<Own::Shared, true>>(s.max_id); rows.push_back(check_one("lb_shared", *a, s)); }
#endif
        bool pass = true;
        for (auto& r : rows) { print_row(r); pass = pass && same(r, rows[0]) && r.c.rejects == 0; }
        std::printf("EQUIVALENCE=%s\n", pass ? "PASS" : "FAIL");
        return pass ? 0 : 1;
    }
    if (mode == "run" && argc >= 4) {
        const std::string cfg = argv[2];
        const Stream s = load(argv[3]);
#ifdef REP_UNITY
        if (cfg == "map_unity") { RepoAdapter<lob::MatchingEngine, false> a{lob::MatchingEngine{}}; return timed("map_unity", a, s); }
#else
        if (cfg == "map") { RepoAdapter<lob::MatchingEngine, false> a{lob::MatchingEngine{}}; return timed("map", a, s); }
        if (cfg == "flat") { RepoAdapter<lob::FlatMatchingEngine, false> a{lob::FlatMatchingEngine{lob::FlatOrderBook(99000, 101000)}}; return timed("flat", a, s); }
        if (cfg == "lb_new") { auto a = std::make_unique<LbAdapter<Own::New, false>>(s.max_id); return timed("lb_new", *a, s); }
        if (cfg == "lb_pool") { auto a = std::make_unique<LbAdapter<Own::Pool, false>>(s.max_id); return timed("lb_pool", *a, s); }
        if (cfg == "lb_shared") { auto a = std::make_unique<LbAdapter<Own::Shared, false>>(s.max_id); return timed("lb_shared", *a, s); }
#endif
        std::fprintf(stderr, "unknown config %s\n", cfg.c_str());
        return 2;
    }
    return 2;
}
