# Stage 4B Intensity Measurement

This checkpoint measures empirical fill probability versus quote distance before any exponential arrival curve is fit.

## Reproduction

```bash
python3 tools/itch_intensity_calibration.py --symbols QQQ --range-bytes 134217728 --output-dir benchmarks/results/stage4b_intensity_measurement
```

The command downloads the widened public Nasdaq TotalView ITCH prefix, tracks QQQ visible order segments, buckets each segment by side adjusted quote distance from the current book mid, and writes the empirical fill probability table.

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

## Widened QQQ Result

The widened QQQ run passes the gate, so the pooled symbol fallback is not needed for this checkpoint.

```text
compressed prefix bytes 134217728
messages read 10976950
supported symbol messages 83209
closed quote segments 42377
filled quote segments 334
execution messages in segments 413
right censored quote segments 175
non empty distance buckets 92
positive fill buckets 25
fit gate passed yes
```

The empirical table is checked in at `benchmarks/results/stage4b_intensity_measurement/fill_probability_by_distance.csv`. The densest buckets are:

```text
distance 0 to 1 cents, observations 6521, filled segments 107, fill probability 0.0164085262996
distance 1 to 2 cents, observations 21627, filled segments 153, fill probability 0.00707449022056
distance 2 to 3 cents, observations 5832, filled segments 18, fill probability 0.00308641975309
distance 3 to 4 cents, observations 378, filled segments 8, fill probability 0.021164021164
```

The raw relationship is not yet a fitted model. Sparse tail buckets can show large fill probabilities from only one or two observations, so the next checkpoint must define the fit bucket inclusion rule before fitting the exponential curve.

## Segment Semantics

A quote segment starts when an ITCH add or replace message creates a visible order and the symbol has a two sided book mid. Distance is side adjusted:

```text
buy distance = mid minus price
sell distance = price minus mid
```

Executions mark the segment as filled. Deletes, cancels to zero, and replaces close the segment. Open segments at the end of the prefix are treated as right censored and excluded from the fill probability denominator.

Replaces start a new quote segment because the posted price and displayed size can change. This is different from the Stage 4A lifetime statistic, which tracks the underlying translated engine order across replace messages.
