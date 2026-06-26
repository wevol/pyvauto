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
        self.port_re = re.compile(
            r"(input|output|inout)\s+(?:(logic|reg|wire)\s+)?(?:(\[.*?\])\s+)?(\w+)",
            re.MULTILINE,
        )

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
                module.ports.append(
                    VerilogPort(
                        name=p_match.group(4),
                        direction=p_match.group(1),
                        port_type=p_match.group(2) or "wire",
                        width=p_match.group(3) or "",
                    )
                )

            # 2. Parse ports from body (Non-ANSI style or mixed)
            if module_body:
                for p_match in self.port_re.finditer(module_body):
                    p_name = p_match.group(4)
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

    def add_directory(self, path: str):
        print(f"Indexing directory: {os.path.abspath(path)}")
        for root, _, files in os.walk(path):
            for file in files:
                if (
                    file.endswith((".v", ".sv")) and file != "test_top.sv"
                ):  # Avoid indexing top as sub
                    full_path = os.path.join(root, file)
                    try:
                        with open(
                            full_path,
                            "r",
                            encoding="utf-8",
                            errors="ignore",
                            newline="",
                        ) as f:
                            mods = self.parser.parse_file(f.read(), full_path)
                            for m in mods:
                                print(f"  Found module: {m.name}")
                                self.modules[m.name] = m
                    except Exception as e:
                        print(f"Error reading {full_path}: {e}")


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

            # Validation of manual connections
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

            ports_to_expand = [p for p in module.ports if p.name not in existing_ports]

            if not ports_to_expand:
                return match.group(0)
            else:
                # Group ports by direction
                outputs = [p for p in ports_to_expand if p.direction == "output"]
                inouts = [p for p in ports_to_expand if p.direction == "inout"]
                inputs = [p for p in ports_to_expand if p.direction == "input"]
                others = [
                    p
                    for p in ports_to_expand
                    if p.direction not in ["output", "input", "inout"]
                ]

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

                if outputs:
                    lines.append("    // Outputs")
                    for p in outputs:
                        lines.append(format_p(p))

                if inouts:
                    lines.append("    // Inouts")
                    for p in inouts:
                        lines.append(format_p(p))

                if inputs:
                    lines.append("    // Inputs")
                    for p in inputs:
                        lines.append(format_p(p))

                for p in others:
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

                port_str = "\n".join(lines)

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

        # Run the match scan on masked content so instantiations inside
        # comments don't get expanded, while using the ORIGINAL content
        # for group extraction via byte offsets (_mask_comments preserves
        # layout, so offsets line up).
        masked = self._mask_comments(content)
        replacements = []
        for match in pattern.finditer(masked):
            # Re-match against original content at the same offsets to recover
            # real group text (comments inside values would be blanks otherwise).
            real_match = pattern.match(content, match.start())
            if real_match is None:
                continue
            replacements.append((match.start(), match.end(), replace_fn(real_match)))

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

        match = regex.search(content)
        if not match:
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

        # Detect ANSI mode: if the port block already contains direction keywords
        # Scan entire port_block for existing ports
        is_ansi = bool(re.search(r"\b(input|output|inout)\b", port_block))

        # Identify existing ports in the header port list
        existing_ports = set()
        # For ANSI, we need to extract names from 'direction [width] name'
        # For Non-ANSI, it's just 'name'
        if is_ansi:
            for p_match in self.project.parser.port_re.finditer(
                self._strip_comments(port_block)
            ):
                existing_ports.add(p_match.group(4))
        else:
            # Remove the tag before splitting
            clean_block = port_block.replace(autoarg_tag, "")
            clean_block = self._strip_comments(clean_block)
            for p in re.split(r",", clean_block):
                p_name = p.strip()
                if p_name:
                    existing_ports.add(p_name)

        # Validation of manual ports in header
        for p_name in existing_ports:
            if not any(p.name == p_name for p in module.ports):
                print(
                    f"Warning: Port '{p_name}' listed in AUTOARG header does not exist in module '{target_mod_name}'."
                )

        # Filter ports to expand
        ports_to_expand = [p for p in module.ports if p.name not in existing_ports]

        # Formatting
        indent = "    "
        limit = 80

        def wrap_lines(items, indent_str, limit=80):
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

        if not ports_to_expand:
            arg_list = ""
        elif is_ansi:
            # ANSI Mode: Generate full declarations, each on a new line
            decls = []
            for p in ports_to_expand:
                width = f"{p.width} " if p.width else ""
                decls.append(f"{p.direction} {width}{p.name}")
            arg_list = ",\n    ".join(decls)
        else:
            # Non-ANSI Mode: Names only, wrapped to 80 chars
            names = [p.name for p in ports_to_expand]
            arg_list = wrap_lines(names, indent, limit)

        tag_index = port_block.find(autoarg_tag)
        before_tag = port_block[:tag_index].strip()
        after_tag = port_block[tag_index + len(autoarg_tag) :].strip()
        arg_list = self._apply_comma_context(arg_list, before_tag, after_tag)

        # Construct replacement: just the tag + new content, no block markers
        if arg_list.strip():
            replacement_block = f"/*AUTOARG*/\n    {arg_list}"
        else:
            replacement_block = "/*AUTOARG*/"

        new_port_block = port_block.replace(autoarg_tag, replacement_block)
        # Clean up trailing comma
        new_port_block = re.sub(r",(\s*)$", r"\1", new_port_block)

        # rstrip mod_start and new_port_block: the regexes captured trailing
        # whitespace/newlines that would accumulate and break idempotency.
        header = mod_start.rstrip()
        if params:
            header += " " + params.strip()
        replacement = f"{header} ({new_port_block.rstrip()}\n);"
        return content[: match.start()] + replacement + content[match.end() :]

    def _expand_auto_signals(
        self, content: str, file_path: str, tag_name: str, signal_type: str
    ) -> str:
        """通用函數：擴展 AUTOWIRE 或 AUTOLOGIC"""
        tag_regex = rf"(/\*{tag_name}\*/)"
        regex = re.compile(
            tag_regex + r"(\s*// Beginning.*?// End of automatics)?",
            re.DOTALL | re.IGNORECASE,
        )

        match = regex.search(content)
        if not match:
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
            return content[: match.start()] + tag + content[match.end() :]

        # 格式化輸出
        signals_str = "\n    ".join(new_signals)
        comment_type = "wires" if signal_type == "wire" else "logic"
        replacement = (
            f"/*{tag_name}*/\n    // Beginning of automatic {comment_type} \n"
            f"    {signals_str}\n    // End of automatics"
        )

        return content[: match.start()] + replacement + content[match.end() :]

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
                    manual_decls[p_match.group(4)] = p_match.group(3) or ""

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
        ansi_match = ansi_regex.search(content)

        if ansi_match:
            mod_start, mod_name, params, port_block, tag = ansi_match.groups()
            print(f"Found {tag_name} in port list of {mod_name}")

            insts = self.project.parser.get_instantiations(content, file_path)
            new_decls = self._collect_auto_decls(
                content.replace(tag, ""), insts, direction, direction,
                semicolon=False, check_manual_widths=True,
            )

            if not new_decls:
                return (
                    content[: ansi_match.start()]
                    + ansi_match.group(0).replace(tag, "")
                    + content[ansi_match.end() :]
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
            return (
                content[: ansi_match.start()]
                + replacement
                + content[ansi_match.end() :]
            )

        # 2. Non-ANSI body context
        body_regex = re.compile(
            rf"(/\*{tag_name}\*/)(\s*// Beginning.*?// End of automatics)?",
            re.DOTALL | re.IGNORECASE,
        )
        match = body_regex.search(content)
        if not match:
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
            return content[: match.start()] + tag + content[match.end() :]

        comment_type = "inputs" if direction == "input" else "outputs"
        block_content = "\n    ".join(new_decls)
        replacement = (
            f"/*{tag_name}*/\n    // Beginning of automatic {comment_type}\n"
            f"    {block_content}\n    // End of automatics"
        )
        return content[: match.start()] + replacement + content[match.end() :]

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

        # Verilog keywords to ignore
        keywords = {
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

        def get_block_body(full_content, start_pos):
            """Extracts the body of the always block starting after 'always @(...)'"""
            body_candidate = full_content[start_pos:].strip()
            if body_candidate.startswith("begin"):
                # Find matching 'end'
                # Simple counter-based approach (ignoring strings/comments for now,
                # though _strip_comments could be used)
                clean_candidate = self._strip_comments(body_candidate)
                # But we need positions in original text.
                # Let's just find keywords in the original text.
                stack = 0
                # Use regex to find block boundaries
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

        def replace_fn(match):
            prefix, paren_content = match.groups()
            tag = "/*AUTOSENSE*/"

            # Find the start of the body in the original content
            body_start = match.end()
            body = get_block_body(content, body_start)

            # Clean body for signal extraction
            clean_body = self._strip_comments(body)
            # Find all identifiers
            all_ids = set(re.findall(r"\b([a-zA-Z_]\w*)\b", clean_body))

            # Filter unique signals that exist in project and aren't keywords
            detected_sigs = set()
            for name in all_ids:
                if name in local_signals and name not in keywords:
                    # Check if it's only used as LHS
                    all_matches = list(re.finditer(rf"\b{name}\b", clean_body))
                    is_read = False
                    for m in all_matches:
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
                            is_read = True
                            break
                    if is_read:
                        detected_sigs.add(name)

            if not detected_sigs:
                return match.group(0)

            sorted_sigs = sorted(list(detected_sigs))
            sig_list = " or ".join(sorted_sigs)

            # Replace tag with tag + signal list (case-insensitive replacement)
            # We normalize to uppercase tag in the output
            new_paren = re.sub(
                r"/\*AUTOSENSE\*/",
                f"/*AUTOSENSE*/{sig_list}",
                paren_content,
                flags=re.IGNORECASE,
            )

            print(f"  AUTOSENSE: Found signals {sorted_sigs}")
            return f"{prefix}({new_paren})"

        return pattern.sub(replace_fn, content)

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

    def expand_all(self, content: str, file_path: str = "") -> str:
        # Find all module ... endmodule blocks
        # Pattern to capture module block including everything until endmodule
        pattern = re.compile(
            r"^[\t ]*module\s+\w+.*?\bendmodule\b",
            re.DOTALL | re.IGNORECASE | re.MULTILINE,
        )

        def replace_fn(match):
            block_text = match.group(0)
            return self.expand_module_block(block_text, file_path)

        return pattern.sub(replace_fn, content)


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("files", nargs="+")
        args = parser.parse_args()

        project = VerilogProject()
        project.add_directory(".")

        expander = VerilogExpander(project)

        for fpath in args.files:
            if not os.path.exists(fpath):
                print(f"Skip: {fpath} (not found)")
                continue

            print(f"Expanding: {fpath}")
            with open(fpath, "r", encoding="utf-8", newline="") as f:
                content = f.read()

            new_content = expander.expand_all(content, fpath)

            if new_content != content:
                with open(fpath, "w", encoding="utf-8", newline="") as f:
                    f.write(new_content)
                print(f"Successfully expanded {fpath}")
            else:
                print(f"No changes made to {fpath}")

    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
