#!/usr/bin/env python3

import argparse
import csv
import math
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


DEFAULT_INPUT_DIR = "benchmarks/results/stage4b_intensity_regular_session"
DEFAULT_OUTPUT_DIR = "benchmarks/results/stage4b_intensity_fit"
MIN_FIT_OBSERVATIONS = 50
MIN_PROBABILITY = 1e-12
MAX_PROBABILITY = 1.0 - 1e-12


@dataclass
class Bucket:
    lower_cents: float
    upper_cents: float
    observations: int
    filled: int
    maintenance: bool

    @property
    def distance_cents(self):
        return 0.5 * (self.lower_cents + self.upper_cents)

    @property
    def empirical_probability(self):
        return 0.0 if self.observations == 0 else self.filled / self.observations


@dataclass
class Segment:
    bucket_lower_cents: float
    distance_cents: float
    price: float
    mid: float
    fill_messages: int


@dataclass
class FitResult:
    base_probability: float
    decay_per_cent: float
    negative_log_likelihood: float
    null_negative_log_likelihood: float
    mcfadden_pseudo_r2: float
    weighted_brier_score: float
    weighted_rmse: float
    likelihood_ratio_statistic: float
    likelihood_ratio_degrees_of_freedom: int
    likelihood_ratio_p_value: float
    decay_standard_error: float
    decay_ci_95_lower: float
    decay_ci_95_upper: float


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-fit-observations", type=int, default=MIN_FIT_OBSERVATIONS)
    return parser.parse_args()


def read_buckets(path):
    buckets = []
    with path.open() as handle:
        for row in csv.DictReader(handle):
            buckets.append(
                Bucket(
                    lower_cents=float(row["bucket_lower_cents"]),
                    upper_cents=float(row["bucket_upper_cents"]),
                    observations=int(row["quote_observations"]),
                    filled=int(row["filled_quote_segments"]),
                    maintenance=row["maintenance_bucket"] == "yes",
                )
            )
    return buckets


def read_segments(path):
    segments = []
    if not path.exists():
        return segments
    with path.open() as handle:
        for row in csv.DictReader(handle):
            segments.append(
                Segment(
                    bucket_lower_cents=float(row["bucket_lower_cents"]),
                    distance_cents=float(row["distance_cents"]),
                    price=float(row["price"]),
                    mid=float(row["mid"]),
                    fill_messages=int(row["fill_messages"]),
                )
            )
    return segments


def include_bucket(bucket, min_observations):
    if bucket.maintenance:
        return False, "maintenance"
    if bucket.observations < min_observations:
        return False, "sparse"
    return True, "included"


def predicted_probability(bucket, base_probability, decay_per_cent):
    probability = base_probability * math.exp(-decay_per_cent * bucket.distance_cents)
    return min(MAX_PROBABILITY, max(MIN_PROBABILITY, probability))


def negative_log_likelihood(buckets, base_probability, decay_per_cent):
    total = 0.0
    for bucket in buckets:
        probability = predicted_probability(bucket, base_probability, decay_per_cent)
        total -= bucket.filled * math.log(probability)
        total -= (bucket.observations - bucket.filled) * math.log1p(-probability)
    return total


def negative_log_likelihood_alpha_decay(buckets, alpha, decay):
    return negative_log_likelihood(buckets, math.exp(alpha), decay)


def numeric_hessian(function, alpha, decay):
    alpha_step = max(1e-5, abs(alpha) * 1e-5)
    decay_step = max(1e-5, abs(decay) * 1e-5)
    center = function(alpha, decay)
    alpha_plus = function(alpha + alpha_step, decay)
    alpha_minus = function(alpha - alpha_step, decay)
    decay_plus = function(alpha, decay + decay_step)
    decay_minus = function(alpha, decay - decay_step)
    both_plus = function(alpha + alpha_step, decay + decay_step)
    alpha_plus_decay_minus = function(alpha + alpha_step, decay - decay_step)
    alpha_minus_decay_plus = function(alpha - alpha_step, decay + decay_step)
    both_minus = function(alpha - alpha_step, decay - decay_step)
    alpha_alpha = (alpha_plus - 2.0 * center + alpha_minus) / (alpha_step * alpha_step)
    decay_decay = (decay_plus - 2.0 * center + decay_minus) / (decay_step * decay_step)
    alpha_decay = (
        both_plus
        - alpha_plus_decay_minus
        - alpha_minus_decay_plus
        + both_minus
    ) / (4.0 * alpha_step * decay_step)
    return alpha_alpha, alpha_decay, decay_decay


def covariance_from_hessian(alpha_alpha, alpha_decay, decay_decay):
    determinant = alpha_alpha * decay_decay - alpha_decay * alpha_decay
    if determinant <= 0.0:
        raise ValueError("fit hessian is not positive definite")
    return decay_decay / determinant, -alpha_decay / determinant, alpha_alpha / determinant


def golden_minimize(function, lower, upper, iterations=120):
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_value = function(left)
    right_value = function(right)
    for _index in range(iterations):
        if left_value < right_value:
            upper = right
            right = left
            right_value = left_value
            left = upper - ratio * (upper - lower)
            left_value = function(left)
        else:
            lower = left
            left = right
            left_value = right_value
            right = lower + ratio * (upper - lower)
            right_value = function(right)
    return 0.5 * (lower + upper)


def fit_exponential(buckets):
    if not buckets:
        raise ValueError("no buckets selected for fit")

    def best_base_for_decay(decay):
        return golden_minimize(
            lambda base: negative_log_likelihood(buckets, base, decay),
            MIN_PROBABILITY,
            MAX_PROBABILITY,
        )

    def objective(decay):
        base = best_base_for_decay(decay)
        return negative_log_likelihood(buckets, base, decay)

    decay = golden_minimize(objective, 0.0, 2.0)
    base = best_base_for_decay(decay)
    model_nll = negative_log_likelihood(buckets, base, decay)
    filled = sum(bucket.filled for bucket in buckets)
    observations = sum(bucket.observations for bucket in buckets)
    null_probability = min(MAX_PROBABILITY, max(MIN_PROBABILITY, filled / observations))
    null_nll = negative_log_likelihood(buckets, null_probability, 0.0)
    log_likelihood = -model_nll
    null_log_likelihood = -null_nll
    pseudo_r2 = 1.0 - log_likelihood / null_log_likelihood
    brier_total = 0.0
    rmse_total = 0.0
    for bucket in buckets:
        predicted = predicted_probability(bucket, base, decay)
        empirical = bucket.empirical_probability
        brier_total += bucket.observations * (
            empirical * (1.0 - predicted) ** 2 + (1.0 - empirical) * predicted**2
        )
        rmse_total += bucket.observations * (empirical - predicted) ** 2
    likelihood_ratio = 2.0 * (null_nll - model_nll)
    likelihood_ratio_p_value = math.erfc(math.sqrt(max(0.0, likelihood_ratio) / 2.0))
    alpha = math.log(base)
    hessian = numeric_hessian(
        lambda current_alpha, current_decay: negative_log_likelihood_alpha_decay(
            buckets, current_alpha, current_decay
        ),
        alpha,
        decay,
    )
    _alpha_variance, _alpha_decay_covariance, decay_variance = covariance_from_hessian(*hessian)
    decay_standard_error = math.sqrt(decay_variance)
    decay_ci_offset = 1.959963984540054 * decay_standard_error
    return FitResult(
        base_probability=base,
        decay_per_cent=decay,
        negative_log_likelihood=model_nll,
        null_negative_log_likelihood=null_nll,
        mcfadden_pseudo_r2=pseudo_r2,
        weighted_brier_score=brier_total / observations,
        weighted_rmse=math.sqrt(rmse_total / observations),
        likelihood_ratio_statistic=likelihood_ratio,
        likelihood_ratio_degrees_of_freedom=1,
        likelihood_ratio_p_value=likelihood_ratio_p_value,
        decay_standard_error=decay_standard_error,
        decay_ci_95_lower=decay - decay_ci_offset,
        decay_ci_95_upper=decay + decay_ci_offset,
    )


def write_fit_input(path, buckets, fit, min_observations):
    with path.open("w", newline="") as handle:
        fieldnames = [
            "bucket_lower_cents",
            "bucket_upper_cents",
            "mean_distance_cents",
            "quote_observations",
            "filled_quote_segments",
            "empirical_probability",
            "fitted_probability",
            "included",
            "exclude_reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for bucket in buckets:
            included, reason = include_bucket(bucket, min_observations)
            writer.writerow(
                {
                    "bucket_lower_cents": f"{bucket.lower_cents:.12g}",
                    "bucket_upper_cents": f"{bucket.upper_cents:.12g}",
                    "mean_distance_cents": f"{bucket.distance_cents:.12g}",
                    "quote_observations": bucket.observations,
                    "filled_quote_segments": bucket.filled,
                    "empirical_probability": f"{bucket.empirical_probability:.12g}",
                    "fitted_probability": f"{predicted_probability(bucket, fit.base_probability, fit.decay_per_cent):.12g}",
                    "included": "yes" if included else "no",
                    "exclude_reason": reason,
                }
            )


def write_summary(path, buckets, included_buckets, fit, min_observations):
    total_observations = sum(bucket.observations for bucket in buckets)
    total_filled = sum(bucket.filled for bucket in buckets)
    included_observations = sum(bucket.observations for bucket in included_buckets)
    included_filled = sum(bucket.filled for bucket in included_buckets)
    excluded_sparse = sum(1 for bucket in buckets if include_bucket(bucket, min_observations)[1] == "sparse")
    excluded_maintenance = sum(1 for bucket in buckets if include_bucket(bucket, min_observations)[1] == "maintenance")
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["field", "value"])
        writer.writerow(["model", "fill_probability = base_probability * exp(-decay_per_cent * distance_cents)"])
        writer.writerow(["min_fit_observations", min_observations])
        writer.writerow(["total_buckets", len(buckets)])
        writer.writerow(["included_buckets", len(included_buckets)])
        writer.writerow(["excluded_sparse_buckets", excluded_sparse])
        writer.writerow(["excluded_maintenance_buckets", excluded_maintenance])
        writer.writerow(["total_quote_observations", total_observations])
        writer.writerow(["total_filled_quote_segments", total_filled])
        writer.writerow(["included_quote_observations", included_observations])
        writer.writerow(["included_filled_quote_segments", included_filled])
        writer.writerow(["base_probability", f"{fit.base_probability:.12g}"])
        writer.writerow(["decay_per_cent", f"{fit.decay_per_cent:.12g}"])
        writer.writerow(["decay_per_tick_if_one_tick_is_one_cent", f"{fit.decay_per_cent:.12g}"])
        writer.writerow(["negative_log_likelihood", f"{fit.negative_log_likelihood:.12g}"])
        writer.writerow(["null_negative_log_likelihood", f"{fit.null_negative_log_likelihood:.12g}"])
        writer.writerow(["mcfadden_pseudo_r2", f"{fit.mcfadden_pseudo_r2:.12g}"])
        writer.writerow(["weighted_brier_score", f"{fit.weighted_brier_score:.12g}"])
        writer.writerow(["weighted_rmse", f"{fit.weighted_rmse:.12g}"])
        writer.writerow(["likelihood_ratio_statistic", f"{fit.likelihood_ratio_statistic:.12g}"])
        writer.writerow(["likelihood_ratio_degrees_of_freedom", fit.likelihood_ratio_degrees_of_freedom])
        writer.writerow(["likelihood_ratio_p_value", f"{fit.likelihood_ratio_p_value:.12g}"])
        writer.writerow(["decay_standard_error", f"{fit.decay_standard_error:.12g}"])
        writer.writerow(["decay_ci_95_lower", f"{fit.decay_ci_95_lower:.12g}"])
        writer.writerow(["decay_ci_95_upper", f"{fit.decay_ci_95_upper:.12g}"])


def is_whole_cent(value):
    cents = value * 100.0
    return abs(cents - round(cents)) < 1e-8


def is_half_cent(value):
    cents = value * 100.0
    doubled = cents * 2.0
    return abs(doubled - round(doubled)) < 1e-8 and not is_whole_cent(value)


def rounded_cents(value):
    return round(value * 100.0, 6)


def write_parity_diagnostics(path, buckets, segments, fit, min_observations):
    included_lowers = {
        bucket.lower_cents
        for bucket in buckets
        if include_bucket(bucket, min_observations)[0]
    }
    segments_by_bucket = {}
    for segment in segments:
        if segment.bucket_lower_cents in included_lowers:
            segments_by_bucket.setdefault(segment.bucket_lower_cents, []).append(segment)

    with path.open("w", newline="") as handle:
        fieldnames = [
            "bucket_lower_cents",
            "mean_distance_cents",
            "parity",
            "quote_observations",
            "filled_quote_segments",
            "empirical_probability",
            "fitted_probability",
            "probability_residual",
            "whole_cent_price_share",
            "half_cent_mid_share",
            "half_cent_distance_share",
            "top_distance_cents",
            "top_distance_share",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for bucket in buckets:
            if bucket.lower_cents not in included_lowers:
                continue
            bucket_segments = segments_by_bucket.get(bucket.lower_cents, [])
            observations = len(bucket_segments)
            filled = sum(1 for segment in bucket_segments if segment.fill_messages > 0)
            fitted = predicted_probability(bucket, fit.base_probability, fit.decay_per_cent)
            distance_counts = Counter(rounded_cents(segment.distance_cents / 100.0) for segment in bucket_segments)
            top_distance, top_count = distance_counts.most_common(1)[0] if distance_counts else (0.0, 0)
            writer.writerow(
                {
                    "bucket_lower_cents": f"{bucket.lower_cents:.12g}",
                    "mean_distance_cents": f"{bucket.distance_cents:.12g}",
                    "parity": "odd" if int(bucket.lower_cents) % 2 else "even",
                    "quote_observations": observations,
                    "filled_quote_segments": filled,
                    "empirical_probability": f"{bucket.empirical_probability:.12g}",
                    "fitted_probability": f"{fitted:.12g}",
                    "probability_residual": f"{bucket.empirical_probability - fitted:.12g}",
                    "whole_cent_price_share": f"{sum(1 for segment in bucket_segments if is_whole_cent(segment.price)) / observations:.12g}",
                    "half_cent_mid_share": f"{sum(1 for segment in bucket_segments if is_half_cent(segment.mid)) / observations:.12g}",
                    "half_cent_distance_share": f"{sum(1 for segment in bucket_segments if is_half_cent(segment.distance_cents / 100.0)) / observations:.12g}",
                    "top_distance_cents": f"{top_distance:.12g}",
                    "top_distance_share": f"{top_count / observations:.12g}",
                }
            )


def svg_circle(cx, cy, radius, fill, stroke):
    return f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'


def write_svg(path, buckets, fit, min_observations):
    included = [bucket for bucket in buckets if include_bucket(bucket, min_observations)[0]]
    max_distance = max(bucket.distance_cents for bucket in included)
    max_probability = max(
        [bucket.empirical_probability for bucket in included]
        + [predicted_probability(bucket, fit.base_probability, fit.decay_per_cent) for bucket in included]
        + [fit.base_probability]
    )
    width = 900
    height = 560
    left = 70
    right = 30
    top = 30
    bottom = 70
    plot_width = width - left - right
    plot_height = height - top - bottom

    def x_scale(distance):
        return left + plot_width * distance / max_distance

    def y_scale(probability):
        return top + plot_height * (1.0 - probability / max_probability)

    line_points = []
    for step in range(160):
        distance = max_distance * step / 159
        probability = fit.base_probability * math.exp(-fit.decay_per_cent * distance)
        line_points.append(f"{x_scale(distance):.3f},{y_scale(probability):.3f}")

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#222"/>',
        f'<text x="{width / 2}" y="{height - 22}" text-anchor="middle" font-family="Arial" font-size="16">distance from mid in cents</text>',
        f'<text x="18" y="{height / 2}" text-anchor="middle" font-family="Arial" font-size="16" transform="rotate(-90 18 {height / 2})">fill probability</text>',
        f'<text x="{left}" y="24" font-family="Arial" font-size="18">regular session QQQ exponential fit</text>',
        f'<polyline points="{" ".join(line_points)}" fill="none" stroke="#0b5fff" stroke-width="3"/>',
    ]
    for bucket in buckets:
        included_bucket, reason = include_bucket(bucket, min_observations)
        if reason == "maintenance":
            elements.append(svg_circle(x_scale(min(bucket.distance_cents, max_distance)), y_scale(0.0), 4, "#d62728", "#8b0000"))
        elif included_bucket:
            elements.append(svg_circle(x_scale(bucket.distance_cents), y_scale(bucket.empirical_probability), 4, "#111", "#111"))
    elements.extend(
        [
            f'<text x="{left + 12}" y="{top + 28}" font-family="Arial" font-size="14">black points are included buckets</text>',
            f'<text x="{left + 12}" y="{top + 48}" font-family="Arial" font-size="14">red points are maintenance buckets</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(elements) + "\n")


def run(args):
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    buckets = read_buckets(input_dir / "bucket_diagnostics.csv")
    segments = read_segments(input_dir / "quote_segments.csv")
    included_buckets = [bucket for bucket in buckets if include_bucket(bucket, args.min_fit_observations)[0]]
    fit = fit_exponential(included_buckets)
    write_fit_input(output_dir / "fit_input_buckets.csv", buckets, fit, args.min_fit_observations)
    write_summary(output_dir / "fit_summary.csv", buckets, included_buckets, fit, args.min_fit_observations)
    if segments:
        write_parity_diagnostics(output_dir / "parity_diagnostics.csv", buckets, segments, fit, args.min_fit_observations)
    write_svg(output_dir / "fill_probability_fit.svg", buckets, fit, args.min_fit_observations)
    print(f"fit decay per cent {fit.decay_per_cent:.12g}")
    print(f"base probability {fit.base_probability:.12g}")
    print(f"likelihood ratio statistic {fit.likelihood_ratio_statistic:.12g}")
    print(f"likelihood ratio p value {fit.likelihood_ratio_p_value:.12g}")
    return 0


def main():
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
