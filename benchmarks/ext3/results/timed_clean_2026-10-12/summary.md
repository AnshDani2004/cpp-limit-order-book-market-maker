# ext3a summary (computed by summarize.py from runs.csv)

runs: 30; invalid (trade count, volume or rejects differ from expected): 0; runs with pre-run 1-min load >= 3.0 or failed gate (LOADED): 0

| config | n | events/s median | events/s min to max | p50 ns median (min to max) | p99 ns median (min to max) | 1-min load (min to max) |
|---|---|---|---|---|---|---|
| map | 5 | 5,317,339 | 4,639,633 to 5,913,875 | 125 (125 to 125) | 625 (542 to 875) | 2.54 to 2.89 |
| lb_new | 5 | 2,092,047 | 1,937,422 to 2,204,642 | 250 (209 to 250) | 2625 (2500 to 2833) | 2.54 to 2.89 |
| flat | 5 | 6,582,118 | 6,329,221 to 6,942,092 | 84 (83 to 84) | 542 (500 to 583) | 2.54 to 2.89 |
| lb_pool | 5 | 2,149,158 | 2,038,529 to 2,194,660 | 209 (208 to 209) | 2583 (2500 to 2833) | 2.54 to 2.74 |
| map_unity | 5 | 5,714,845 | 5,566,147 to 5,999,804 | 125 (125 to 125) | 583 (542 to 625) | 2.54 to 2.74 |
| lb_shared | 5 | 1,891,840 | 1,786,789 to 1,907,978 | 250 (250 to 250) | 2917 (2875 to 3125) | 2.54 to 2.74 |

## Decision rule (pre-registered)
- PRIMARY map vs lb_new: events/s: map faster; p50 ns: map lower; p99 ns: map lower; median events/s ratio map/lb_new = 2.542
- secondary (descriptive) flat vs lb_new: events/s: flat faster; p50 ns: flat lower; p99 ns: flat lower; median events/s ratio flat/lb_new = 3.146
- secondary (descriptive) map_unity vs lb_new: events/s: map_unity faster; p50 ns: map_unity lower; p99 ns: map_unity lower; median events/s ratio map_unity/lb_new = 2.732
- secondary (descriptive) map vs lb_pool: events/s: map faster; p50 ns: map lower; p99 ns: map lower; median events/s ratio map/lb_pool = 2.474
- secondary (descriptive) map vs lb_shared: events/s: map faster; p50 ns: map lower; p99 ns: map lower; median events/s ratio map/lb_shared = 2.811
- secondary (descriptive) map vs flat: events/s: flat faster; p50 ns: flat lower; p99 ns: no clear difference; median events/s ratio map/flat = 0.808
- secondary (descriptive) map vs map_unity: events/s: no clear difference; p50 ns: no clear difference; p99 ns: no clear difference; median events/s ratio map/map_unity = 0.930

