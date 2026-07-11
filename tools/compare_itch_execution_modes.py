#!/usr/bin/env python3

import argparse
import csv
import shutil
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-dir", required=True)
    parser.add_argument("--external-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def read_rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def metric_rows(path):
    rows = read_rows(path)
    return {row.get("field") or row.get("metric"): row["value"] for row in rows}


def trade_quantity(rows):
    return sum(int(row["quantity"]) for row in rows)


def order_id_values(rows):
    return [int(row["order_id"]) for row in rows]


def unknown_aggressor_rows(rows):
    return sum(1 for row in rows if row["taker_order_id"] == "0")


def write_summary(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(rows)


def write_changed_trades(path, market_trades, external_trades):
    with path.open("w", newline="") as handle:
        fieldnames = [
            "row_index",
            "market_timestamp",
            "external_timestamp",
            "market_price",
            "external_price",
            "market_quantity",
            "external_quantity",
            "market_buy_order_id",
            "external_buy_order_id",
            "market_sell_order_id",
            "external_sell_order_id",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for index, (market_row, external_row) in enumerate(zip(market_trades, external_trades), start=1):
            if market_row == external_row:
                continue
            writer.writerow(
                {
                    "row_index": index,
                    "market_timestamp": market_row["timestamp"],
                    "external_timestamp": external_row["timestamp"],
                    "market_price": market_row["price"],
                    "external_price": external_row["price"],
                    "market_quantity": market_row["quantity"],
                    "external_quantity": external_row["quantity"],
                    "market_buy_order_id": market_row["buy_order_id"],
                    "external_buy_order_id": external_row["buy_order_id"],
                    "market_sell_order_id": market_row["sell_order_id"],
                    "external_sell_order_id": external_row["sell_order_id"],
                }
            )


def main():
    args = parse_args()
    market_dir = Path(args.market_dir)
    external_dir = Path(args.external_dir)
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    market_summary = metric_rows(market_dir / "summary.csv")
    external_summary = metric_rows(external_dir / "summary.csv")
    market_trades = read_rows(market_dir / "trades.csv")
    external_trades = read_rows(external_dir / "trades.csv")
    market_book = read_rows(market_dir / "book_state.csv")
    external_book = read_rows(external_dir / "book_state.csv")
    market_orders = read_rows(market_dir / "translated_orders.csv")
    external_orders = read_rows(external_dir / "translated_orders.csv")
    market_order_ids = order_id_values(market_orders)
    external_order_ids = order_id_values(external_orders)

    pair_count = min(len(market_trades), len(external_trades))
    market_quantity = trade_quantity(market_trades)
    external_quantity = trade_quantity(external_trades)
    changed_price_or_quantity = sum(
        1
        for market_row, external_row in zip(market_trades, external_trades)
        if market_row["price"] != external_row["price"] or market_row["quantity"] != external_row["quantity"]
    )
    changed_full_trade_rows = sum(
        1 for market_row, external_row in zip(market_trades, external_trades) if market_row != external_row
    )

    rows = [
        ("market_replay_trades", market_summary["replay_trades"]),
        ("external_replay_trades", external_summary["replay_trades"]),
        ("market_trade_quantity", market_quantity),
        ("external_trade_quantity", external_quantity),
        ("trade_count_match", str(len(market_trades) == len(external_trades)).lower()),
        ("trade_quantity_match", str(market_quantity == external_quantity).lower()),
        ("paired_trade_rows_compared", pair_count),
        ("changed_price_or_quantity_rows", changed_price_or_quantity),
        ("changed_full_trade_rows", changed_full_trade_rows),
        ("market_book_rows", len(market_book)),
        ("external_book_rows", len(external_book)),
        ("book_state_match", str(market_book == external_book).lower()),
        ("market_translated_zero_order_id_rows", sum(1 for value in market_order_ids if value == 0)),
        ("external_translated_zero_order_id_rows", sum(1 for value in external_order_ids if value == 0)),
        ("market_min_translated_order_id", min(market_order_ids) if market_order_ids else 0),
        ("external_min_translated_order_id", min(external_order_ids) if external_order_ids else 0),
        ("external_unknown_aggressor_trade_rows", unknown_aggressor_rows(external_trades)),
    ]
    write_summary(output_dir / "execution_mode_comparison.csv", rows)
    write_changed_trades(output_dir / "changed_trade_rows.csv", market_trades, external_trades)

    print((output_dir / "execution_mode_comparison.csv").resolve())
    print((output_dir / "changed_trade_rows.csv").resolve())


if __name__ == "__main__":
    main()
