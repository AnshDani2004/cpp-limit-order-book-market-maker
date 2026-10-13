#!/usr/bin/env bash
# Rebuild the Stage 4A / 5A order-level ITCH files that are not stored in this repository.
#
# The repository keeps only results derived from the Nasdaq ITCH sample (aggregate CSVs, docs and the
# Stage 5B calibrated-flow outputs). The order-level files (one row per ITCH message, trade or resting
# order: translated_orders.csv, translation_detail.csv, trades.csv, book_state.csv) are regenerated
# from Nasdaq's public sample file with this script:
#
#   1. download the first 33,554,432 bytes of
#      https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/03272019.NASDAQ_ITCH50.gz (HTTP Range request) into
#      data/itch/ (git-ignored) and check its SHA-256;
#   2. run tools/itch_replay.py on it in both execution modes, in a temporary directory;
#   3. copy the four order-level files into benchmarks/results/stage4a_itch_replay and
#      benchmarks/results/stage5a_itch_market_mode and check them against
#      benchmarks/results/itch_order_level_files.sha256.
#
# The committed aggregate files in those directories are not touched.
# Usage: tools/fetch_itch_sample.sh            (BUILD_DIR=... to reuse an existing orderbook_replay build;
#                                              without it, itch_replay.py builds with CMAKE or cmake)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL="https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/03272019.NASDAQ_ITCH50.gz"
BYTES=33554432
PREFIX="data/itch/03272019.NASDAQ_ITCH50.prefix${BYTES}.gz"
PREFIX_SHA256="1ab9d3a3f1be147c6eacb90ab04d220cd53a4a8679c7fc0b142445166ad5be35"
FILES="translated_orders.csv translation_detail.csv trades.csv book_state.csv"

mkdir -p data/itch
if [ ! -f "$PREFIX" ]; then
  echo "downloading the first $BYTES bytes of the Nasdaq ITCH sample"
  curl -fsS -r "0-$((BYTES - 1))" -A "cpp-lob-stage4a/1.0" -o "$PREFIX.part" "$URL"
  mv "$PREFIX.part" "$PREFIX"
fi
got="$(shasum -a 256 "$PREFIX" | awk '{print $1}')"
if [ "$got" != "$PREFIX_SHA256" ]; then
  echo "SHA-256 mismatch for $PREFIX: got $got, expected $PREFIX_SHA256" >&2
  exit 1
fi
echo "sample prefix OK ($PREFIX_SHA256)"

if [ -n "${BUILD_DIR:-}" ]; then
  build_args=(--build-dir "$BUILD_DIR" --skip-build)
else
  build_args=(--build-dir build/stage4a_itch_replay)
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
python3 tools/itch_replay.py --symbol QQQ --input-gz "$PREFIX" --output-dir "$tmp/stage4a" "${build_args[@]}" > /dev/null
python3 tools/itch_replay.py --symbol QQQ --input-gz "$PREFIX" --execution-mode market --output-dir "$tmp/stage5a" "${build_args[@]}" > /dev/null
for f in $FILES; do
  cp "$tmp/stage4a/$f" "benchmarks/results/stage4a_itch_replay/$f"
  cp "$tmp/stage5a/$f" "benchmarks/results/stage5a_itch_market_mode/$f"
done
shasum -a 256 -c benchmarks/results/itch_order_level_files.sha256
