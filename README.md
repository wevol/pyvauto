# Pyautocomplete - Python Verilog Auto-Generator

Python 版本的 Verilog 自動化工具，提供類似 Emacs `verilog-mode` 的自動擴展功能。本工具旨在現代化的開發環境（如 VS Code）中，提供高效、穩定且不依賴 Emacs 的硬體描述語言開發體驗。

## 功能特點

- ✅ **混合模式支援**: 所有自動化標籤皆支援與手動宣告混合並存，不會產生重複定義。
- ✅ **AUTOINST**: 自動產生模組實例化的埠口連接（與手動連線自動去重）。
- ✅ **AUTOARG**: 自動維護模組埠口列表，支援 **ANSI (混合模式)** 與 **Non-ANSI** 風格。
- ✅ **AUTOINPUT / AUTOOUTPUT**: 自動從子模組中提取並宣告未定義的輸入/輸出埠口。
- ✅ **AUTOWIRE**: 自動建立實例化模組間互連所需的 `wire` 宣告。
- ✅ **智慧替換**: 產生的區塊具備穩定性，重複執行不會產生冗餘標籤或語法錯誤。
- ✅ **高效解析**: 內建高效 Python Regex 解析器，支援精確的語法分析與自動化擴展。

## 安裝

```bash
# 克隆或下載本專案
cd pyvlog

# 建議使用虛擬環境 (Python 3.8+)
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 無需額外依賴，核心功能僅需 Python 標準庫
```

## 使用方式

### 基本用法

```bash
python pyautocomplete.py <file1.sv> <file2.sv> ...
```

### 功能展示

#### 1. 混合模式 AUTOINST
手動宣告關鍵訊號，其餘由 `AUTOINST` 補全：
```systemverilog
sub_module u_inst (
    .clk(my_special_clk), // 手動連線
    /*AUTOINST*/           // 自動補齊 rst_n, data_i, data_o
);
```

#### 2. ANSI 混合模式 AUTOARG
在標頭直接使用 `/*AUTOARG*/`，工具會根據 Body 內的宣告生成完整埠口內容：
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

## 專案結構

- `pyautocomplete.py`: 主要入口，整合擴展邏輯與 CLI。
- `parser.py`: 核心解析模組，使用 Regex 進行語法分析。
- `test_*.sv`: 各項功能的驗證測試案例。

## 開發狀態

- [x] 核心 AUTOINST/AUTOARG 混合支援
- [x] AUTOINPUT/AUTOOUTPUT 智慧宣告
- [x] AUTOWIRE 連線追蹤
- [x] Regex 解析效能優化
- [ ] SystemVerilog Interface 專屬支援
- [ ] 支援更多關鍵字的高級參數傳遞標籤 (AUTOPARAM)

## License

MIT

## 貢獻

歡迎提交 Issue 和 Pull Request！


