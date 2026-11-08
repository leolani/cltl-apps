@echo off
rem Windows counterpart of run_host_server.sh: creates venv\ next to this
rem script, installs cltl-backend[host] into it from git and starts leoserv, the host
rem microphone/camera server, on port 8000. Works from cmd and PowerShell
rem alike, so it needs no execution-policy change. Run it in its own window:
rem   start "leoserv" modules\backend\run_host_server.cmd
rem Extra arguments are passed on to leoserv, e.g. --cam_index 1.
setlocal

set "VENV_DIR=%~dp0venv"

rem All three from the ref_scenarios branch, as custom-module\requirements.notebook.txt
rem pins them, so leoserv runs the same cltl-backend, cltl.combot and emissor as
rem the containers rather than PyPI's: the published cltl-backend 1.0.dev0 (and
rem main) lack the /sound endpoint that [cltl.backend.text_output] remote_type:
rem sound posts speech to, and emissor is listed explicitly so cltl.combot's own
rem dependency on it does not resolve to PyPI's. Moving refs are installed once;
rem delete venv\ to pick up newer commits. Building emissor from git only works
rem cleanly on Python 3.10, hence the interpreter check below.
set REQUIREMENTS="emissor @ git+https://github.com/leolani/emissor.git@ref_scenarios" "cltl.combot @ git+https://github.com/leolani/cltl-combot.git@ref_scenarios" "cltl-backend[host] @ git+https://github.com/leolani/cltl-backend.git@ref_scenarios"

rem Install when leoserv.exe is missing rather than when venv\ is: an install
rem that was interrupted leaves the directory behind and is retried here.
if exist "%VENV_DIR%\Scripts\leoserv.exe" goto run

rem Python 3.10, for emissor (above); PyAudio's Windows wheels, with
rem PortAudio bundled, would allow up to 3.13. "python3" is often the
rem Microsoft Store stub on Windows, so use the py launcher, or CLTL_PYTHON
rem to name an interpreter explicitly.
rem CLTL_PYTHON is re-quoted, minus any quotes it came with, for paths with spaces.
if defined CLTL_PYTHON (
    set "PYTHON="%CLTL_PYTHON:"=%""
    goto create
)
py -3.10 -c "" >nul 2>&1 && (
    set "PYTHON=py -3.10"
    goto create
)
echo Python 3.10 not found through the py launcher. 1>&2
echo Install it from https://www.python.org/downloads/windows/ (with the py launcher), 1>&2
echo or set CLTL_PYTHON to the full path of a Python 3.10 python.exe. 1>&2
exit /b 1

:create
rem pip clones the git refs above, so git has to be on PATH.
where git >nul 2>&1 || (
    echo git not found on PATH; install Git for Windows: https://git-scm.com/download/win 1>&2
    exit /b 1
)
echo Creating virtual environment at %VENV_DIR% with %PYTHON% ...
%PYTHON% -m venv "%VENV_DIR%" || exit /b 1
rem "python -m pip", not pip.exe: pip.exe cannot replace itself on Windows.
"%VENV_DIR%\Scripts\python.exe" -m pip install --quiet --upgrade pip || exit /b 1
"%VENV_DIR%\Scripts\python.exe" -m pip install %REQUIREMENTS% || exit /b 1

:run
rem Same flags as run_host_server.sh, which explains them; in particular
rem --resolution VGA keeps leoserv's NATIVE default out of storage\.
"%VENV_DIR%\Scripts\leoserv.exe" ^
    --rate 16000 ^
    --channels 1 ^
    --frame_duration 30 ^
    --resolution VGA ^
    --port 8000 ^
    %*
exit /b %errorlevel%
