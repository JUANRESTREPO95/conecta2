"""Configuración del panel Conecta2."""
from pathlib import Path

CARPETA = Path(__file__).resolve().parent.parent
BD = CARPETA / "datos" / "conecta2.db"
BD.parent.mkdir(exist_ok=True)
ESTATICOS = CARPETA / "app" / "estaticos"
PLANTILLAS = CARPETA / "app" / "plantillas"
LOGOS = CARPETA / "datos" / "logos"
LOGOS.mkdir(exist_ok=True)

# Sesiones: duración en horas
SESION_HORAS = 12

PUERTO_DEFECTO = 8010

# Datos de A2 (donde corre el panel de desarrollo, Windows con driver ODBC).
# En el VPS esto va vacío: quien lee A2 es el agente y sube por la API.
import os
A2_DATA = os.environ.get(
    "CONECTA2_A2_DATA",
    r"C:\Users\juanp\Documents\CLAUDE\conecta2\DESARROLLO\a2HAC_BigStar\Empre001\Data")