#!/usr/bin/env python3

import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "itch_replay.py"
SPEC = importlib.util.spec_from_file_location("itch_replay", MODULE_PATH)
itch_replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(itch_replay)


def u48(value):
    return value.to_bytes(6, "big")


def frame(payload):
    return struct.pack(">H", len(payload)) + payload


def add_message(order_ref, timestamp, side, shares, stock, price):
    return (
        b"A"
        + struct.pack(">H", 1)
        + struct.pack(">H", 2)
        + u48(timestamp)
        + struct.pack(">Q", order_ref)
        + side.encode("ascii")
        + struct.pack(">I", shares)
        + stock.encode("ascii").ljust(8, b" ")
        + struct.pack(">I", price)
    )


def execute_message(order_ref, timestamp, shares):
    return (
        b"E"
        + struct.pack(">H", 1)
        + struct.pack(">H", 2)
        + u48(timestamp)
        + struct.pack(">Q", order_ref)
        + struct.pack(">I", shares)
        + struct.pack(">Q", 999)
    )


def cancel_message(order_ref, timestamp, shares):
    return (
        b"X"
        + struct.pack(">H", 1)
        + struct.pack(">H", 2)
        + u48(timestamp)
        + struct.pack(">Q", order_ref)
        + struct.pack(">I", shares)
    )


def delete_message(order_ref, timestamp):
    return b"D" + struct.pack(">H", 1) + struct.pack(">H", 2) + u48(timestamp) + struct.pack(">Q", order_ref)


def replace_message(old_ref, new_ref, timestamp, shares, price):
    return (
        b"U"
        + struct.pack(">H", 1)
        + struct.pack(">H", 2)
        + u48(timestamp)
        + struct.pack(">Q", old_ref)
        + struct.pack(">Q", new_ref)
        + struct.pack(">I", shares)
        + struct.pack(">I", price)
    )


class ItchReplayTests(unittest.TestCase):
    def test_parser_reads_framed_messages(self):
        data = frame(add_message(100, 10, "B", 50, "TEST", 12345)) + frame(delete_message(100, 20))

        payloads = list(itch_replay.iter_framed_messages(data))
        parsed = [itch_replay.parse_message(payload) for payload in payloads]

        self.assertEqual(["A", "D"], [message.message_type for message in parsed])
        self.assertEqual(100, parsed[0].order_ref)
        self.assertEqual("TEST", parsed[0].stock)
        self.assertEqual(50, parsed[0].shares)
        self.assertEqual(12345, parsed[0].price)

    def test_translation_maps_supported_messages_to_engine_events(self):
        payloads = [
            add_message(100, 10, "B", 100, "TEST", 12345),
            execute_message(100, 20, 40),
            cancel_message(100, 30, 10),
            replace_message(100, 200, 40, 80, 12300),
            delete_message(200, 50),
        ]
        messages = [itch_replay.parse_message(payload) for payload in payloads]

        result = itch_replay.translate_messages(messages, "TEST")

        self.assertEqual(["new", "new", "modify", "modify", "cancel"], [event.action for event in result.events])
        self.assertEqual(["limit", "market", "", "", ""], [event.order_type for event in result.events])
        self.assertEqual(["buy", "sell", "", "", ""], [event.side for event in result.events])
        self.assertEqual(["100", "40", "50", "80", ""], [event.quantity for event in result.events])
        self.assertEqual("12300", result.events[3].price)
        self.assertEqual(100, result.events[4].order_id)
        self.assertEqual({"limit": 1, "market": 1, "cancel": 1, "modify": 2}, result.engine_counts)
        self.assertEqual(40, result.executed_quantity)
        self.assertEqual(140, result.removed_quantity)
        self.assertEqual(1, len(result.lifetimes))
        self.assertEqual("delete", result.lifetimes[0].reason)
        self.assertEqual(40, result.lifetimes[0].nanoseconds)

    def test_translation_filters_other_symbols(self):
        messages = [
            itch_replay.parse_message(add_message(100, 10, "S", 100, "SKIP", 12345)),
            itch_replay.parse_message(add_message(200, 20, "S", 25, "TEST", 12355)),
        ]

        result = itch_replay.translate_messages(messages, "TEST")

        self.assertEqual(1, len(result.events))
        self.assertEqual(1, result.ignored_messages)
        self.assertEqual(200, result.events[0].order_id)


if __name__ == "__main__":
    unittest.main()
