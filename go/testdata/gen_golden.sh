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

# Delete goldens: un-expand each expanded golden that has a .del.golden, so the
# delete round-trip fixtures stay oracle-derived alongside the expand goldens.
for del in "$here/golden"/*.del.golden; do
  [ -e "$del" ] || continue
  name="$(basename "$del" .del.golden)"
  work="$(mktemp -d)"
  cp "$here/golden/$name.golden" "$work/$name.sv"
  ( cd "$work" && python3 "$repo/pyvauto.py" --delete "$name.sv" >/dev/null 2>&1 )
  cp "$work/$name.sv" "$del"
  rm -rf "$work"
done

# Full corpus: the real tests/*.sv fixtures. Some reference sub-modules in
# OTHER fixtures, so run Python with the whole corpus present.
corpus="$(mktemp -d)"
cp "$repo/tests"/*.sv "$corpus"/
for f in "$corpus"/*.sv; do
  name="$(basename "$f" .sv)"
  ( cd "$corpus" && python3 "$repo/pyvauto.py" "$name.sv" >/dev/null 2>&1 )
done
for f in "$repo/tests"/*.sv; do
  name="$(basename "$f" .sv)"
  cp "$corpus/$name.sv" "$here/golden/tests_$name.golden"
done
rm -rf "$corpus"

echo "goldens regenerated:"
ls -1 "$here/golden"
