" ============================================================================
" pyvauto — Verilog Auto-Expansion Plugin
" Calls an external Python 3 to run pyvauto.py.
" ============================================================================

" Prevent double-loading
if exists('g:loaded_pyvauto')
    finish
endif
let g:loaded_pyvauto = 1

" Python 3 executable (override if it isn't 'python3' on your system)
if !exists('g:pyvauto_python')
    let g:pyvauto_python = 'python3'
endif

" Path to pyvauto.py. Default: the project root one directory above this
" plugin file (plugin/pyvauto.vim -> ../pyvauto.py).
if !exists('g:pyvauto_script')
    let g:pyvauto_script = expand('<sfile>:p:h:h') . '/pyvauto.py'
endif

" Main expansion function
function! PyvautoExpand()
    " Remember the cursor position
    let l:save_cursor = getpos('.')

    " Save the file
    write

    " Absolute path of the current file
    let l:file = expand('%:p')

    " Build the command
    let l:cmd = shellescape(g:pyvauto_python) . ' ' .
              \ shellescape(g:pyvauto_script) . ' ' .
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

" Command to expand the current file (:VA kept as a short alias)
command! Pyvauto call PyvautoExpand()
command! VA call PyvautoExpand()

" Default mappings: \va and F5 (disable with: let g:pyvauto_no_mappings = 1)
if !exists('g:pyvauto_no_mappings') || !g:pyvauto_no_mappings
    nnoremap <silent> <Leader>va :Pyvauto<CR>
    nnoremap <silent> <F5> :Pyvauto<CR>
endif

" Optional: expand automatically when saving .v / .sv files (off by default)
if exists('g:pyvauto_on_save') && g:pyvauto_on_save
    augroup PyvautoExpand
        autocmd!
        autocmd BufWritePost *.v,*.sv call PyvautoExpand()
    augroup END
endif

" ============================================================================
" Configuration (add to your .vimrc):
"
"   let g:pyvauto_python = 'python3'              " Python 3 executable
"   let g:pyvauto_script = '/path/to/pyvauto.py'  " explicit script path
"   let g:pyvauto_on_save = 1                      " expand on save
"   let g:pyvauto_no_mappings = 1                  " disable \va and F5
"
" Usage: press \va or F5 in a Verilog file, or run :Pyvauto
" ============================================================================
