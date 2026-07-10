# Stage 4B Intensity Measurement

This checkpoint measures empirical fill probability versus quote distance before any exponential arrival curve is fit.

## Reproduction

```bash
python3 tools/itch_intensity_calibration.py --symbols QQQ --range-bytes 201326592 --start-time 09:30:00 --output-dir benchmarks/results/stage4b_intensity_regular_session
```

The command downloads the widened public Nasdaq TotalView ITCH prefix, warms the QQQ book from the beginning of the capture, opens measured quote segments only at or after `09:30:00`, buckets each segment by side adjusted quote distance from the current book mid, and writes the empirical fill probability table.

## Automatic Gate

The script refuses to proceed past measurement unless the fit coverage gate passes. The thresholds are:

```text
closed quote segments at least 500
filled quote segments at least 100
non empty distance buckets at least 8
positive fill buckets at least 5
```

The original Stage 4A QQQ prefix fails this gate automatically:

```text
compressed prefix bytes 33554432
closed quote segments 6394
filled quote segments 50
execution messages in segments 57
non empty distance buckets 47
positive fill buckets 11
fit gate passed no
fit gate message filled_quote_segments 50 below 100
```

This is the intended behavior. The script writes the measurement files, prints the failed field, and exits with a failure status instead of allowing a later fit to treat the thin sample as ready.

## Scope Decision

The first widened QQQ run used `134217728` compressed bytes and reached only `09:28:53.045169096`, before the regular `09:30:00` open. It is therefore a before regular hours diagnostic, not the Stage 4B fit source.

The range probe showed:

```text
150994944 compressed bytes reached 09:30:00.639885444
167772160 compressed bytes reached 09:30:22.736152206
201326592 compressed bytes reached 09:32:38.716540708
```

The chosen Stage 4B fit source is QQQ from `201326592` compressed bytes, restricted to quote segments that open at or after `09:30:00`. The pooled real ITCH fallback is not needed because this regular session QQQ run passes the gate.

## Regular Session QQQ Result

```text
compressed prefix bytes 201326592
source last time 09:32:38.716540708
measurement start time 09:30:00.000000000
closed quote segments 25518
filled quote segments 652
execution messages in segments 845
right censored quote segments 6484
non empty distance buckets 74
positive fill buckets 15
fit gate passed yes
```

The regular session empirical table is checked in at `benchmarks/results/stage4b_intensity_regular_session/fill_probability_by_distance.csv`. The densest buckets are:

```text
distance 0 to 1 cents, observations 13284, filled segments 519, fill probability 0.0390695573622
distance 1 to 2 cents, observations 8002, filled segments 105, fill probability 0.0131217195701
distance 2 to 3 cents, observations 746, filled segments 7, fill probability 0.00938337801609
distance 3 to 4 cents, observations 294, filled segments 5, fill probability 0.0170068027211
```

The raw relationship is not yet a fitted model. Sparse tail buckets can show large fill probabilities from only one or two observations, so the next checkpoint must define the fit bucket inclusion rule before fitting the exponential curve.

## Before Regular Hours Diagnostic

The before regular hours QQQ run remains checked in at `benchmarks/results/stage4b_intensity_measurement`. It is useful as a diagnostic comparison, but it is not the Stage 4B fit source.

```text
compressed prefix bytes 134217728
source last time 09:28:53.045169096
closed quote segments 42377
filled quote segments 334
execution messages in segments 413
non empty distance buckets 92
positive fill buckets 25
fit gate passed yes
```

## Extreme Distance Diagnostics

The before regular hours distance outlier table is checked in at `benchmarks/results/stage4b_intensity_measurement/distance_outliers.csv`. The regular session distance outlier table is checked in at `benchmarks/results/stage4b_intensity_regular_session/distance_outliers.csv`.

The negative filled tail point is an opening book formation artifact:

```text
open time 04:00:04.746707719
order ref 92683
side buy
price 179.57
best bid 160.00
best ask 179.63
mid 169.815
distance cents minus 975.5
fill messages 1
filled quantity 4
close time 04:00:07.105053198
close reason delete
```

The nearby negative extreme observations also occur between `04:00:01.625994004` and `04:00:30.663278381`, with the same stale `160.00` best bid driving a midpoint far below the active QQQ price. This should be handled by a stated warmup exclusion rule before fitting, not by deleting a single bad point.

The very large positive point is different:

```text
open time 08:56:25.469080993
order ref 7361883
side sell
price 199999.99
best bid 179.17
best ask 179.18
mid 179.175
distance cents 19982081.5
fill messages 0
filled quantity 0
close time 09:00:19.678700738
close reason delete
```

This point is not near a QQQ trading status transition in the parsed prefix. It is one of several before regular hours off market quotes, including a paired `0.01` buy quote in the immediately preceding message. The prefix ends at `09:28:53.045169096`, before the regular `09:30` open, so this run is retained only as a before regular hours diagnostic.

The other before regular hours far tail buckets show the same off market stub signature rather than normal wide passive quotes:

```text
bucket 17916, open time 08:56:25.469075894, side buy, price 0.01, best bid 179.17, best ask 179.18, mid 179.175, close reason delete
bucket 8064, open time 08:53:18.911371119, side sell, price 259.82, best bid 179.17, best ask 179.19, mid 179.18, close reason delete
bucket 8063, open time 08:53:18.911358319, side buy, price 98.55, best bid 179.17, best ask 179.19, mid 179.18, close reason delete
bucket 7660, open time 08:53:16.032872627, side buy, price 102.57, best bid 179.16, best ask 179.18, mid 179.17, close reason delete
bucket 3139, open time 09:04:30.326523940, side buy, price 147.95, best bid 179.33, best ask 179.35, mid 179.34, close reason delete
```

These do not cluster in the `04:00:00` to `04:00:30` opening window. They are later before regular hours stub quote levels, often appearing as paired deep buy and sell prices around a normal QQQ mid. They are unfilled and should not be treated as evidence about the executable fill decay curve.

The regular session outliers are smaller but show a similar maintenance ladder:

```text
bucket 733, open time 09:30:01.401698143, side buy, price 172.00, best bid 179.33, best ask 179.34, mid 179.335, close reason delete
bucket 584, open time 09:30:04.615873328, side sell, price 185.25, best bid 179.40, best ask 179.42, mid 179.41, close reason delete
bucket 540, open time 09:30:02.205389352, side buy, price 173.96, best bid 179.36, best ask 179.37, mid 179.365, close reason replace
bucket 539, open time 09:30:02.252791639, side sell, price 184.76, best bid 179.36, best ask 179.37, mid 179.365, close reason replace
```

The `538` to `540` cent buckets contain many unfilled replace segments within the first two regular session minutes. They look like systematic stub quote maintenance rather than normal near touch liquidity. The next checkpoint must define a fit inclusion rule that excludes this maintenance tail by a stated rule, not by deleting individual rows.

## Ladder Size And Fit Rule

The regular session bucket diagnostics are checked in at `benchmarks/results/stage4b_intensity_regular_session/bucket_diagnostics.csv`. The `538` to `540` cent maintenance ladder has this measured shape:

```text
total closed quote segments 25518
ladder closed quote segments 1276
ladder share of closed quote segments 5.00039188024 percent
ladder filled quote segments 0
ladder distinct order refs 1276
ladder distinct side price levels 69
ladder source message type U share 100 percent
ladder close reason replace share 100 percent
first ladder open time 09:30:00.305358998
last ladder open time 09:32:38.225403439
```

The ladder is therefore a meaningful fraction of the regular session sample, not a tiny nuisance. It is not caused by one repeated order reference because every segment has a distinct ITCH order reference. It is also not concentrated in only one or two exact prices. The robust signature is bucket level maintenance behavior: many observations, no fills, all opened by replace messages, and all closed by replace messages.

The next exponential fit must use this coordinate independent inclusion rule:

```text
exclude a bucket from fit input if quote observations are at least 50, filled quote segments are 0, replace message share is at least 0.95, and replace close share is at least 0.95
```

This rule excludes systematic stub quote maintenance wherever it appears, without naming the `538` to `540` cent coordinates. The rule does not exclude sparse one observation tail rows by itself. Those remain outside the fit only if the fit checkpoint also applies a separate minimum observation rule.

Applied to the current regular session QQQ run, this rule flags exactly three buckets:

```text
bucket 538, quote observations 65, filled quote segments 0, replace message share 1, replace close share 1
bucket 539, quote observations 924, filled quote segments 0, replace message share 1, replace close share 1
bucket 540, quote observations 287, filled quote segments 0, replace message share 1, replace close share 1
```

## Segment Semantics

A quote segment starts when an ITCH add or replace message creates a visible order and the symbol has a two sided book mid. Distance is side adjusted:

```text
buy distance = mid minus price
sell distance = price minus mid
```

Executions mark the segment as filled. Deletes, cancels to zero, and replaces close the segment. Open segments at the end of the prefix are treated as right censored and excluded from the fill probability denominator.

Replaces start a new quote segment because the posted price and displayed size can change. This is different from the Stage 4A lifetime statistic, which tracks the underlying translated engine order across replace messages.

A valid two sided mid requires both sides to exist and best bid to be strictly below best ask. If only one side exists, or if the book is crossed, no quote segment is opened for that add or replace message. In the widened QQQ run, `3` candidate segments were skipped because only one side was available and `0` were skipped because the book was crossed.

When a measurement start time is provided, earlier messages still build the active book, but they do not open measured quote segments. This is how the regular session run avoids measuring before regular hours quote segments while still using the existing book state at `09:30:00`.
