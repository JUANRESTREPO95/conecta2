# Conecta2 — Análisis desde cero

Arranque: 2026-11-03. Trabajamos sobre la copia real de A2 en
`C:\Users\juanp\Documents\CLAUDE\CONECTOR\a2HAC_BigStar` (backup RAR
`REM-20261026-(211649).rar` ya extraído y eliminado la carpeta temporal).

## Qué es Conecta2

Reemplazo del **Conector** actual (`Conector.exe` + nube sitio24x.com + APK):
web de pedidos para los vendedores + agente que inserta los pedidos en **A2**.

## Paso 1 — A2 funcionando ✅

- A2 (`A2Sistema.exe`) abre y Juan ingresa a la empresa **Empre001** sin errores.
- Juan reorganizó las rutas de las tablas en A2 para que apunten a esta copia.

## Estructura de la copia

- Programa: `a2HAC_BigStar\` (A2Sistema.exe, Conector.exe, dbsys.exe...).
- Empresa: `a2HAC_BigStar\Empre001\`, con **Data** (tablas .dat/.idx/.blb) y
  **CONFIGR** (formularios y configuración por documento: PEDIDOS, FACTURAS...).

## Tablas clave (Empre001\Data)

- `SInventario.dat` — productos del catálogo.
- `SClientes.dat` — clientes.
- `SEncabezadoVenta` / `SDetalleVenta.dat` — encabezados y líneas de ventas
  (pedidos tipo 10 y facturas tipo 11). Ahí vive el **precio real** de venta.
- `SDetalleInv` — costos.
- Nota 2026-10-27: los pedidos insertados en A2 viven en tablas tipo
  `FTI_DOCUMENTO` (documento `17-20260020`); por revisar si esta copia las
  trae (aún no aparecen en Data; se revisa al tener acceso ODBC).

## Acceso a datos (en curso)

- Driver **DBISAM ODBC 4.29 (32 bits)** de Elevate Software: **no instalado**
  en este PC. El sitio oficial exige registro gratuito:
  <https://www.elevatesoft.com/download?category=dbisam>.
  - Espejos: software.informer, softdeluxe (verificar antes).
- La conexión es local: `DRIVER={DBISAM 4 ODBC Driver};ConnectionType=Local;CatalogName=<Empre001\Data>`.
- Por ser driver de 32 bits hace falta **Python 3.11 de 32 bits** con `pyodbc`.
- Caché de precios por `FDI_AUTOINCREMENT` (leer por fecha tarda 268 s;
  por autoincremento ~0,5 s con 20.000 filas).

## Paso 3 — Conector actual (pendiente)

Analizar `Conector.exe` + carpeta `Conectores\` y `CMS_WCom_a2.CMS` para
entender qué hace hoy (con qué tablas habla y qué formato usa la nube).

## Decisiones del diseño anterior (a revalidar)

- Web responsive, sin app nativa. Sin selección de cliente (referencia libre).
- Número de pedido `vendedor-año+consecutivo` (`17-20260020`).
- Hoja PDF/PNG con 5 campos: Pedido, Fecha, Referencia, Vendedor, Monto.
- Monto sin IVA (A2 lo calcula al facturar).
- Borrar pedidos: solo admin y solo en Conecta2.
- Sincronización: catálogo 5 min, pedidos 30 s.
- Precio = último precio vendido (`SDetalleVenta`).
- Admin elige depósito 1, 2 o suma. Claves gestionadas en Conecta2.
- Cliente por defecto: CONSUMIDOR FINAL, NIT 2222222222.