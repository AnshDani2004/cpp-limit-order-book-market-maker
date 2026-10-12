#!/usr/bin/env bash
# Fetch Liquibook at the pinned commit into benchmarks/ext3/third_party/liquibook (git-ignored).
set -euo pipefail
PIN=2427613b32f1667abae68a01df6af9ba8270f8e7
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/third_party/liquibook"
if [ ! -d "$DEST/.git" ]; then
  git clone --quiet https://github.com/enewhuis/liquibook.git "$DEST"
fi
git -C "$DEST" fetch --quiet origin
git -C "$DEST" checkout --quiet "$PIN"
test "$(git -C "$DEST" rev-parse HEAD)" = "$PIN"
echo "liquibook at $(git -C "$DEST" rev-parse HEAD)"
