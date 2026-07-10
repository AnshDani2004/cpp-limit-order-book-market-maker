# Stage 4B Intensity Fit

This checkpoint fits the first exponential arrival curve after the regular session scope, coverage gate, and maintenance bucket rule were fixed.

## Reproduction

```bash
python3 tools/fit_itch_intensity.py --input-dir benchmarks/results/stage4b_intensity_regular_session --output-dir benchmarks/results/stage4b_intensity_fit
```

The input is QQQ from `201326592` compressed bytes of the public Nasdaq TotalView ITCH sample. The book is warmed from the beginning of the capture, but measured quote segments open only at or after `09:30:00`.

## Fit Input

The fit reads `benchmarks/results/stage4b_intensity_regular_session/bucket_diagnostics.csv`.

The inclusion rule is:

```text
include buckets with quote observations at least 50
exclude buckets marked as maintenance buckets
```

The maintenance bucket mark comes from the rule documented in `docs/stage4b_intensity_measurement.md`: at least `50` observations, zero fills, replace message share at least `0.95`, and replace close share at least `0.95`.

Applied to this QQQ regular session run:

```text
total buckets 74
included buckets 17
excluded sparse buckets 54
excluded maintenance buckets 3
total quote observations 25518
total filled quote segments 652
included quote observations 23761
included filled quote segments 642
```

## Model

```text
fill_probability = base_probability * exp(-decay_per_cent * distance_cents)
```

The fit uses binomial maximum likelihood on bucket level observations, so included zero fill buckets still influence the curve.

## Result

```text
base_probability 0.049524662687
decay_per_cent 0.63274456291
decay_per_tick_if_one_tick_is_one_cent 0.63274456291
negative_log_likelihood 2876.23540321
null_negative_log_likelihood 2951.64615553
mcfadden_pseudo_r2 0.0255487102268
weighted_brier_score 0.0261199804099
weighted_rmse 0.00474337362356
```

The fitted decay is positive and captures the first order drop in fill probability as distance moves away from the touch. It is a usable calibrated input for the next Stage 4B comparison.

The fit quality is modest. The empirical buckets are noisy and not monotone after the nearest two cents. In particular, the `3.5`, `5.5`, `7.5`, `9.5`, and `11.5` cent buckets sit above the smooth decay curve despite low observation counts. This result should be described as a defensible one parameter decay calibration on a short real data slice, not as proof that the exponential form fully explains the observed fill process.

## Artifacts

```text
benchmarks/results/stage4b_intensity_fit/fit_input_buckets.csv
benchmarks/results/stage4b_intensity_fit/fit_summary.csv
benchmarks/results/stage4b_intensity_fit/fill_probability_fit.svg
```
