@echo off
rem Windows counterpart of run_host_server.sh: creates venv\ next to this
rem script, installs cltl-backend[host] into it from git and starts leoserv, the host
rem microphone/camera server, on port 8000. Works from cmd and PowerShell
rem alike, so it needs no execution-policy change. Run it in its own window:
rem   start "leoserv" modules\backend\run_host_server.cmd
rem Extra arguments are passed on to leoserv, e.g. --cam_index 1.
setlocal

set "VENV_DIR=%~dp0venv"

rem From the ref_scenarios branch, the ref custom-module\requirements.notebook.txt
rem pins too, not PyPI: the published 1.0.dev0 (and main) lack the /sound
rem endpoint that [cltl.backend.text_output] remote_type: sound posts speech to.
rem A moving ref is installed once; delete venv\ to pick up newer commits.
set "CLTL_BACKEND=cltl-backend[host] @ git+https://github.com/leolani/cltl-backend.git@ref_scenarios"

rem Install when leoserv.exe is missing rather than when venv\ is: an install
rem that was interrupted leaves the directory behind and is retried here.
if exist "%VENV_DIR%\Scripts\leoserv.exe" goto run

rem Python 3.10-3.13 only: PyAudio publishes Windows wheels (with PortAudio
rem bundled) up to 3.13, and anything newer would try to compile it from
rem source. "python3" is often the Microsoft Store stub on Windows, so use the
rem py launcher, or CLTL_PYTHON to name an interpreter explicitly.
rem CLTL_PYTHON is re-quoted, minus any quotes it came with, for paths with spaces.
if defined CLTL_PYTHON (
    set "PYTHON="%CLTL_PYTHON:"=%""
    goto create
)
for %%v in (3.10 3.11 3.12 3.13) do (
    py -%%v -c "" >nul 2>&1 && (
        set "PYTHON=py -%%v"
        goto create
    )
)
echo No Python 3.10-3.13 found through the py launcher. 1>&2
echo Install one from https://www.python.org/downloads/windows/ (with the py launcher), 1>&2
echo or set CLTL_PYTHON to the full path of a python.exe of one of those versions. 1>&2
exit /b 1

:create
rem pip clones the git ref above, so git has to be on PATH.
where git >nul 2>&1 || (
    echo git not found on PATH; install Git for Windows: https://git-scm.com/download/win 1>&2
    exit /b 1
)
echo Creating virtual environment at %VENV_DIR% with %PYTHON% ...
%PYTHON% -m venv "%VENV_DIR%" || exit /b 1
rem "python -m pip", not pip.exe: pip.exe cannot replace itself on Windows.
"%VENV_DIR%\Scripts\python.exe" -m pip install --quiet --upgrade pip || exit /b 1
"%VENV_DIR%\Scripts\python.exe" -m pip install "%CLTL_BACKEND%" || exit /b 1

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
