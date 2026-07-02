# pyvauto (Go MVP)

A standalone Go port of `pyvauto` — no Python runtime needed for the expand
path. This is an **MVP**: it implements the CLI, parser, `AUTOINST`, and
`AUTOARG`, with output verified byte-for-byte against the Python `pyvauto.py`
via golden tests. Everything else is still Python-only (see Scope).

## Build

```bash
cd go
go build -o pyvauto ./cmd/pyvauto
```

Cross-compile a self-contained binary for another platform:

```bash
GOOS=linux   GOARCH=amd64 go build -o pyvauto-linux-amd64   ./cmd/pyvauto
GOOS=darwin  GOARCH=arm64 go build -o pyvauto-darwin-arm64  ./cmd/pyvauto
GOOS=windows GOARCH=amd64 go build -o pyvauto-windows-amd64.exe ./cmd/pyvauto
```

## Usage

```bash
pyvauto [--incdir DIR]... <file.sv> [file2.sv ...]
```

- Expands `AUTOINST` and `AUTOARG` in place (writes only when content changes).
- Sub-modules are searched in each target file's own directory plus any
  `--incdir` directories.
- `--delete` is **not implemented** in the MVP and exits with an error.

## Scope (MVP)

- **In:** CLI, parser, `AUTOINST` (fill a bare tag: group by direction, widths,
  keep manual connections before the tag), `AUTOARG` (Emacs-style regeneration +
  direction grouping).
- **Out (still use the Python `pyvauto.py`):** `AUTOWIRE`, `AUTOLOGIC`,
  `AUTOINPUT`, `AUTOOUTPUT`, `AUTOSENSE`, `--delete`, AUTOINST width-mismatch
  warnings, and AUTOINST advanced reconcile (re-run add/remove, width refresh).

## Vim plugin

The bundled Vim plugin can call this binary for the expand path — set
`g:pyvauto_bin` to the built binary:

```vim
let g:pyvauto_bin = '/path/to/go/pyvauto'
```

`:Pyvauto` / `:VA` then run the binary directly (no Python). `:NVA`
(un-expand) still uses Python, since the Go MVP has no delete.

## Tests

```bash
cd go
go vet ./...
go test ./...
```

Golden fixtures live in `testdata/`. Regenerate the expected outputs from the
Python oracle after an intentional behavior change:

```bash
bash testdata/gen_golden.sh
```
