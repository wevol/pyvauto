# pyvauto - Python Verilog Auto-Generator

[English](README.md) | **繁體中文**

[![CI](https://github.com/wevol/pyvauto/actions/workflows/ci.yml/badge.svg)](https://github.com/wevol/pyvauto/actions/workflows/ci.yml)
[![Go](https://github.com/wevol/pyvauto/actions/workflows/go.yml/badge.svg)](https://github.com/wevol/pyvauto/actions/workflows/go.yml)

Python 版本的 Verilog 自動化工具，提供類似 Emacs `verilog-mode` 的自動擴展功能。本工具**專為 Vim 設計**（內附 Vim 插件），讓你不必依賴 Emacs，也能在 Vim 中以一個快捷鍵完成 AUTOINST / AUTOARG / AUTOWIRE 等自動擴展。本體是純 Python CLI，因此也能獨立從命令列執行、或接進 CI；其他編輯器（如 VS Code）目前沒有專屬插件，需自行在終端機呼叫 CLI 再重新載入檔案。

> **兩種實作。** 參考實作是純 Python 的 `pyvauto.py`（即本文件）。另有一份獨立的 **Go** 移植版位於 [`go/`](go/README.md)——單一自足執行檔、不需 Python runtime，透過 golden 測試對 `tests/*.sv` 語料與 Python 輸出**逐位元組對齊**（CI 有一個 job 會用 Python 重新產生 golden，兩版一旦漂移就失敗）。用 `let g:pyvauto_bin = '/path/to/go/pyvauto'` 讓 Vim 插件改走該執行檔。兩版共用同一套 `tests/*.sv` fixture。

## 功能特點

pyvauto 實作了 Emacs `verilog-mode` AUTO tag 的一個子集。**有支援的 tag，行為與 Emacs verilog-mode 相同**——相同的展開結果、相同的混合模式處理（手動宣告與 AUTO tag 並存、不重複）、相同的冪等重跑（產生的區塊會被替換而非累加），以及相同的 `// Outputs` / `// Inouts` / `// Inputs` 方向分組。與 Emacs 的差異列於下方。

支援的 tag：

- **AUTOINST** —— 模組實例化的埠口連接；重跑時會對比子模組當前的埠口做增減。
- **AUTOARG** —— 模組埠口列表，支援 ANSI（混合模式）與 Non-ANSI 兩種風格。
- **AUTOINPUT / AUTOOUTPUT** —— 把子模組中未宣告的埠口往上傳遞到外層模組。
- **AUTOWIRE / AUTOLOGIC** —— 宣告互連子模組所需的 `wire` / `logic`。
- **AUTOSENSE** —— 填入 `always @(/*AUTOSENSE*/...)` 的敏感列表。

### 與 Emacs verilog-mode 的差異

- **不需要 Emacs。** pyvauto 可作為 Vim 插件、獨立 CLI，或接進 CI 執行。本體是純 Python（僅標準庫，相容 Python 3.6.8+）；另有一份 byte 級對拍的 Go port 位於 [`go/`](go/README.md)。
- **只支援部分 AUTO tag。** 僅實作上列的 tag，其餘（如 `AUTOPARAM`、`AUTOTIEOFF`、`AUTORESET`、SystemVerilog interface）尚未支援——見 [開發狀態](#開發狀態)。
- **以 Regex 解析，非完整語法解析。** 分析前會先移除註解；以 `module … ( … ) ;` 的形狀判斷 ANSI / Non-ANSI；以 `ModName inst (...)` 樣式辨識實例化（Verilog 關鍵字會被跳過）。完整解析器能接受的特殊寫法，pyvauto 可能無法辨識。

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

> ℹ️ AUTOINST 等跨模組擴展時，CLI 會在**目標檔案所在的目錄**尋找子模組定義。
> 若子模組在別處，用 `--incdir DIR`（可重複）加入搜尋目錄：`python pyvauto.py --incdir rtl/common top.sv`。

### 功能展示

#### 1. 混合模式 AUTOINST
手動宣告關鍵訊號，其餘由 `AUTOINST` 補全：
```systemverilog
sub_module u_inst (
    .clk(my_special_clk), // 手動連線
    /*AUTOINST*/           // 自動補齊 rst_n, data_i, data_o
);
```
子模組埠口變動後再跑一次，AUTOINST 會重新對齊：被刪掉的埠口連線消失、新增的埠口補進對應的 `// Outputs` / `// Inputs` 分組、tag 前的 `.clk(my_special_clk)` 原樣保留、既有連線沿用原本的線名但寬度刷新成子模組埠口的寬度。

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

#### 3. Non-ANSI AUTOARG — Emacs 風格方向分組
使用裸標頭 `/*AUTOARG*/` 時，埠口名稱列表每次執行都會重新產生，並依方向分組。手動埠口請放在標籤**之前**；標籤之後的內容全由工具自動維護（刪掉的埠口會消失、新增的埠口會落到對應分組）。以下：
```systemverilog
module m (/*AUTOARG*/);
    input  clk, rst_n;
    output valid;
    inout  bus;
endmodule
```
會展開成：
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
