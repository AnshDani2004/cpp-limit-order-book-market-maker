# Stage 4B Calibration Gate

This note fixes the data decision before any arrival intensity curve is fit.

## Decision

The Stage 4A replay sample is not sufficient for Stage 4B intensity calibration. It has enough volume for order flow mix, size distribution, and lifetime diagnostics, but it has too few executions for a fill probability curve.

Stage 4B must not fit an exponential arrival curve on the Stage 4A QQQ sample alone.

The first probe widened the public Nasdaq TotalView ITCH prefix from `33554432` compressed bytes to `134217728` compressed bytes, but that only reached before regular hours data. The primary Stage 4B calibration input is now QQQ from `201326592` compressed bytes with measured quote segments restricted to those opening at or after `09:30:00`. If those QQQ distance bins fail the fit coverage gate in a later run, the fallback will be a clearly labeled pooled real ITCH calibration from multiple symbols in the same regular session prefix. The Stage 3 synthetic flow is only a final fallback if the widened real data still fails the execution coverage gate.

## Regular Session Scope

The `134217728` byte QQQ measurement reached only `09:28:53.045169096`, before the regular `09:30:00` open. It is therefore a before regular hours diagnostic, not the Stage 4B fit source.

Stage 4B will use option A: widen the QQQ pull into regular session data and measure only quote segments that open at or after `09:30:00`. The book is still warmed from earlier messages, but calibration quote segments do not open before the regular session boundary.

The range probe showed:

```text
150994944 compressed bytes reached 09:30:00.639885444
167772160 compressed bytes reached 09:30:22.736152206
201326592 compressed bytes reached 09:32:38.716540708
```

The chosen regular session calibration input is QQQ from `201326592` compressed bytes with measurement start `09:30:00`. That run passed the fit coverage gate with `25518` closed quote segments, `652` filled quote segments, `74` non empty distance buckets, and `15` positive fill buckets. Because the regular session QQQ run passes the gate, pooled real ITCH symbols and Stage 3 synthetic flow are not needed for the next fit checkpoint.

## Probe Evidence

The probe parsed complete Soup framed messages from three public ITCH compressed prefixes and counted executions for active visible orders.

```text
33554432 compressed bytes
QQQ execution messages 57
QQQ execution closures 11

67108864 compressed bytes
QQQ execution messages 198
QQQ execution closures 34

134217728 compressed bytes
QQQ execution messages 413
QQQ execution closures 136
SPY execution messages 469
SPY execution closures 255
TVIX execution messages 683
TVIX execution closures 427
IGC execution messages 803
IGC execution closures 505
VEON execution messages 1127
VEON execution closures 791
CNC execution messages 1972
CNC execution closures 1344
```

The important point is not that these symbols should all be mixed without care. The point is that the original Stage 4A QQQ sample is clearly too thin for intensity estimation, while a wider real ITCH pull creates a viable real data path before falling back to synthetic flow.

## Fit Coverage Gate

Before reporting a fitted exponential arrival curve, the calibration script must report the number of closed quote segments, filled quote segments, execution messages inside those segments, non empty distance buckets, and buckets with positive fills.

The fit coverage gate is automatic. The script must refuse to proceed past measurement unless all of these thresholds are met:

```text
closed quote segments at least 500
filled quote segments at least 100
non empty distance buckets at least 8
positive fill buckets at least 5
```

The positive fill bucket threshold is `5` because an exponential arrival curve has two fitted parameters, and five positive points leave visible degrees of freedom instead of fitting a curve through one or two lucky distances. The filled quote segment threshold is `100` so repeated partial execution messages on a small number of orders cannot by themselves pass the gate.

If QQQ from the widened prefix fails this gate, the script must print the exact failed fields and stop. The next run is the clearly labeled pooled real ITCH fallback from the same widened prefix. The Stage 3 synthetic flow remains the final fallback if the widened real data still fails the gate.

The curve fit itself is not allowed to be the first place this decision appears. The calibration data source and fallback rule are fixed here first.
