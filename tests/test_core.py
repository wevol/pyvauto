"""
核心功能測試 - 確保 pyvauto 核心邏輯正確運作

這些測試用於驗證：
1. 解析器能正確解析 Verilog 模組
2. 擴展器能正確擴展各種自動化標籤
3. 整合測試：端到端處理 Verilog 檔案
"""

import sys
from pathlib import Path

# 添加專案根目錄到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyvauto import (
    VerilogPort,
    VerilogModule,
    RegexVerilogParser,
    VerilogProject,
    VerilogExpander,
)


class TestVerilogParser:
    """測試 Verilog 解析器功能"""

    def test_parse_simple_module(self):
        """測試解析簡單模組"""
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

        # 驗證埠口
        port_names = [p.name for p in modules[0].ports]
        assert "clk" in port_names
        assert "rst_n" in port_names
        assert "data_out" in port_names

    def test_parse_module_with_parameters(self):
        """測試解析帶參數的模組"""
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
        """同一行以逗號分隔的多個 port 都必須被解析出來，
        且共用該行的 direction 與 width。"""
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
        """ANSI 逐埠重複 direction（input a, input b）不可被逗號合併，
        誤把後面的 'input' 當成 port 名稱。"""
        parser = RegexVerilogParser()
        content = "module m (input a, input b, output c);\nendmodule\n"
        mod = parser.parse_file(content, "m.sv")[0]
        assert [p.name for p in mod.ports] == ["a", "b", "c"]

    def test_parse_ports_ansi_shared_direction_comma_list(self):
        """ANSI 共用 direction 的逗號清單（input a, b, output c, d）全部收集。"""
        parser = RegexVerilogParser()
        content = "module m (input a, b, output c, d);\nendmodule\n"
        mod = parser.parse_file(content, "m.sv")[0]
        assert [p.name for p in mod.ports] == ["a", "b", "c", "d"]


class TestVerilogExpander:
    """測試 Verilog 擴展器功能"""

    def test_expand_autoinst_basic(self):
        """測試基本 AUTOINST 擴展"""
        project = VerilogProject()

        # 添加子模組定義
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

        # 測試擴展
        expander = VerilogExpander(project)
        top_content = """
        module top;
            sub u_sub (
                /*AUTOINST*/
            );
        endmodule
        """

        result = expander.expand_autoinst(top_content)

        # 驗證結果包含自動生成的埠口連接 (包含寬度資訊)
        assert ".clk(clk)" in result or ".clk (clk)" in result
        assert "data_in" in result  # 檢查訊號名稱存在
        assert "data_out" in result  # 檢查訊號名稱存在

    def test_expand_autoarg(self):
        """測試 AUTOARG 擴擴展"""
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

        # 驗證結果包含自動生成的埠口列表
        assert "clk" in result
        assert "rst_n" in result
        assert "result" in result

    def test_expand_autologic(self):
        """測試 AUTOLOGIC 擴展"""
        project = VerilogProject()

        # 模擬子模組
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
        """Return the AUTOARG name list (text between the tag and ');')."""
        start = result.find("/*AUTOARG*/") + len("/*AUTOARG*/")
        end = result.find(");", start)
        return result[start:end]

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
        """New ports appear in declaration order, with no stale duplicate chunk."""
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
        assert names == ["clk", "rst_n", "mode", "valid", "busy"]

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


class TestBugFixes:
    """回歸測試：確保已修復的邏輯錯誤不再復現"""

    def test_autosense_includes_equality_operands(self):
        """Bug 2: AUTOSENSE 不應把 `==` 比較的運算元誤判為寫入"""
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
        """回歸：expand_autosense 走 _apply_masked_replacements 遮罩註解，
        被 `//` 註解掉的 always 區塊不得被展開（與 autoinst 行為一致）。"""
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
        """expand_autoarg 必須遮罩註解：一個被 `//` 註解掉、且排在前面的
        module header 不得被選中，真正的 module 才該被展開。"""
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
        """遮罩一致性：被 `//` 註解掉的 /*AUTOWIRE*/ 不得被展開
        （_expand_auto_signals，AUTOLOGIC 共用同一路徑）。"""
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
        """遮罩一致性：被 `//` 註解掉的 /*AUTOINPUT*/ 不得被展開
        （_expand_auto_port，AUTOOUTPUT 共用同一路徑）。"""
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
        """Bug 3: AUTOINST 前後已有手動連線時不得產生 `,,`"""
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
        """Bug 1: 母模組訊號寬度與子模組埠寬度不一致時，應在該行加警告註解"""
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
        # data_in 寬度不一致 → 該行必須含 WARNING
        warn_lines = [l for l in result.splitlines() if "data_in" in l and "WARNING" in l]
        assert warn_lines, f"expected WARNING comment on data_in line, got:\n{result}"
        # data_out 寬度一致 → 不應有 WARNING
        assert not any(
            "data_out" in l and "WARNING" in l for l in result.splitlines()
        )

    def test_get_instantiations_handles_concatenation(self):
        """Bug 4: get_instantiations 應能解析 `.x({a, b})` 這類連線"""
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
        """Bug 4 邊界: 支援單層巢狀括號 `.x(func(a, b))`"""
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
        """Bug 2 邊界: 修正 `==` 誤判後，`<=` NBA 仍必須被視為寫入（不該進敏感列表）"""
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
        assert " q " not in sens_line and "(q" not in sens_line  # q 是 LHS，不應出現

    def test_autosense_detects_inequality_operands(self):
        """Bug 2 邊界: `!=` / `===` 的運算元也應偵測為讀取"""
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
        """Bug 1 反例: 寬度一致、或母模組未宣告時，不應產生 WARNING"""
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
            // 'unknown' 未在母模組宣告
            sub u (/*AUTOINST*/);
        endmodule
        """
        result = expander.expand_autoinst(top)
        assert "WARNING" not in result, f"unexpected WARNING:\n{result}"

    def test_autowire_declares_missing_output_signals(self):
        """AUTOWIRE 應為 sub 模組 output 連接的未宣告訊號產生 wire"""
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
        """AUTOINPUT 在 ANSI 埠口列表中應補上子模組所需的 input"""
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
        # output 不該被 AUTOINPUT 插入
        header = result[: result.find("endmodule")]
        assert "input c" not in header

    def test_autoinput_non_ansi_body(self):
        """AUTOINPUT 在模組本體中應生成 `input ...;` 宣告"""
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
        """AUTOINPUT body 路徑展開兩次不應產生重複宣告"""
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
        """AUTOOUTPUT 在 ANSI 埠口列表中應補上子模組驅動的 output"""
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
        """AUTOOUTPUT 在模組本體中應生成 `output ...;` 宣告"""
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
        """AUTOOUTPUT body 路徑展開兩次不應產生重複宣告"""
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
        """AUTOWIRE 展開兩次應產生相同結果（替換既有自動區塊，不重複附加）"""
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
        # 自動區塊標記只應出現一次
        assert once.count("// Beginning of automatic") == 1

    def test_autowire_skips_manually_declared_wire(self):
        """AUTOWIRE 混合模式: 已手動宣告的 wire 不應被重複宣告"""
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
        # 未宣告的 auto_sig 由 AUTOWIRE 補上
        assert "wire [7:0] auto_sig;" in result
        # 已手動宣告的 manual_sig 不應被再宣告一次
        assert result.count("wire [3:0] manual_sig") == 1

    def test_autologic_idempotent(self):
        """AUTOLOGIC 展開兩次應產生相同結果"""
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
        """AUTOLOGIC 混合模式: 已手動宣告的 logic 不應被重複宣告"""
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
        """AUTOSENSE happy-path: 組合邏輯讀取的訊號應全部進入敏感列表，被寫入的不進"""
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
        # 讀取的 a、b 應進敏感列表
        assert "a" in sens_line and "b" in sens_line
        # 被寫入的 out 是 LHS，不應出現於敏感列表
        assert "out" not in sens_line

    def test_autoarg_non_ansi_with_manual_ports(self):
        """Non-ANSI AUTOARG: 手動列出的埠名不應重複出現在自動展開區塊"""
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
        # clk 只應出現一次於 port list（手動處），自動區塊不應再列 clk
        header = result[: result.find(");")]
        assert header.count("clk") == 1
        assert "rst_n" in header
        assert "data_out" in header

    def test_autoinst_ignores_instantiation_inside_comment(self):
        """註解內的 `sub u(...)` 不得被視為實例化（get_instantiations 應已剝除註解）"""
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
        """AUTOINST 混合模式: 手動連線保留原樣，自動區塊只補剩餘埠"""
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
        # 手動連線訊號保持
        assert "my_special_clk" in result
        # clk 只應出現一次（手動），不應被 AUTOINST 再補
        assert result.count(".clk") == 1
        # 其餘埠由 AUTOINST 補齊
        assert ".rst_n" in result
        assert ".data_i" in result
        assert ".data_o" in result

    def test_strip_comments_preserves_string_literals(self):
        """strip_comments_safely 不能吃掉字串內的 `//` 或 `/* */`"""
        from pyvauto import strip_comments_safely
        src = '$display("http://example.com /* not a comment */");'
        out = strip_comments_safely(src)
        assert "http://example.com" in out
        assert "/* not a comment */" in out

    def test_expand_autoinst_skips_commented_instantiation(self):
        """AUTOINST 主流程應忽略註解內的實例化，不回寫該行"""
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
        # 註解那行不能被展開（仍在 // 後）
        commented = [l for l in result.splitlines() if l.strip().startswith("//")]
        assert any("u_dead" in l and "/*AUTOINST*/" in l for l in commented)
        # live 實例應正常展開
        assert ".a" in result and ".b" in result

    def test_autoinst_with_nested_paren_manual_conn(self):
        """手動連線含巢狀括號 `.x(func(a, b))`，應被 parse_named_port_connections 正確保留"""
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
        # 手動連線完整保留
        assert "mux(a, b)" in result
        # sel 不應被 AUTOINST 再展一次
        assert result.count(".sel") == 1
        # 其餘埠補齊
        assert ".other" in result and ".out" in result

    def test_expand_all_is_idempotent(self):
        """冪等性: 對同一內容重複展開兩次，第二次應與第一次結果相同"""
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
    """整合測試 - 端到端功能驗證"""

    def test_full_expansion_workflow(self):
        """測試完整的擴展工作流程"""
        project = VerilogProject()

        # 定義子模組
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

        # 頂層模組使用 AUTOINST
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

        # 驗證 AUTOARG 和 AUTOINST 都被擴展
        assert "x" in result
        assert "y" in result
        # 檢查埠口名稱存在（不嚴格檢查格式）
        assert ".a" in result and "a" in result
        assert ".b" in result and "b" in result
        assert ".sum" in result and "sum" in result


class TestDeleteAuto:
    """反展開 delete_all：清除自動產生內容、只留裸 tag（對應 emacs verilog-delete-auto）。
    主要用 round-trip 風格：裸 tag -> expand_all -> delete_all 應回到原始裸 tag。"""

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
        assert "wire [7:0] data_o;" in expanded  # sanity：展開確實有產生
        deleted = expander.delete_all(expanded, "top.sv")
        assert deleted == bare  # 反展開回到原始裸 tag

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
        # 反展開後再展開應回到展開狀態（證明帶回可重新展開的等價狀態）
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
        assert deleted == bare  # AUTOSENSE 應 byte-perfect 還原

    def test_delete_autoinput_body_round_trip(self):
        expander = self._expander_with_sub()
        bare = """module top;
    /*AUTOINPUT*/
    sub u (.clk(clk), .data_i(data_i), .data_o(data_o));
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        assert "input [7:0] data_i;" in expanded  # sanity（body 形式）
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
        assert "output [7:0] data_o;" in expanded  # sanity（body 形式）
        deleted = expander.delete_all(expanded, "top.sv")
        assert "/*AUTOOUTPUT*/" in deleted
        assert "output [7:0] data_o;" not in deleted
        assert deleted == bare

    def test_ansi_autoinput_output_not_reversible(self):
        """已知限制：ANSI port-list 形式的 AUTOINPUT/AUTOOUTPUT 展開時 tag 即被
        port 宣告取代（tag 消失），故不可逆。只有 body 形式可反展開。"""
        expander = self._expander_with_sub()
        bare = """module top (/*AUTOOUTPUT*/);
    sub u (.clk(clk), .data_i(data_i), .data_o(data_o));
endmodule
"""
        expanded = expander.expand_all(bare, "top.sv")
        assert "/*AUTOOUTPUT*/" not in expanded  # 展開即丟 tag（destructive）
        # 無 tag 可定位 → delete_all 維持原樣，不會誤刪這些 port 宣告
        assert expander.delete_all(expanded, "top.sv") == expanded

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
        assert expander.expand_all(deleted, "top.sv") == expanded  # 再展開回原狀

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
        assert expander.delete_all(once, "top.sv") == once  # 反展開冪等

    def test_delete_ignores_commented_tag(self):
        expander = self._expander_with_sub()
        content = """module top;
    // /*AUTOWIRE*/
    // sub u ( /*AUTOINST*/ );
endmodule
"""
        assert expander.delete_all(content, "top.sv") == content
