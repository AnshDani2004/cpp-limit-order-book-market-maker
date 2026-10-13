// Independent replication: stream generator written from PREREG.md section 3 (ext3a).
// Re-implements the repo's hand-chosen FlowGenerator draw order (benchmarks/orderbook_benchmark.cpp,
// read as the PREREG's named reference) with the two PREREG changes: empty owner ids, and every
// modify is a cancel/replace to a new price (redrawn until it differs), new size U{1..100}.
// Usage: rep_gen <out.csv> [--mode-draw] [--negative-control-original-modify]
//   --mode-draw: still consume the original 1..100 mode draw before the new-price draw (variant probe).
#include "lob/matching_engine.hpp"
#include <cstdio>
#include <cstring>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {
enum Act { LIMIT = 0, MARKET = 1, CANCEL = 2, MODIFY = 3 };
struct Ev { int phase; Act act; lob::OrderId id; lob::Side side; lob::Price price; lob::Quantity qty; lob::Timestamp ts;
            bool reduce; };  // reduce: original-rule same-price reduction (negative control only)

struct Active {
  std::vector<lob::OrderId> ids;
  std::unordered_map<lob::OrderId, std::size_t> pos;
  void remove(lob::OrderId id) {
    auto it = pos.find(id); if (it == pos.end()) return;
    auto i = it->second; auto b = ids.back(); ids[i] = b; pos[b] = i; ids.pop_back(); pos.erase(it);
  }
  void upsert(lob::OrderId id) { if (pos.find(id) == pos.end()) { pos[id] = ids.size(); ids.push_back(id); } }
  lob::OrderId pick(std::mt19937_64& r) { std::uniform_int_distribution<std::size_t> d(0, ids.size() - 1); return ids[d(r)]; }
};

struct Gen {
  std::mt19937_64 rng{42};
  lob::MatchingEngine eng;
  Active act;
  lob::OrderId next_id = 1; lob::Timestamp next_ts = 1; lob::Price ref = 100000;
  bool mode_draw = false, negctl = false;

  lob::Side side() { std::uniform_int_distribution<int> d(0, 1); return d(rng) == 0 ? lob::Side::Buy : lob::Side::Sell; }
  lob::Quantity qty() { std::uniform_int_distribution<lob::Quantity> d(1, 100); return d(rng); }
  lob::Price passive(lob::Side s) { std::uniform_int_distribution<lob::Price> d(5, 200); auto o = d(rng); return s == lob::Side::Buy ? ref - o : ref + o; }
  void step() { std::uniform_int_distribution<int> d(-1, 1); ref += d(rng); if (ref > 100250) --ref; else if (ref < 99750) ++ref; }

  Ev limit(int ph) { Ev e{}; e.phase = ph; e.act = LIMIT; e.ts = next_ts++; e.side = side(); e.price = passive(e.side); e.qty = qty(); e.id = next_id++; return e; }
  Ev measured() {
    step();
    std::uniform_int_distribution<int> d(1, 100); int x = d(rng);
    if (x <= 60 || act.ids.empty()) return limit(1);
    Ev e{}; e.phase = 1;
    if (x <= 70) { e.act = MARKET; e.ts = next_ts++; e.side = side(); e.qty = qty(); e.id = next_id++; e.price = 0; return e; }
    if (x <= 90) { e.act = CANCEL; e.ts = next_ts++; e.id = act.pick(rng); auto s = eng.book().snapshot_order(e.id); e.side = s->side; e.price = *s->price; e.qty = 0; return e; }
    e.act = MODIFY; e.ts = next_ts++; e.id = act.pick(rng);
    auto s = eng.book().snapshot_order(e.id);
    if (!s) return limit(1);
    e.side = s->side;
    if (negctl) {
      std::uniform_int_distribution<int> m(1, 100);
      if (m(rng) <= 50 && s->remaining_quantity > 1) {
        std::uniform_int_distribution<lob::Quantity> r(1, s->remaining_quantity - 1);
        e.reduce = true; e.price = *s->price; e.qty = r(rng); return e;
      }
      e.price = passive(s->side); e.qty = qty(); return e;
    }
    if (mode_draw) { std::uniform_int_distribution<int> m(1, 100); (void)m(rng); }
    const auto cur = *s->price;
    do { e.price = passive(s->side); } while (e.price == cur);
    e.qty = qty();
    return e;
  }
  void sync(lob::OrderId id) { if (eng.book().contains(id)) act.upsert(id); else act.remove(id); }
  void apply(const Ev& e) {
    lob::ExecutionResult r;
    if (e.act == LIMIT) r = eng.submit_order(lob::Order::limit(e.id, "", e.side, e.price, e.qty, e.ts));
    else if (e.act == MARKET) r = eng.submit_order(lob::Order::market(e.id, "", e.side, e.qty, e.ts));
    else if (e.act == CANCEL) r = eng.cancel_order(e.id, e.ts);
    else r = eng.modify_order(e.id, e.reduce ? std::optional<lob::Price>{} : std::optional<lob::Price>{e.price}, e.qty, e.ts);
    if (!r.accepted) throw std::runtime_error("generated event rejected: " + r.reject_reason);
    if (e.act == CANCEL) act.remove(e.id); else sync(e.id);
    for (auto& t : r.trades) sync(t.maker_order_id);
  }
};
}  // namespace

int main(int argc, char** argv) {
  if (argc < 2) { std::fprintf(stderr, "usage: rep_gen out.csv [--mode-draw] [--negative-control-original-modify]\n"); return 2; }
  Gen g;
  for (int i = 2; i < argc; ++i) {
    if (!std::strcmp(argv[i], "--mode-draw")) g.mode_draw = true;
    else if (!std::strcmp(argv[i], "--negative-control-original-modify")) g.negctl = true;
  }
  FILE* f = std::fopen(argv[1], "w"); if (!f) return 1;
  std::fprintf(f, "phase,action,id,side,price,qty,ts\n");
  static const char* an[] = {"limit", "market", "cancel", "replace"};
  long cnt[4] = {0, 0, 0, 0}; long reduces = 0;
  auto out = [&](const Ev& e) {
    std::fprintf(f, "%s,%s,%llu,%s,%lld,%lld,%lld\n", e.phase ? "measured" : "warmup", e.reduce ? "reduce" : an[e.act],
                 (unsigned long long)e.id, e.side == lob::Side::Buy ? "buy" : "sell", (long long)e.price, (long long)e.qty, (long long)e.ts);
  };
  for (int i = 0; i < 20000; ++i) { auto e = g.limit(0); g.apply(e); out(e); }
  for (int i = 0; i < 1000000; ++i) { auto e = g.measured(); g.apply(e); out(e); ++cnt[e.act]; if (e.reduce) ++reduces; }
  std::fclose(f);
  std::printf("measured mix: limit=%ld market=%ld cancel=%ld modify=%ld (of which same-price reductions=%ld)\n", cnt[0], cnt[1], cnt[2], cnt[3], reduces);
  return 0;
}
