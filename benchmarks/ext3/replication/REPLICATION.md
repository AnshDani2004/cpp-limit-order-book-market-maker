# Extension 3(a) independent replication: repo order book vs Liquibook

Written by the independent replication agent, 2026-10-12, from `benchmarks/ext3/PREREG.md` (frozen at
878949d) only. I did not read `benchmarks/ext3/*.cpp|*.sh|*.py`, `results/`, `RESULTS.md`, `STATUS.md`,
`KILLED_b.md` or the copies in `ext/cpp/`. Everything here is my own code: `src/rep_gen.cpp` (stream),
`src/rep_harness.cpp` (adapters, check, timing), `build.sh`, `run_timed.sh`, `summarize.py`,
`tools/sha_probe.py`. Machine-readable numbers: `replica.json`.

## Setup

* Apple M3, macOS 26.5.1, Apple clang 21.0.0 (clang-2100.1.1.101), flags
  `-O3 -DNDEBUG -std=c++20 -arch arm64 -Wall -Wextra` for every TU, Liquibook via `-isystem`, no LTO/PGO/-mcpu.
* Repo engine: the four sources (`flat_order_book`, `matching_engine`, `order_book`, `price_level`) from the
  clone at HEAD 50135a3 (`include/` and `src/` identical to 219b03e, `git diff` empty), compiled into my own
  `build/liblob_engine.a`. The repo clone was not modified.
* Liquibook cloned fresh into `third_party/liquibook` at 2427613b32f1667abae68a01df6af9ba8270f8e7.
* Two binaries: `rep_harness` (engine as static library) and `rep_harness_unity` (`-DREP_UNITY`, the four
  `.cpp` files included into the harness TU).

## 1. Stream

| property | PREREG | replica |
|---|---|---|
| rows (excluding header) | 1,020,000 | 1,020,000 |
| measured mix limit / market / cancel / replace | 599,678 / 100,557 / 199,517 / 100,248 | 599,678 / 100,557 / 199,517 / 100,248 (exact) |
| SHA-256 | e1e9535a...8c3394 | 9993edae...21b59b9 (different) |

The mix matching exactly means the replica consumes the `mt19937_64` (seed 42) draws in the same order as
the original. The SHA differs because the PREREG gives only the column names, not the value encodings (see
ambiguities); a bounded probe of 48 plausible encodings found no match. The replica is not meant to be
byte-identical. The generator is deterministic (regenerated stream had the same SHA).

## 2. Equivalence check (untimed)

All six configurations give identical values, which equal the PREREG's table field for field:

| measured trades | volume | rejects | best bid (size) | best ask (size) | levels bid/ask | orders bid/ask | size bid/ask |
|---|---|---|---|---|---|---|---|
| 372,120 | 9,486,560 | 0 | 100142 (57) | 100153 (16148) | 575 / 298 | 72,627 / 72,110 | 3,667,041 / 3,645,589 |

Replica FNV-1a hashes (equal across all configs): trade sequence `3fc627fc83a6c66b`, final book
`bf1408ef136bd721`. These are not comparable to the PREREG's hash values because the byte layout is
unspecified. `EQUIVALENCE=PASS` for both binaries (`results/equivalence/`).

Negative control (original modify rule, 50% same-price reductions; my stream SHA ec24165f...a711f):
`EQUIVALENCE=FAIL`. map = flat (350,663 trades, volume 8,858,835, 0 rejects); all three Liquibook configs
350,671 trades, volume 8,858,958, 5 rejects, different final book. The qualitative result is reproduced
(the check detects the priority difference). The counts differ from the PREREG's (365,276 / 365,229 / 20
rejects), so my negative-control stream is not the same as theirs (details unspecified, see ambiguities).

## 3. Timed comparison (`results/run1/`)

Gate passed at the first poll (1-min load 2.19, no lock file); lock `ext3_timing.lock` created for the
sequence and removed at the end. Per-run pre-run load 2.00 to 2.19, no run flagged LOADED, power
"AC Power" for all 30 runs. All 30 runs valid (372,120 trades, 9,486,560 volume, 0 rejects). The sequence
ran 19:54:18 to 19:54:38 (about 20 s). Five rounds, fixed order map, lb_new, flat, lb_pool, map_unity,
lb_shared, one fresh process each.

| config | events/s median | events/s min to max | p50 ns median (range) | p99 ns median (range) |
|---|---|---|---|---|
| map (PRIMARY A) | 5,456,741 | 5,096,076 to 5,593,750 | 125 (125 to 125) | 625 (583 to 667) |
| lb_new (PRIMARY B) | 1,954,474 | 1,843,133 to 2,075,588 | 250 (209 to 250) | 2,791 (2,709 to 3,333) |
| flat | 6,346,117 | 6,105,752 to 6,658,756 | 84 (84 to 84) | 584 (542 to 708) |
| lb_pool | 2,074,395 | 1,973,385 to 2,109,020 | 209 (209 to 209) | 2,666 (2,625 to 2,875) |
| map_unity | 5,679,519 | 5,613,842 to 5,714,679 | 125 (125 to 125) | 584 (583 to 625) |
| lb_shared | 1,812,950 | 1,745,518 to 1,864,584 | 250 (250 to 250) | 3,167 (2,958 to 3,208) |

p50 values are a few `steady_clock` ticks (about 41.7 ns) and are coarse.

**Primary decision (PREREG section 8 rule): map is faster than lb_new on events/s** (median 5,456,741 vs
1,954,474; map's minimum 5,096,076 exceeds lb_new's maximum 2,075,588). Ratio of medians 2.79. Secondary,
descriptive: map also has lower p50 and p99 than lb_new by the same rule. Other secondary pairs: flat,
map_unity faster than every Liquibook config; flat faster than map; map_unity faster than map (ratio 0.96,
ranges disjoint); map vs flat p99 and map vs map_unity p50/p99: no clear difference.

Context, not part of the replication rule: the original clean-machine rerun commit message (50135a3)
reports map 5.32M vs Liquibook 2.09M events/s medians. My lb_new median is lower (1.95M) and map slightly
higher (5.46M); same direction and decision. I did not open that run's files.

## Ambiguities and choices

1. The PREREG says the generator re-implements `FlowGenerator` in `benchmarks/orderbook_benchmark.cpp`
   without giving its draw order. I read that file (outside `benchmarks/ext3/`, not on the forbidden list,
   named by the PREREG) to get the draw order; I did not read any ext3 code.
2. Modify rule: the PREREG does not say whether the original 1..100 "mode" draw is still consumed. Without
   it the mix matches the PREREG exactly; with it the mix is 599,738 / 100,434 / 199,867 / 99,961. I used
   the version without it.
3. Cancel/replace target always live: kept the original fallback (if the active set is empty, the event
   becomes a limit add).
4. CSV value encodings (phase, action and side labels, what goes in side/price/qty for cancels and market
   orders, header) are unspecified, so the SHA cannot be reproduced except by guessing. Mine:
   `warmup|measured`, `limit|market|cancel|replace`, `buy|sell`, market price 0, cancel rows carry the
   target's side and current price with qty 0.
5. FNV-1a hashing: byte layout unspecified. Mine: FNV-1a 64 over each field as an 8-byte little-endian
   word; trade fields (measured event index, maker id, taker id, price, qty); book levels as (price, total
   size, order count), bids best-first then asks best-first.
6. Negative control: details of the original-rule stream (owner ids, draw order) unspecified; my version
   uses empty owners and the original modify draws verbatim, and maps reductions to `modify_order(id,
   current price, qty)` / `replace(ptr, qty - open, current price)`.
7. Liquibook adapter: market orders are not put in the id map (the PREREG table only says live[id] for
   limit adds); they are deleted (lb_new) at the end of their own event. An inbound limit or replaced order
   that fully fills is removed from the map and deleted after the call. `order_qty()` keeps the original
   size; `on_replace` updates price and open quantity only, as the PREREG says.
8. lb_pool: one preallocated slot per order id (max id + 1), allocated before the warm-up.
9. Load rule: the replication brief is stricter than PREREG section 7 rule 3 (I would not have run if the
   gate failed after 45 minutes). The gate passed, so this did not matter.

## Status

Replicated: equivalence values (exact), measured mix (exact), the primary decision (map faster than lb_new),
and the direction of every secondary pair. Not replicated: the stream SHA and the two FNV hashes (layout
unspecified), and the negative-control counts (only its FAIL outcome). One run sequence on one machine.
