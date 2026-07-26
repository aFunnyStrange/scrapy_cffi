@echo off
setlocal
where python >nul 2>nul
if errorlevel 1 goto py_fallback
python "%~dp0demo_docker.py" %*
exit /b %errorlevel%

:py_fallback
py -3 "%~dp0demo_docker.py" %*
exit /b %errorlevel%
