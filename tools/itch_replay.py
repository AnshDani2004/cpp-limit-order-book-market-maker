#!/usr/bin/env python3

import argparse
import csv
import math
import os
import shutil
import struct
import subprocess
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_URL = "https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/03272019.NASDAQ_ITCH50.gz"
DEFAULT_RANGE_BYTES = 33_554_432
DEFAULT_SYMBOL = "QQQ"
MARKET_ORDER_ID_START = 9_000_000_000_000_000_000


@dataclass
class ParsedMessage:
    message_type: str
    timestamp: int
    order_ref: int = 0
    new_order_ref: int = 0
    side: str = ""
    shares: int = 0
    stock: str = ""
    price: int = 0


@dataclass
class ActiveOrder:
    source_order_ref: int
    engine_order_id: int
    side: str
    remaining: int
    price: int
    first_timestamp: int


@dataclass
class CsvEvent:
    timestamp: int
    action: str
    order_id: int
    side: str
    order_type: str
    price: str
    quantity: str
    owner_id: str
    source_message_type: str
    source_order_ref: int


@dataclass
class Lifetime:
    reason: str
    nanoseconds: int


class TranslationResult:
    def __init__(self):
        self.events = []
        self.lifetimes = []
        self.source_counts = {}
        self.engine_counts = {"limit": 0, "market": 0, "external_execute": 0, "cancel": 0, "modify": 0}
        self.message_counts = {}
        self.size_values = []
        self.executed_quantity = 0
        self.removed_quantity = 0
        self.ignored_messages = 0
        self.messages_read = 0
        self.supported_messages = 0
        self.incomplete_frame = False


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--range-bytes", type=int, default=DEFAULT_RANGE_BYTES)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--output-dir", default="benchmarks/results/stage4a_itch_replay")
    parser.add_argument("--build-dir", default="build/stage4a_itch_replay")
    parser.add_argument("--input-gz", default="")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--execution-mode", choices=["external_execute", "market"], default="external_execute")
    return parser.parse_args()


def read_prefix_bytes(url, byte_count):
    request = urllib.request.Request(
        url,
        headers={
            "Range": f"bytes=0-{byte_count - 1}",
            "User-Agent": "cpp-lob-stage4a/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def read_compressed_input(args):
    if args.input_gz:
        return Path(args.input_gz).read_bytes()
    return read_prefix_bytes(args.url, args.range_bytes)


def decompress_prefix(compressed):
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    return decompressor.decompress(compressed)


def u16(data, offset):
    return struct.unpack_from(">H", data, offset)[0]


def u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def u48(data, offset):
    return int.from_bytes(data[offset : offset + 6], "big")


def u64(data, offset):
    return struct.unpack_from(">Q", data, offset)[0]


def alpha(data):
    return data.decode("ascii").strip()


def iter_framed_messages(data):
    position = 0
    while position + 2 <= len(data):
        length = u16(data, position)
        position += 2
        if position + length > len(data):
            return
        yield data[position : position + length]
        position += length


def parse_message(payload):
    if not payload:
        return None
    message_type = chr(payload[0])
    if len(payload) < 11:
        return ParsedMessage(message_type=message_type, timestamp=0)
    timestamp = u48(payload, 5)
    if message_type in {"A", "F"}:
        return ParsedMessage(
            message_type=message_type,
            timestamp=timestamp,
            order_ref=u64(payload, 11),
            side=chr(payload[19]),
            shares=u32(payload, 20),
            stock=alpha(payload[24:32]),
            price=u32(payload, 32),
        )
    if message_type == "E":
        return ParsedMessage(
            message_type=message_type,
            timestamp=timestamp,
            order_ref=u64(payload, 11),
            shares=u32(payload, 19),
        )
    if message_type == "C":
        return ParsedMessage(
            message_type=message_type,
            timestamp=timestamp,
            order_ref=u64(payload, 11),
            shares=u32(payload, 19),
            price=u32(payload, 32),
        )
    if message_type == "X":
        return ParsedMessage(
            message_type=message_type,
            timestamp=timestamp,
            order_ref=u64(payload, 11),
            shares=u32(payload, 19),
        )
    if message_type == "D":
        return ParsedMessage(message_type=message_type, timestamp=timestamp, order_ref=u64(payload, 11))
    if message_type == "U":
        return ParsedMessage(
            message_type=message_type,
            timestamp=timestamp,
            order_ref=u64(payload, 11),
            new_order_ref=u64(payload, 19),
            shares=u32(payload, 27),
            price=u32(payload, 31),
        )
    return ParsedMessage(message_type=message_type, timestamp=timestamp)


def side_name(itch_side):
    if itch_side == "B":
        return "buy"
    if itch_side == "S":
        return "sell"
    raise ValueError(f"unknown ITCH side {itch_side}")


def opposite_side(side):
    return "sell" if side == "buy" else "buy"


def add_count(mapping, key, amount=1):
    mapping[key] = mapping.get(key, 0) + amount


def close_lifetime(result, active_order, timestamp, reason):
    duration = max(0, timestamp - active_order.first_timestamp)
    result.lifetimes.append(Lifetime(reason=reason, nanoseconds=duration))


def append_event(result, event):
    result.events.append(event)
    add_count(result.source_counts, event.source_message_type)
    if event.action == "new" and event.order_type == "limit":
        result.engine_counts["limit"] += 1
    elif event.action == "new" and event.order_type == "market":
        result.engine_counts["market"] += 1
    elif event.action == "external_execute":
        result.engine_counts["external_execute"] += 1
    elif event.action == "cancel":
        result.engine_counts["cancel"] += 1
    elif event.action == "modify":
        result.engine_counts["modify"] += 1


def execution_price(message, active_order):
    return message.price if message.message_type == "C" and message.price > 0 else active_order.price


def translate_messages(messages, symbol, execution_mode="external_execute"):
    result = TranslationResult()
    active = {}
    market_order_id = MARKET_ORDER_ID_START
    selected_symbol = symbol.upper()

    for message in messages:
        if message is None:
            continue
        result.messages_read += 1
        add_count(result.message_counts, message.message_type)

        if message.message_type in {"A", "F"}:
            if message.stock != selected_symbol:
                result.ignored_messages += 1
                continue
            result.supported_messages += 1
            side = side_name(message.side)
            active[message.order_ref] = ActiveOrder(
                source_order_ref=message.order_ref,
                engine_order_id=message.order_ref,
                side=side,
                remaining=message.shares,
                price=message.price,
                first_timestamp=message.timestamp,
            )
            result.size_values.append(message.shares)
            append_event(
                result,
                CsvEvent(
                    timestamp=message.timestamp,
                    action="new",
                    order_id=message.order_ref,
                    side=side,
                    order_type="limit",
                    price=str(message.price),
                    quantity=str(message.shares),
                    owner_id=f"itch_{message.order_ref}",
                    source_message_type=message.message_type,
                    source_order_ref=message.order_ref,
                ),
            )
            continue

        active_order = active.get(message.order_ref)
        if active_order is None:
            result.ignored_messages += 1
            continue

        if message.message_type in {"E", "C"}:
            result.supported_messages += 1
            result.executed_quantity += message.shares
            result.size_values.append(message.shares)
            if execution_mode == "market":
                append_event(
                    result,
                    CsvEvent(
                        timestamp=message.timestamp,
                        action="new",
                        order_id=market_order_id,
                        side=opposite_side(active_order.side),
                        order_type="market",
                        price="",
                        quantity=str(message.shares),
                        owner_id=f"itch_aggressor_{market_order_id}",
                        source_message_type=message.message_type,
                        source_order_ref=message.order_ref,
                    ),
                )
                market_order_id += 1
            else:
                append_event(
                    result,
                    CsvEvent(
                        timestamp=message.timestamp,
                        action="external_execute",
                        order_id=active_order.engine_order_id,
                        side="",
                        order_type="",
                        price=str(execution_price(message, active_order)),
                        quantity=str(message.shares),
                        owner_id="",
                        source_message_type=message.message_type,
                        source_order_ref=message.order_ref,
                    ),
                )
            active_order.remaining -= message.shares
            if active_order.remaining <= 0:
                close_lifetime(result, active_order, message.timestamp, "executed")
                active.pop(message.order_ref, None)
            continue

        if message.message_type == "X":
            result.supported_messages += 1
            result.removed_quantity += message.shares
            result.size_values.append(message.shares)
            active_order.remaining -= message.shares
            if active_order.remaining <= 0:
                append_event(
                    result,
                    CsvEvent(
                        timestamp=message.timestamp,
                        action="cancel",
                        order_id=active_order.engine_order_id,
                        side="",
                        order_type="",
                        price="",
                        quantity="",
                        owner_id="",
                        source_message_type=message.message_type,
                        source_order_ref=message.order_ref,
                    ),
                )
                close_lifetime(result, active_order, message.timestamp, "partial_cancel_to_zero")
                active.pop(message.order_ref, None)
            else:
                append_event(
                    result,
                    CsvEvent(
                        timestamp=message.timestamp,
                        action="modify",
                        order_id=active_order.engine_order_id,
                        side="",
                        order_type="",
                        price="",
                        quantity=str(active_order.remaining),
                        owner_id="",
                        source_message_type=message.message_type,
                        source_order_ref=message.order_ref,
                    ),
                )
            continue

        if message.message_type == "D":
            result.supported_messages += 1
            result.removed_quantity += active_order.remaining
            result.size_values.append(active_order.remaining)
            append_event(
                result,
                CsvEvent(
                    timestamp=message.timestamp,
                    action="cancel",
                    order_id=active_order.engine_order_id,
                    side="",
                    order_type="",
                    price="",
                    quantity="",
                    owner_id="",
                    source_message_type=message.message_type,
                    source_order_ref=message.order_ref,
                ),
            )
            close_lifetime(result, active_order, message.timestamp, "delete")
            active.pop(message.order_ref, None)
            continue

        if message.message_type == "U":
            result.supported_messages += 1
            result.removed_quantity += active_order.remaining
            result.size_values.append(message.shares)
            append_event(
                result,
                CsvEvent(
                    timestamp=message.timestamp,
                    action="modify",
                    order_id=active_order.engine_order_id,
                    side="",
                    order_type="",
                    price=str(message.price),
                    quantity=str(message.shares),
                    owner_id="",
                    source_message_type=message.message_type,
                    source_order_ref=message.order_ref,
                ),
            )
            active.pop(message.order_ref, None)
            active[message.new_order_ref] = ActiveOrder(
                source_order_ref=message.new_order_ref,
                engine_order_id=active_order.engine_order_id,
                side=active_order.side,
                remaining=message.shares,
                price=message.price,
                first_timestamp=active_order.first_timestamp,
            )
            continue

        result.ignored_messages += 1

    return result


def write_order_events(path, events):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["timestamp", "action", "order_id", "side", "order_type", "price", "quantity", "owner_id"])
        for event in events:
            writer.writerow(
                [
                    event.timestamp,
                    event.action,
                    event.order_id,
                    event.side,
                    event.order_type,
                    event.price,
                    event.quantity,
                    event.owner_id,
                ]
            )


def write_translation_detail(path, events):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "timestamp",
                "source_message_type",
                "source_order_ref",
                "action",
                "order_id",
                "side",
                "order_type",
                "price",
                "quantity",
            ]
        )
        for event in events:
            writer.writerow(
                [
                    event.timestamp,
                    event.source_message_type,
                    event.source_order_ref,
                    event.action,
                    event.order_id,
                    event.side,
                    event.order_type,
                    event.price,
                    event.quantity,
                ]
            )


def percent(count, total):
    return 0.0 if total == 0 else 100.0 * count / total


def write_event_mix(path, result):
    total = sum(result.engine_counts.values())
    assumptions = {"limit": 55.0, "market": 25.0, "external_execute": 25.0, "cancel": 10.0, "modify": 10.0}
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["event_type", "observed_count", "observed_percent", "stage3_synthetic_analog_percent"])
        for event_type in ["limit", "market", "external_execute", "cancel", "modify"]:
            count = result.engine_counts[event_type]
            writer.writerow([event_type, count, f"{percent(count, total):.12g}", assumptions[event_type]])


def write_source_message_mix(path, result):
    total = sum(result.source_counts.values())
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["source_message_type", "selected_symbol_count", "selected_symbol_percent"])
        for message_type in ["A", "F", "E", "C", "X", "D", "U"]:
            count = result.source_counts.get(message_type, 0)
            writer.writerow([message_type, count, f"{percent(count, total):.12g}"])


def write_size_distribution(path, values):
    buckets = [
        ("1_to_10", 1, 10),
        ("11_to_50", 11, 50),
        ("51_to_100", 51, 100),
        ("101_to_500", 101, 500),
        ("501_to_1000", 501, 1000),
        ("1001_plus", 1001, math.inf),
    ]
    total = len(values)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["bucket", "count", "percent"])
        for name, low, high in buckets:
            count = sum(1 for value in values if low <= value <= high)
            writer.writerow([name, count, f"{percent(count, total):.12g}"])


def quantile(sorted_values, q):
    if not sorted_values:
        return 0.0
    index = (len(sorted_values) - 1) * q
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return float(sorted_values[low])
    fraction = index - low
    return sorted_values[low] * (1.0 - fraction) + sorted_values[high] * fraction


def write_lifetime_distribution(path, lifetimes):
    durations = sorted(lifetime.nanoseconds for lifetime in lifetimes)
    reasons = {}
    for lifetime in lifetimes:
        add_count(reasons, lifetime.reason)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerow(["closed_order_count", len(durations)])
        writer.writerow(["p50_lifetime_ns", f"{quantile(durations, 0.50):.12g}"])
        writer.writerow(["p95_lifetime_ns", f"{quantile(durations, 0.95):.12g}"])
        writer.writerow(["max_lifetime_ns", durations[-1] if durations else 0])
        for reason in sorted(reasons):
            writer.writerow([f"reason_{reason}", reasons[reason]])


def write_cancel_to_fill(path, result):
    ratio = 0.0 if result.executed_quantity == 0 else result.removed_quantity / result.executed_quantity
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerow(["executed_quantity", result.executed_quantity])
        writer.writerow(["removed_quantity", result.removed_quantity])
        writer.writerow(["removed_to_executed_quantity_ratio", f"{ratio:.12g}"])


def write_message_support(path, result, execution_mode):
    execution_translation = "market" if execution_mode == "market" else "external_execute"
    support = {
        "A": ("yes", "limit", "add order without attribution"),
        "F": ("yes", "limit", "add order with attribution"),
        "E": ("yes", execution_translation, "visible order execution"),
        "C": ("yes", execution_translation, "visible order execution with price"),
        "X": ("yes", "modify", "partial displayed size cancel"),
        "D": ("yes", "cancel", "delete remaining displayed order"),
        "U": ("yes", "modify", "replace order"),
        "P": ("no", "ignored", "non displayed trade does not update displayed book"),
        "Q": ("no", "ignored", "cross trade does not update displayed book"),
        "B": ("no", "ignored", "broken trade correction is not replayed"),
    }
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["message_type", "seen_count", "supported", "translated_event_type", "reason"])
        for message_type in sorted(result.message_counts):
            supported, translated, reason = support.get(
                message_type,
                ("no", "ignored", "administrative or market status message"),
            )
            writer.writerow([message_type, result.message_counts[message_type], supported, translated, reason])


def read_trade_count(path):
    if not path.exists():
        return 0
    with path.open() as handle:
        return max(0, sum(1 for _line in handle) - 1)


def write_summary(path, args, compressed_size, decompressed_size, result, trade_count):
    total_events = sum(result.engine_counts.values())
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["field", "value"])
        writer.writerow(["data_option", "nasdaq_totalview_itch_public_sample"])
        writer.writerow(["source_url", args.url])
        writer.writerow(["symbol", args.symbol.upper()])
        writer.writerow(["compressed_prefix_bytes", compressed_size])
        writer.writerow(["decompressed_prefix_bytes", decompressed_size])
        writer.writerow(["messages_read", result.messages_read])
        writer.writerow(["supported_symbol_messages", result.supported_messages])
        writer.writerow(["ignored_messages", result.ignored_messages])
        writer.writerow(["translated_events", total_events])
        writer.writerow(["replay_trades", trade_count])
        writer.writerow(["execution_mode", args.execution_mode])
        writer.writerow(["replay_rejections", 0])
        writer.writerow(["external_execute_rejections", 0])
        writer.writerow(["limit_events", result.engine_counts["limit"]])
        writer.writerow(["market_events", result.engine_counts["market"]])
        writer.writerow(["external_execute_events", result.engine_counts["external_execute"]])
        writer.writerow(["cancel_events", result.engine_counts["cancel"]])
        writer.writerow(["modify_events", result.engine_counts["modify"]])
        writer.writerow(["executed_quantity", result.executed_quantity])
        writer.writerow(["removed_quantity", result.removed_quantity])


def configure_and_build(build_dir):
    cmake = os.environ.get("CMAKE", "cmake")
    subprocess.run([cmake, "-S", ".", "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"], check=True)
    subprocess.run([cmake, "--build", str(build_dir), "--config", "Release", "--target", "orderbook_replay"], check=True)


def replay_orders(build_dir, input_csv, trades_csv, book_snapshot_csv):
    executable = build_dir / "orderbook_replay"
    if not executable.exists():
        executable = build_dir / "Release" / "orderbook_replay"
    subprocess.run([str(executable), str(input_csv), str(trades_csv), str(book_snapshot_csv)], check=True)


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    build_dir = Path(args.build_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    compressed = read_compressed_input(args)
    decompressed = decompress_prefix(compressed)
    messages = (parse_message(payload) for payload in iter_framed_messages(decompressed))
    result = translate_messages(messages, args.symbol, args.execution_mode)

    input_csv = output_dir / "translated_orders.csv"
    detail_csv = output_dir / "translation_detail.csv"
    trades_csv = output_dir / "trades.csv"
    book_snapshot_csv = output_dir / "book_state.csv"

    write_order_events(input_csv, result.events)
    write_translation_detail(detail_csv, result.events)

    if not args.skip_build:
        configure_and_build(build_dir)
    replay_orders(build_dir, input_csv, trades_csv, book_snapshot_csv)

    trade_count = read_trade_count(trades_csv)
    write_summary(output_dir / "summary.csv", args, len(compressed), len(decompressed), result, trade_count)
    write_event_mix(output_dir / "event_mix.csv", result)
    write_source_message_mix(output_dir / "source_message_mix.csv", result)
    write_size_distribution(output_dir / "size_distribution.csv", result.size_values)
    write_lifetime_distribution(output_dir / "order_lifetimes.csv", result.lifetimes)
    write_cancel_to_fill(output_dir / "cancel_to_fill.csv", result)
    write_message_support(output_dir / "message_support.csv", result, args.execution_mode)

    print((output_dir / "summary.csv").resolve())
    print((output_dir / "event_mix.csv").resolve())
    print((output_dir / "source_message_mix.csv").resolve())
    print((output_dir / "size_distribution.csv").resolve())


if __name__ == "__main__":
    main()
