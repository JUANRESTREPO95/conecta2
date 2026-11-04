"""Lectura de A2 por ODBC (solo corre donde exista el driver DBISAM).

En producción esto lo usa el agente (PC Windows de la empresa); mientras
desarrollamos, el panel también lo puede leer porque corre con Python de
32 bits sobre la copia local.
"""
from pathlib import Path

try:  # el driver solo existe en la PC de A2; el panel corre sin él
    import pyodbc
except ImportError:  # pragma: no cover
    pyodbc = None

from app import config

CADENA = "DRIVER={DBISAM 4 ODBC Driver};ConnectionType=Local;CatalogName="


def conectar(data: str = ""):
    if pyodbc is None:
        raise RuntimeError("Este equipo no tiene el driver DBISAM/pyodbc; "
                           "la lectura de A2 solo se hace en la PC del agente.")
    catalogo = data or config.A2_DATA
    con = pyodbc.connect(CADENA + str(catalogo), autocommit=True)
    con.setdecoding(pyodbc.SQL_CHAR, encoding="cp1252")
    return con


def _cur(data: str = ""):
    return conectar(data).cursor()


def leer_catalogo(data: str = "") -> list[dict]:
    """Productos activos y marcados para la web (FI_INTERNET)."""
    cur = _cur(data)
    cur.execute("SELECT FI_CODIGO, FI_DESCRIPCION, FI_MARCA, FI_CATEGORIA, "
                "FI_UNIDAD, FI_MONEDA, FI_STATUS, FI_INTERNET FROM Sinventario")
    cols = [d[0] for d in cur.description]
    productos = []
    k = {"FI_CODIGO": "codigo", "FI_DESCRIPCION": "descripcion",
         "FI_MARCA": "marca", "FI_CATEGORIA": "categoria",
         "FI_UNIDAD": "unidad", "FI_MONEDA": "moneda",
         "FI_STATUS": "activo", "FI_INTERNET": "internet"}
    while True:
        fila = cur.fetchone()
        if fila is None:
            break
        d = dict(zip(cols, fila))
        productos.append({k[c]: d[c] for c in k})
    return productos


def leer_vendedores(data: str = "") -> list[dict]:
    """Vendedores de A2 (Svendedores): código, nombre, activo y clave de A2."""
    cur = _cur(data)
    cur.execute("SELECT FV_CODIGO, FV_DESCRIPCION, FV_STATUS, FV_CLAVE "
                "FROM Svendedores")
    vendedores = []
    while True:
        fila = cur.fetchone()
        if fila is None:
            break
        codigo = str(fila[0] or "").strip()
        if not codigo:
            continue
        vendedores.append({
            "codigo": codigo,
            "nombre": str(fila[1] or "").strip() or codigo,
            "activo": bool(fila[2]),
            "clave_a2": (str(fila[3]).strip() if fila[3] is not None else ""),
        })
    return vendedores


def leer_stock(data: str = "") -> dict:
    """Existencia por (codigo_producto, deposito)."""
    cur = _cur(data)
    cur.execute("SELECT FT_CODIGOPRODUCTO, FT_CODIGODEPOSITO, SUM(FT_EXISTENCIA) "
                "FROM SinvDep GROUP BY FT_CODIGOPRODUCTO, FT_CODIGODEPOSITO")
    stock = {}
    while True:
        fila = cur.fetchone()
        if fila is None:
            break
        stock[(fila[0].strip().upper(), int(fila[1]))] = float(fila[2] or 0)
    return stock


def leer_precios_ultimos(limite: int = 100_000, data: str = "") -> dict:
    """Último precio de venta por producto, mirando hacia atrás `limite` líneas."""
    cur = _cur(data)
    cur.execute(f"SELECT FDI_CODIGO, FDI_PRECIODEVENTA, FDI_AUTOINCREMENT "
                f"FROM SDetalleVenta WHERE FDI_TIPOOPERACION = 11 "
                f"ORDER BY FDI_AUTOINCREMENT DESC")
    precios = {}
    vistos = 0
    while vistos < limite:
        fila = cur.fetchone()
        if fila is None:
            break
        vistos += 1
        cod = fila[0].strip().upper()
        precio = fila[1]
        if precio is not None and precio >= 0 and cod not in precios:
            precios[cod] = float(precio)
    return precios