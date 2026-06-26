# Vim Integration Guide

## The problem it solves

If your Vim was built with only Python 2.7 support and can't run Python 3 code
directly, this project ships an **external-command approach**: Vim shells out to
your system's Python 3 to run `pyvauto.py`.

---

## Python version support

`pyvauto.py` runs on:
- ✅ Python 3.6.8+
- ✅ Python 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13

**Compatibility notes:**
- Uses `typing.Optional` instead of the `|` union operator.
- Uses `typing.List` / `typing.Set` for return-type hints.
- Relies only on standard-library features available since Python 3.6.

> The standalone tool targets 3.6.8+. The project's own dev/test environment
> (uv + pytest) targets Python 3.13 — see the main README.

---

## Installation

### 1. Confirm Python 3 is available

```bash
python --version    # should report Python 3.6.8 or newer
# if the above is Python 2.x, try:
python3 --version
```

### 2. Install the Vim plugin

Add the project directory to Vim's `runtimepath`:

```vim
" in your .vimrc
set runtimepath+=/path/to/pyvauto
```

Or copy the plugin file manually:

```bash
# Linux/macOS
cp plugin/verilog_auto.vim ~/.vim/plugin/

# Windows
copy plugin\verilog_auto.vim %USERPROFILE%\vimfiles\plugin\
```

### 3. Configuration (optional)

Customize in your `.vimrc`:

```vim
" if your Python 3 executable isn't 'python' (e.g. it's 'python3')
let g:verilog_auto_python = 'python3'

" if pyvauto.py needs an explicit path
let g:verilog_auto_script = '/path/to/pyvauto/pyvauto.py'

" expand automatically on save (optional)
let g:verilog_auto_on_save = 1

" disable the default mappings (if you want your own)
let g:verilog_auto_no_mappings = 1
```

---

## Usage

### Option 1: key mappings

In a Verilog file (`.v` or `.sv`):

- press **`\va`** (backslash + va)
- or press **`F5`**

### Option 2: command

```vim
:VerilogAuto
```

### Workflow

1. Add an AUTO tag (e.g. `/*AUTOINST*/`) in your Verilog file.
2. Press `\va` or `F5`.
3. The plugin will:
   - save the current file
   - call the external Python 3 to run `pyvauto.py`
   - reload the file automatically
   - show a result message

---

## Custom key mappings

To use a different shortcut:

```vim
" disable the default mappings
let g:verilog_auto_no_mappings = 1

" map to <Leader>e (e.g. \e)
nnoremap <silent> <Leader>e :VerilogAuto<CR>

" or use another function key
nnoremap <silent> <F9> :VerilogAuto<CR>
```

---

## Troubleshooting

### Error: Python not found

```vim
" specify the full path to the Python executable
let g:verilog_auto_python = '/usr/bin/python3'   " or e.g. C:/Python313/python.exe on Windows
```

### Error: pyvauto.py not found

```vim
" use an absolute path
let g:verilog_auto_script = '/path/to/pyvauto/pyvauto.py'
```

### Check the configuration

Run inside Vim:

```vim
:echo g:verilog_auto_python
:echo g:verilog_auto_script
```

to confirm the paths are correct.

---

## Why this approach

✅ **Bypasses Vim's Python version limit** — uses the system Python 3
✅ **Zero dependencies** — no third-party packages required
✅ **Cross-platform** — works on Windows, Linux, and macOS
✅ **Backward compatible** — supports Python 3.6.8+
✅ **Simple integration** — one keystroke runs every expansion

---

## Testing

Run the test suite to confirm everything works:

```bash
cd /path/to/pyvauto

# run the tests
python -m pytest tests/ -v

# manual test
python pyvauto.py tests/test_top.sv
```

All tests should pass.
