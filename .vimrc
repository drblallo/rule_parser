function! s:SilentRun(target, executible, args)
	let s:exec = "!./" . a:executible . " " . a:args
	return [AQAppend(s:exec)]
endfunction

function! s:RunTest(param, executible, args)
	let l:t = s:SilentRun(a:param, a:executible, a:args)
	call AQAppendOpen(1, l:t[0])
	call AQAppendOpenError(0, l:t[0])
endfunction

command! -nargs=0 TONE call s:RunTest("Test", "./main.py", expand("%:p"))
command! -nargs=0 TPRINT call s:RunTest("Test", "./main.py", expand("%:p") . " --before-printing")
command! -nargs=0 TPRINTT call s:RunTest("Test", "./main.py", expand("%:p") . " --type-checked")


nnoremap <leader><leader>to :TONE<cr>
nnoremap <leader><leader>tp :TPRINT<cr>
nnoremap <leader><leader>tt :TPRINTT<cr>
