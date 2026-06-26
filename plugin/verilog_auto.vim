" ============================================================================
" Verilog Auto-Expansion Plugin
" 使用外部 Python 3 調用 pyautocomplete.py
" ============================================================================

" 防止重複載入
if exists('g:loaded_verilog_auto')
    finish
endif
let g:loaded_verilog_auto = 1

" 設定 Python 執行檔路徑（可自訂）
if !exists('g:verilog_auto_python')
    let g:verilog_auto_python = 'python3'  " Windows 通常是 'python'，Linux/Mac 可能是 'python3'
endif

" 設定 pyautocomplete.py 路徑（可自訂）
if !exists('g:verilog_auto_script')
    " 預設假設腳本在此插件的父目錄
    let g:verilog_auto_script = expand('<sfile>:p:h:h') . '/plugin/pyautocomplete.py'
endif

" 主要擴展函數
function! VerilogExpandAuto()
    " 保存當前游標位置
    let l:save_cursor = getpos('.')
    
    " 保存檔案
    write
    
    " 獲取當前檔案的絕對路徑
    let l:file = expand('%:p')
    
    " 構建命令
    let l:cmd = shellescape(g:verilog_auto_python) . ' ' . 
              \ shellescape(g:verilog_auto_script) . ' ' . 
              \ shellescape(l:file)
    
    " 執行命令並捕獲輸出
    echo "Expanding Verilog auto tags..."
    let l:output = system(l:cmd)
    
    " 檢查執行結果
    if v:shell_error == 0
        " 重新載入檔案
        edit!
        " 恢復游標位置
        call setpos('.', l:save_cursor)
        echo "Verilog auto expansion completed successfully!"
    else
        " 顯示錯誤訊息
        echohl ErrorMsg
        echo "Error expanding Verilog auto tags:"
        echo l:output
        echohl None
    endif
endfunction

" 快速擴展當前檔案的命令
command! AT call VerilogExpandAuto()

" 預設快捷鍵（可自訂）
"if !exists('g:verilog_auto_no_mappings') || !g:verilog_auto_no_mappings
"    " 使用 <Leader>va 觸發擴展（Leader 預設是 \）
"    nnoremap <silent> <Leader>va :AT<CR>
    
    " 或者使用 F5 鍵
    nnoremap <silent> <F5> :AT<CR>
"endif

" 自動命令：保存 .v 或 .sv 檔案時自動擴展（可選，預設關閉）
if exists('g:verilog_auto_on_save') && g:verilog_auto_on_save
    augroup VerilogAutoExpand
        autocmd!
        autocmd BufWritePost *.v,*.sv call VerilogExpandAuto()
    augroup END
endif

" ============================================================================
" 配置說明
" ============================================================================
" 在 .vimrc 中加入以下內容來自訂設定：
"
" " 設定 Python 執行檔（如果不在 PATH 中）
" let g:verilog_auto_python = 'python3'
"
" " 設定 pyautocomplete.py 的路徑（如果不在預設位置）
" let g:verilog_auto_script = '/autocomplete-vim/pyautocomplete.py'
"
" " 啟用自動保存時擴展（預設關閉）
" let g:verilog_auto_on_save = 1
"
" " 禁用預設快捷鍵
" let g:verilog_auto_no_mappings = 1
"
" 使用方式：
" 1. 在 Verilog 檔案中按 F5 鍵
" 2. 或執行命令 :AT
" ============================================================================
