#!/usr/bin/env bash
# Build everything for Extension 3(a) with one compiler and one flag set (PREREG.md section 4).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
B="$HERE/build"
CXX="${CXX:-clang++}"
FLAGS=(-O3 -DNDEBUG -std=c++20 -arch arm64 -Wall -Wextra)
mkdir -p "$B/obj"
"$HERE/fetch_liquibook.sh"
LB="$HERE/third_party/liquibook/src"
# This repo's engine as a static library, as CMakeLists.txt builds lob_core (same sources, same flags).
OBJS=()
for s in flat_order_book matching_engine order_book price_level; do
  "$CXX" "${FLAGS[@]}" -I"$ROOT/include" -c "$ROOT/src/$s.cpp" -o "$B/obj/$s.o"
  OBJS+=("$B/obj/$s.o")
done
rm -f "$B/liblob_engine.a"
ar rcs "$B/liblob_engine.a" "${OBJS[@]}"
"$CXX" "${FLAGS[@]}" -I"$ROOT/include" "$HERE/gen_stream.cpp" "$B/liblob_engine.a" -o "$B/gen_stream"
"$CXX" "${FLAGS[@]}" -I"$ROOT/include" -isystem "$LB" "$HERE/ext3_harness.cpp" "$B/liblob_engine.a" -o "$B/ext3_harness"
"$CXX" "${FLAGS[@]}" -DEXT3_UNITY -I"$ROOT/include" -isystem "$LB" "$HERE/ext3_harness.cpp" -o "$B/ext3_harness_unity"
"$CXX" --version | head -1
echo "flags: ${FLAGS[*]}"
