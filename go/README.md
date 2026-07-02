# pyvauto (Go)

A standalone Go port of `pyvauto` — no Python runtime needed. It implements the
full CLI, parser, every AUTO tag, and `--delete`, with output verified
byte-for-byte against the Python `pyvauto.py` via golden tests over the real
`tests/*.sv` corpus.

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

- Expands every AUTO tag in place (writes only when content changes).
- `--delete` un-expands (strips auto-generated content, leaves the bare tags).
- Sub-modules are searched in each target file's own directory plus any
  `--incdir` directories.

## Scope

Full parity with `pyvauto.py`: `AUTOINST` (incl. reconcile + width-mismatch
warnings), `AUTOARG`, `AUTOINPUT`, `AUTOOUTPUT`, `AUTOWIRE`, `AUTOLOGIC`,
`AUTOSENSE`, and `--delete` — all matched byte-for-byte against the Python
oracle on the `tests/*.sv` corpus.

## Vim plugin

The bundled Vim plugin can call this binary for the expand path — set
`g:pyvauto_bin` to the built binary:

```vim
let g:pyvauto_bin = '/path/to/go/pyvauto'
```

`:Pyvauto` / `:VA` (expand) and `:NVA` (un-expand) then run the binary
directly — no Python needed.

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
