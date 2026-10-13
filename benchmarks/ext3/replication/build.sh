#!/bin/bash
# Replication build: same compiler and flags as PREREG section 5, for every TU.
set -euo pipefail
cd "$(dirname "$0")"
R=/Users/ansh/quant-projects-audit/existing/cpp-limit-order-book-market-maker
LB=third_party/liquibook/src
F="-O3 -DNDEBUG -std=c++20 -arch arm64 -Wall -Wextra"
mkdir -p build/obj
for s in flat_order_book matching_engine order_book price_level; do
  clang++ $F -I$R/include -c $R/src/$s.cpp -o build/obj/$s.o
done
rm -f build/liblob_engine.a; ar rcs build/liblob_engine.a build/obj/*.o
clang++ $F -I$R/include src/rep_gen.cpp build/liblob_engine.a -o build/rep_gen
if [ -f src/rep_harness.cpp ]; then
  clang++ $F -I$R/include -isystem $LB src/rep_harness.cpp build/liblob_engine.a -o build/rep_harness
  clang++ $F -DREP_UNITY -I$R/include -isystem $LB src/rep_harness.cpp -o build/rep_harness_unity
fi
clang++ --version | head -1
