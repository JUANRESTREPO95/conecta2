@echo off
rem Instalador del Agente Conecta2 — ejecutar como administrador
cd /d "%~dp0"
powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
pause