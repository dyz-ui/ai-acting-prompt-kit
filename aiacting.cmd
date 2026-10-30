@echo off
rem Windows 下的命令入口：aiacting <子命令>
rem 优先用项目自带的 .venv，没有就退回系统 Python
setlocal
set "HERE=%~dp0"
if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" -m aiacting %*
) else (
  python -m aiacting %*
)
