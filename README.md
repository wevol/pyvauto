# pyvauto - Python Verilog Auto-Generator

**English** | [繁體中文](README.zh-TW.md)

[![CI](https://github.com/wevol/pyvauto/actions/workflows/ci.yml/badge.svg)](https://github.com/wevol/pyvauto/actions/workflows/ci.yml)

A Python Verilog automation tool that brings Emacs `verilog-mode`-style AUTO expansion to your editor. pyvauto is **built for Vim** (a Vim plugin is included): you get one-keystroke AUTOINST / AUTOARG / AUTOWIRE expansion without depending on Emacs. The core is a pure-Python CLI, so it also runs standalone from the command line or in CI. Other editors (e.g. VS Code) have no dedicated plugin yet — there you invoke the CLI from a terminal and reload the file.

## Features

- ✅ **Mixed-mode support**: every AUTO tag coexists with manual declarations — no duplicate definitions.
- ✅ **AUTOINST**: auto-generates instance port connections (manual connections are detected and de-duplicated).
- ✅ **AUTOARG**: maintains the module port list in both **ANSI (mixed-mode)** and **Non-ANSI** styles. The Non-ANSI list is regenerated on every run and grouped by direction under `// Outputs` / `// Inouts` / `// Inputs` headers, just like Emacs.
- ✅ **AUTOINPUT / AUTOOUTPUT**: pulls undeclared input/output ports up from sub-instances and declares them.
- ✅ **AUTOWIRE**: declares the `wire`s needed to interconnect instantiated modules.
- ✅ **Stable replacement (idempotent)**: generated blocks are detected and replaced, so re-running never accumulates redundant tags or breaks syntax.
- ✅ **Fast parsing**: a built-in regex-based Verilog parser handles the analysis and expansion.

## Installation

```bash
# clone or download this project
cd pyvauto
```

- **Running the tool**: `pyvauto.py` has zero external dependencies (standard library only) and is **compatible with Python 3.6.8+** — so it works with an old system Python, e.g. when called from Vim. Just run `python pyvauto.py ...`.
- **Development / tests**: this uv project pins its environment to **Python 3.13** (`requires-python` in `pyproject.toml` and `uv.lock`; pytest also needs a recent Python). Run `uv sync` to set up the environment.

## Vim integration (primary use case)

The bundled Vim plugin `plugin/pyvauto.vim` shells out to the system Python 3 to run the expansion, so **it works even if your Vim is only built with Python 2.7**.

```vim
" add the project directory to runtimepath in your .vimrc
set runtimepath+=/path/to/pyvauto

" override if your system Python 3 command isn't 'python3'
let g:pyvauto_python = 'python3'
```

In a Verilog/SystemVerilog file (`.v` / `.sv`):

- press **`\va`** or **`F5`**, or run **`:Pyvauto`** to expand
- press **`\nva`** or **`F6`**, or run **`:NVA`** to **un-expand** (strip the auto-generated content, leaving the bare tags)
- the plugin saves the buffer → calls `pyvauto.py` → reloads the file

For the full setup (custom mappings, expand-on-save, explicit paths, troubleshooting) see [VIM_INTEGRATION.md](VIM_INTEGRATION.md).

## Usage

### Command-line basics

You can also expand files in place straight from the command line (handy for CI, or for editors without a dedicated plugin used alongside a terminal):

```bash
python pyvauto.py <file1.sv> <file2.sv> ...

# reverse it — strip auto-generated content, leave the bare tags (like emacs verilog-delete-auto)
python pyvauto.py --delete <file1.sv> ...
```

> ℹ️ For cross-module expansions like AUTOINST, the CLI searches the **target file's own directory** for sub-module definitions.
> If a sub-module lives elsewhere, add its directory with `--incdir DIR` (repeatable): `python pyvauto.py --incdir rtl/common top.sv`.

### Examples

#### 1. Mixed-mode AUTOINST
Declare the key signals by hand; let `AUTOINST` fill in the rest:
```systemverilog
sub_module u_inst (
    .clk(my_special_clk), // manual connection
    /*AUTOINST*/           // auto-fills rst_n, data_i, data_o
);
```

#### 2. ANSI mixed-mode AUTOARG
Put `/*AUTOARG*/` right in the header; the tool generates the full port list from the body declarations:
```systemverilog
module top (
    input clk,
    /*AUTOARG*/
    output [7:0] data_out
);
    input rst_n;
    input [7:0] data_in;
    // ...
endmodule
```

#### 3. Non-ANSI AUTOARG — Emacs-style direction grouping
With a bare `/*AUTOARG*/` header, the port-name list is regenerated on every run and grouped by direction. Put any manual ports **before** the tag; everything after it is auto-managed (removed ports drop out, added ports land in the right group). This:
```systemverilog
module m (/*AUTOARG*/);
    input  clk, rst_n;
    output valid;
    inout  bus;
endmodule
```
expands to:
```systemverilog
module m (/*AUTOARG*/
    // Outputs
    valid,
    // Inouts
    bus,
    // Inputs
    clk, rst_n
);
    input  clk, rst_n;
    output valid;
    inout  bus;
endmodule
```

## Project structure

- `pyvauto.py`: the single-file core — regex parser, expansion logic, and CLI (zero external dependencies).
- `plugin/pyvauto.vim`: the Vim plugin that calls `pyvauto.py`.
- `VIM_INTEGRATION.md`: full Vim integration and configuration guide.
- `tests/`: pytest unit tests and `*.sv` verification fixtures.

## Status

- [x] Core AUTOINST/AUTOARG mixed-mode support
- [x] AUTOINPUT/AUTOOUTPUT smart declarations
- [x] AUTOWIRE connection tracking
- [x] Regex parsing performance tuning
- [ ] Dedicated SystemVerilog interface support
- [ ] Advanced parameter-passing tag (AUTOPARAM)

## License

MIT

## Contributing

Issues and pull requests are welcome!

## Acknowledgements

This project was built entirely with [Claude Code](https://claude.com/claude-code).
