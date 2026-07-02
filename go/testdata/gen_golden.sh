#!/usr/bin/env bash
# Regenerate golden outputs from the Python reference (the oracle).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$here/../.."
mkdir -p "$here/golden"
for in in "$here/inputs"/*.sv; do
  name="$(basename "$in" .sv)"
  work="$(mktemp -d)"
  cp "$in" "$work/$name.sv"
  ( cd "$work" && python3 "$repo/pyvauto.py" "$name.sv" >/dev/null 2>&1 )
  cp "$work/$name.sv" "$here/golden/$name.golden"
  rm -rf "$work"
done
echo "goldens regenerated:"
ls -1 "$here/golden"
