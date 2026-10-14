# Commit IDs before and after 2026-10-14

On 2026-10-14 the commit messages on this branch were edited to remove trailer lines. Nothing else
changed: every file, author and date is the same, so each commit below has the same tree as before.
Only the commit IDs changed, from the first edited commit onward.

The records in `benchmarks/ext3/` (PREREG.md, RESULTS.md, replication/REPLICATION.md,
replication/replica.json) are left exactly as written, so they cite the old IDs. Use this table to
find the current commit. Commit messages were updated to the new IDs.

| Old | New | Commit |
|---|---|---|
| 219b03e | 9f5c9c9 | audit: cpp-limit-order-book-market-maker |
| 878949d | 5bb7c6c | FREEZE ext3a: PREREG for repo engine vs Liquibook (pinned 2427613), stream generator, harness, equivalence check (PASS) and negative control (FAIL), run and summary scripts |
| 4b3ea3a | d96a59e | ext3b: KILLED by its rule (mbo-queue shadows are best-price, fixed-horizon, open-loop); design for later, nothing run |
| 2dd5ba8 | b83c6d0 | ext3a: timed runs as pre-registered (LOADED MACHINE, load 68 to 98: gate never passed), results and RESULTS.md, NOT YET REPLICATED |
| 50135a3 | db207a4 | ext3a: clean-machine timed rerun (gate passed, load 2.54-2.89; battery power noted): map 5.32M vs Liquibook 2.09M events/s median, ranges disjoint; NOT YET REPLICATED |
| f347b4a | ea8b8bd | ext3a: fairness review saved (decision holds on this deep-queue stream; reverses on a near-empty book); RESULTS qualifier and power-label fix |
| baf9274 | ae8c68b | ext3a: independent replication saved (same decision: map 5.46M vs Liquibook 1.95M events/s on AC power) |
| e8e6dfa | 7afd007 | Replace the order-level Nasdaq ITCH sample files with a download script plus checksums; derived results kept |
| 63e9888 | f027886 | Merge main (ITCH order-level files replaced by fetch script plus checksums) into ext3-named-baseline |
