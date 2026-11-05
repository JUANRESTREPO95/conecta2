# Conecta2 — Agente de A2 (Windows)

El agente es el programa que corre en el PC donde está **A2**. Hace dos cosas:

- **Sube** al panel el catálogo, las existencias, los clientes, los vendedores
  y los precios de lista.
- **Baja** los pedidos hechos en el panel y los **monta en A2** como pedidos
  (documento tipo 10), con su cliente y sus líneas.

Es **un solo `.exe`**: trae Python y pyodbc adentro. Lo único que hay que
instalar aparte, una sola vez, es el **driver DBISAM ODBC 4.29 de 32 bits**.
El panel no se instala acá: ese vive en el VPS (Portainer).

---

## 1. Antes de empezar (una sola vez en ese PC)

| # | Qué | Cómo |
|---|-----|------|
| 1 | **A2 instalado y funcionando** | Que abra la empresa (`Empre001`) sin errores. |
| 2 | **Driver DBISAM ODBC 4.29 (32 bits)** | Ejecutar `DBISAM_ODBC_429b132bit.exe` y reiniciar si lo pide. El instalador del agente avisa si no lo encuentra. |
| 3 | **Token del agente** | En el panel: **Empresas → Token del agente → Copiar**. Es por empresa; si se renueva, hay que cambiarlo en el agente. |
| 4 | **Datos de la empresa** | Tener a mano la **URL del panel** (ej. `https://pedidos.col.lt`) y la **carpeta Data de A2** (ej. `C:\A2\Empre001\Data`). |

> No hace falta instalar Python ni pyodbc en ese PC.

---

## 2. Instalar el agente

1. Copiar **`Instalador Conecta2.exe`** al PC de A2 (solo ese archivo).
2. Clic derecho → **Ejecutar como administrador**. Si Windows pide permiso,
   aceptar (el instalador se reabre solo con permisos).
3. Responder las ventanas que van saliendo:

   | Pregunta | Qué poner |
   |----------|-----------|
   | URL del panel | `https://pedidos.col.lt` (sin `/` al final) |
   | TOKEN del agente | el que copiaste de **Empresas** |
   | Carpeta Data de A2 | botón de carpetas → `...\Empre001\Data` (la que tiene `SOperacionInv.dat`) |
   | Depósito | `1` (F) o `2` (W). Si no sabes, deja `1`. |

4. El instalador:
   - verifica el driver DBISAM,
   - copia el agente a `C:\Conecta2\agente`,
   - guarda la configuración,
   - prueba la conexión con el panel,
   - crea el acceso directo **“Conecta2 Agente”** en el Escritorio,
   - deja el registro en `C:\Conecta2\instalador.log`.
5. Al final pregunta si quiere abrir el agente. Decir **Sí**.

A partir de ahí el agente queda **en la bandeja, junto al reloj**, sin ventana.

---

## 3. Cómo se usa

- **Doble clic** en el ícono de la bandeja (o en el acceso directo) → ventana
  con el estado: conexión con el panel, último ciclo, pedidos montados y
  errores, más el registro en vivo.
- **Clic derecho** en el ícono → *Abrir panel*, *Configuración*,
  *Correr ciclo ahora*, *Salir*.
- **Configuración**: URL, token, carpeta de A2, depósito y **Probar conexión**.
  Se aplica al guardar, sin reiniciar.
- **Salir** pide confirmación: mientras esté cerrado no se montan pedidos ni
  se actualiza el catálogo.
- Cerrar la ventana con la **X** no lo cierra: lo devuelve a la bandeja.

> El agente no se instala como servicio: corre mientras la sesión de Windows
> esté abierta. El PC debe quedar encendido (y sin suspensión) para que A2 y
> los pedidos estén al día.

> Abrir **una sola instancia**. Si abres dos, verás dos íconos en la bandeja y
> conviene cerrar una.

---

## 4. Comprobar que quedó bien

1. En el panel, **Catálogo** debe mostrar productos con precio y existencia.
2. En el agente, el chip **PANEL / API** en verde y **ÚLTIMO CICLO** con hora
   reciente (se actualiza cada 30 segundos).
3. Hacer un pedido de prueba en el panel → en **1 minuto** aparece en A2 como
   pedido, con su cliente en la columna **Clientes** y el nombre en
   **Persona Contacto**.
4. En el panel, el pedido pasa a **montado**.

---

## 5. Archivos y rutas

| Ruta | Qué es |
|------|--------|
| `C:\Conecta2\agente\Conecta2Agente.exe` | El agente |
| `C:\Conecta2\agente\config_agente.json` | URL, token, carpeta de A2 y depósito |
| `C:\Conecta2\agente\log_agente.txt` | Registro de lo que hace (aquí se mira si algo falla) |
| `C:\Conecta2\agente\datos\` | Cachés (precios ya subidos, etc.) |
| `C:\Conecta2\instalador.log` | Registro de la instalación |
| `Escritorio\Conecta2 Agente.lnk` | Acceso directo |

En esta carpeta (`AGENTE`) están el instalador, el `.exe` suelto y el kit para
regenerar el instalador (`instalar.ps1`, `sfx.ini`). **Solo se distribuye
`Instalador Conecta2.exe`**; no copies `config_agente.json` ni `datos\` a otro
PC, porque llevan el token y datos del equipo anterior.

---

## 6. Actualizar el agente

Cuando haya una versión nueva:

1. En el PC de A2, clic derecho en el ícono de la bandeja → **Salir** (o
   Administrador de tareas → finalizar `Conecta2Agente.exe`).
2. Ejecutar el **`Instalador Conecta2.exe`** nuevo como administrador y
   responder otra vez URL, token, carpeta y depósito.
3. Abrirlo de nuevo.

La configuración anterior queda pisada por la que escribas en el instalador.
Si solo quieres cambiar un dato (token, depósito), no hace falta reinstalar:
**Configuración** en el agente.

---

## 7. Problemas frecuentes

| Síntoma | Qué revisar |
|---------|-------------|
| “No encuentro el driver DBISAM ODBC (32 bits)” | Instalar `DBISAM_ODBC_429b132bit.exe` y reiniciar. Debe ser **32 bits**. |
| Chip PANEL en rojo / “token rechazado” | Token vencido o de otra empresa. Copiar de nuevo en **Empresas → Token del agente** y pegarlo en **Configuración → Probar conexión**. |
| “No conecta” con una URL `https://` | Usar la URL exacta del panel, con `https://` y sin `/` al final. El agente reintenta solo con TLS 1.2 si la red corta TLS 1.3. |
| El catálogo no se actualiza | Ver que el agente esté abierto (ícono en la bandeja) y que **ÚLTIMO CICLO** avance. El catálogo se refresca cada 5 minutos. |
| El pedido no aparece en A2 | Revisar `log_agente.txt`: si dice “panel no responde” o el error de A2, el pedido queda en cola y se monta cuando se arregle. |
| El pedido sale **sin cliente** en A2 | El cliente se toma de la ficha del cliente en A2; si el cliente no existe allá, el pedido va como CONSUMIDOR FINAL. Revisar que el cliente esté en el panel (se actualizan con el agente). |
| Cantidades o códigos raros | El agente respeta el código exacto del producto (espacios, puntos, mayúsculas). Revisar que el producto exista igual en A2. |
| Sale dos veces el ícono | Hay dos instancias abiertas: cerrar una desde el Administrador de tareas. |
| Windows no deja instalar | Ejecutar el instalador **como administrador** y aceptar el aviso de SmartScreen (“Más información → Ejecutar de todas formas”). |

---

## 8. Recompilar (solo desarrollo)

En `DESARROLLO\conecta2\agente`:

```bat
"C:\Users\juanp\Python311-32\python.exe" -m PyInstaller --noconfirm Conecta2Agente.spec
```

Después copiar `dist\Conecta2Agente.exe` a esta carpeta y regenerar el
instalador (con WinRAR instalado):

```bat
"C:\Program Files\WinRAR\WinRAR.exe" a -sfx -zsfx.ini -ep1 "Instalador Conecta2.exe" ^
  Conecta2Agente.exe instalar.bat instalar.ps1 Leame.txt sfx.ini
```

`instalar.bat` solo llama a `instalar.ps1`; el `sfx.ini` hace que el
autoextraíble ejecute ese `.bat`.
