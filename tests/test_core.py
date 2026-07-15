"""
Core functionality tests — ensure pyvauto's core logic works correctly.

These tests verify:
1. The parser parses Verilog modules correctly
2. The expander expands the various automation tags correctly
3. Integration: end-to-end processing of Verilog files
"""

import sys
from pathlib import Path

# Add the project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyvauto import (
    VerilogPort,
    VerilogModule,
    RegexVerilogParser,
    VerilogProject,
    VerilogExpander,
)


class TestVerilogParser:
    """Tests for the Verilog parser."""

    def test_parse_simple_module(self):
        """Parse a simple module."""
        parser = RegexVerilogParser()
        content = """
        module simple (
            input clk,
            input rst_n,
            output [7:0] data_out
        );
        endmodule
        """
        modules = parser.parse_file(content, "test.sv")

        assert len(modules) == 1
        assert modules[0].name == "simple"
        assert len(modules[0].ports) == 3

        # Verify the ports
        port_names = [p.name for p in modules[0].ports]
        assert "clk" in port_names
        assert "rst_n" in port_names
        assert "data_out" in port_names

    def test_parse_module_with_parameters(self):
        """Parse a module with parameters."""
        parser = RegexVerilogParser()
        content = """
        module param_mod #(
            parameter WIDTH = 8,
            parameter DEPTH = 16
        )(
            input [WIDTH-1:0] data_in
        );
        endmodule
        """
        modules = parser.parse_file(content, "test.sv")

        assert len(modules) == 1
        assert "WIDTH" in modules[0].parameters
        assert "DEPTH" in modules[0].parameters

    def test_parse_ports_multiple_vars_per_line(self):
        """Multiple comma-separated ports on one line must all be parsed,
        sharing that line's direction and width."""
        parser = RegexVerilogParser()
        content = """
        module marg (/*AUTOARG*/);
            input        clk, rst_n, en;
            output [3:0] x, y;
        endmodule
        """
        mod = parser.parse_file(content, "marg.sv")[0]

        names = [p.name for p in mod.ports]
        assert names == ["clk", "rst_n", "en", "x", "y"]

        by_name = {p.name: p for p in mod.ports}
        assert by_name["rst_n"].direction == "input"
        assert by_name["en"].direction == "input"
        assert by_name["y"].direction == "output"
        # width is shared across the comma list
        assert by_name["x"].width == "[3:0]"
        assert by_name["y"].width == "[3:0]"

    def test_parse_ports_ansi_repeated_direction_not_merged(self):
        """ANSI per-port repeated direction (input a, input b) must not be
        merged by the comma so a following 'input' is taken as a port name."""
        parser = RegexVerilogParser()
        content = "module m (input a, input b, output c);\nendmodule\n"
        mod = parser.parse_file(content, "m.sv")[0]
        assert [p.name for p in mod.ports] == ["a", "b", "c"]

    def test_parse_ports_ansi_shared_direction_comma_list(self):
        """ANSI shared-direction comma list (input a, b, output c, d) is fully collected."""
        parser = RegexVerilogParser()
        content = "module m (input a, b, output c, d);\nendmodule\n"
        mod = parser.parse_file(content, "m.sv")[0]
        assert [p.name for p in mod.ports] == ["a", "b", "c", "d"]


class TestVerilogExpander:
    """Tests for the Verilog expander."""

    def test_expand_autoinst_basic(self):
        """Basic AUTOINST expansion."""
        project = VerilogProject()

        # Add the sub-module definition
        sub_module_content = """
        module sub (
            input clk,
            input [7:0] data_in,
            output [7:0] data_out
        );
        endmodule
        """

        modules = project.parser.parse_file(sub_module_content, "sub.sv")
        for m in modules:
            project.modules[m.name] = m

        # Run the expansion
        expander = VerilogExpander(project)
        top_content = """
        module top;
            sub u_sub (
                /*AUTOINST*/
            );
        endmodule
        """

        result = expander.expand_autoinst(top_content)

        # Verify the result contains the auto-generated port connections (with width info)
        assert ".clk(clk)" in result or ".clk (clk)" in result
        assert "data_in" in result  # signal name is present
        assert "data_out" in result  # signal name is present

    def test_expand_autoarg(self):
        """AUTOARG expansion."""
        project = VerilogProject()
        expander = VerilogExpander(project)

        content = """
        module test_mod (
            /*AUTOARG*/
        );
            input clk;
            input rst_n;
            output [7:0] result;
        endmodule
        """

        result = expander.expand_autoarg(content, "test.sv")

        # Verify the result contains the auto-generated port list
        assert "clk" in result
        assert "rst_n" in result
        assert "result" in result

    def test_expand_autologic(self):
        """AUTOLOGIC expansion."""
        project = VerilogProject()

        # Mock the sub-module
        sub_content = """
        module sub_mod (
            output [15:0] out_sig
        );
        endmodule
        """
        modules = project.parser.parse_file(sub_content, "sub.sv")
        for m in modules:
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top_content = """
        module top;
            /*AUTOLOGIC*/
            
            sub_mod u_sub (
                .out_sig(my_logic_sig)
            );
        endmodule
        """

        result = expander.expand_autologic(top_content, "top.sv")

        assert "logic [15:0] my_logic_sig;" in result

    def _arg_line(self, result):
        """Return the AUTOARG port names (between the tag and ');'),
        excluding // group-header comment lines."""
        start = result.find("/*AUTOARG*/") + len("/*AUTOARG*/")
        end = result.find(");", start)
        region = result[start:end]
        return "\n".join(
            ln for ln in region.splitlines() if not ln.strip().startswith("//")
        )

    def test_autoarg_regenerates_after_port_removed(self):
        """Re-running AUTOARG must drop a port that was deleted from the body."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m (/*AUTOARG*/
                clk, rst_n, en, valid
        );
            input        clk, rst_n;
            output       valid;
        endmodule
        """
        result = expander.expand_autoarg(content, "m.sv")
        args = self._arg_line(result)
        assert "en" not in args
        for name in ("clk", "rst_n", "valid"):
            assert name in args

    def test_autoarg_regenerates_after_port_added(self):
        """New ports appear (grouped: outputs first, then inputs), no stale chunk."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m (/*AUTOARG*/
                clk, valid
        );
            input        clk, rst_n, mode;
            output       valid, busy;
        endmodule
        """
        result = expander.expand_autoarg(content, "m.sv")
        args = self._arg_line(result)
        names = [n.strip() for n in args.split(",") if n.strip()]
        assert names == ["valid", "busy", "clk", "rst_n", "mode"]

    def test_autoarg_groups_by_direction(self):
        """Ports are listed under // Outputs / // Inouts / // Inputs headers,
        outputs first, matching Emacs / AUTOINST grouping."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m (/*AUTOARG*/);
            input        clk;
            output       done;
            inout        bus;
        endmodule
        """
        result = expander.expand_autoarg(content, "m.sv")
        assert "// Outputs" in result
        assert "// Inouts" in result
        assert "// Inputs" in result
        assert (
            result.index("// Outputs")
            < result.index("// Inouts")
            < result.index("// Inputs")
        )
        assert result.index("done") < result.index("bus") < result.index("clk")

    def test_autoarg_handles_no_space_before_bracket(self):
        """`input[7:0] x` / `output[3:0] y` (no space before the bus width) are
        parsed like their spaced forms; `inputxyz` is not mistaken for a port."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m (/*AUTOARG*/);
            input        clk;
            input[7:0]   data_in;
            output[3:0]  data_out;
            wire         inputxyz;
        endmodule
        """
        result = expander.expand_autoarg(content, "m.sv")
        assert "data_in" in result
        assert "data_out" in result
        assert "clk" in result
        # the wire named `inputxyz` must not leak into the port list
        assert "inputxyz" not in result[: result.index("endmodule")].split(");")[0]

    def test_autoarg_handles_no_space_before_bracket_with_type(self):
        """A no-space type keyword — `input wire[7:0] x` / `output reg[3:0] y` —
        is parsed as type+width, not as a port named `wire`/`reg`. Identifiers
        such as `regfile` are not split on the `reg` prefix."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m (/*AUTOARG*/);
            input  wire[7:0] w_in;
            output reg[3:0]  r_out;
            wire regfile;
        endmodule
        """
        result = expander.expand_autoarg(content, "m.sv")
        header = result[: result.index(");")]
        assert "w_in" in header and "r_out" in header
        # the type keywords must not appear as port names
        assert "wire" not in header and "reg" not in header

    def test_autosense_detects_no_space_typed_signals(self):
        """Standalone `wire[7:0] a;` / `reg[3:0] b;` (no space before the width)
        are recognised as local signals, so AUTOSENSE lists them."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = (
            "module m (input clk, output reg q);\n"
            "    wire[7:0] a;\n"
            "    reg[3:0] b;\n"
            "    always @(/*AUTOSENSE*/) q = a[0] & b[0];\n"
            "endmodule\n"
        )
        result = expander.expand_all(content, "m.sv")
        assert "a" in result.split("/*AUTOSENSE*/")[1].split(")")[0]
        assert "b" in result.split("/*AUTOSENSE*/")[1].split(")")[0]

    def test_autoarg_grouped_delete_round_trip(self):
        """Expand (producing grouped comments) then delete returns to a bare
        tag, keeping the manual name before the tag."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m (
            clk,
            /*AUTOARG*/
        );
            input clk;
            input rst_n;
            output valid;
        endmodule
        """
        expanded = expander.expand_autoarg(content, "m.sv")
        assert "// Outputs" in expanded
        deleted = expander.delete_all(expanded, "m.sv")
        assert "// Outputs" not in deleted
        assert "// Inputs" not in deleted
        assert "/*AUTOARG*/" in deleted
        header = deleted[: deleted.find(");")]
        assert "clk" in header

    def test_autoarg_preserves_manual_before_tag(self):
        """A name listed before the tag stays, is not duplicated, and the
        auto region regenerates the rest."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m (
            clk,
            /*AUTOARG*/
        );
            input clk;
            input rst_n;
            output [7:0] data_out;
        endmodule
        """
        result = expander.expand_autoarg(content, "m.sv")
        header = result[: result.find(");")]
        assert header.count("clk") == 1
        for name in ("rst_n", "data_out"):
            assert name in header

    def test_autoarg_regeneration_is_idempotent(self):
        """Two consecutive expands with unchanged ports produce identical text."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m (/*AUTOARG*/);
            input        clk, rst_n;
            output       valid;
        endmodule
        """
        once = expander.expand_autoarg(content, "m.sv")
        twice = expander.expand_autoarg(once, "m.sv")
        assert once == twice

    def test_autoinput_skips_constant_connection(self):
        """A sub input tied to a constant (.clk(1'b0)) must not become a parent input,
        and must not produce a phantom `input 1;`; real nets still propagate."""
        project = VerilogProject()
        sub = "module sub (input clk, input rst_n);\nendmodule\n"
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOINPUT*/
            sub u (.clk(1'b0), .rst_n(my_rst));
        endmodule
        """
        result = expander.expand_autoinput(top, "top.sv")
        assert "input 1'b0;" not in result
        assert "input 1;" not in result
        assert "input my_rst;" in result

    def test_autoinput_keeps_bit_select_base(self):
        """A bit-select connection still propagates its base net."""
        project = VerilogProject()
        sub = "module sub (input sel);\nendmodule\n"
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOINPUT*/
            sub u (.sel(bus[0]));
        endmodule
        """
        result = expander.expand_autoinput(top, "top.sv")
        assert "input bus;" in result

    def test_autowire_skips_non_identifier_connection(self):
        """AUTOWIRE must not declare a wire for a concatenation/expression output
        connection, but still declares one for a real net."""
        project = VerilogProject()
        sub = "module sub (output [7:0] q, output [7:0] r);\nendmodule\n"
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOWIRE*/
            sub u (.q({a, b}), .r(real_net));
        endmodule
        """
        result = expander.expand_autowire(top, "top.sv")
        assert "wire [7:0] {a, b};" not in result
        assert "wire [7:0] real_net;" in result


class TestBugFixes:
    """Regression tests: ensure fixed logic bugs do not resurface."""

    def test_autosense_includes_equality_operands(self):
        """Bug 2: AUTOSENSE must not treat operands of `==` as writes."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m;
            reg state;
            reg idle;
            reg out;
            always @(/*AUTOSENSE*/) begin
                if (state == idle) out = 1'b0;
            end
        endmodule
        """
        result = expander.expand_autosense(content, "m.sv")
        sensitivity_line = [l for l in result.splitlines() if "AUTOSENSE" in l][0]
        assert "state" in sensitivity_line
        assert "idle" in sensitivity_line

    def test_autosense_ignores_commented_out_block(self):
        """Regression: expand_autosense goes through _apply_masked_replacements,
        so a `//`-commented always block must not be expanded (matching autoinst)."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m;
            reg a;
            reg b;
            // always @(/*AUTOSENSE*/) b = a;
        endmodule
        """
        result = expander.expand_autosense(content, "m.sv")
        assert result == content  # commented-out tag must be left untouched

    def test_autoarg_skips_commented_out_header(self):
        """expand_autoarg must mask comments: a `//`-commented module header
        that appears first must not be picked; only the real module is expanded."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
// module old (/*AUTOARG*/);
module m (
    input clk,
    /*AUTOARG*/
);
    input rst;
    output done;
endmodule
"""
        result = expander.expand_autoarg(content, "m.sv")
        # commented-out header left untouched
        assert "// module old (/*AUTOARG*/);" in result
        # real module m's header (everything up to the closing ');') must gain
        # the expanded ports — rst/done in the body alone don't prove expansion.
        header = result.split("module m")[1].split(");")[0]
        assert "rst" in header and "done" in header

    def test_autowire_ignores_commented_out_tag(self):
        """Masking consistency: a `//`-commented /*AUTOWIRE*/ must not be expanded
        (_expand_auto_signals; AUTOLOGIC shares the same path)."""
        project = VerilogProject()
        sub = "module sub (input clk, output [7:0] dat);\nendmodule\n"
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        expander = VerilogExpander(project)
        top = """module top;
    // /*AUTOWIRE*/
    sub u (.clk(clk), .dat(dat));
endmodule
"""
        result = expander.expand_all(top, "top.sv")
        assert result == top  # commented tag -> no expansion

    def test_autoinput_ignores_commented_out_tag(self):
        """Masking consistency: a `//`-commented /*AUTOINPUT*/ must not be expanded
        (_expand_auto_port; AUTOOUTPUT shares the same path)."""
        project = VerilogProject()
        sub = "module sub (input [3:0] sel);\nendmodule\n"
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        expander = VerilogExpander(project)
        top = """module top;
    // /*AUTOINPUT*/
    sub u (.sel(sel));
endmodule
"""
        result = expander.expand_all(top, "top.sv")
        assert result == top  # commented tag -> no expansion

    def test_autoinst_no_double_comma_when_surrounded(self):
        """Bug 3: AUTOINST must not produce `,,` when manual connections surround it."""
        project = VerilogProject()
        sub = """
        module sub (input a, input b, output c);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            sub u (.a(x), /*AUTOINST*/, .c(z));
        endmodule
        """
        result = expander.expand_autoinst(top)
        assert ",," not in result.replace(" ", "").replace("\n", "")

    def test_autoinst_width_mismatch_warning(self):
        """Bug 1: when the parent signal width differs from the sub-module port width, add a warning comment on that line."""
        project = VerilogProject()
        sub = """
        module sub (input [7:0] data_in, output [7:0] data_out);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            wire [15:0] data_in;
            wire [7:0] data_out;
            sub u (/*AUTOINST*/);
        endmodule
        """
        result = expander.expand_autoinst(top)
        # data_in width mismatch -> that line must contain WARNING
        warn_lines = [l for l in result.splitlines() if "data_in" in l and "WARNING" in l]
        assert warn_lines, f"expected WARNING comment on data_in line, got:\n{result}"
        # data_out width matches -> no WARNING
        assert not any(
            "data_out" in l and "WARNING" in l for l in result.splitlines()
        )

    def test_get_instantiations_handles_concatenation(self):
        """Bug 4: get_instantiations must parse connections like `.x({a, b})`."""
        parser = RegexVerilogParser()
        content = """
        module top;
            sub u (.data({hi, lo}), .plain(single));
        endmodule
        """
        insts = parser.get_instantiations(content, "top.sv")
        assert len(insts) == 1
        assert insts[0]["ports"]["data"] == "{hi, lo}"
        assert insts[0]["ports"]["plain"] == "single"

    def test_get_instantiations_handles_nested_parens(self):
        """Bug 4 edge case: support one level of nested parens `.x(func(a, b))`."""
        parser = RegexVerilogParser()
        content = """
        module top;
            sub u (.sel(mux(a, b)), .sum(x + (y - z)));
        endmodule
        """
        insts = parser.get_instantiations(content, "top.sv")
        assert insts[0]["ports"]["sel"] == "mux(a, b)"
        assert insts[0]["ports"]["sum"] == "x + (y - z)"

    def test_autosense_preserves_nonblocking_write(self):
        """Bug 2 edge case: after fixing the `==` misdetection, `<=` NBA must still count as a write (not enter the sensitivity list)."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m;
            reg clk;
            reg d;
            reg q;
            always @(/*AUTOSENSE*/) begin
                q <= d;
            end
        endmodule
        """
        result = expander.expand_autosense(content, "m.sv")
        sens_line = [l for l in result.splitlines() if "AUTOSENSE" in l][0]
        assert "d" in sens_line  # read
        assert " q " not in sens_line and "(q" not in sens_line  # q is the LHS, must not appear

    def test_autosense_detects_inequality_operands(self):
        """Bug 2 edge case: operands of `!=` / `===` must also be detected as reads."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m;
            reg a;
            reg b;
            reg out;
            always @(/*AUTOSENSE*/) begin
                if (a !== b) out = 1'b1;
            end
        endmodule
        """
        result = expander.expand_autosense(content, "m.sv")
        sens_line = [l for l in result.splitlines() if "AUTOSENSE" in l][0]
        assert "a" in sens_line and "b" in sens_line

    def test_autoinst_no_false_warning_when_widths_match(self):
        """Bug 1 counter-case: no WARNING when widths match or the parent signal is undeclared."""
        project = VerilogProject()
        sub = """
        module sub (input [7:0] matched, input [7:0] unknown, input no_width);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            wire [7:0] matched;
            wire no_width;
            // 'unknown' is not declared in the parent module
            sub u (/*AUTOINST*/);
        endmodule
        """
        result = expander.expand_autoinst(top)
        assert "WARNING" not in result, f"unexpected WARNING:\n{result}"

    def test_autowire_declares_missing_output_signals(self):
        """AUTOWIRE should declare a wire for an undeclared signal driven by a sub-module output."""
        project = VerilogProject()
        sub = """
        module producer (output [3:0] data);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOWIRE*/
            producer u (.data(bus));
        endmodule
        """
        result = expander.expand_autowire(top, "top.sv")
        assert "wire [3:0] bus;" in result

    def test_autoinput_ansi_port_list(self):
        """AUTOINPUT should add the inputs required by sub-modules into the ANSI port list."""
        project = VerilogProject()
        sub = """
        module sub (input [3:0] a, input b, output c);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top (
            output c,
            /*AUTOINPUT*/
        );
            sub u (.a(a), .b(b), .c(c));
        endmodule
        """
        result = expander.expand_autoinput(top, "top.sv")
        assert "input [3:0] a" in result
        assert "input b" in result
        # outputs must not be inserted by AUTOINPUT
        header = result[: result.find("endmodule")]
        assert "input c" not in header

    def test_autoinput_non_ansi_body(self):
        """AUTOINPUT should emit `input ...;` declarations in the module body."""
        project = VerilogProject()
        sub = """
        module sub (input [7:0] din);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOINPUT*/
            sub u (.din(din));
        endmodule
        """
        result = expander.expand_autoinput(top, "top.sv")
        assert "input [7:0] din;" in result

    def test_autoinput_non_ansi_body_idempotent(self):
        """AUTOINPUT body path must not produce duplicate declarations on a second expand."""
        project = VerilogProject()
        sub = """
        module sub (input [7:0] din);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOINPUT*/
            sub u (.din(din));
        endmodule
        """
        once = expander.expand_autoinput(top, "top.sv")
        twice = expander.expand_autoinput(once, "top.sv")
        assert once == twice

    def test_autooutput_ansi_port_list(self):
        """AUTOOUTPUT should add sub-module-driven outputs into the ANSI port list."""
        project = VerilogProject()
        sub = """
        module sub (input a, output [7:0] result);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top (
            input a,
            /*AUTOOUTPUT*/
        );
            sub u (.a(a), .result(result));
        endmodule
        """
        result = expander.expand_autooutput(top, "top.sv")
        assert "output [7:0] result" in result

    def test_autooutput_non_ansi_body(self):
        """AUTOOUTPUT should emit `output ...;` declarations in the module body."""
        project = VerilogProject()
        sub = """
        module sub (output [15:0] dout);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOOUTPUT*/
            sub u (.dout(dout));
        endmodule
        """
        result = expander.expand_autooutput(top, "top.sv")
        assert "output [15:0] dout;" in result

    def test_autooutput_non_ansi_body_idempotent(self):
        """AUTOOUTPUT body path must not produce duplicate declarations on a second expand."""
        project = VerilogProject()
        sub = """
        module sub (output [15:0] dout);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOOUTPUT*/
            sub u (.dout(dout));
        endmodule
        """
        once = expander.expand_autooutput(top, "top.sv")
        twice = expander.expand_autooutput(once, "top.sv")
        assert once == twice

    def test_autowire_idempotent(self):
        """Expanding AUTOWIRE twice yields the same result (replaces the existing auto block, not appends)."""
        project = VerilogProject()
        sub = """
        module producer (output [3:0] data);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOWIRE*/
            producer u (.data(bus));
        endmodule
        """
        once = expander.expand_autowire(top, "top.sv")
        twice = expander.expand_autowire(once, "top.sv")
        assert once == twice
        # the auto-block marker should appear only once
        assert once.count("// Beginning of automatic") == 1

    def test_autowire_skips_manually_declared_wire(self):
        """AUTOWIRE mixed mode: a manually declared wire must not be re-declared."""
        project = VerilogProject()
        sub = """
        module producer (output [3:0] a_out, output [7:0] b_out);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            wire [3:0] manual_sig;
            /*AUTOWIRE*/
            producer u (.a_out(manual_sig), .b_out(auto_sig));
        endmodule
        """
        result = expander.expand_autowire(top, "top.sv")
        # the undeclared auto_sig is added by AUTOWIRE
        assert "wire [7:0] auto_sig;" in result
        # the manually declared manual_sig must not be declared again
        assert result.count("wire [3:0] manual_sig") == 1

    def test_autologic_idempotent(self):
        """Expanding AUTOLOGIC twice yields the same result."""
        project = VerilogProject()
        sub = """
        module sub_mod (output [15:0] out_sig);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            /*AUTOLOGIC*/
            sub_mod u_sub (.out_sig(my_logic_sig));
        endmodule
        """
        once = expander.expand_autologic(top, "top.sv")
        twice = expander.expand_autologic(once, "top.sv")
        assert once == twice
        assert once.count("// Beginning of automatic") == 1

    def test_autologic_skips_manually_declared_logic(self):
        """AUTOLOGIC mixed mode: a manually declared logic must not be re-declared."""
        project = VerilogProject()
        sub = """
        module sub_mod (output [15:0] a_sig, output [7:0] b_sig);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            logic [15:0] manual_logic;
            /*AUTOLOGIC*/
            sub_mod u (.a_sig(manual_logic), .b_sig(auto_logic));
        endmodule
        """
        result = expander.expand_autologic(top, "top.sv")
        assert "logic [7:0] auto_logic;" in result
        assert result.count("logic [15:0] manual_logic") == 1

    def test_autosense_basic_combinational(self):
        """AUTOSENSE happy path: signals read by combinational logic enter the sensitivity list; written ones do not."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module m;
            reg a;
            reg b;
            reg out;
            always @(/*AUTOSENSE*/) begin
                out = a & b;
            end
        endmodule
        """
        result = expander.expand_autosense(content, "m.sv")
        sens_line = [l for l in result.splitlines() if "AUTOSENSE" in l][0]
        # a and b are read -> should be in the sensitivity list
        assert "a" in sens_line and "b" in sens_line
        # out is written (LHS) -> must not appear in the sensitivity list
        assert "out" not in sens_line

    def test_autoarg_non_ansi_with_manual_ports(self):
        """Non-ANSI AUTOARG: a manually listed port name must not be duplicated in the auto block."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        content = """
        module top (
            clk,
            /*AUTOARG*/
        );
            input clk;
            input rst_n;
            output [7:0] data_out;
        endmodule
        """
        result = expander.expand_autoarg(content, "top.sv")
        # clk should appear once in the port list (manual); the auto block must not list clk again
        header = result[: result.find(");")]
        assert header.count("clk") == 1
        assert "rst_n" in header
        assert "data_out" in header

    def test_autoinst_ignores_instantiation_inside_comment(self):
        """A `sub u(...)` inside a comment must not be treated as an instantiation (get_instantiations strips comments)."""
        parser = RegexVerilogParser()
        content = """
        module top;
            // sub u_commented (.x(y));
            /* sub u_block (.x(y)); */
            sub u_real (.x(y));
        endmodule
        """
        insts = parser.get_instantiations(content, "top.sv")
        inst_names = [i["instance_name"] for i in insts]
        assert "u_real" in inst_names
        assert "u_commented" not in inst_names
        assert "u_block" not in inst_names

    def test_autoinst_mixed_mode_preserves_manual(self):
        """AUTOINST mixed mode: manual connections are kept as-is; the auto block only fills the remaining ports."""
        project = VerilogProject()
        sub = """
        module sub (input clk, input rst_n, input [7:0] data_i, output [7:0] data_o);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            sub u (
                .clk(my_special_clk),
                /*AUTOINST*/
            );
        endmodule
        """
        result = expander.expand_autoinst(top)
        # the manual connection's signal is kept
        assert "my_special_clk" in result
        # clk should appear once (manual); AUTOINST must not add it again
        assert result.count(".clk") == 1
        # the remaining ports are filled by AUTOINST
        assert ".rst_n" in result
        assert ".data_i" in result
        assert ".data_o" in result

    def test_strip_comments_preserves_string_literals(self):
        """strip_comments_safely must not eat `//` or `/* */` inside string literals."""
        from pyvauto import strip_comments_safely
        src = '$display("http://example.com /* not a comment */");'
        out = strip_comments_safely(src)
        assert "http://example.com" in out
        assert "/* not a comment */" in out

    def test_expand_autoinst_skips_commented_instantiation(self):
        """The AUTOINST main flow must ignore an instantiation inside a comment and not rewrite that line."""
        project = VerilogProject()
        sub = """
        module sub (input a, output b);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            // sub u_dead (/*AUTOINST*/);
            sub u_live (/*AUTOINST*/);
        endmodule
        """
        result = expander.expand_autoinst(top, "top.sv")
        # the commented line must not be expanded (still after //)
        commented = [l for l in result.splitlines() if l.strip().startswith("//")]
        assert any("u_dead" in l and "/*AUTOINST*/" in l for l in commented)
        # the live instance should expand normally
        assert ".a" in result and ".b" in result

    def test_autoinst_with_nested_paren_manual_conn(self):
        """A manual connection with nested parens `.x(func(a, b))` must be preserved by parse_named_port_connections."""
        project = VerilogProject()
        sub = """
        module sub (input [7:0] sel, input other, output out);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        top = """
        module top;
            sub u (
                .sel(mux(a, b)),
                /*AUTOINST*/
            );
        endmodule
        """
        result = expander.expand_autoinst(top, "top.sv")
        # the manual connection is preserved intact
        assert "mux(a, b)" in result
        # sel must not be expanded again by AUTOINST
        assert result.count(".sel") == 1
        # the remaining ports are filled
        assert ".other" in result and ".out" in result

    def test_autoinst_reconcile_removes_and_adds(self):
        """Re-run after sub ports change: removed port drops, new port added
        in-group, manual before-tag connection kept, no duplicate headers."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        sub = """
        module sub (input clk, input rst_n, output [7:0] data_o, output valid);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        top = """
        module top;
            sub u (
                .clk(my_special_clk),
                /*AUTOINST*/
                // Outputs
                .data_o (data_o[7:0]),
                // Inputs
                .rst_n (rst_n),
                .data_i (data_i[7:0])
            );
        endmodule
        """
        result = expander.expand_autoinst(top, "top.sv")
        assert "my_special_clk" in result
        assert result.count(".clk") == 1
        assert ".data_i" not in result
        assert ".valid" in result
        assert result.count("// Outputs") == 1

    def test_autoinst_reconcile_refreshes_width_keeps_wire_name(self):
        """An after-tag manual connection keeps its wire name but takes the
        module port's bus width."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        sub = """
        module sub (output [15:0] data_o);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        top = """
        module top;
            sub u (
                /*AUTOINST*/
                // Outputs
                .data_o (my_out[7:0])
            );
        endmodule
        """
        result = expander.expand_autoinst(top, "top.sv")
        assert ".data_o (my_out[15:0])" in result
        assert "[7:0]" not in result

    def test_autoinst_reconcile_keeps_complex_expression(self):
        """A complex signal expression after the tag is kept verbatim; no width
        is forced onto it."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        sub = """
        module sub (input [7:0] data_i);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        top = """
        module top;
            sub u (
                /*AUTOINST*/
                // Inputs
                .data_i ({a, b})
            );
        endmodule
        """
        result = expander.expand_autoinst(top, "top.sv")
        assert ".data_i ({a, b})" in result
        assert "{a, b}[7:0]" not in result

    def test_autoinst_reconcile_idempotent(self):
        """Two consecutive expands with unchanged ports are identical."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        sub = """
        module sub (input clk, input [7:0] d, output [7:0] q);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        top = """
        module top;
            sub u (
                .clk(my_clk),
                /*AUTOINST*/
            );
        endmodule
        """
        once = expander.expand_autoinst(top, "top.sv")
        twice = expander.expand_autoinst(once, "top.sv")
        assert once == twice

    def test_autoinst_reconcile_delete_round_trip(self):
        """Expand then delete returns to a bare tag, keeping the before-tag
        manual connection."""
        project = VerilogProject()
        expander = VerilogExpander(project)
        sub = """
        module sub (input clk, output [7:0] q);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        top = """
        module top;
            sub u (
                .clk(my_clk),
                /*AUTOINST*/
            );
        endmodule
        """
        expanded = expander.expand_autoinst(top, "top.sv")
        assert ".q" in expanded
        deleted = expander.delete_all(expanded, "top.sv")
        assert ".q" not in deleted
        assert "my_clk" in deleted
        assert "/*AUTOINST*/" in deleted

    def test_expand_all_is_idempotent(self):
        """Idempotency: expanding the same content twice yields identical results."""
        project = VerilogProject()
        sub = """
        module sub (input [7:0] a, output [7:0] b);
        endmodule
        """
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m

        expander = VerilogExpander(project)
        content = """
        module top (/*AUTOARG*/);
            input [7:0] a;
            output [7:0] b;
            /*AUTOWIRE*/
            sub u (/*AUTOINST*/);
        endmodule
        """
        once = expander.expand_all(content, "top.sv")
        twice = expander.expand_all(once, "top.sv")
        assert once == twice, f"non-idempotent expansion:\n--- once ---\n{once}\n--- twice ---\n{twice}"


class TestIntegration:
    """Integration tests — end-to-end verification."""

    def test_full_expansion_workflow(self):
        """Test the full expansion workflow."""
        project = VerilogProject()

        # Define the sub-module
        sub_content = """
        module adder (
            input [7:0] a,
            input [7:0] b,
            output [7:0] sum
        );
        endmodule
        """
        modules = project.parser.parse_file(sub_content, "adder.sv")
        for m in modules:
            project.modules[m.name] = m

        # Top module uses AUTOINST
        top_content = """
        module calculator (
            /*AUTOARG*/
        );
            input [7:0] x;
            input [7:0] y;
            output [7:0] result;

            adder u_add (
                /*AUTOINST*/
            );
        endmodule
        """

        expander = VerilogExpander(project)
        result = expander.expand_all(top_content, "calculator.sv")

        # Verify both AUTOARG and AUTOINST were expanded
        assert "x" in result
        assert "y" in result
        # Check the port names are present (without strict format checks)
        assert ".a" in result and "a" in result
        assert ".b" in result and "b" in result
        assert ".sum" in result and "sum" in result


class TestDeleteAuto:
    """Un-expand delete_all: strip auto-generated content, leaving only bare
    tags (like emacs verilog-delete-auto). Mostly round-trip style: bare tag ->
    expand_all -> delete_all should return to the original bare tag."""

    def _expander_with_sub(self):
        project = VerilogProject()
        sub = "module sub (input clk, input [7:0] data_i, output [7:0] data_o);\nendmodule\n"
        for m in project.parser.parse_file(sub, "sub.sv"):
            project.modules[m.name] = m
        return VerilogExpander(project)

    def test_delete_autowire_round_trip(self):
        expander = self._expander_with_sub()
        bare = """module top;
    /*AUTOWIRE*/
    sub u (.clk(clk), .data_i(data_i), .data_o(data_o));
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        assert "wire [7:0] data_o;" in expanded  # sanity: the expansion did produce content
        deleted = expander.delete_all(expanded, "top.sv")
        assert deleted == bare  # un-expand returns to the original bare tag

    def test_delete_autoinst_round_trip(self):
        expander = self._expander_with_sub()
        bare = """module top;
    sub u (
        /*AUTOINST*/
    );
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        assert ".data_o" in expanded  # sanity
        deleted = expander.delete_all(expanded, "top.sv")
        assert "/*AUTOINST*/" in deleted
        assert ".data_o" not in deleted and ".clk" not in deleted
        # Re-expanding after un-expand should return to the expanded state (proves an equivalent re-expandable state)
        assert expander.expand_all(deleted, "top.sv") == expanded

    def test_delete_autoarg_round_trip(self):
        expander = self._expander_with_sub()
        bare = """module top (/*AUTOARG*/);
    input clk;
    input rst_n;
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        assert "clk, rst_n" in expanded  # sanity
        deleted = expander.delete_all(expanded, "top.sv")
        assert "/*AUTOARG*/" in deleted
        assert "clk, rst_n" not in deleted
        assert expander.expand_all(deleted, "top.sv") == expanded

    def test_delete_autosense_round_trip(self):
        project = VerilogProject()
        expander = VerilogExpander(project)
        bare = """module m;
    reg a;
    reg b;
    reg q;
    always @(/*AUTOSENSE*/) begin
        q = a & b;
    end
endmodule
"""
        expanded = expander.expand_all(bare, "m.sv")
        assert "a or b" in expanded  # sanity
        deleted = expander.delete_all(expanded, "m.sv")
        assert "/*AUTOSENSE*/" in deleted
        assert "a or b" not in deleted
        assert deleted == bare  # AUTOSENSE should restore byte-perfectly

    def test_delete_autoinput_body_round_trip(self):
        expander = self._expander_with_sub()
        bare = """module top;
    /*AUTOINPUT*/
    sub u (.clk(clk), .data_i(data_i), .data_o(data_o));
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        assert "input [7:0] data_i;" in expanded  # sanity (body form)
        deleted = expander.delete_all(expanded, "top.sv")
        assert "/*AUTOINPUT*/" in deleted
        assert "input [7:0] data_i;" not in deleted
        assert deleted == bare

    def test_delete_autooutput_body_round_trip(self):
        expander = self._expander_with_sub()
        bare = """module top;
    /*AUTOOUTPUT*/
    sub u (.clk(clk), .data_i(data_i), .data_o(data_o));
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        assert "output [7:0] data_o;" in expanded  # sanity (body form)
        deleted = expander.delete_all(expanded, "top.sv")
        assert "/*AUTOOUTPUT*/" in deleted
        assert "output [7:0] data_o;" not in deleted
        assert deleted == bare

    def test_ansi_autoinput_output_round_trip(self):
        """ANSI port-list AUTOINPUT/AUTOOUTPUT is reversible: expansion keeps the
        tag and wraps the generated ports in the same // Beginning … // End of
        automatics markers the body form (and Emacs) use, so delete_all can strip
        them back to the bare tag and a re-expand reproduces the same output."""
        expander = self._expander_with_sub()
        bare = """module top (/*AUTOOUTPUT*/);
    sub u (.clk(clk), .data_i(data_i), .data_o(data_o));
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        # Expansion keeps the tag and emits a reversible marker block.
        assert "/*AUTOOUTPUT*/" in expanded
        assert "// Beginning of automatic outputs" in expanded
        assert "// End of automatics" in expanded
        assert "output [7:0] data_o" in expanded

        deleted = expander.delete_all(expanded, "top.sv")
        # Un-expand restores the bare tag and drops the generated ports/markers.
        assert "/*AUTOOUTPUT*/" in deleted
        assert "// Beginning of automatic outputs" not in deleted
        assert "output [7:0] data_o" not in deleted

        # The restored bare form re-expands to exactly the same output (idempotent
        # round-trip), and expanding twice is a no-op.
        assert expander.expand_all(deleted, "top.sv") == expanded
        assert expander.expand_all(expanded, "top.sv") == expanded

    def test_delete_all_round_trip_multiple_tags(self):
        expander = self._expander_with_sub()
        bare = """module top (/*AUTOARG*/);
    input clk;
    input rst_n;

    /*AUTOWIRE*/

    sub u_sub (
        /*AUTOINST*/
    );
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        deleted = expander.delete_all(expanded, "top.sv")
        for tag in ("/*AUTOARG*/", "/*AUTOWIRE*/", "/*AUTOINST*/"):
            assert tag in deleted
        assert "Beginning of automatic" not in deleted
        assert ".data_o" not in deleted and "clk, rst_n" not in deleted
        assert expander.expand_all(deleted, "top.sv") == expanded  # re-expanding returns to the original

    def test_delete_all_is_idempotent(self):
        expander = self._expander_with_sub()
        bare = """module top (/*AUTOARG*/);
    input clk;
    /*AUTOWIRE*/
    sub u_sub (
        /*AUTOINST*/
    );
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        once = expander.delete_all(expanded, "top.sv")
        assert expander.delete_all(once, "top.sv") == once  # un-expand is idempotent

    def test_delete_ignores_commented_tag(self):
        expander = self._expander_with_sub()
        content = """module top;
    // /*AUTOWIRE*/
    // sub u ( /*AUTOINST*/ );
endmodule
"""
        assert expander.delete_all(content, "top.sv") == content
