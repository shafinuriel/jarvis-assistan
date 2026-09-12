@echo off
title Jarvis
cd /d "%\~dp0"

:loop
echo [%date% %time%] Jarvis запускается...
start "" /B pythonw main.py
echo Jarvis работает...

:wait
timeout /t 5 /nobreak >nul

tasklist /FI "IMAGENAME eq pythonw.exe" | find /I "pythonw.exe" >nul
if errorlevel 1 (
    echo [%date% %time%] Jarvis упал. Перезапускаю...
    goto loop
)

goto wait