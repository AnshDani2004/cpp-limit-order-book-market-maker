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
likelihood_ratio_statistic 150.821504639
likelihood_ratio_degrees_of_freedom 1
likelihood_ratio_p_value 1.14657252666e-34
decay_standard_error 0.0766819728931
decay_ci_95_lower 0.482450657776
decay_ci_95_upper 0.783038468044
```

The fitted decay is positive and captures the first order drop in fill probability as distance moves away from the touch. A likelihood ratio test against the constant probability null gives statistic `150.821504639` with `1` degree of freedom and p value `1.14657252666e-34`. The 95 percent Wald interval for `decay_per_cent` is `0.482450657776` to `0.783038468044`.

This means the low McFadden pseudo R squared does not mean the decay term is fake. It means the exponential distance term is statistically real, while most of the absolute variation remains unexplained, which is expected in rare event binomial data where bucket probabilities are only a few percent.

The fit quality is still modest. The empirical buckets are noisy and not monotone after the nearest two cents. In particular, the `3.5`, `5.5`, `7.5`, `9.5`, and `11.5` cent buckets sit above the smooth decay curve despite low observation counts. This result should be described as a statistically robust decay effect on a short real data slice, not as proof that the exponential form fully explains the observed fill process.

## Parity Diagnostic

The odd half cent residual pattern was checked against raw quote segment prices and mids. The segment export is checked in at `benchmarks/results/stage4b_intensity_regular_session/quote_segments.csv`, and the diagnostic table is checked in at `benchmarks/results/stage4b_intensity_fit/parity_diagnostics.csv`.

All included quote segments use whole cent order prices. Many buckets also have a dominant exact half cent distance because the QQQ mid often sits at a half cent while displayed orders are posted on whole cents. This is real tick geometry, but it is not unique to the buckets above the curve.

```text
bucket 3, parity odd, residual 0.0115988812843, half cent mid share 0.755102040816
bucket 4, parity even, residual minus 0.00287232052537, half cent mid share 0.653846153846
bucket 5, parity odd, residual 0.028777448747, half cent mid share 0.833333333333
bucket 6, parity even, residual 0.010178725694, half cent mid share 0.769230769231
bucket 7, parity odd, residual 0.00947062159027, half cent mid share 0.712871287129
bucket 8, parity even, residual minus 0.000228582518364, half cent mid share 0.72131147541
bucket 9, parity odd, residual 0.00597615346869, half cent mid share 0.884146341463
bucket 10, parity even, residual minus 0.0000644834208722, half cent mid share 0.862179487179
bucket 11, parity odd, residual 0.00453196083264, half cent mid share 0.703196347032
bucket 12, parity even, residual minus 0.0000181908555262, half cent mid share 0.8125
```

The quoted price convention explains why many distances land exactly at half cent points. It does not by itself explain why several odd buckets are above the curve, because even buckets show the same whole cent price share and similar half cent mid shares. The safer interpretation is that the residual pattern combines normal tick geometry with sparse bucket fill noise, not a confirmed odd versus even microstructure effect.

## Artifacts

```text
benchmarks/results/stage4b_intensity_fit/fit_input_buckets.csv
benchmarks/results/stage4b_intensity_fit/fit_summary.csv
benchmarks/results/stage4b_intensity_fit/fill_probability_fit.svg
benchmarks/results/stage4b_intensity_fit/parity_diagnostics.csv
benchmarks/results/stage4b_intensity_regular_session/quote_segments.csv
```
