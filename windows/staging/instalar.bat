@echo off
rem Instalador del Agente Conecta2 (paquete .exe)
cd /d "%~dp0"
powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
