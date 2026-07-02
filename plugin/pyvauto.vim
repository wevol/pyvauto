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
" Auto-detect a usable Python 3. Skips the Microsoft Store 'App execution
" alias' stub (WindowsApps\python3.exe), which hangs forever under system().
function! s:DetectPython() abort
    for l:cand in ['python3', 'python', 'py']
        if executable(l:cand)
            " exepath() resolves the real binary; reject the Store stub.
            if exepath(l:cand) =~? 'WindowsApps'
                continue
            endif
            return l:cand
        endif
    endfor
    return 'python3'  " last-resort fallback (Unix convention)
endfunction

if !exists('g:pyvauto_python')
    let g:pyvauto_python = s:DetectPython()
endif

" Path to pyvauto.py. Default: the project root one directory above this
" plugin file (plugin/pyvauto.vim -> ../pyvauto.py).
if !exists('g:pyvauto_script')
    " Locate pyvauto.py relative to this plugin file. Two supported layouts:
    "   1. flat install  — pyvauto.py sits NEXT TO pyvauto.vim
    "                       (e.g. both copied into ~/.vim/plugin/)
    "   2. repo layout    — pyvauto.vim in repo/plugin/, pyvauto.py one dir up
    " Prefer the same dir; fall back to the parent. Whichever exists wins.
    let s:dir = expand('<sfile>:p:h')
    if filereadable(s:dir . '/pyvauto.py')
        let g:pyvauto_script = s:dir . '/pyvauto.py'
    else
        let g:pyvauto_script = fnamemodify(s:dir, ':h') . '/pyvauto.py'
    endif
endif
" Expand ~ / env vars so a user-supplied path (e.g. '~/.vim/plugin/pyvauto.py')
" survives shellescape(), which would otherwise quote the literal ~ and break
" the call (Python can't open a path starting with ~).
let g:pyvauto_script = expand(g:pyvauto_script)

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
    " If g:pyvauto_bin points at a compiled binary (e.g. the Go build), use it
    " directly for the expand path — no Python needed. The Go MVP has no delete,
    " so the un-expand path always falls back to Python.
    if !a:delete && exists('g:pyvauto_bin') && !empty(g:pyvauto_bin)
        let l:cmd = shellescape(g:pyvauto_bin) . ' ' . shellescape(expand('%:p'))
    else
        let l:cmd = shellescape(g:pyvauto_python) . ' ' .
                  \ shellescape(g:pyvauto_script) . l:flag . ' ' .
                  \ shellescape(expand('%:p'))
    endif

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
