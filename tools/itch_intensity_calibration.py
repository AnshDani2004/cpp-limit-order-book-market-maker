#!/usr/bin/env python3

import argparse
import csv
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import itch_replay


DEFAULT_RANGE_BYTES = 134_217_728
DEFAULT_SYMBOLS = "QQQ"
DEFAULT_OUTPUT_DIR = "benchmarks/results/stage4b_intensity_measurement"
DEFAULT_BUCKET_WIDTH_CENTS = 1.0
DEFAULT_OUTLIER_DISTANCE_CENTS = 100.0
PRICE_UNITS_PER_CENT = 100
MIN_CLOSED_QUOTE_SEGMENTS = 500
MIN_FILLED_QUOTE_SEGMENTS = 100
MIN_NON_EMPTY_DISTANCE_BUCKETS = 8
MIN_POSITIVE_FILL_BUCKETS = 5


@dataclass
class MidSnapshot:
    best_bid: int | None
    best_ask: int | None
    mid_price_units: float | None
    state: str


@dataclass
class QuoteSegment:
    source_order_ref: int
    source_message_type: str
    open_message_index: int
    symbol: str
    side: str
    price: int
    shares: int
    open_timestamp: int
    best_bid: int
    best_ask: int
    mid_price_units: float
    distance_price_units: float
    bucket_lower_price_units: int
    fill_messages: int = 0
    filled_quantity: int = 0
    close_reason: str = ""
    close_timestamp: int = 0


@dataclass
class CalibrationOrder:
    source_order_ref: int
    symbol: str
    side: str
    remaining: int
    price: int
    segment_index: int | None


@dataclass
class CoverageSummary:
    closed_quote_segments: int
    filled_quote_segments: int
    execution_messages_in_segments: int
    right_censored_quote_segments: int
    non_empty_distance_buckets: int
    positive_fill_buckets: int
    symbol_count: int


@dataclass
class CalibrationResult:
    segments: list[QuoteSegment]
    censored_segments: int
    messages_read: int
    supported_messages: int
    ignored_messages: int
    skipped_one_sided_mid_segments: int
    skipped_crossed_mid_segments: int
    symbols: list[str]
    bucket_width_price_units: int


class CalibrationGateError(RuntimeError):
    pass


class SymbolBook:
    def __init__(self):
        self.bid_sizes = {}
        self.ask_sizes = {}

    def best_bid(self):
        if not self.bid_sizes:
            return None
        return max(self.bid_sizes)

    def best_ask(self):
        if not self.ask_sizes:
            return None
        return min(self.ask_sizes)

    def mid(self):
        return self.mid_snapshot().mid_price_units

    def mid_snapshot(self):
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return MidSnapshot(best_bid=bid, best_ask=ask, mid_price_units=None, state="one_sided")
        if bid >= ask:
            return MidSnapshot(best_bid=bid, best_ask=ask, mid_price_units=None, state="crossed")
        return MidSnapshot(best_bid=bid, best_ask=ask, mid_price_units=(bid + ask) / 2.0, state="valid")

    def add(self, side, price, quantity):
        sizes = self.bid_sizes if side == "buy" else self.ask_sizes
        sizes[price] = sizes.get(price, 0) + quantity

    def remove(self, side, price, quantity):
        sizes = self.bid_sizes if side == "buy" else self.ask_sizes
        next_quantity = sizes.get(price, 0) - quantity
        if next_quantity > 0:
            sizes[price] = next_quantity
        else:
            sizes.pop(price, None)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=itch_replay.DEFAULT_URL)
    parser.add_argument("--range-bytes", type=int, default=DEFAULT_RANGE_BYTES)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--input-gz", default="")
    parser.add_argument("--bucket-width-cents", type=float, default=DEFAULT_BUCKET_WIDTH_CENTS)
    parser.add_argument("--outlier-distance-cents", type=float, default=DEFAULT_OUTLIER_DISTANCE_CENTS)
    parser.add_argument("--allow-thin-measurement", action="store_true")
    return parser.parse_args()


def parse_symbols(value):
    return sorted({symbol.strip().upper() for symbol in value.split(",") if symbol.strip()})


def distance_for_order(side, price, mid):
    if side == "buy":
        return mid - price
    return price - mid


def bucket_lower(distance_price_units, bucket_width_price_units):
    return math.floor(distance_price_units / bucket_width_price_units) * bucket_width_price_units


def time_of_day(timestamp):
    seconds, nanoseconds = divmod(timestamp, 1_000_000_000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{nanoseconds:09d}"


def open_segment(
    segments,
    source_order_ref,
    source_message_type,
    open_message_index,
    symbol,
    side,
    price,
    shares,
    timestamp,
    snapshot,
    bucket_width_price_units,
):
    mid = snapshot.mid_price_units
    distance = distance_for_order(side, price, mid)
    segment = QuoteSegment(
        source_order_ref=source_order_ref,
        source_message_type=source_message_type,
        open_message_index=open_message_index,
        symbol=symbol,
        side=side,
        price=price,
        shares=shares,
        open_timestamp=timestamp,
        best_bid=snapshot.best_bid,
        best_ask=snapshot.best_ask,
        mid_price_units=mid,
        distance_price_units=distance,
        bucket_lower_price_units=bucket_lower(distance, bucket_width_price_units),
    )
    segments.append(segment)
    return len(segments) - 1


def count_mid_skip(snapshot):
    if snapshot.state == "one_sided":
        return 1, 0
    if snapshot.state == "crossed":
        return 0, 1
    return 0, 0


def close_segment(segments, segment_index, timestamp, reason):
    if segment_index is None:
        return
    segment = segments[segment_index]
    if segment.close_reason:
        return
    segment.close_timestamp = timestamp
    segment.close_reason = reason


def record_fill(segments, segment_index, shares):
    if segment_index is None:
        return
    segment = segments[segment_index]
    segment.fill_messages += 1
    segment.filled_quantity += shares


def measure_intensity(messages, symbols, bucket_width_cents):
    selected_symbols = set(symbols)
    bucket_width_price_units = int(round(bucket_width_cents * PRICE_UNITS_PER_CENT))
    if bucket_width_price_units <= 0:
        raise ValueError("bucket width must be positive")

    books = {symbol: SymbolBook() for symbol in selected_symbols}
    active = {}
    segments = []
    messages_read = 0
    supported_messages = 0
    ignored_messages = 0
    skipped_one_sided_mid_segments = 0
    skipped_crossed_mid_segments = 0

    for message in messages:
        if message is None:
            continue
        messages_read += 1

        if message.message_type in {"A", "F"}:
            if message.stock not in selected_symbols:
                ignored_messages += 1
                continue
            supported_messages += 1
            side = itch_replay.side_name(message.side)
            book = books[message.stock]
            snapshot = book.mid_snapshot()
            segment_index = None
            if snapshot.mid_price_units is not None:
                segment_index = open_segment(
                    segments,
                    message.order_ref,
                    message.message_type,
                    messages_read,
                    message.stock,
                    side,
                    message.price,
                    message.shares,
                    message.timestamp,
                    snapshot,
                    bucket_width_price_units,
                )
            else:
                one_sided, crossed = count_mid_skip(snapshot)
                skipped_one_sided_mid_segments += one_sided
                skipped_crossed_mid_segments += crossed
            active[message.order_ref] = CalibrationOrder(
                source_order_ref=message.order_ref,
                symbol=message.stock,
                side=side,
                remaining=message.shares,
                price=message.price,
                segment_index=segment_index,
            )
            book.add(side, message.price, message.shares)
            continue

        active_order = active.get(message.order_ref)
        if active_order is None:
            ignored_messages += 1
            continue

        book = books[active_order.symbol]

        if message.message_type in {"E", "C"}:
            supported_messages += 1
            removed = min(active_order.remaining, message.shares)
            record_fill(segments, active_order.segment_index, removed)
            active_order.remaining -= removed
            book.remove(active_order.side, active_order.price, removed)
            if active_order.remaining <= 0:
                close_segment(segments, active_order.segment_index, message.timestamp, "executed")
                active.pop(message.order_ref, None)
            continue

        if message.message_type == "X":
            supported_messages += 1
            removed = min(active_order.remaining, message.shares)
            active_order.remaining -= removed
            book.remove(active_order.side, active_order.price, removed)
            if active_order.remaining <= 0:
                close_segment(segments, active_order.segment_index, message.timestamp, "cancel")
                active.pop(message.order_ref, None)
            continue

        if message.message_type == "D":
            supported_messages += 1
            book.remove(active_order.side, active_order.price, active_order.remaining)
            close_segment(segments, active_order.segment_index, message.timestamp, "delete")
            active.pop(message.order_ref, None)
            continue

        if message.message_type == "U":
            supported_messages += 1
            book.remove(active_order.side, active_order.price, active_order.remaining)
            close_segment(segments, active_order.segment_index, message.timestamp, "replace")
            active.pop(message.order_ref, None)
            snapshot = book.mid_snapshot()
            segment_index = None
            if snapshot.mid_price_units is not None:
                segment_index = open_segment(
                    segments,
                    message.new_order_ref,
                    message.message_type,
                    messages_read,
                    active_order.symbol,
                    active_order.side,
                    message.price,
                    message.shares,
                    message.timestamp,
                    snapshot,
                    bucket_width_price_units,
                )
            else:
                one_sided, crossed = count_mid_skip(snapshot)
                skipped_one_sided_mid_segments += one_sided
                skipped_crossed_mid_segments += crossed
            active[message.new_order_ref] = CalibrationOrder(
                source_order_ref=message.new_order_ref,
                symbol=active_order.symbol,
                side=active_order.side,
                remaining=message.shares,
                price=message.price,
                segment_index=segment_index,
            )
            book.add(active_order.side, message.price, message.shares)
            continue

        ignored_messages += 1

    closed_segments = [segment for segment in segments if segment.close_reason]
    censored_segments = len(segments) - len(closed_segments)
    return CalibrationResult(
        segments=closed_segments,
        censored_segments=censored_segments,
        messages_read=messages_read,
        supported_messages=supported_messages,
        ignored_messages=ignored_messages,
        skipped_one_sided_mid_segments=skipped_one_sided_mid_segments,
        skipped_crossed_mid_segments=skipped_crossed_mid_segments,
        symbols=symbols,
        bucket_width_price_units=bucket_width_price_units,
    )


def bucket_rows(result):
    buckets = {}
    for segment in result.segments:
        row = buckets.setdefault(
            segment.bucket_lower_price_units,
            {
                "quote_observations": 0,
                "filled_quote_segments": 0,
                "execution_messages": 0,
                "filled_quantity": 0,
                "distance_sum": 0.0,
            },
        )
        row["quote_observations"] += 1
        row["distance_sum"] += segment.distance_price_units
        if segment.fill_messages > 0:
            row["filled_quote_segments"] += 1
            row["execution_messages"] += segment.fill_messages
            row["filled_quantity"] += segment.filled_quantity

    rows = []
    for lower in sorted(buckets):
        row = buckets[lower]
        observations = row["quote_observations"]
        filled = row["filled_quote_segments"]
        rows.append(
            {
                "bucket_lower_cents": lower / PRICE_UNITS_PER_CENT,
                "bucket_upper_cents": (lower + result.bucket_width_price_units) / PRICE_UNITS_PER_CENT,
                "mean_distance_cents": row["distance_sum"] / observations / PRICE_UNITS_PER_CENT,
                "quote_observations": observations,
                "filled_quote_segments": filled,
                "fill_probability": 0.0 if observations == 0 else filled / observations,
                "execution_messages": row["execution_messages"],
                "filled_quantity": row["filled_quantity"],
            }
        )
    return rows


def coverage_summary(result, rows):
    filled_quote_segments = sum(1 for segment in result.segments if segment.fill_messages > 0)
    return CoverageSummary(
        closed_quote_segments=len(result.segments),
        filled_quote_segments=filled_quote_segments,
        execution_messages_in_segments=sum(segment.fill_messages for segment in result.segments),
        right_censored_quote_segments=result.censored_segments,
        non_empty_distance_buckets=len(rows),
        positive_fill_buckets=sum(1 for row in rows if row["filled_quote_segments"] > 0),
        symbol_count=len(result.symbols),
    )


def fit_gate_failures(summary):
    failures = []
    if summary.closed_quote_segments < MIN_CLOSED_QUOTE_SEGMENTS:
        failures.append(
            f"closed_quote_segments {summary.closed_quote_segments} below {MIN_CLOSED_QUOTE_SEGMENTS}"
        )
    if summary.filled_quote_segments < MIN_FILLED_QUOTE_SEGMENTS:
        failures.append(
            f"filled_quote_segments {summary.filled_quote_segments} below {MIN_FILLED_QUOTE_SEGMENTS}"
        )
    if summary.non_empty_distance_buckets < MIN_NON_EMPTY_DISTANCE_BUCKETS:
        failures.append(
            f"non_empty_distance_buckets {summary.non_empty_distance_buckets} below "
            f"{MIN_NON_EMPTY_DISTANCE_BUCKETS}"
        )
    if summary.positive_fill_buckets < MIN_POSITIVE_FILL_BUCKETS:
        failures.append(
            f"positive_fill_buckets {summary.positive_fill_buckets} below {MIN_POSITIVE_FILL_BUCKETS}"
        )
    return failures


def assert_fit_gate(summary):
    failures = fit_gate_failures(summary)
    if failures:
        raise CalibrationGateError("fit coverage gate failed: " + "; ".join(failures))


def write_bucket_rows(path, rows):
    with path.open("w", newline="") as handle:
        fieldnames = [
            "bucket_lower_cents",
            "bucket_upper_cents",
            "mean_distance_cents",
            "quote_observations",
            "filled_quote_segments",
            "fill_probability",
            "execution_messages",
            "filled_quantity",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "bucket_lower_cents": f"{row['bucket_lower_cents']:.12g}",
                    "bucket_upper_cents": f"{row['bucket_upper_cents']:.12g}",
                    "mean_distance_cents": f"{row['mean_distance_cents']:.12g}",
                    "quote_observations": row["quote_observations"],
                    "filled_quote_segments": row["filled_quote_segments"],
                    "fill_probability": f"{row['fill_probability']:.12g}",
                    "execution_messages": row["execution_messages"],
                    "filled_quantity": row["filled_quantity"],
                }
            )


def format_price_units(value):
    return f"{value / 10000:.12g}"


def format_distance_cents(value):
    return f"{value / PRICE_UNITS_PER_CENT:.12g}"


def write_distance_outliers(path, result, threshold_cents):
    threshold_price_units = threshold_cents * PRICE_UNITS_PER_CENT
    with path.open("w", newline="") as handle:
        fieldnames = [
            "source_order_ref",
            "source_message_type",
            "open_message_index",
            "open_timestamp",
            "open_time",
            "side",
            "price",
            "shares",
            "best_bid",
            "best_ask",
            "mid",
            "distance_cents",
            "bucket_lower_cents",
            "fill_messages",
            "filled_quantity",
            "close_reason",
            "close_timestamp",
            "close_time",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for segment in sorted(result.segments, key=lambda item: abs(item.distance_price_units), reverse=True):
            if abs(segment.distance_price_units) < threshold_price_units:
                continue
            writer.writerow(
                {
                    "source_order_ref": segment.source_order_ref,
                    "source_message_type": segment.source_message_type,
                    "open_message_index": segment.open_message_index,
                    "open_timestamp": segment.open_timestamp,
                    "open_time": time_of_day(segment.open_timestamp),
                    "side": segment.side,
                    "price": format_price_units(segment.price),
                    "shares": segment.shares,
                    "best_bid": format_price_units(segment.best_bid),
                    "best_ask": format_price_units(segment.best_ask),
                    "mid": format_price_units(segment.mid_price_units),
                    "distance_cents": format_distance_cents(segment.distance_price_units),
                    "bucket_lower_cents": format_distance_cents(segment.bucket_lower_price_units),
                    "fill_messages": segment.fill_messages,
                    "filled_quantity": segment.filled_quantity,
                    "close_reason": segment.close_reason,
                    "close_timestamp": segment.close_timestamp,
                    "close_time": time_of_day(segment.close_timestamp),
                }
            )


def write_summary(path, args, result, summary, rows, gate_failures):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["field", "value"])
        writer.writerow(["source_url", args.url])
        writer.writerow(["symbols", ",".join(result.symbols)])
        writer.writerow(["compressed_prefix_bytes", args.range_bytes])
        writer.writerow(["bucket_width_cents", f"{args.bucket_width_cents:.12g}"])
        writer.writerow(["messages_read", result.messages_read])
        writer.writerow(["supported_symbol_messages", result.supported_messages])
        writer.writerow(["ignored_messages", result.ignored_messages])
        writer.writerow(["skipped_one_sided_mid_segments", result.skipped_one_sided_mid_segments])
        writer.writerow(["skipped_crossed_mid_segments", result.skipped_crossed_mid_segments])
        writer.writerow(["closed_quote_segments", summary.closed_quote_segments])
        writer.writerow(["filled_quote_segments", summary.filled_quote_segments])
        writer.writerow(["execution_messages_in_segments", summary.execution_messages_in_segments])
        writer.writerow(["right_censored_quote_segments", summary.right_censored_quote_segments])
        writer.writerow(["non_empty_distance_buckets", summary.non_empty_distance_buckets])
        writer.writerow(["positive_fill_buckets", summary.positive_fill_buckets])
        writer.writerow(["min_closed_quote_segments", MIN_CLOSED_QUOTE_SEGMENTS])
        writer.writerow(["min_filled_quote_segments", MIN_FILLED_QUOTE_SEGMENTS])
        writer.writerow(["min_non_empty_distance_buckets", MIN_NON_EMPTY_DISTANCE_BUCKETS])
        writer.writerow(["min_positive_fill_buckets", MIN_POSITIVE_FILL_BUCKETS])
        writer.writerow(["fit_gate_passed", "yes" if not gate_failures else "no"])
        writer.writerow(["fit_gate_message", "passed" if not gate_failures else "; ".join(gate_failures)])
        if rows:
            best_row = max(rows, key=lambda row: row["quote_observations"])
            writer.writerow(["largest_bucket_lower_cents", f"{best_row['bucket_lower_cents']:.12g}"])
            writer.writerow(["largest_bucket_quote_observations", best_row["quote_observations"]])


def run(args):
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    compressed = itch_replay.read_compressed_input(args)
    decompressed = itch_replay.decompress_prefix(compressed)
    messages = (itch_replay.parse_message(payload) for payload in itch_replay.iter_framed_messages(decompressed))
    symbols = parse_symbols(args.symbols)
    result = measure_intensity(messages, symbols, args.bucket_width_cents)
    rows = bucket_rows(result)
    summary = coverage_summary(result, rows)
    gate_failures = fit_gate_failures(summary)

    write_bucket_rows(output_dir / "fill_probability_by_distance.csv", rows)
    write_distance_outliers(output_dir / "distance_outliers.csv", result, args.outlier_distance_cents)
    write_summary(output_dir / "summary.csv", args, result, summary, rows, gate_failures)

    if gate_failures:
        message = "fit coverage gate failed: " + "; ".join(gate_failures)
        print(message, file=sys.stderr)
        if not args.allow_thin_measurement:
            return 2
    else:
        print("fit coverage gate passed")
    return 0


def main():
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
