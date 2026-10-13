# Adversarial fairness review, Extension 3(a): map book vs Liquibook (2427613), 2026-10-13

Saved by the main session (the subagent could not write report files). Files in this folder are copies
of the reviewer's workspace (adv_harness.cpp: the frozen harness plus scan mode, lb_vec, noop, noclock and
per-class sums, SHA prefix 4959c1d1; gen_param.cpp: generator with parameters, defaults reproduce stream
SHA e1e9535a; run_adv.sh; equivalence and scan outputs; results_timed/). Timed runs 2026-10-13 00:53:02Z
to 00:53:35Z, lock held, load 2.04 to 2.35, AC power, 0 LOADED runs; frozen stream 5 rounds, alternative
streams 3 rounds (exploratory). Nothing in benchmarks/ext3/ was modified by the reviewer.

## Verdict
The primary decision holds on the frozen stream ("map faster", reproduced, ranges disjoint, against every
Liquibook variant tried, including a best-case adapter). The 2.5x gap is a property of this stream's very
long queues, not a general ranking: on a near-empty book Liquibook is faster. Any wording without the
stream qualifier is unsupported.

## Threats, ranked
1. Stream dependence (HIGH). On the frozen stream Liquibook's cancel/replace walks a mean of 76.8 multimap
   nodes (p50 58, p99 287, max 385); levels at the target price hold a mean of 152.5 orders. By stream
   (exploratory, 3 rounds, equivalence PASS on each): s5 (mean level 90) map 6.43M vs lb_new 2.63M ev/s;
   s6 (13.5) map 9.25M vs lb_new 6.98M vs lb_vec 8.54M; s1 (8.3) map 8.00M (7.89 to 8.18) vs lb_new 6.05M vs
   lb_vec 7.98M (7.55 to 8.01), no clear difference; s4 (1.3, near-empty book) lb_new 11.11M (11.03 to
   11.12) beats map 10.27M (9.90 to 10.35), disjoint; lb_vec 15.47M. Generators: s5 52/10/28 limit/market/
   cancel weights, offsets 5 to 200; s6 50/10/30, 1 to 30; s1 45/10/35, 5 to 200; s4 40/15/35, 1 to 10,
   warm-up 1k (others 20k). Scan-step means: frozen 76.8, s5 45.5, s6 7.2, s1 4.6, s4 1.1.
2. Attribution (measured). Frozen stream, per-event clock sums, lb_new: cancel 1,080 ns mean (215 ms total)
   and replace 1,236 ns (124 ms) make up 339 of about 498 ms; map: cancel 217 ns, replace 436 ns. Liquibook
   limit adds also slower (230 vs 144 ns); market orders equal (208 vs 221 ns). The gap is mostly
   Liquibook's linear per-price search for the order to cancel or replace.
3. Non-stationary stream (MEDIUM). The live book grows through the measured window (46,752 orders after
   200k events, 144,737 after 1M), so Liquibook's cost per event rises over the run; much deeper queues
   than CL/NG top of book.
4. Adapter cost (LOW). lb_vec (preallocated slots, vector indexed by id, no hash map, no new/delete) 2.23M
   median (1.95 to 2.38M) vs lb_new 1.95M (about 14%); map (min 4.43M) still wins. lb_new's id map mirrors
   the repo's own internal index, so it is fair.
5. Timer (LOW). Loop plus two clock reads cost about 30 ns per event (noop 33.3M ev/s). Without per-event
   clocks: map 5.13M, lb_new 1.97M, lb_vec 2.35M; the timer slightly compresses the ratio (2.61 without
   clocks vs 2.42 with); it does not favour map.
6. Power and session (LOW). AC power, Low Power Mode off, load 2.04 to 2.35: map 4.74M median (4.43 to
   5.45M) vs lb_new 1.95M (1.37 to 2.05M), ratio 2.42 vs 2.54 in the battery run.
7. Doc inconsistency: RESULTS.md's limitation line "on AC power; battery 16% charging" describes the loaded
   session, while section 2b ran on battery. (Fixed by the main session.)

Checked, no problem: equivalence compares the full fill sequence (event index, maker, taker, price, qty)
plus the final-book hash; PASS for all configs plus lb_vec on the frozen stream and s1, s4, s5, s6. Same
flags for both engines; no live asserts in Liquibook; its debug path fires only on deprecated calls; its
order-book-only mode is its fastest. Binaries predate later commits, which change only results and docs.

## Wording supported
"On one synthetic stream with very deep queues (about 150 orders at the price of a typical cancel, book
growing to about 145k orders), the repo's map book processed events about 2.4 to 2.5x faster than Liquibook
(5.3M vs 2.1M events/s median, non-overlapping 5-run ranges; reproduced at 4.7M vs 2.0M in an adversarial
rerun). The gap comes mainly from Liquibook's linear search within a price level on cancel/replace. On
shallower synthetic books the gap shrinks, then reverses: Liquibook was faster on a near-empty book
(exploratory)." Never "faster than Liquibook" without the stream qualifier.
