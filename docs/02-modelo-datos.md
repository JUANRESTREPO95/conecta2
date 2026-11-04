# Conecta2 — Modelo de datos A2 (mapeo real)

Leído por ODBC contra `a2HAC_BigStar\Empre001\Data` el 2026-11-03.
Scripts del análisis en `C:\Users\juanp\Documents\CLAUDE\CONECTOR\conecta2\analisis\`.

## Truco general para SQL de DBISAM

- No soporta `TOP 1` ni `MAX(...)` en subconsulta; usar `SELECT *` y
  `fetchone()` / literal.
- Las columnas del `ORDER BY` deben estar en el `SELECT`.
- No acepta parámetros `?` con el driver (HY004); pasar literales inline.
- El texto viene como Latin-1: configurar
  `con.setdecoding(pyodbc.SQL_CHAR, encoding="cp1252")`.
- Varios productos traen espacios al inicio del código (`' GG-1914'`).

## Catálogo — `Sinventario`

- Clave de producto: `FI_CODIGO` (con espacios que se recortan).
- `FI_DESCRIPCION`, `FI_STATUS` (True=activo), `FI_MARCA`, `FI_CATEGORIA`,
  `FI_UNIDAD`, `FI_MONEDA` ('1').
- **`FI_PRECIOLISTA` existe pero está 100% vacía** (0 de 28.550) → se
  reconfirma: el precio real está en la última venta (`SDetalleVenta`).
- `FI_INTERNET`: bandera que podría filtrar el catálogo (por decidir).
- También hay `FI_ZEXTRA1..6` (por si la web necesita campos extra más adelante).

## Existencia por depósito — `SinvDep`

- `FT_CODIGOPRODUCTO` + `FT_CODIGODEPOSITO` + `FT_EXISTENCIA`.
- También: `FT_EXISTENCIAAPARTADA`, `FT_VISIBLE`, `FT_TIPO` (4 en las filas
  vistas), `FT_EXISTENCIAPEDIDO`.
- Filas: depósito 1 = 28.386, depósito 2 = 7.555. La suma para el modo
  "ambos" es solo sumar `FT_EXISTENCIA` de los dos códigos.

## Depósitos — `Sdepositos`

- `FDP_CODIGO` 1 = **'F'** y 2 = **'W'**, ambos activos. Coincide con la
  decisión de que el admin elija depósito 1, 2 o la suma.

## Vendedores — `Svendedores`

- `FV_CODIGO` ('26'...), `FV_DESCRIPCION` (nombre), `FV_STATUS` (activo),
  `FV_CLAVE` (clave para entrar a A2; varios quedan vacíos).
- El panel de Conecta2 maneja su propia clave de acceso web por vendedor.

## Pedidos insertados en A2 (lo que hoy hace el Conector)

**Cabecera — `SOperacionInv`** (aquí viven los encabezados FTI de ventas,
pedidos, compras, etc., separados por `FTI_TIPO`). Tipos encontrados:
- 11 = facturas (18.000), 10 = pedidos (4.111), 8, 6, 2, 3... otros.

Pedido típico insertado por el Conector (ejemplo `26-C018245`):

| Campo | Valor |
|---|---|
| `FTI_DOCUMENTO` | `26-C018245` (vendedor + `-C0` + contador) |
| `FTI_TIPO` | 10 (pedido) |
| `FTI_STATUS` | 4 |
| `FTI_VISIBLE` | True |
| `FTI_FECHAEMISION` | 2026-10-26 |
| `FTI_DEPOSITOSOURCE` | 1 |
| `FTI_MONEDA` | 1 |
| `FTI_VENDEDORASIGNADO` | '26' |
| `FTI_TOTALPRECIO` / `FTI_TOTALNETO` | 5.600,0 (sin IVA) |
| `FTI_RIFCLIENTE` / `FTI_NITCLIENTE` | vacíos |
| `FTI_DETALLECOMENTARIO` | referencia (texto del vendedor) |

Ojo: hay pedidos tipo 10 con formato distinto (`00011867`, vendedor 17,
`FTI_TOTALNETO` lleno) que parecen venir de otra vía (caja/POS), no del
Conector.

**Líneas — `SDetalleVenta`** (columna clave real: `FDI_TIPOOPERACION`, no
`FDI_TIPO`):

| Campo | Valor ejemplo |
|---|---|
| `FDI_DOCUMENTO` | `26-C018245` |
| `FDI_TIPOOPERACION` | 10 |
| `FDI_CODIGO` | `001BT` (código de producto) |
| `FDI_CANTIDAD` | 1.0 |
| `FDI_PRECIODEVENTA` | 5.600,0 (y `FDI_PRECIOSINDESCUENTO`) |
| `FDI_PORCENTIMPUESTO1` | True (A2 calcula el IVA al facturar) |
| `FDI_DEPOSITOSOURCE` / `FDI_USADEPOSITOS` | 1 / True |
| `FDI_STATUS` / `FDI_VISIBLE` | 4 / True |
| `FDI_OPERACION_AUTOINCREMENT` | 22396 (enlaza con `FTI_AUTOINCREMENT` de la cabecera) |
| `FDI_FECHAOPERACION` | 2026-10-26 |

## Numeración de pedidos (decisión por tomar)

- Hoy el Conector usa **contador global** `vendedor-C0NNNNNN`
  (`00-C018230`, `26-C018242`... los números avanzan entre vendedores).
- La idea anterior era `vendedor-año+consecutivo` (`17-20260020`).
- Opciones para el panel nuevo: copiar el formato C0 del Conector o usar el
  esquema año+consecutivo. **Pendiente con Juan.**

## Precios

- Sin precios de lista en catálogo (columna vacía). Precio = última venta
  del producto (`FDI_PRECIODEVENTA` en `SDetalleVenta`).
- Caché de precios por `FDI_AUTOINCREMENT` (escaneo por fecha: 268 s por
  20.000 filas; por autoincremento ~0,5 s). Arranque recomendado: mirar
  hacia atrás ~50.000 ventas.