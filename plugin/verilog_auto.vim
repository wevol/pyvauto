" ============================================================================
" Verilog Auto-Expansion Plugin
" Calls an external Python 3 to run pyvauto.py.
" ============================================================================

" Prevent double-loading
if exists('g:loaded_verilog_auto')
    finish
endif
let g:loaded_verilog_auto = 1

" Python 3 executable (override if it isn't 'python3' on your system)
if !exists('g:verilog_auto_python')
    let g:verilog_auto_python = 'python3'
endif

" Path to pyvauto.py. Default: the project root one directory above this
" plugin file (plugin/verilog_auto.vim -> ../pyvauto.py).
if !exists('g:verilog_auto_script')
    let g:verilog_auto_script = expand('<sfile>:p:h:h') . '/pyvauto.py'
endif

" Main expansion function
function! VerilogExpandAuto()
    " Remember the cursor position
    let l:save_cursor = getpos('.')

    " Save the file
    write

    " Absolute path of the current file
    let l:file = expand('%:p')

    " Build the command
    let l:cmd = shellescape(g:verilog_auto_python) . ' ' .
              \ shellescape(g:verilog_auto_script) . ' ' .
              \ shellescape(l:file)

    " Run it and capture the output
    echo "Expanding Verilog auto tags..."
    let l:output = system(l:cmd)

    if v:shell_error == 0
        " Reload the file and restore the cursor
        edit!
        call setpos('.', l:save_cursor)
        echo "Verilog auto expansion completed successfully!"
    else
        echohl ErrorMsg
        echo "Error expanding Verilog auto tags:"
        echo l:output
        echohl None
    endif
endfunction

" Command to expand the current file (:AT kept as a short alias)
command! VerilogAuto call VerilogExpandAuto()
command! AT call VerilogExpandAuto()

" Default mappings: \va and F5 (disable with: let g:verilog_auto_no_mappings = 1)
if !exists('g:verilog_auto_no_mappings') || !g:verilog_auto_no_mappings
    nnoremap <silent> <Leader>va :VerilogAuto<CR>
    nnoremap <silent> <F5> :VerilogAuto<CR>
endif

" Optional: expand automatically when saving .v / .sv files (off by default)
if exists('g:verilog_auto_on_save') && g:verilog_auto_on_save
    augroup VerilogAutoExpand
        autocmd!
        autocmd BufWritePost *.v,*.sv call VerilogExpandAuto()
    augroup END
endif

" ============================================================================
" Configuration (add to your .vimrc):
"
"   let g:verilog_auto_python = 'python3'              " Python 3 executable
"   let g:verilog_auto_script = '/path/to/pyvauto.py'  " explicit script path
"   let g:verilog_auto_on_save = 1                      " expand on save
"   let g:verilog_auto_no_mappings = 1                  " disable \va and F5
"
" Usage: press \va or F5 in a Verilog file, or run :VerilogAuto
" ============================================================================
