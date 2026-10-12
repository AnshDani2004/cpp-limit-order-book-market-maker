# Extension 3(a) results: this repo's order book vs Liquibook on one identical stream

**LOADED MACHINE. NOT YET REPLICATED.** Every timed run in this file ran with a 1-minute load
average of 68 to 98 on an 8-core Apple M3, because other agents' jobs were using the machine. The
pre-registered gate (load below 3.0) never passed in 45 minutes, so, as PREREG.md section 7
requires, the sequence ran anyway and every number below carries that label. These are not
clean-machine numbers. An independent rerun and an adversarial fairness review, done from
PREREG.md only, are still to come.

Protocol: `PREREG.md`, frozen at commit 878949d (`FREEZE ext3a`) before any timed run. Timed runs
used binaries built from that commit (`raw_stdout.txt` records `repo_commit: 878949d...`). No
deviation from the PREREG.

## 1. Equivalence check: PASS

All five configurations (map, flat, lb_new, lb_pool, lb_shared), in both binaries, gave the same
result on the 1,020,000-event stream (SHA-256 `e1e9535a...8c3394`): 372,120 measured trades, volume
9,486,560, 0 rejects, the same trade-sequence hash `faae67780bb4e8f2` (every trade's event index,
maker id, taker id, price and quantity, in order) and the same final book (hash `634497979a84c9d0`;
best bid 100142 size 57, best ask 100153 size 16148; 575 bid and 298 ask levels; 72,627 and 72,110
resting orders). Files: `results/equivalence/check_ext3_harness.txt`, `check_ext3_harness_unity.txt`.

Negative control: a stream that keeps the repo's original same-price size reductions gives
`EQUIVALENCE=FAIL` (Liquibook 365,229 trades, volume 9,207,013, 20 rejects vs the repo's 365,276,
9,206,720, 0), because Liquibook's `replace` re-queues where the repo keeps priority. File:
`results/equivalence/negative_control_original_modify_check.txt`. That stream was not timed.

Every one of the 30 timed runs also reproduced 372,120 trades, 9,486,560 volume and 0 rejects
(`runs.csv`), so no run was invalid.

## 2. Timed results (LOADED MACHINE, NOT YET REPLICATED)

Source: `results/timed_2026-10-12/runs.csv` (one row per run, with its pre-run load), the 30
`<config>_run<r>_summary.csv` files, `raw_stdout.txt`, and `summary.md` (written by
`summarize.py`). 1,000,000 measured events and 20,000 warm-up events per run; 5 runs per config,
interleaved in rounds `map, lb_new, flat, lb_pool, map_unity, lb_shared`; 2026-10-12 21:01Z to 21:05Z.

| config | role | events/s median | events/s min to max | p50 ns median (min to max) | p99 ns median (min to max) | 1-min load |
|---|---|---|---|---|---|---|
| map (this repo, std::map book) | PRIMARY | 2,366,067 | 2,132,158 to 3,732,455 | 209 (167 to 250) | 1,625 (1,125 to 1,667) | 68.45 to 95.07 |
| lb_new (Liquibook, new/delete per order) | PRIMARY | 851,380 | 23,276 to 1,062,982 | 334 (333 to 1,208) | 11,667 (9,000 to 43,084) | 68.45 to 95.07 |
| flat (this repo, flat book) | secondary | 2,715,650 | 917,252 to 3,690,988 | 208 (125 to 416) | 1,500 (1,125 to 3,167) | 77.12 to 95.07 |
| lb_pool (Liquibook, preallocated orders) | secondary | 216,422 | 161,524 to 1,175,279 | 833 (292 to 1,125) | 31,833 (7,958 to 38,917) | 82.01 to 94.33 |
| map_unity (this repo, engine in harness TU) | secondary | 2,312,807 | 899,815 to 3,343,331 | 209 (167 to 500) | 1,667 (1,208 to 3,417) | 79.37 to 98.39 |
| lb_shared (Liquibook, shared_ptr orders) | secondary | 192,763 | 8,142 to 751,410 | 500 (417 to 709) | 16,417 (12,542 to 38,667) | 79.37 to 98.39 |

## 3. Decision under the pre-registered rule (LOADED MACHINE)

* **PRIMARY, map vs lb_new, events/s: map faster.** Median 2,366,067 vs 851,380 (ratio 2.78), and
  the ranges do not overlap (map's slowest run, 2,132,158, beats lb_new's fastest, 1,062,982).
  On p50 and p99, map is also lower under the same rule (secondary metrics).
* Secondary (descriptive): map is faster than lb_pool (median ratio 10.9) and lb_shared (12.3) with
  non-overlapping ranges. flat vs lb_new and map_unity vs lb_new: **no clear difference** on events/s
  (one loaded flat run at 917,252 and one map_unity run at 899,815 fall inside lb_new's range),
  although their medians are 3.19x and 2.72x lb_new's. map vs flat and map vs map_unity: no clear
  difference on any metric.
* Descriptive, not pre-registered: within each of the 5 rounds, map's events/s exceeded lb_new's.

Because every run was loaded, this decision is a **loaded-machine result only**. It may not survive
a clean rerun, and the size of the gap (2.78x) should not be quoted.

## 4. What the load did (report, not excuse)

* The spread is huge. Single runs were descheduled for very long stretches: lb_shared run 2 has a
  maximum per-event latency of 120.9 s and 8,142 events/s; lb_new run 5 has a 41.5 s maximum and
  23,276 events/s; lb_new run 1 a 0.12 s maximum and 105,145 events/s. The repo configs also had
  bad runs (flat run 1: 917,252; map_unity run 3: 899,815).
* Liquibook configurations ordered in a way their design does not predict: lb_pool (no heap
  allocation for order objects in the timed window) had a lower median (216,422) than lb_new
  (851,380). So with this much noise the ordering among the Liquibook variants is not interpretable.
* The map runs at this load (median 2.37M events/s, p50 209 ns) are slower than the audit's
  low-load map runs on the repo's own stream (4.63M to 5.01M, p50 125 ns,
  `benchmarks/results/audit_2026-10-12_apple_m3/lowload_rerun/README.md`). The streams also
  differ (section 5), so that comparison is only indicative.
* What would change the conclusion: a clean-machine rerun (load below 3.0) in which lb_new's range
  overlaps map's. The independent replication should run on an idle machine.

## 5. Fairness caveats (what each engine does per event that the other does not)

Both engines get the same events, the same timer and loop, the same compiler and flags
(`-O3 -DNDEBUG -std=c++20 -arch arm64`, no LTO or PGO). They still do different work per event,
because they are different designs; nothing was removed from either.

This repo's engine, and not Liquibook:
* returns a full `ExecutionResult` by value: a `std::vector<Trade>` (heap allocation whenever the
  order trades) and a `std::optional<Order>` copy (`Order` is 88 bytes and holds a `std::string`);
* checks and inserts every new id into an ever-growing `unordered_set` of all ids seen
  (duplicate-id rejection), plus a `contains` check against the live-order index;
* copies the order (`snapshot_order`) on every cancel and modify before acting;
* keeps a `std::map` node per price level and a `std::list` node per order;
* runs the self-trade-prevention entry check (returns at once here: owner ids are empty).

Liquibook, and not this repo:
* pushes a `Callback` record per accept, fill, cancel and replace plus a `book_update` record per
  call, then dispatches them in a loop with a try/catch and two virtual calls per record;
* calls `set_market_price` and checks the (empty) stop-order maps on every fill;
* finds an order to cancel or replace by `multimap::find(price)` and then walks the orders at that
  price until the pointer matches, so the cost grows with the queue length at that price. The repo
  goes from the id index to the level (`std::map` lookup) and erases through a stored list iterator.
  The final book here holds about 72,000 orders per side on 298 to 575 levels, so queues are long;
  whether this scan explains the gap was NOT measured (no profile was taken);
* erases and re-inserts the multimap node on every replace.

The Liquibook adapter (written for this benchmark, not part of Liquibook) adds per event: an
`unordered_map` lookup, insert or erase from order id to pointer (the stream addresses orders by id,
Liquibook by pointer); the listener's open-quantity bookkeeping; in lb_new one `new` and one
`delete` per order; in lb_shared one `make_shared` and atomic reference counting. A different
adapter (for example a vector indexed by id) could be faster; it was not tested.

Build asymmetry: Liquibook is header-only and fully inlinable into the harness; the repo engine is
linked as a static library. `map_unity` removes this asymmetry; map vs map_unity showed no clear
difference (medians 2,366,067 vs 2,312,807).

## 6. Limitations

* LOADED MACHINE (above). The one result that matters, the primary decision, needs a clean rerun.
* Synthetic stream only: one seed, one instrument, the repo's own generator family (uniform sizes,
  prices 5 to 200 ticks from a random-walk reference). Engines can rank differently on other flow,
  for example shallower queues, where Liquibook's per-price scan is cheaper.
* The stream is the common subset: no self-trade prevention, no same-price size reductions, no
  all-or-none or stop orders (Liquibook features the repo lacks), no depth or BBO tracking (Liquibook
  offers it via `DepthOrderBook`; not used).
* Timer: `steady_clock` advances in about 41.7 ns ticks on this machine, and each sample includes
  one clock read, so p50 values are a few ticks and coarse; events/s is the primary metric.
* Single thread, single process, no I/O; one machine (Apple M3, macOS 26.5.1, Apple clang 21.0.0,
  on AC power; the battery was at 16% and charging at the start of the session).
* Liquibook is pinned at 2427613 and used through its public API. Its `PERFORMANCE.md` figure (2.0M
  to 2.5M inserts/s, adds only, its own test on a 2.4 GHz i7) measures something else and is not
  comparable.

## 7. Files

`PREREG.md` (frozen protocol), `gen_stream.cpp`, `ext3_harness.cpp`, `build.sh`,
`fetch_liquibook.sh`, `run_timed.sh`, `summarize.py`, `results/equivalence/`,
`results/timed_2026-10-12/` (`runs.csv`, `summary.md`, `raw_stdout.txt`, 30 per-run summaries).
