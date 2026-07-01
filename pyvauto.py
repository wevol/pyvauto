import re
import os
import argparse
import sys
import traceback
from typing import Optional, Dict, List, Set


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


_TYPE_DECL_RE = re.compile(
    r"\b(wire|reg|logic|integer|bit|real|byte|shortint|int|longint)\b\s+(\[.*?\]\s+)?([\w\s,]+);",
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
# Verilog 解析器類別 (原 parser.py 的內容)
# ============================================================================


class VerilogPort:
    """Verilog 埠口定義"""

    def __init__(
        self, name: str, direction: str, width: str = "", port_type: str = "wire"
    ):
        self.name = name
        self.direction = direction
        self.width = width
        self.port_type = port_type


class VerilogModule:
    """Verilog 模組定義"""

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
    """基於正則表達式的 Verilog 解析器"""

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
        self.port_re = re.compile(
            r"(input|output|inout)\s+(?:(logic|reg|wire)\s+)?(?:(\[.*?\])\s+)?"
            r"(\w+(?:\s*,\s*(?!input\b|output\b|inout\b)\w+)*)",
            re.MULTILINE,
        )

    @staticmethod
    def _port_names(name_group: str) -> List[str]:
        """Split a port_re group(4) match into individual port names,
        e.g. 'clk, rst_n,\\n en' -> ['clk', 'rst_n', 'en']."""
        return [n.strip() for n in name_group.split(",")]

    def parse_file(self, content: str, file_path: str = "") -> List:
        """解析 Verilog 檔案內容並返回模組列表"""
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
        """提取 Verilog 實例化資訊"""
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
        """提取區域訊號定義（含 ports、parameters、wire/reg/logic 宣告）"""
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
        """提取區域訊號與其位寬對映（找不到或無位寬則為空字串）"""
        widths: Dict[str, str] = {}
        content_no_comments = strip_comments_safely(content)

        for mod in self.parse_file(content, file_path):
            for p in mod.ports:
                widths.setdefault(p.name, p.width or "")

        for name, width in _scan_type_decls(content_no_comments).items():
            widths.setdefault(name, width)

        return widths


# ============================================================================
# Verilog 專案與擴展器類別
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
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith((".v", ".sv")) and file != "test_top.sv":
                    self._index_file(os.path.join(root, file))

    def resolve(self, path: str, needed: Set[str]) -> None:
        """Index only the modules in `needed` (plus any co-located in the
        same files), parsing as few files as possible. Module names are
        globally unique, so first-found wins."""
        pending = set(needed)
        if not pending:
            return

        # One cheap directory listing — file names only, no reads/parsing.
        candidates = []                  # all candidate .v/.sv paths
        by_basename = {}                 # '<name>' -> path, for the fast-path
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith((".v", ".sv")) and file != "test_top.sv":
                    full = os.path.join(root, file)
                    candidates.append(full)
                    by_basename.setdefault(os.path.splitext(file)[0], full)

        print(f"Resolving {len(pending)} module(s) under {os.path.abspath(path)}")
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

            # Find already connected ports and their signals
            # Search ENTIRE port_block so we don't duplicate previously auto-generated ports

            clean_block = self._strip_comments(port_block)
            manual_conns = parse_named_port_connections(clean_block)

            existing_ports = set(manual_conns.keys())
            self._warn_manual_connection_widths(
                module, manual_conns, mod_name, inst_name
            )

            ports_to_expand = [p for p in module.ports if p.name not in existing_ports]

            if not ports_to_expand:
                return match.group(0)

            port_str = self._build_autoinst_port_lines(
                ports_to_expand, mod_name, local_widths, port_block, autoinst_tag
            )

            # Construct replacement: just the tag + new content, no block markers
            # Handle leading comma if needed
            tag_index = port_block.find(autoinst_tag)
            before_tag = port_block[:tag_index].strip()
            port_str = self._apply_comma_context(port_str, before_tag, "")

            replacement = f"/*AUTOINST*/\n{port_str}"

            new_port_block = port_block.replace(autoinst_tag, replacement)

            # Clean up trailing comma: check global port list context
            # This is tricky because we just built the block.
            # If we rely on the previous logic: new_port_block = re.sub(r",(\s*)$", r"\1", new_port_block)
            # This cleans comma at end of the WHOLE port block list.
            new_port_block = re.sub(r",(\s*)$", r"\1", new_port_block)
            # Collapse accidental double commas introduced when surrounding manual
            # connections already had their own commas.
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
        self, ports_to_expand, mod_name, local_widths, port_block, autoinst_tag
    ):
        """Render the auto-generated /*AUTOINST*/ port connections: group by
        direction, add commas, and append width-mismatch warning comments."""
        lines = []
        # Track warning-comment suffixes keyed by line index so that any
        # later comma-insertion step puts the comma BEFORE the comment.
        line_warnings: Dict[int, str] = {}

        def format_p(p):
            padding = " "
            width_str = p.width if p.width else ""
            line = f"    .{p.name}{padding}({p.name}{width_str})"
            local_w = local_widths.get(p.name, "")
            if _widths_mismatch(p.width, local_w):
                line_warnings[len(lines)] = (
                    f"  // WARNING: width mismatch — "
                    f"{mod_name}.{p.name} is {p.width}, local {p.name} is {local_w}"
                )
            return line

        # Grouped directions first, each under its header, then any others
        # in original order.
        for direction, header in (
            ("output", "    // Outputs"),
            ("inout", "    // Inouts"),
            ("input", "    // Inputs"),
        ):
            members = [p for p in ports_to_expand if p.direction == direction]
            if members:
                lines.append(header)
                for p in members:
                    lines.append(format_p(p))

        for p in ports_to_expand:
            if p.direction not in ("output", "inout", "input"):
                lines.append(format_p(p))

        # Add commas to port lines
        port_indices = [
            i for i, line in enumerate(lines) if line.strip().startswith(".")
        ]

        if port_indices:
            # Add comma to all except last port
            for i in port_indices[:-1]:
                lines[i] += ","

            # Logic for trailing comma: if there is content after the tag, add comma
            tag_index = port_block.find(autoinst_tag)
            after_tag = port_block[tag_index + len(autoinst_tag) :].strip()

            if after_tag and not after_tag.startswith(","):
                lines[port_indices[-1]] += ","

        # Append warning comments AFTER comma-insertion so the comma
        # stays part of the port list and is not swallowed by the comment.
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
        wrapped to 80 columns."""
        if not ports_to_expand:
            return ""
        if is_ansi:
            # ANSI Mode: full declarations ('direction [width] name'), one per line
            decls = [
                f"{p.direction} {f'{p.width} ' if p.width else ''}{p.name}"
                for p in ports_to_expand
            ]
            return ",\n    ".join(decls)

        # Non-ANSI Mode: Names only, wrapped to 80 chars
        names = [p.name for p in ports_to_expand]
        return self._wrap_names(names, "    ")

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
        """通用函數：擴展 AUTOWIRE 或 AUTOLOGIC"""
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

        # 格式化輸出
        signals_str = "\n    ".join(new_signals)
        comment_type = "wires" if signal_type == "wire" else "logic"
        replacement = (
            f"/*{tag_name}*/\n    // Beginning of automatic {comment_type} \n"
            f"    {signals_str}\n    // End of automatics"
        )

        return self._splice(content, match, replacement)

    def expand_autowire(self, content: str, file_path: str) -> str:
        """擴展 /*AUTOWIRE*/"""
        return self._expand_auto_signals(content, file_path, "AUTOWIRE", "wire")

    def expand_autologic(self, content: str, file_path: str) -> str:
        """擴展 /*AUTOLOGIC*/"""
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

            insts = self.project.parser.get_instantiations(content, file_path)
            new_decls = self._collect_auto_decls(
                content.replace(tag, ""), insts, direction, direction,
                semicolon=False, check_manual_widths=True,
            )

            if not new_decls:
                return self._splice(
                    content, ansi_match, ansi_match.group(0).replace(tag, "")
                )

            tag_index = port_block.find(tag)
            before = port_block[:tag_index].strip()
            after = port_block[tag_index + len(tag) :].strip()

            block = ",\n    ".join(new_decls)
            block = self._apply_comma_context(block, before, after)

            new_port_block = port_block.replace(tag, block)
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
        """擴展 /*AUTOINPUT*/"""
        return self._expand_auto_port(content, file_path, "AUTOINPUT", "input")

    def expand_autooutput(self, content: str, file_path: str) -> str:
        """擴展 /*AUTOOUTPUT*/"""
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
        """反展開：對每個 module block 移除自動產生內容，只留裸 tag。"""
        return self._per_module_block(content, file_path, self.delete_module_block)

    def delete_module_block(self, content: str, file_path: str) -> str:
        """Reverse every AUTO expansion within a single module block."""
        content = self._delete_autoinst(content)
        # body-form AUTOWIRE/AUTOLOGIC/AUTOINPUT/AUTOOUTPUT: drop the
        # // Beginning … // End block, keep the bare tag. The block's presence is
        # itself proof of a real expansion, so commented-out tags (which have no
        # such block) are left alone — no masking needed here.
        content = _AUTO_SIGNAL_BLOCK_RE.sub(lambda m: m.group(1), content)
        content = self._delete_autosense(content)
        # AUTOARG keeps its tag after expansion (reversible). ANSI AUTOINPUT/
        # AUTOOUTPUT replace the tag with port decls (tag is gone), so only their
        # body form is reversible — handled by the block sub above.
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
            # 丟棄 tag 後的自動連線，只保留 ')' 那一行的縮排（最後一個換行起）
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
            help="反展開：移除自動產生內容、只留裸 tag（不展開）",
        )
        args = parser.parse_args()

        project = VerilogProject()
        expander = VerilogExpander(project)

        # Index only the sub-modules the target files actually instantiate.
        needed: Set[str] = set()
        for fpath in args.files:
            if not os.path.exists(fpath):
                continue
            with open(fpath, "r", encoding="utf-8", errors="ignore", newline="") as f:
                for inst in project.parser.get_instantiations(f.read(), fpath):
                    needed.add(inst["module_name"])
        project.resolve(".", needed)

        for fpath in args.files:
            if not os.path.exists(fpath):
                print(f"Skip: {fpath} (not found)")
                continue

            print(f"{'Deleting' if args.delete else 'Expanding'}: {fpath}")
            with open(fpath, "r", encoding="utf-8", newline="") as f:
                content = f.read()

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
