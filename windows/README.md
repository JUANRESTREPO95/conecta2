# Conecta2 — instalador para Windows (agente)

## Qué es

`Instalador Conecta2.exe` — ejecutable autoextraíble que instala en la PC del
negocio (donde vive A2):

1. Python 3.11 **32 bits** en `C:\Conecta2\python32` (si falta)
2. Driver **DBISAM ODBC 4.29 (32 bits)** (si falta)
3. `pyodbc`
4. El **agente** en `C:\Conecta2\agente`
5. Acceso directo **"Conecta2 Agente"** en el Escritorio

El asistente pide: URL del panel, TOKEN del agente (se copia del panel:
**Empresas → Token del agente**), carpeta `Empre001\Data` de A2 y depósito.
Al final prueba la conexión con el panel.

## Uso

Doble clic en `Instalador Conecta2.exe` → aceptar el aviso de administrador
de Windows. (Sin firma digital, Windows puede pedir "Más información →
Ejecutar de todas formas".)

## Estructura para reconstruirlo

| Archivo/carpeta | Qué es |
|---|---|
| `Instalador Conecta2.exe` | paquete final listo para entregar |
| `staging/` | contenido que se empaqueta (agente, instaladores, scripts) |
| `sfx.ini` | configuración del autoextraíble (ejecuta `instalar.bat`) |

Para regenerar el .exe después de cambiar el agente:

```bat
cd staging
"C:\Program Files\WinRAR\Rar.exe" a -r -sfx -z"../sfx.ini" "../Instalador Conecta2.exe" .
```

## Notas

- `staging/instalar.ps1` es el asistente (en ASCII a propósito: PowerShell 5.1
  rompe los acentos sin BOM).
- Cada empresa tiene su propio token; el mismo instalador sirve para todos los
  negocios, solo cambia el token y la carpeta de A2.
- El agente no necesita el panel en la misma máquina: funciona con la URL del
  panel aunque esté en otro servidor.
