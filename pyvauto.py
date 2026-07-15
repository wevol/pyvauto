import re
import os
import argparse
import sys
import traceback
from typing import Optional, Dict, List, Set, Union


# ============================================================================
# Shared helpers (string-aware comment stripping & depth-counted port parsing)
# ============================================================================


_STRIP_COMMENTS_RE = re.compile(
    r'"(?:\\.|[^"\\])*"'
    r'|//[^\n]*'
    r'|/\*.*?\*/',
    re.DOTALL,
)


def strip_comments_safely(text: str) -> str:
    """Strip // and /* */ comments while preserving string literals intact."""

    def sub(m):  # type: ignore[override]
        s = m.group(0)
        if s.startswith('"'):
            return s
        return ""

    return _STRIP_COMMENTS_RE.sub(sub, text)


_NAMED_PORT_RE = re.compile(r"\.(\w+)\s*\(")


def parse_named_port_connections(block: str) -> Dict[str, str]:
    """Parse `.name(value)` pairs, depth-counting parens so nested `(...)`
    and `{...}` in the value don't truncate the match."""
    ports: Dict[str, str] = {}
    n = len(block)
    i = 0
    while i < n:
        if block[i] != ".":
            i += 1
            continue
        m = _NAMED_PORT_RE.match(block, i)
        if not m:
            i += 1
            continue
        name = m.group(1)
        start = m.end()
        j = start
        depth = 1
        while j < n and depth > 0:
            c = block[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            j += 1
        if depth != 0:
            break
        ports[name] = block[start : j - 1].strip()
        i = j
    return ports


_AUTO_TAG_RE = re.compile(
    r"/\*\s*(AUTOINST|AUTOARG|AUTOWIRE|AUTOLOGIC|AUTOINPUT|AUTOOUTPUT|AUTOSENSE)\s*\*/",
    re.IGNORECASE,
)


# `\b…\b\s*` (and `\s*` after the width) tolerate the no-space forms
# `wire[7:0] a;` / `reg[3:0] b;`; the `\b` after the keyword still rejects
# identifiers such as `wireless` / `regfile`.
_TYPE_DECL_RE = re.compile(
    r"\b(wire|reg|logic|integer|bit|real|byte|shortint|int|longint)\b\s*(\[.*?\]\s*)?([\w\s,]+);",
    re.MULTILINE,
)


def _scan_type_decls(content_no_comments: str) -> Dict[str, str]:
    """Return {signal_name: width_str} for all wire/reg/logic/... declarations."""
    result: Dict[str, str] = {}
    for m in _TYPE_DECL_RE.finditer(content_no_comments):
        width = (m.group(2) or "").strip()
        for name in re.split(r",", m.group(3)):
            clean = name.strip().split("=")[0].strip()
            if clean and clean not in result:
                result[clean] = width
    return result


_INST_SKIP_KEYWORDS = {
    "module",
    "if",
    "always",
    "initial",
    "case",
    "generate",
    "assign",
    "begin",
    "endmodule",
    "function",
    "task",
}

# Verilog keywords AUTOSENSE must never treat as a sensitivity-list signal.
_AUTOSENSE_KEYWORDS = {
    "always",
    "begin",
    "end",
    "if",
    "else",
    "case",
    "endcase",
    "assign",
    "default",
    "posedge",
    "negedge",
    "or",
    "and",
    "logic",
    "reg",
    "wire",
    "initial",
    "input",
    "output",
    "inout",
    "module",
    "endmodule",
    "task",
    "endtask",
    "function",
    "endfunction",
    "fork",
    "join",
    "generate",
    "endgenerate",
    "repeat",
    "while",
    "for",
    "forever",
    "integer",
    "bit",
}


# "module … endmodule" block; expanders and deleters are applied per block.
_MODULE_BLOCK_RE = re.compile(
    r"^[\t ]*module\s+\w+.*?\bendmodule\b",
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)

# Body-context auto-signal blocks (AUTOWIRE/AUTOLOGIC/AUTOINPUT/AUTOOUTPUT);
# un-expand strips the generated block and keeps the bare tag.
_AUTO_SIGNAL_BLOCK_RE = re.compile(
    r"(/\*(?:AUTOWIRE|AUTOLOGIC|AUTOINPUT|AUTOOUTPUT)\*/)\s*// Beginning.*?// End of automatics",
    re.DOTALL | re.IGNORECASE,
)


def _widths_mismatch(w1: str, w2: str) -> bool:
    """True if two width strings represent different widths (ignoring whitespace)."""
    if not w1 or not w2:
        return False
    return re.sub(r"\s+", "", w1) != re.sub(r"\s+", "", w2)


# ============================================================================
# Verilog parser classes (formerly parser.py)
# ============================================================================


class VerilogPort:
    """A Verilog port definition."""

    def __init__(
        self, name: str, direction: str, width: str = "", port_type: str = "wire"
    ):
        self.name = name
        self.direction = direction
        self.width = width
        self.port_type = port_type


class VerilogModule:
    """A Verilog module definition."""

    def __init__(
        self,
        name: str,
        parameters: Optional[dict] = None,
        ports: Optional[list] = None,
        file_path: str = "",
    ):
        self.name = name
        self.parameters = parameters if parameters is not None else {}
        self.ports = ports if ports is not None else []
        self.file_path = file_path


class RegexVerilogParser:
    """Regex-based Verilog parser."""

    def __init__(self):
        self.module_re = re.compile(
            r"(?m)^[\t ]*module\s+(\w+)\s*(#\s*\(.*?\))?\s*\((.*?)\)\s*;", re.DOTALL
        )
        self.param_re = re.compile(r"(\w+)\s*=\s*([^,)\s]+)")
        # group(4) captures the whole comma-separated name list sharing one
        # direction/type/width (e.g. `input [7:0] a, b, c`). The negative
        # lookahead stops the list at the next declaration so an ANSI header
        # like `input a, input b` is NOT merged into one port. Split group(4)
        # with `_port_names` to get the individual names.
        # `\b\s*` after the direction and after the type keyword (and `\s*`
        # after the width) tolerate the no-space forms `input[7:0] x` and
        # `input wire[7:0] x`; the `\b`s still reject identifiers such as
        # `inputxyz` / `wireless`.
        self.port_re = re.compile(
            r"(input|output|inout)\b\s*(?:(logic|reg|wire)\b\s*)?(?:(\[.*?\])\s*)?"
            r"(\w+(?:\s*,\s*(?!input\b|output\b|inout\b)\w+)*)",
            re.MULTILINE,
        )

    @staticmethod
    def _port_names(name_group: str) -> List[str]:
        """Split a port_re group(4) match into individual port names,
        e.g. 'clk, rst_n,\\n en' -> ['clk', 'rst_n', 'en']."""
        return [n.strip() for n in name_group.split(",")]

    def parse_file(self, content: str, file_path: str = "") -> List:
        """Parse Verilog file content and return the list of modules."""
        modules = []
        content_no_comments = strip_comments_safely(content)

        for match in self.module_re.finditer(content_no_comments):
            mod_name = match.group(1)
            param_block = match.group(2) or ""
            port_block = match.group(3) or ""

            # Extract module body: from end of port list ')' to 'endmodule'
            start_pos = match.end()
            end_module_match = re.search(
                r"\bendmodule\b", content_no_comments[start_pos:]
            )
            module_body = ""
            if end_module_match:
                module_body = content_no_comments[
                    start_pos : start_pos + end_module_match.start()
                ]

            module = VerilogModule(name=mod_name, file_path=file_path)

            if param_block:
                inner_params = re.search(r"#\s*\((.*)\)", param_block, re.DOTALL)
                if inner_params:
                    for p_match in self.param_re.finditer(inner_params.group(1)):
                        module.parameters[p_match.group(1)] = p_match.group(2)

            # 1. Parse ports from header (ANSI style)
            for p_match in self.port_re.finditer(port_block):
                for name in self._port_names(p_match.group(4)):
                    module.ports.append(
                        VerilogPort(
                            name=name,
                            direction=p_match.group(1),
                            port_type=p_match.group(2) or "wire",
                            width=p_match.group(3) or "",
                        )
                    )

            # 2. Parse ports from body (Non-ANSI style or mixed)
            if module_body:
                for p_match in self.port_re.finditer(module_body):
                    for p_name in self._port_names(p_match.group(4)):
                        if not any(p.name == p_name for p in module.ports):
                            module.ports.append(
                                VerilogPort(
                                    name=p_name,
                                    direction=p_match.group(1),
                                    port_type=p_match.group(2) or "wire",
                                    width=p_match.group(3) or "",
                                )
                            )

            modules.append(module)
        return modules

    def get_instantiations(self, content: str, file_path: str) -> List:
        """Extract Verilog instantiation info."""
        content_no_comments = strip_comments_safely(content)

        inst_pattern = re.compile(
            r"(\w+)\s+(\w+)\s*(#\s*\(.*?\))?\s*\(([^;]*?)\)\s*;", re.DOTALL
        )

        insts = []
        for match in inst_pattern.finditer(content_no_comments):
            mod_name, inst_name, _, port_block = match.groups()

            if mod_name in _INST_SKIP_KEYWORDS:
                continue

            ports = parse_named_port_connections(port_block)

            insts.append(
                {"module_name": mod_name, "instance_name": inst_name, "ports": ports}
            )
        return insts

    def get_local_signals(self, content: str, file_path: str) -> Set:
        """Extract local signal definitions (ports, parameters, wire/reg/logic declarations)."""
        content_no_comments = strip_comments_safely(content)
        signals: Set[str] = set()

        for mod in self.parse_file(content, file_path):
            for p in mod.ports:
                signals.add(p.name)
            for param in mod.parameters:
                signals.add(param)

        signals.update(_scan_type_decls(content_no_comments).keys())

        param_pattern = re.compile(
            r"\b(parameter|localparam)\b\s+(?:.*?\b)?(\w+)\s*=", re.MULTILINE
        )
        for m in param_pattern.finditer(content_no_comments):
            signals.add(m.group(2))

        return signals

    def get_local_signal_widths(self, content: str, file_path: str) -> Dict[str, str]:
        """Extract local signals mapped to their bit widths (empty string when absent or scalar)."""
        widths: Dict[str, str] = {}
        content_no_comments = strip_comments_safely(content)

        for mod in self.parse_file(content, file_path):
            for p in mod.ports:
                widths.setdefault(p.name, p.width or "")

        for name, width in _scan_type_decls(content_no_comments).items():
            widths.setdefault(name, width)

        return widths


# ============================================================================
# Verilog project and expander classes
# ============================================================================


class VerilogProject:
    def __init__(self):
        self.modules: Dict[str, VerilogModule] = {}
        self.parser = RegexVerilogParser()

    def _index_file(self, full_path: str, _content: Optional[str] = None) -> None:
        try:
            if _content is None:
                with open(
                    full_path,
                    "r",
                    encoding="utf-8",
                    errors="ignore",
                    newline="",
                ) as f:
                    _content = f.read()
            mods = self.parser.parse_file(_content, full_path)
            for m in mods:
                print(f"  Found module: {m.name}")
                self.modules[m.name] = m
        except Exception as e:
            print(f"Error reading {full_path}: {e}")

    def add_directory(self, path: str):
        print(f"Indexing directory: {os.path.abspath(path)}")
        # Sorted traversal: os.walk order is filesystem-dependent, and with
        # duplicate module names "first-found wins" — keep it deterministic
        # (and matching the Go port's lexical WalkDir) on every platform.
        for root, dirs, files in os.walk(path):
            dirs.sort()
            for file in sorted(files):
                if file.endswith((".v", ".sv")) and file != "test_top.sv":
                    self._index_file(os.path.join(root, file))

    def resolve(self, roots: Union[str, List[str]], needed: Set[str]) -> None:
        """Index only the modules in `needed` (plus any co-located in the
        same files), parsing as few files as possible, across one or more root
        directories. Module names are globally unique, so first-found wins.
        `roots` may be a single path (str) or a list of paths."""
        pending = set(needed)
        if not pending:
            return
        if isinstance(roots, str):
            roots = [roots]
        # De-duplicate roots by realpath, preserving order.
        seen = set()
        uniq_roots = []
        for r in roots:
            rp = os.path.realpath(r)
            if rp not in seen:
                seen.add(rp)
                uniq_roots.append(r)

        # One cheap directory listing per root — file names only, no parsing.
        candidates = []                  # all candidate .v/.sv paths
        by_basename = {}                 # '<name>' -> path, for the fast-path
        # Sorted traversal: see add_directory — first-found-wins resolution must
        # not depend on filesystem listing order.
        for path in uniq_roots:
            for root, dirs, files in os.walk(path):
                dirs.sort()
                for file in sorted(files):
                    if file.endswith((".v", ".sv")) and file != "test_top.sv":
                        full = os.path.join(root, file)
                        candidates.append(full)
                        by_basename.setdefault(os.path.splitext(file)[0], full)

        roots_str = ", ".join(os.path.abspath(r) for r in uniq_roots)
        print(f"Resolving {len(pending)} module(s) under {roots_str}")
        parsed = set()

        # B — filename fast-path: parse only '<name>.v' / '<name>.sv'.
        for name in list(pending):
            hit = by_basename.get(name)
            if hit and hit not in parsed:
                self._index_file(hit)
                parsed.add(hit)
                pending.difference_update(self.modules.keys())
                if not pending:
                    return

        # A — early-stop fallback: lightweight text pre-filter, then full parse.
        # Read each file once; skip files that provably declare none of the
        # pending module names. Match `module <name>` tolerant of any
        # whitespace (tab/newline/multi-space) with word boundaries, mirroring
        # the parser — so a literal-space check can't miss `module\tfoo`, and
        # `a` doesn't false-match `module abc`. False positives (e.g. a name in
        # a comment) only cost a wasted parse; false negatives are impossible.
        for full in candidates:
            if not pending:
                return
            if full in parsed:
                continue
            try:
                with open(
                    full, "r", encoding="utf-8", errors="ignore", newline=""
                ) as fh:
                    content = fh.read()
            except Exception:
                continue
            prefilter = re.compile(
                r"\bmodule\s+(?:"
                + "|".join(re.escape(n) for n in pending)
                + r")\b"
            )
            if not prefilter.search(content):
                continue
            self._index_file(full, _content=content)
            parsed.add(full)
            pending.difference_update(self.modules.keys())


class VerilogExpander:
    def __init__(self, project: VerilogProject):
        self.project = project

    def _strip_comments(self, text: str) -> str:
        return strip_comments_safely(text)

    @staticmethod
    def _apply_comma_context(block: str, before: str, after: str) -> str:
        """Prepend/append commas so *block* connects cleanly to surrounding content."""
        if not block.strip():
            return block
        if before and not before.endswith(","):
            block = ", " + block.lstrip()
        if after and not (block.rstrip().endswith(",") or after.startswith(",")):
            block = block.rstrip() + ","
        return block

    @staticmethod
    def _reconcile_signal(existing: str, width_str: str) -> str:
        """Reuse an existing connection's signal, refreshing its bus width to
        the module port's `width_str`. A simple identifier (optionally with a
        `[..]`) keeps its base name and takes `width_str`; a complex expression
        (concatenation, constant, function call, …) is returned verbatim."""
        m = re.match(r"^\s*(\w+)\s*(\[[^\]]*\])?\s*$", existing)
        if not m:
            return existing
        return f"{m.group(1)}{width_str}"

    def _mask_comments(self, text: str) -> str:
        """Replace comment characters with spaces (preserving line layout) so
        regex passes see no comments — but keep AUTO tags and string literals
        intact. Used when we need byte-offset fidelity with the original text."""

        def mask_line(m):  # type: ignore[override]
            return " " * len(m.group(0))

        result = re.sub(r"//[^\n]*", mask_line, text)

        def mask_block(m):  # type: ignore[override]
            s = m.group(0)
            if _AUTO_TAG_RE.fullmatch(s):
                return s
            return "".join(c if c == "\n" else " " for c in s)

        return re.sub(r"/\*.*?\*/", mask_block, result, flags=re.DOTALL)

    def expand_autoinst(self, content: str, file_path: str = "") -> str:
        # Match the whole module instantiation but capture the /*AUTOINST*/ part specifically
        # Pattern: mod_name inst_name (#params)? ( ... /*AUTOINST*/ ... );
        # Updated to capture only the tag, treating surrounding content as "existing"
        pattern = re.compile(
            r"(\w+)\s+(\w+)\s*(#\s*\(.*?\))?\s*\(([^;]*?(/\*AUTOINST\*/)[^;]*?)\)\s*;",
            re.DOTALL | re.IGNORECASE,
        )

        local_widths = self.project.parser.get_local_signal_widths(content, file_path)

        def replace_fn(match):
            mod_name, inst_name, param_override, port_block, autoinst_tag = (
                match.groups()
            )

            if mod_name in _INST_SKIP_KEYWORDS:
                return match.group(0)

            module = self.project.modules.get(mod_name)
            if not module:
                print(f"Warning: Module {mod_name} not found in project.")
                return match.group(0)

            # Reconcile against the module's current ports. Connections BEFORE
            # the tag are manual: keep them verbatim and claim their ports. The
            # region AFTER the tag is rebuilt from the module ports each run —
            # removed ports drop out, new ports are added, and existing signal
            # names are reused (bus widths refreshed to the module).
            tag_index = port_block.find(autoinst_tag)
            before_tag = port_block[:tag_index]
            after_tag = port_block[tag_index + len(autoinst_tag):]

            before_conns = parse_named_port_connections(
                self._strip_comments(before_tag)
            )
            after_conns = parse_named_port_connections(
                self._strip_comments(after_tag)
            )
            claimed = set(before_conns.keys())

            all_conns = dict(after_conns)
            all_conns.update(before_conns)
            self._warn_manual_connection_widths(
                module, all_conns, mod_name, inst_name
            )

            ports_to_emit = [p for p in module.ports if p.name not in claimed]
            port_str = self._build_autoinst_port_lines(
                ports_to_emit, mod_name, local_widths, after_conns
            )

            before_stripped = before_tag.strip()
            if port_str.strip():
                port_str = self._apply_comma_context(port_str, before_stripped, "")
                new_port_block = before_tag + f"/*AUTOINST*/\n{port_str}"
            else:
                new_port_block = before_tag + "/*AUTOINST*/"

            # Tidy trailing / doubled commas around the manual prefix.
            new_port_block = re.sub(r",(\s*)$", r"\1", new_port_block)
            new_port_block = re.sub(r",(\s*),", r",\1", new_port_block)

            result = f"{mod_name} {inst_name} {param_override or ''} ({new_port_block}\n    );"
            print(f"Expanded instance {inst_name} of {mod_name}")
            return result

        return self._apply_masked_replacements(content, pattern, replace_fn)

    def _warn_manual_connection_widths(self, module, manual_conns, mod_name, inst_name):
        """Print warnings for hand-written port connections: unknown ports and
        bus-width mismatches against the module definition."""
        for p_name, sig_val in manual_conns.items():
            p_def = next((p for p in module.ports if p.name == p_name), None)
            if not p_def:
                print(
                    f"Warning: Port '{p_name}' does not exist in module '{mod_name}'."
                )
                continue

            sig_width_match = re.search(r"(\[.*?\])$", sig_val)
            sig_width = sig_width_match.group(1) if sig_width_match else ""

            if _widths_mismatch(p_def.width, sig_width):
                print(
                    f"Warning: Width mismatch for port '{p_name}' in instance '{inst_name}'. Module has '{p_def.width}', connection has '{sig_width}'."
                )

    def _build_autoinst_port_lines(
        self, ports_to_emit, mod_name, local_widths, after_conns
    ):
        """Render the /*AUTOINST*/ connections: group by direction, reuse any
        existing signal's base name (refreshing bus width to the module port),
        and append width-mismatch warning comments. This block is the last
        content before ')', so the final port carries no trailing comma."""
        lines = []
        line_warnings: Dict[int, str] = {}

        def format_p(p):
            width_str = p.width if p.width else ""
            existing = after_conns.get(p.name)
            if existing is not None:
                signal = self._reconcile_signal(existing, width_str)
            else:
                signal = f"{p.name}{width_str}"
            line = f"    .{p.name} ({signal})"
            local_w = local_widths.get(p.name, "")
            if existing is None and _widths_mismatch(p.width, local_w):
                line_warnings[len(lines)] = (
                    f"  // WARNING: width mismatch — "
                    f"{mod_name}.{p.name} is {p.width}, local {p.name} is {local_w}"
                )
            return line

        for direction, header in (
            ("output", "    // Outputs"),
            ("inout", "    // Inouts"),
            ("input", "    // Inputs"),
        ):
            members = [p for p in ports_to_emit if p.direction == direction]
            if members:
                lines.append(header)
                for p in members:
                    lines.append(format_p(p))

        for p in ports_to_emit:
            if p.direction not in ("output", "inout", "input"):
                lines.append(format_p(p))

        port_indices = [
            i for i, line in enumerate(lines) if line.strip().startswith(".")
        ]
        if port_indices:
            for i in port_indices[:-1]:
                lines[i] += ","

        for i, warning in line_warnings.items():
            lines[i] = lines[i] + warning

        return "\n".join(lines)

    def _iter_masked_matches(self, content, pattern):
        """Yield (masked_match, real_match) for each occurrence of `pattern` that
        is NOT inside a comment. The scan runs on masked content (comments
        blanked, AUTO tags preserved, layout/offsets unchanged by _mask_comments)
        and re-matches the ORIGINAL content at the masked match's offset to
        recover real group text. real_match is None when the original does not
        re-match there. This is the single place the mask + re-match-at-offset
        idiom lives."""
        masked = self._mask_comments(content)
        for masked_match in pattern.finditer(masked):
            yield masked_match, pattern.match(content, masked_match.start())

    @staticmethod
    def _splice(content, match, replacement):
        """Replace `match`'s span in `content` with `replacement`."""
        return content[: match.start()] + replacement + content[match.end() :]

    def _apply_masked_replacements(self, content, pattern, replace_fn):
        """Expand every occurrence of `pattern` not inside a comment, splicing the
        results (built from the real, unmasked match) back into the content."""
        replacements = []
        for masked_match, real_match in self._iter_masked_matches(content, pattern):
            if real_match is None:
                continue
            replacements.append(
                (masked_match.start(), masked_match.end(), replace_fn(real_match))
            )

        if not replacements:
            return content

        parts = []
        cursor = 0
        for start, end, text in replacements:
            parts.append(content[cursor:start])
            parts.append(text)
            cursor = end
        parts.append(content[cursor:])
        return "".join(parts)

    def _first_unmasked_match(self, content, pattern):
        """Return `pattern`'s first match in `content` that is NOT inside a
        comment, re-matched against the original text (or None if there is none)."""
        for _masked, real in self._iter_masked_matches(content, pattern):
            return real
        return None

    def expand_autoarg(self, content: str, file_path: str) -> str:
        """
        Expands /*AUTOARG*/ in module headers.
        Supports both Non-ANSI (names only) and ANSI (full declarations) contexts.
        """
        # Updated to capture only the tag, treating surrounding content as "existing"
        regex = re.compile(
            r"(\bmodule\s+(\w+)\s*)(#\s*\(.*?\))?\s*\(([^;]*?(/\*AUTOARG\*/)[^;]*?)\)\s*;",
            re.DOTALL | re.IGNORECASE,
        )

        # Ignore a commented-out /*AUTOARG*/ header by scanning masked content.
        match = self._first_unmasked_match(content, regex)
        if match is None:
            return content

        # Groups: 1: module start, 2: module name, 3: params, 4: port list content, 5: tag
        mod_start, target_mod_name, params, port_block, autoarg_tag = match.groups()

        print(f"Found AUTOARG in {file_path}")

        # Re-parse to get all port declarations (from body)
        modules = self.project.parser.parse_file(content, file_path)
        module = next((m for m in modules if m.name == target_mod_name), None)

        if not module or not module.ports:
            print(f"  No ports found for {target_mod_name} (or module parse failed)")
            # Just preserve the tag if no ports found
            return (
                content[: match.start()]
                + match.group(0).replace(autoarg_tag, "/*AUTOARG*/")
                + content[match.end() :]
            )

        # Emacs model: manual args live BEFORE the tag and are preserved; the
        # region AFTER the tag is stale auto output and is regenerated from the
        # module's current ports on every run (so removed ports disappear and
        # added ports show up in declaration order).
        tag_index = port_block.find(autoarg_tag)
        before_tag = port_block[:tag_index].strip()  # manual; after_tag discarded

        # Detect ANSI from the manual region only (empty -> bare names, the
        # common case and Emacs' behavior).
        is_ansi = bool(re.search(r"\b(input|output|inout)\b", before_tag))

        # Manual ports before the tag are preserved and not duplicated.
        existing_ports = self._collect_header_ports(before_tag, autoarg_tag, is_ansi)

        # Validation of manual ports in header
        for p_name in existing_ports:
            if not any(p.name == p_name for p in module.ports):
                print(
                    f"Warning: Port '{p_name}' listed in AUTOARG header does not exist in module '{target_mod_name}'."
                )

        ports_to_expand = [p for p in module.ports if p.name not in existing_ports]
        arg_list = self._format_autoarg_list(ports_to_expand, is_ansi)
        arg_list = self._apply_comma_context(arg_list, before_tag, "")

        if arg_list.strip():
            tag_with_args = f"/*AUTOARG*/\n    {arg_list}"
        else:
            tag_with_args = "/*AUTOARG*/"

        # Rebuild: manual-before-tag + tag + regenerated args.
        new_port_block = (before_tag + " " if before_tag else "") + tag_with_args
        # Clean up trailing comma
        new_port_block = re.sub(r",(\s*)$", r"\1", new_port_block)

        # rstrip mod_start and new_port_block: the regexes captured trailing
        # whitespace/newlines that would accumulate and break idempotency.
        header = mod_start.rstrip()
        if params:
            header += " " + params.strip()
        replacement = f"{header} ({new_port_block.rstrip()}\n);"
        return self._splice(content, match, replacement)

    def _collect_header_ports(self, port_block, autoarg_tag, is_ansi):
        """Collect names of ports already listed in an AUTOARG module header.
        ANSI headers carry 'direction [width] name' declarations; Non-ANSI
        headers are a bare comma-separated name list."""
        existing_ports = set()
        if is_ansi:
            for p_match in self.project.parser.port_re.finditer(
                self._strip_comments(port_block)
            ):
                for name in self.project.parser._port_names(p_match.group(4)):
                    existing_ports.add(name)
        else:
            # Remove the tag before splitting
            clean_block = port_block.replace(autoarg_tag, "")
            clean_block = self._strip_comments(clean_block)
            for p in re.split(r",", clean_block):
                p_name = p.strip()
                if p_name:
                    existing_ports.add(p_name)
        return existing_ports

    def _format_autoarg_list(self, ports_to_expand, is_ansi):
        """Render the AUTOARG port list. ANSI mode emits one full declaration
        ('direction [width] name') per line; Non-ANSI mode emits bare names
        grouped by direction under // Outputs / // Inouts / // Inputs headers,
        wrapped to 80 columns within each group."""
        if not ports_to_expand:
            return ""
        if is_ansi:
            # ANSI Mode: full declarations ('direction [width] name'), one per line
            decls = [
                f"{p.direction} {f'{p.width} ' if p.width else ''}{p.name}"
                for p in ports_to_expand
            ]
            return ",\n    ".join(decls)

        # Non-ANSI Mode: group by direction with // headers (Emacs style),
        # names wrapped to 80 columns within each group. Same order and header
        # strings as AUTOINST.
        groups = []
        for direction, header in (
            ("output", "    // Outputs"),
            ("inout", "    // Inouts"),
            ("input", "    // Inputs"),
        ):
            members = [p.name for p in ports_to_expand if p.direction == direction]
            if members:
                groups.append((header, members))
        others = [
            p.name
            for p in ports_to_expand
            if p.direction not in ("output", "inout", "input")
        ]
        if others:
            groups.append((None, others))

        lines = []
        for gi, (header, names) in enumerate(groups):
            if header:
                lines.append(header)
            block = self._wrap_names(names, "    ")
            if gi != len(groups) - 1:
                block += ","  # comma joining this group to the next
            lines.append(block)
        # Strip the first line's indent: the caller's f-string prepends "    "
        # to the first line only, so every rendered line ends at 4 spaces.
        return "\n".join(lines).lstrip()

    @staticmethod
    def _wrap_names(items, indent_str, limit=80):
        lines = []
        curr_line = indent_str
        for i, item in enumerate(items):
            suffix = "," if i < len(items) - 1 else ""
            to_add = item + suffix
            # +1 for space after comma
            if i > 0 and len(curr_line) + len(to_add) + 1 > limit:
                lines.append(curr_line.rstrip())
                curr_line = indent_str + to_add
            else:
                if i > 0:
                    curr_line += " "
                curr_line += to_add
        if curr_line.strip():
            lines.append(curr_line.rstrip())
        return "\n".join(lines)

    def _expand_auto_signals(
        self, content: str, file_path: str, tag_name: str, signal_type: str
    ) -> str:
        """Shared helper: expand AUTOWIRE or AUTOLOGIC."""
        tag_regex = rf"(/\*{tag_name}\*/)"
        regex = re.compile(
            tag_regex + r"(\s*// Beginning.*?// End of automatics)?",
            re.DOTALL | re.IGNORECASE,
        )

        match = self._first_unmasked_match(content, regex)
        if match is None:
            return content

        print(f"Found {tag_name} in {file_path}")

        tag, existing_block = match.groups()
        content_for_signals = content.replace(existing_block or "", "")
        insts = self.project.parser.get_instantiations(content, file_path)
        new_signals = self._collect_auto_decls(
            content_for_signals, insts, "output", signal_type, semicolon=True
        )
        for decl in new_signals:
            print(f"  {tag_name}: {decl}")

        if not new_signals:
            return self._splice(content, match, tag)

        # Format the output
        signals_str = "\n    ".join(new_signals)
        comment_type = "wires" if signal_type == "wire" else "logic"
        replacement = (
            f"/*{tag_name}*/\n    // Beginning of automatic {comment_type} \n"
            f"    {signals_str}\n    // End of automatics"
        )

        return self._splice(content, match, replacement)

    def expand_autowire(self, content: str, file_path: str) -> str:
        """Expand /*AUTOWIRE*/."""
        return self._expand_auto_signals(content, file_path, "AUTOWIRE", "wire")

    def expand_autologic(self, content: str, file_path: str) -> str:
        """Expand /*AUTOLOGIC*/."""
        return self._expand_auto_signals(content, file_path, "AUTOLOGIC", "logic")

    def _collect_auto_decls(
        self,
        content_for_signals: str,
        insts: list,
        filter_direction: str,
        emit_keyword: str,
        semicolon: bool,
        check_manual_widths: bool = False,
    ) -> list:
        """Build declarations for sub-instance ports matching *filter_direction*.

        Skips signals already declared locally.  When *check_manual_widths* is
        True, also warns when a manually declared port has a different width than
        the driving sub-instance port.
        """
        local_signals = self.project.parser.get_local_signals(content_for_signals, "")

        manual_decls: Dict[str, str] = {}
        if check_manual_widths:
            for p_match in self.project.parser.port_re.finditer(
                self._strip_comments(content_for_signals)
            ):
                if p_match.group(1) == filter_direction:
                    for name in self.project.parser._port_names(p_match.group(4)):
                        manual_decls[name] = p_match.group(3) or ""

        suffix = ";" if semicolon else ""
        decls: list = []
        for inst in insts:
            module_def = self.project.modules.get(inst["module_name"])
            if not module_def:
                continue
            for p_name, s_name in inst["ports"].items():
                p_def = next(
                    (p for p in module_def.ports if p.name == p_name), None
                )
                if not (p_def and p_def.direction == filter_direction):
                    continue
                base = s_name.split("[")[0].strip()
                # Skip constants/literals/expressions (e.g. 1'b0, {a, b}, func(x));
                # only a real net identifier can be propagated up.
                if not re.match(r"^[A-Za-z_]\w*$", base):
                    continue
                if base not in local_signals:
                    width = f"{p_def.width} " if p_def.width else ""
                    decl = f"{emit_keyword} {width}{base}{suffix}"
                    if decl not in decls:
                        decls.append(decl)
                        local_signals.add(base)
                elif check_manual_widths and base in manual_decls and _widths_mismatch(
                    p_def.width, manual_decls[base]
                ):
                    print(
                        f"Warning: Width mismatch for manual {filter_direction} '{base}'. "
                        f"Target port '{p_name}' of module '{inst['module_name']}' "
                        f"has '{p_def.width}', manual decl has '{manual_decls[base]}'."
                    )
        return decls

    def _expand_auto_port(
        self, content: str, file_path: str, tag_name: str, direction: str
    ) -> str:
        """Generic expander for /*AUTOINPUT*/ or /*AUTOOUTPUT*/.
        Handles both ANSI (port list) and Non-ANSI (body) contexts."""
        # 1. ANSI port list context
        ansi_regex = re.compile(
            rf"(\bmodule\s+(\w+)\s*)(#\s*\(.*?\))?\s*\(([^;]*?(/\*{tag_name}\*/)[^;]*?)\)\s*;",
            re.DOTALL | re.IGNORECASE,
        )
        ansi_match = self._first_unmasked_match(content, ansi_regex)

        if ansi_match:
            mod_start, mod_name, params, port_block, tag = ansi_match.groups()
            print(f"Found {tag_name} in port list of {mod_name}")

            tag_index = port_block.find(tag)
            before = port_block[:tag_index].strip()
            after_raw = port_block[tag_index + len(tag) :]
            # Idempotency: a previous run leaves a `// Beginning … // End of
            # automatics` block right after the tag. Strip it before recomputing
            # so a re-run replaces the block instead of nesting a new one.
            block_match = re.match(
                r"\s*// Beginning of automatic \w+.*?// End of automatics",
                after_raw,
                re.DOTALL,
            )
            existing_block = block_match.group(0) if block_match else ""
            # Manual ports written after the tag; drop the leading separating
            # comma so we can re-emit them on their own line below the block.
            after = after_raw[len(existing_block) :].strip().lstrip(",").strip()

            content_for_signals = content.replace(tag, "")
            if existing_block:
                content_for_signals = content_for_signals.replace(existing_block, "")

            insts = self.project.parser.get_instantiations(content, file_path)
            new_decls = self._collect_auto_decls(
                content_for_signals, insts, direction, direction,
                semicolon=False, check_manual_widths=True,
            )

            head = port_block[:tag_index]
            if not new_decls:
                # Nothing to add: bare tag, keep any trailing manual ports.
                new_port_block = f"{head}{tag}" + (f", {after}" if after else "")
            else:
                # Keep the tag and wrap the generated decls in the same Emacs
                # `// Beginning … // End of automatics` markers the body form
                # uses, so `--delete` (_AUTO_SIGNAL_BLOCK_RE) can reverse it.
                # Trailing manual ports go on their own line so the End-of-
                # automatics comment does not swallow them.
                comment_type = "inputs" if direction == "input" else "outputs"
                decls = ",\n    ".join(new_decls)
                decls = self._apply_comma_context(decls, before, "")
                if after and not decls.rstrip().endswith(","):
                    decls = decls.rstrip() + ","
                lines = [
                    tag,
                    f"    // Beginning of automatic {comment_type}",
                    f"    {decls}",
                    "    // End of automatics",
                ]
                if after:
                    lines.append(f"    {after}")
                new_port_block = head + "\n".join(lines)

            header = mod_start.rstrip()
            if params:
                header += " " + params.strip()
            replacement = f"{header} ({new_port_block.rstrip()}\n);"
            return self._splice(content, ansi_match, replacement)

        # 2. Non-ANSI body context
        body_regex = re.compile(
            rf"(/\*{tag_name}\*/)(\s*// Beginning.*?// End of automatics)?",
            re.DOTALL | re.IGNORECASE,
        )
        match = self._first_unmasked_match(content, body_regex)
        if match is None:
            return content

        print(f"Found {tag_name} in body of {file_path}")
        tag, existing_block = match.groups()
        content_for_signals = content.replace(existing_block or "", "")

        insts = self.project.parser.get_instantiations(content, file_path)
        new_decls = self._collect_auto_decls(
            content_for_signals, insts, direction, direction,
            semicolon=True, check_manual_widths=True,
        )

        if not new_decls:
            return self._splice(content, match, tag)

        comment_type = "inputs" if direction == "input" else "outputs"
        block_content = "\n    ".join(new_decls)
        replacement = (
            f"/*{tag_name}*/\n    // Beginning of automatic {comment_type}\n"
            f"    {block_content}\n    // End of automatics"
        )
        return self._splice(content, match, replacement)

    def expand_autoinput(self, content: str, file_path: str) -> str:
        """Expand /*AUTOINPUT*/."""
        return self._expand_auto_port(content, file_path, "AUTOINPUT", "input")

    def expand_autooutput(self, content: str, file_path: str) -> str:
        """Expand /*AUTOOUTPUT*/."""
        return self._expand_auto_port(content, file_path, "AUTOOUTPUT", "output")

    def expand_autosense(self, content: str, file_path: str) -> str:
        """
        Expands /*AUTOSENSE*/ in always blocks.
        """
        # Match always @(...)
        # Pattern captures:
        # 1: "always @("
        # 2: Content of parens (containing /*AUTOSENSE*/)
        # 3: ")"
        pattern = re.compile(
            r"(always\s*@\s*)\(([^)]*/\*AUTOSENSE\*/[^)]*)\)",
            re.DOTALL | re.IGNORECASE,
        )

        # Get local signals for filtering
        local_signals = self.project.parser.get_local_signals(content, file_path)

        def replace_fn(match):
            prefix, paren_content = match.groups()
            tag = "/*AUTOSENSE*/"

            # Find the start of the body in the original content
            body_start = match.end()
            body = self._extract_always_block_body(content, body_start)

            # Clean body for signal extraction
            clean_body = self._strip_comments(body)
            # Find all identifiers
            all_ids = set(re.findall(r"\b([a-zA-Z_]\w*)\b", clean_body))

            # Filter unique signals that exist in project and aren't keywords
            detected_sigs = set()
            for name in all_ids:
                if name in local_signals and name not in _AUTOSENSE_KEYWORDS:
                    if self._signal_is_read(name, clean_body):
                        detected_sigs.add(name)

            if not detected_sigs:
                return match.group(0)

            sorted_sigs = sorted(list(detected_sigs))
            sig_list = " or ".join(sorted_sigs)

            # Replace the tag *and any previously-generated list that follows
            # it* with the freshly detected signals. Discarding the old trailing
            # content keeps AUTOSENSE idempotent — re-running must replace the
            # list, not accumulate duplicates after the tag.
            new_paren = re.sub(
                r"/\*AUTOSENSE\*/.*",
                f"/*AUTOSENSE*/{sig_list}",
                paren_content,
                flags=re.IGNORECASE | re.DOTALL,
            )

            print(f"  AUTOSENSE: Found signals {sorted_sigs}")
            return f"{prefix}({new_paren})"

        # Scan masked content so commented-out `always @(/*AUTOSENSE*/...)`
        # blocks are ignored, matching AUTOINST's comment-safe behavior.
        return self._apply_masked_replacements(content, pattern, replace_fn)

    def _extract_always_block_body(self, full_content, start_pos):
        """Extract the body of the always block starting after 'always @(...)'.
        For a `begin ... end` body, balance begin/case/fork against
        end/endcase/join; otherwise take up to the first ';'."""
        body_candidate = full_content[start_pos:].strip()
        if body_candidate.startswith("begin"):
            stack = 0
            for m in re.finditer(
                r"\b(begin|end|case|endcase|fork|join)\b", body_candidate
            ):
                kw = m.group(1)
                if kw in ("begin", "case", "fork"):
                    stack += 1
                elif kw in ("end", "endcase", "join"):
                    stack -= 1

                if stack == 0:
                    return body_candidate[: m.end()]
        else:
            # Single statement, find first ';'
            idx = body_candidate.find(";")
            if idx != -1:
                return body_candidate[: idx + 1]
        return body_candidate

    def _signal_is_read(self, name, clean_body):
        """Heuristic: True if `name` appears in an always-block body as a read
        (RHS / condition), not purely on the LHS of a blocking (=) or
        non-blocking (<=) assignment. A bus index (`name[...]`) is skipped before
        inspecting what follows, so `name[i] = ...` still counts as a write."""
        for m in re.finditer(rf"\b{name}\b", clean_body):
            suffix = clean_body[m.end() :].lstrip()
            if suffix.startswith("["):
                bracket_stack = 0
                skip_idx = 0
                for char in suffix:
                    if char == "[":
                        bracket_stack += 1
                    elif char == "]":
                        bracket_stack -= 1
                    skip_idx += 1
                    if bracket_stack == 0:
                        break
                suffix = suffix[skip_idx:].lstrip()

            is_blocking_assign = suffix.startswith("=") and not suffix.startswith("==")
            is_nonblocking_assign = suffix.startswith("<=") and not suffix.startswith("<==")
            if not (is_blocking_assign or is_nonblocking_assign):
                return True
        return False

    def expand_module_block(self, content: str, file_path: str) -> str:
        """Expands all tags within a single module block."""
        content = self.expand_autoinst(content)
        content = self.expand_autoinput(content, file_path)
        content = self.expand_autooutput(content, file_path)
        content = self.expand_autowire(content, file_path)
        content = self.expand_autologic(content, file_path)
        content = self.expand_autosense(content, file_path)
        content = self.expand_autoarg(content, file_path)
        return content

    def _per_module_block(self, content, file_path, block_fn):
        """Apply block_fn(block_text, file_path) to each module…endmodule block."""
        return _MODULE_BLOCK_RE.sub(
            lambda m: block_fn(m.group(0), file_path), content
        )

    def expand_all(self, content: str, file_path: str = "") -> str:
        return self._per_module_block(content, file_path, self.expand_module_block)

    def delete_all(self, content: str, file_path: str = "") -> str:
        """Un-expand: for each module block, remove auto-generated content, leaving the bare tags."""
        return self._per_module_block(content, file_path, self.delete_module_block)

    def delete_module_block(self, content: str, file_path: str) -> str:
        """Reverse every AUTO expansion within a single module block."""
        content = self._delete_autoinst(content)
        # AUTOWIRE/AUTOLOGIC/AUTOINPUT/AUTOOUTPUT — both body form and ANSI
        # header form keep the tag and wrap decls in a // Beginning … // End
        # block, so a single sub drops the block and restores the bare tag. The
        # block's presence is itself proof of a real expansion, so commented-out
        # tags (which have no such block) are left alone — no masking needed here.
        content = _AUTO_SIGNAL_BLOCK_RE.sub(lambda m: m.group(1), content)
        content = self._delete_autosense(content)
        # AUTOARG keeps its tag after expansion, so its header list is un-expanded
        # here (the block sub above only touches the marker-wrapped forms).
        content = self._delete_header_tag(content, "AUTOARG")
        return content

    def _delete_autoinst(self, content):
        """Reverse /*AUTOINST*/: keep manual connections written before the tag,
        drop the auto-generated connections after it (up to the instance ')')."""
        pattern = re.compile(
            r"(\w+)\s+(\w+)\s*(#\s*\(.*?\))?\s*\(([^;]*?(/\*AUTOINST\*/)[^;]*?)\)\s*;",
            re.DOTALL | re.IGNORECASE,
        )

        def replace_fn(match):
            if match.group(1) in _INST_SKIP_KEYWORDS:
                return match.group(0)
            port_block = match.group(4)
            tag = match.group(5)
            tag_end = port_block.find(tag) + len(tag)
            after = port_block[tag_end:]
            # Drop the auto content after the tag, keeping only the ')' line's indentation (from the last newline).
            trailing = after[after.rfind("\n") :] if "\n" in after else ""
            new_block = port_block[:tag_end] + trailing
            return match.group(0).replace(port_block, new_block, 1)

        return self._apply_masked_replacements(content, pattern, replace_fn)

    def _delete_header_tag(self, content, tag_name):
        """Reverse a header-context tag (AUTOARG / ANSI AUTOINPUT / AUTOOUTPUT):
        keep manual ports before the tag, drop the auto-generated list, and
        rebuild the header like the matching expander does."""
        regex = re.compile(
            rf"(\bmodule\s+(\w+)\s*)(#\s*\(.*?\))?\s*\(([^;]*?(/\*{tag_name}\*/)[^;]*?)\)\s*;",
            re.DOTALL | re.IGNORECASE,
        )
        match = self._first_unmasked_match(content, regex)
        if match is None:
            return content
        mod_start, _name, params, port_block, tag = match.groups()
        head = port_block[: port_block.find(tag)]
        new_port_block = (head + tag).rstrip()
        header = mod_start.rstrip()
        if params:
            header += " " + params.strip()
        return self._splice(content, match, f"{header} ({new_port_block}\n);")

    def _delete_autosense(self, content):
        """Reverse /*AUTOSENSE*/: drop the auto-filled sensitivity signals after
        the tag, leaving `always @(/*AUTOSENSE*/)`."""
        pattern = re.compile(
            r"(always\s*@\s*)\(([^)]*/\*AUTOSENSE\*/[^)]*)\)",
            re.DOTALL | re.IGNORECASE,
        )

        def replace_fn(match):
            prefix, paren = match.groups()
            tag = "/*AUTOSENSE*/"
            new_paren = paren[: paren.find(tag)] + tag
            return f"{prefix}({new_paren})"

        return self._apply_masked_replacements(content, pattern, replace_fn)


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("files", nargs="+")
        parser.add_argument(
            "--delete",
            "-k",
            action="store_true",
            help="Un-expand: strip auto-generated content, leaving only the bare tags (no expansion).",
        )
        parser.add_argument(
            "--incdir",
            action="append",
            default=[],
            metavar="DIR",
            help="Extra directory to search for sub-module definitions (repeatable).",
        )
        args = parser.parse_args()

        project = VerilogProject()
        expander = VerilogExpander(project)

        for fpath in args.files:
            if not os.path.exists(fpath):
                print(f"Skip: {fpath} (not found)")
                continue

            with open(fpath, "r", encoding="utf-8", newline="") as f:
                content = f.read()

            if not args.delete:
                # Resolve only the sub-modules THIS file instantiates, searching
                # the file's own directory plus any --incdir dirs.
                needed = {
                    inst["module_name"]
                    for inst in project.parser.get_instantiations(content, fpath)
                }
                roots = [os.path.dirname(fpath) or "."] + args.incdir
                project.resolve(roots, needed)

            print(f"{'Deleting' if args.delete else 'Expanding'}: {fpath}")
            transform = expander.delete_all if args.delete else expander.expand_all
            new_content = transform(content, fpath)

            if new_content != content:
                with open(fpath, "w", encoding="utf-8", newline="") as f:
                    f.write(new_content)
                print(f"Successfully {'deleted' if args.delete else 'expanded'} {fpath}")
            else:
                print(f"No changes made to {fpath}")

    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
