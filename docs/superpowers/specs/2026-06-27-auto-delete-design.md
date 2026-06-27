# 反展開(`--delete`)設計

## Context

pyvauto 目前只能展開 AUTO tag,展開後原地修改檔案、沒有還原途徑。使用者要回到展開前的裸 tag 狀態,只能靠 `git restore` 或手動刪。Emacs `verilog-mode` 有對應的 `verilog-delete-auto`(C-c C-k):清掉自動產生內容、只留 tag。本設計為 pyvauto 補上等效能力,並在 Vim 插件對稱補上反展開的命令/按鍵綁定。

決策(使用者已拍板):反展開涵蓋**全部 tag**,用**啟發式**定位自動內容、**不改既有展開輸出格式**。已知取捨:AUTOINST/AUTOARG/AUTOSENSE/ANSI 形式的 AUTOINPUT/AUTOOUTPUT 沒有結束標記,反展開靠「刪 tag 後到結構邊界」;若使用者把手動連線/port 寫在 tag **之後**,會被一起刪。慣例是手動寫在 tag 前,故風險低且可接受。

## 反展開模型

每個 tag 反展開都是 `/*TAG*/<自動內容>` → `/*TAG*/`,全程走遮罩(`_first_unmasked_match` / `_iter_masked_matches`),所以被 `//` 註解掉的 tag 不會被動到——與展開行為一致。自動內容的邊界分兩類:

### A 類:有起訖標記(乾淨可逆)
適用:AUTOWIRE、AUTOLOGIC,以及 **body 形式**的 AUTOINPUT / AUTOOUTPUT。
展開輸出形如:
```
/*AUTOWIRE*/
    // Beginning of automatic wires
    wire [7:0] data_o;
    // End of automatics
```
反展開:移除 tag 後的 `(\s*// Beginning.*?// End of automatics)`,留 tag。重用展開器既有的 `existing_block` regex(`_expand_auto_signals` / `_expand_auto_port` 已在用)。

### B 類:無起訖標記,刪 tag 後到結構邊界
適用:AUTOINST、AUTOARG、AUTOSENSE,以及 **ANSI port-list 形式**的 AUTOINPUT / AUTOOUTPUT。

| Tag | 結構邊界 | 反展開後 |
|---|---|---|
| AUTOINST | instance 的 `)` | port_block 還原成 `before_tag + /*AUTOINST*/`(保留 tag 前手動連線) |
| AUTOARG | header 的 `)` | port_block 還原成 `before_tag + /*AUTOARG*/` |
| AUTOSENSE | sensitivity `)` | `always @(/*AUTOSENSE*/)` |

> **已知限制(實作後確認)**:ANSI port-list 形式的 AUTOINPUT/AUTOOUTPUT 展開時,tag 直接被 port 宣告**取代**(`_expand_auto_port` 的 `port_block.replace(tag, …)`),tag 消失、無從定位,故**不可逆**。只有 body 形式(有 `// Beginning…// End` 邊界且保留 tag)可反展開。AUTOARG / AUTOINST / AUTOSENSE 展開都保留 tag,可逆。

作法:用展開時的同一個(遮罩版)regex 抓到結構,取出 `port_block` / paren 內容,以 tag 為界丟棄 tag 之後的內容,重建後用 `_splice` 寫回。

## 架構(對稱於現有展開管線)

- `delete_all(content, file_path)` ↔ `expand_all`:用同一個 `module…endmodule` block 切分,逐 block 呼叫 `delete_module_block`。
- `delete_module_block` 依序呼叫:`_delete_autoinst` → ANSI/body 的 `_delete_auto_port` → `_delete_auto_signals`(AUTOWIRE/AUTOLOGIC)→ `_delete_autosense` → `_delete_autoarg`。
- 重用既有 helper:`_mask_comments` / `_iter_masked_matches` / `_first_unmasked_match` / `_splice`。
- 不新增外部依賴(維持 stdlib-only,`test_standalone.py` 仍須通過)。

## CLI

`python pyvauto.py --delete <files…>`(短旗標 `-k`)。`main()` 加一個 `--delete`/`-k` argparse 旗標;給了就走 `delete_all`、**不**走 `expand_all`(兩者互斥)。其餘流程(掃 cwd、逐檔、僅內容有變才寫回)不變。

## Vim 插件(對稱新增反展開)

| 展開(現有) | 反展開(新增) |
|---|---|
| `PyvautoExpand()` | `PyvautoDelete()`(shell out 多帶 `--delete`) |
| `:Pyvauto` / `:VA` | `:NVA`(只此一個短命令,不加長命令) |
| `\va` | `\nva` |
| `<F5>` | `<F6>` |

- 把 `PyvautoExpand` / `PyvautoDelete` 的共用流程(存檔 → shell out → reload → 回報)抽成一個帶旗標參數的內部函式,兩者各傳是否加 `--delete`。
- mapping 沿用同一個開關 `g:pyvauto_no_mappings`(同時控制 va 與 nva)。

## 不變量

- **冪等**:對沒有自動內容的檔案反展開不改變內容;反展開兩次結果相同。
- **混合保留**:A 類完全保留手動宣告;B 類保留 tag 前的手動連線/port(tag 後的手動內容會被刪——已接受)。
- **僅在內容有變時寫回**(沿用 `main` 既有 `new_content != content` 判斷)。

## 測試計畫(TDD)

1. 各 tag 的反展開單元測試(A 類四個、B 類:AUTOINST/AUTOARG/AUTOSENSE/ANSI-port)。
2. **往返可逆**(最關鍵):`裸 tag → expand_all → delete_all` 應回到等價於原始裸 tag 的內容。涵蓋多 tag 的綜合 fixture。
3. 冪等:`delete_all` 跑兩次不變;對裸 tag 檔反展開不變。
4. 註解一致性:被 `//` 註解掉的 tag,反展開不動它。
5. CLI:`--delete` 旗標走反展開、不展開;與展開互斥。
6. Vim 端到端(headless,沿用 `tests/test_plugin.py` 模式):`:NVA` 命令存在、`\nva`/`<F6>` 綁定、開檔執行 `:NVA` 後檔案被反展開。

## 驗證

- `uv run pytest tests/`(或 `.venv/bin/python -m pytest tests/`)全綠,含新測試。
- `test_standalone.py` 仍通過(stdlib-only)。
- 真實 vim 端到端:`裸 tag → :Pyvauto(展開) → :NVA(反展開)` 回到裸 tag。
