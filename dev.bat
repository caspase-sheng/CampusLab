@echo off
rem 用 PowerShell 跑 dev.ps1，顺便绕开执行策略限制。
rem %~dp0 = 本 bat 所在目录（带末尾反斜杠），路径含空格也能正确加引号。
rem %* = 把命令行参数原样传给 dev.ps1，所以 dev.bat -CheckOnly 一样能用。
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" %*
if errorlevel 1 pause