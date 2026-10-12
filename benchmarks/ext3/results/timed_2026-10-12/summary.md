# ext3a summary (computed by summarize.py from runs.csv)

runs: 30; invalid (trade count, volume or rejects differ from expected): 0; runs with pre-run 1-min load >= 3.0 or failed gate (LOADED): 30

| config | n | events/s median | events/s min to max | p50 ns median (min to max) | p99 ns median (min to max) | 1-min load (min to max) |
|---|---|---|---|---|---|---|
| map | 5 | 2,366,067 | 2,132,158 to 3,732,455 | 209 (167 to 250) | 1625 (1125 to 1667) | 68.45 to 95.07 |
| lb_new | 5 | 851,380 | 23,276 to 1,062,982 | 334 (333 to 1208) | 11667 (9000 to 43084) | 68.45 to 95.07 |
| flat | 5 | 2,715,650 | 917,252 to 3,690,988 | 208 (125 to 416) | 1500 (1125 to 3167) | 77.12 to 95.07 |
| lb_pool | 5 | 216,422 | 161,524 to 1,175,279 | 833 (292 to 1125) | 31833 (7958 to 38917) | 82.01 to 94.33 |
| map_unity | 5 | 2,312,807 | 899,815 to 3,343,331 | 209 (167 to 500) | 1667 (1208 to 3417) | 79.37 to 98.39 |
| lb_shared | 5 | 192,763 | 8,142 to 751,410 | 500 (417 to 709) | 16417 (12542 to 38667) | 79.37 to 98.39 |

## Decision rule (pre-registered)
- PRIMARY map vs lb_new: events/s: map faster; p50 ns: map lower; p99 ns: map lower; median events/s ratio map/lb_new = 2.779
- secondary (descriptive) flat vs lb_new: events/s: no clear difference; p50 ns: no clear difference; p99 ns: flat lower; median events/s ratio flat/lb_new = 3.190
- secondary (descriptive) map_unity vs lb_new: events/s: no clear difference; p50 ns: no clear difference; p99 ns: map_unity lower; median events/s ratio map_unity/lb_new = 2.717
- secondary (descriptive) map vs lb_pool: events/s: map faster; p50 ns: map lower; p99 ns: map lower; median events/s ratio map/lb_pool = 10.933
- secondary (descriptive) map vs lb_shared: events/s: map faster; p50 ns: map lower; p99 ns: map lower; median events/s ratio map/lb_shared = 12.275
- secondary (descriptive) map vs flat: events/s: no clear difference; p50 ns: no clear difference; p99 ns: no clear difference; median events/s ratio map/flat = 0.871
- secondary (descriptive) map vs map_unity: events/s: no clear difference; p50 ns: no clear difference; p99 ns: no clear difference; median events/s ratio map/map_unity = 1.023
