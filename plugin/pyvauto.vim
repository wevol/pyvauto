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

" Shared runner: a:delete=0 expands, a:delete=1 un-expands (passes --delete).
function! s:Run(delete) abort
    " Remember the cursor position
    let l:save_cursor = getpos('.')

    " Save the file
    write

    " Build the command (add --delete for the un-expand path)
    let l:flag = a:delete ? ' --delete' : ''
    let l:verb = a:delete ? 'Deleting' : 'Expanding'
    let l:noun = a:delete ? 'deletion' : 'expansion'
    let l:cmd = shellescape(g:pyvauto_python) . ' ' .
              \ shellescape(g:pyvauto_script) . l:flag . ' ' .
              \ shellescape(expand('%:p'))

    " Run it and capture the output
    echo l:verb . ' Verilog auto tags...'
    let l:output = system(l:cmd)

    if v:shell_error == 0
        " Reload the file and restore the cursor
        edit!
        call setpos('.', l:save_cursor)
        echo 'Verilog auto ' . l:noun . ' completed successfully!'
    else
        echohl ErrorMsg
        echo 'Error ' . tolower(l:verb) . ' Verilog auto tags:'
        echo l:output
        echohl None
    endif
endfunction

function! PyvautoExpand()
    call s:Run(0)
endfunction

function! PyvautoDelete()
    call s:Run(1)
endfunction

" Commands: :Pyvauto / :VA expand, :NVA un-expands (delete)
command! Pyvauto call PyvautoExpand()
command! VA call PyvautoExpand()
command! NVA call PyvautoDelete()

" Default mappings (disable with: let g:pyvauto_no_mappings = 1):
"   \va / F5 expand,  \nva / F6 un-expand
if !exists('g:pyvauto_no_mappings') || !g:pyvauto_no_mappings
    nnoremap <silent> <Leader>va :Pyvauto<CR>
    nnoremap <silent> <F5> :Pyvauto<CR>
    nnoremap <silent> <Leader>nva :NVA<CR>
    nnoremap <silent> <F6> :NVA<CR>
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
"   let g:pyvauto_no_mappings = 1                  " disable \va/F5 + \nva/F6
"
" Usage: \va or F5 (or :Pyvauto) expands; \nva or F6 (or :NVA) un-expands.
" ============================================================================
