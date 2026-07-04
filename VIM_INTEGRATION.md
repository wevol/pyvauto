# Vim Integration Guide

The bundled plugin lets you expand AUTO tags from inside Vim with one keystroke.
It works even if your Vim was built with **only Python 2.7** (or no Python at
all): instead of running Python inside Vim, the plugin shells out to your
system's Python 3 to run `pyvauto.py`. Zero dependencies, and it runs the same
on Linux, macOS, and Windows.

## Quick start

1. Make sure Python 3.6.8+ is on your `PATH` (`python3 --version`).
2. Add the project to Vim's `runtimepath`:
   ```vim
   " in your .vimrc
   set runtimepath+=/path/to/pyvauto
   ```
3. Open a `.v`/`.sv` file, put an AUTO tag (e.g. `/*AUTOINST*/`) where you want
   it, and press **`F5`** (or `\va`). The plugin saves the buffer, runs the
   expansion, and reloads the file in place.

That's it — no configuration needed in the common case, because the plugin
auto-detects both your Python 3 executable and the path to `pyvauto.py`.

## Commands & key mappings

In a Verilog/SystemVerilog buffer:

| Action | Mapping | Ex command |
|--------|---------|------------|
| Expand AUTO tags | `\va` or `F5` | `:Pyvauto` (or `:VA`) |
| Un-expand (strip generated content, keep the bare tags) | `\nva` or `F6` | `:NVA` |

`\` is Vim's default `<Leader>`, so `\va` means leader-then-`va`. To use your own
mappings, disable the defaults and bind the commands yourself:

```vim
let g:pyvauto_no_mappings = 1
nnoremap <silent> <Leader>e :Pyvauto<CR>
nnoremap <silent> <F9>      :NVA<CR>
```

## Configuration

All settings are optional. Put any you need in your `.vimrc`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `g:pyvauto_python` | auto-detected: `python3` → `python` → `py` (skips the Windows Store stub) | The Python 3 executable. Set only if detection picks the wrong one. |
| `g:pyvauto_script` | auto-located: next to `pyvauto.vim`, else one directory up | Path to `pyvauto.py`. `~` and `$ENV` vars are expanded for you. Set if you installed the script elsewhere. |
| `g:pyvauto_bin` | unset | Path to a compiled binary (e.g. the [Go build](go/README.md)). When set, it runs directly — **no Python or `pyvauto.py` needed**. |
| `g:pyvauto_on_save` | off | Set to `1` to expand automatically on every `:w` of a `.v`/`.sv` file. |
| `g:pyvauto_no_mappings` | off | Set to `1` to disable the default `\va`/`F5` and `\nva`/`F6` mappings. |

```vim
" examples
let g:pyvauto_python  = 'python3'
let g:pyvauto_script  = '~/.vim/plugin/pyvauto.py'
let g:pyvauto_bin     = '/path/to/pyvauto/go/pyvauto'   " use the Go binary
let g:pyvauto_on_save = 1
```

## Installation

The `runtimepath` method in [Quick start](#quick-start) is the simplest. If you
prefer to copy files into your plugin directory instead, **copy `pyvauto.py`
alongside `pyvauto.vim`** so the plugin can find the script automatically:

```bash
# Linux / macOS
cp plugin/pyvauto.vim pyvauto.py ~/.vim/plugin/

# Windows
copy plugin\pyvauto.vim %USERPROFILE%\vimfiles\plugin\
copy pyvauto.py         %USERPROFILE%\vimfiles\plugin\
```

### How the script path is resolved

The plugin looks for `pyvauto.py` in two places, first match wins:

1. **Next to `pyvauto.vim`** — the flat install above.
2. **One directory up** — the repo layout, where `pyvauto.vim` lives in
   `plugin/` and `pyvauto.py` sits at the project root.

If you copy *only* `pyvauto.vim` (without `pyvauto.py`), set `g:pyvauto_script`
to the script's location.

## Troubleshooting

**"Python not found"** — detection couldn't find a usable interpreter. Point it
at one explicitly:

```vim
let g:pyvauto_python = '/usr/bin/python3'      " Windows, e.g. C:/Python313/python.exe
```

**"pyvauto.py not found"** — set an absolute path to the script:

```vim
let g:pyvauto_script = '/path/to/pyvauto/pyvauto.py'
```

**`python3: can't open file '~/.vim/plugin/pyvauto.py'`** — a literal `~` reached
Python. The plugin expands `~`/`$ENV` on load, so a current `pyvauto.vim` handles
this for you. If you still hit it on an older plugin, expand the path yourself:

```vim
let g:pyvauto_script = expand('~/.vim/plugin/pyvauto.py')
```

**Check what's configured** — run inside Vim:

```vim
:echo g:pyvauto_python
:echo g:pyvauto_script
```

## Python compatibility

`pyvauto.py` targets **Python 3.6.8+** (tested through 3.13). It uses
`typing.Optional`/`List`/`Set` rather than the newer `|` union syntax and relies
only on the standard library, so an old system Python is fine.

> This is about the *standalone tool's* runtime. The project's own dev/test
> environment (uv + pytest) targets Python 3.13 — see the main
> [README](README.md).

## Verifying your setup

```bash
cd /path/to/pyvauto
python -m pytest tests/ -v            # run the test suite
python pyvauto.py tests/test_top.sv   # or expand a sample file by hand
```
