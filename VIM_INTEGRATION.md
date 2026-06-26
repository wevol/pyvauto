# Vim 整合使用說明

## 問題解決

如果您的 Vim 只編譯了 Python 2.7 支持，無法直接執行 Python 3 程式碼，本專案提供了**外部命令調用方案**，讓 Vim 調用系統的 Python 3 來執行 `pyautocomplete.py`。

---

## Python 版本支援

`pyautocomplete.py` 現在支援：
- ✅ Python 3.6.8+
- ✅ Python 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13

**已驗證兼容性**：
- 使用 `typing.Optional` 取代 `|` union 運算符
- 使用 `typing.List`, `typing.Set` 作為返回值類型
- 所有標準庫功能在 Python 3.6+ 都可用

---

## 安裝步驟

### 1. 確認 Python 3 可用

```bash
# 檢查版本
python --version   # 應該顯示 Python 3.6.8 或更高

# 如果上面是 Python 2.x，試試
python3 --version
```

### 2. 安裝 Vim 插件

將整個專案目錄放到 Vim 的 runtimepath：

```vim
" 在 .vimrc 中添加
set runtimepath+=D:/code/PYTHON/autocomplete-vim
```

或者手動複製插件文件：

```bash
# Linux/Mac
cp plugin/verilog_auto.vim ~/.vim/plugin/

# Windows
copy plugin\verilog_auto.vim %USERPROFILE%\vimfiles\plugin\
```

### 3. 配置（可選）

在 `.vimrc` 中自訂設定：

```vim
" 如果 Python 執行檔不是 'python'（例如是 'python3'）
let g:verilog_auto_python = 'python3'

" 如果 pyautocomplete.py 路徑需要明確指定
let g:verilog_auto_script = 'D:/code/PYTHON/autocomplete-vim/pyautocomplete.py'

" 啟用保存時自動擴展（可選）
let g:verilog_auto_on_save = 1

" 禁用預設快捷鍵（如果想自訂）
let g:verilog_auto_no_mappings = 1
```

---

## 使用方式

### 方法 1：快捷鍵

在 Verilog 檔案 (`.v` 或 `.sv`) 中：

- **按 `\va`** (反斜線 + va)
- **或按 `F5`**

### 方法 2：命令

```vim
:VerilogAuto
```

### 工作流程

1. 在 Verilog 檔案中添加自動化標籤（如 `/*AUTOINST*/`）
2. 按 `\va` 或 `F5`
3. 插件會：
   - 保存當前檔案
   - 調用外部 Python 3 執行 `pyautocomplete.py`
   - 自動重新載入檔案
   - 顯示結果訊息

---

## 自訂快捷鍵

如果想使用不同的快捷鍵：

```vim
" 禁用預設快捷鍵
let g:verilog_auto_no_mappings = 1

" 自訂為 <Leader>e（例如 \e）
nnoremap <silent> <Leader>e :VerilogAuto<CR>

" 或使用其他功能鍵
nnoremap <silent> <F9> :VerilogAuto<CR>
```

---

## 故障排除

### 錯誤：找不到 Python

```vim
" 明確指定 Python 完整路徑
let g:verilog_auto_python = 'C:/Python36/python.exe'
```

### 錯誤：找不到 pyautocomplete.py

```vim
" 使用絕對路徑
let g:verilog_auto_script = 'D:/code/PYTHON/autocomplete-vim/pyautocomplete.py'
```

### 檢查配置

在 Vim 中執行：

```vim
:echo g:verilog_auto_python
:echo g:verilog_auto_script
```

確認路徑正確。

---

## 優勢

✅ **繞過 Vim Python 版本限制** - 使用系統 Python 3
✅ **零依賴** - 無需安裝第三方套件
✅ **跨平台** - Windows、Linux、Mac 都可用
✅ **向後兼容** - Python 3.6.8+ 都支援
✅ **簡單整合** - 一個快捷鍵完成所有擴展

---

## 測試

執行測試確保一切正常：

```bash
cd D:/code/PYTHON/autocomplete-vim

# 執行測試
python -m pytest tests/ -v

# 手動測試
python pyautocomplete.py tests/test_top.sv
```

所有測試應該通過。
