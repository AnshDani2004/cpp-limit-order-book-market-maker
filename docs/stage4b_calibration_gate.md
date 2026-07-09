# Stage 4B Calibration Gate

This note fixes the data decision before any arrival intensity curve is fit.

## Decision

The Stage 4A replay sample is not sufficient for Stage 4B intensity calibration. It has enough volume for order flow mix, size distribution, and lifetime diagnostics, but it has too few executions for a fill probability curve.

Stage 4B must not fit an exponential arrival curve on the Stage 4A QQQ sample alone.

The primary Stage 4B calibration input will be a widened public Nasdaq TotalView ITCH prefix from the same sample file, using `134217728` compressed bytes instead of `33554432`. The first calibration candidate is QQQ from that widened prefix so the symbol stays consistent with Stage 4A. If the QQQ distance bins still do not have enough positive fill observations after binning by quote distance, the fallback will be a clearly labeled pooled real ITCH calibration from multiple symbols in the same widened prefix. The Stage 3 synthetic flow is only a final fallback if the widened real data still fails the execution coverage gate.

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

Before reporting a fitted exponential arrival curve, the calibration script must report the number of execution observations used, the number of non empty distance buckets, and the number of buckets with positive fills. If QQQ from the widened prefix has too few positive fill buckets to support a meaningful curve, the writeup must say that plainly and use the pooled real ITCH fallback or the Stage 3 synthetic fallback with the weaker claim clearly labeled.

The curve fit itself is not allowed to be the first place this decision appears. The calibration data source and fallback rule are fixed here first.
