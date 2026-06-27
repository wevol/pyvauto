# pyvauto - Python Verilog Auto-Generator

[English](README.md) | **繁體中文**

[![CI](https://github.com/wevol/pyvauto/actions/workflows/ci.yml/badge.svg)](https://github.com/wevol/pyvauto/actions/workflows/ci.yml)

Python 版本的 Verilog 自動化工具，提供類似 Emacs `verilog-mode` 的自動擴展功能。本工具**專為 Vim 設計**（內附 Vim 插件），讓你不必依賴 Emacs，也能在 Vim 中以一個快捷鍵完成 AUTOINST / AUTOARG / AUTOWIRE 等自動擴展。本體是純 Python CLI，因此也能獨立從命令列執行、或接進 CI；其他編輯器（如 VS Code）目前沒有專屬插件，需自行在終端機呼叫 CLI 再重新載入檔案。

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
cd pyvauto
```

- **執行本工具**：`pyvauto.py` 零外部依賴、只用 Python 標準庫，**相容 Python 3.6.8+**
  （所以能用舊版系統 Python，例如透過 Vim 呼叫）。直接 `python pyvauto.py ...` 即可。
- **開發 / 跑測試**：本 uv 專案的環境鎖定在 **Python 3.13**（`pyproject.toml` 的 `requires-python`
  與 `uv.lock` 為此設定，pytest 也需要較新的 Python）。執行 `uv sync` 建立環境即可。

## Vim 整合（主要用途）

本專案內附 Vim 插件 `plugin/pyvauto.vim`，透過呼叫系統的 Python 3 來執行擴展，因此**即使你的 Vim 只內建 Python 2.7 也能使用**。

```vim
" 在 .vimrc 中將專案目錄加入 runtimepath
set runtimepath+=/path/to/pyvauto

" 若系統 Python 3 指令不是 'python3' 可自訂
let g:pyvauto_python = 'python3'
```

在 Verilog/SystemVerilog 檔案 (`.v` / `.sv`) 中：

- 展開：按 **`\va`** 或 **`F5`**，或執行 **`:Pyvauto`**
- 反展開：按 **`\nva`** 或 **`F6`**，或執行 **`:NVA`**（清除自動產生內容、只留裸 tag）
- 插件會自動保存檔案 → 呼叫 `pyvauto.py` → 重新載入

完整設定（自訂快捷鍵、保存時自動擴展、路徑指定、故障排除）請見 [VIM_INTEGRATION.md](VIM_INTEGRATION.md)。

## 使用方式

### 命令列基本用法

也可以直接從命令列對檔案做就地擴展（適合 CI，或在沒有專屬插件的編輯器中搭配終端機使用）：

```bash
python pyvauto.py <file1.sv> <file2.sv> ...

# 反向操作 —— 清除自動產生內容、只留裸 tag（對應 emacs verilog-delete-auto）
python pyvauto.py --delete <file1.sv> ...
```

> ⚠️ CLI 會索引**當前工作目錄 (`.`)** 來尋找模組定義，而非目標檔案所在目錄。
> 因此 AUTOINST 等跨模組擴展，請**從含有子模組定義的專案根目錄執行**。

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

- `pyvauto.py`: 單檔本體，整合 Regex 解析器、擴展邏輯與 CLI（零外部依賴）。
- `plugin/pyvauto.vim`: Vim 插件，呼叫 `pyvauto.py` 完成擴展。
- `VIM_INTEGRATION.md`: Vim 整合與設定的完整說明。
- `tests/`: pytest 單元測試與 `*.sv` 驗證案例。

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

## 致謝

本專案全部使用 [Claude Code](https://claude.com/claude-code) 製作。
