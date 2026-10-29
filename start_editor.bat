@echo off
chcp 65001 >nul
title RPMC Exam Editor
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)
"%PY_EXE%" rpmc.py editor %*
if %ERRORLEVEL% neq 0 pause

