"""Lectura de A2 por ODBC (solo en la PC que tiene el driver DBISAM de 32 bits).

Versión autosuficiente del lector: no depende de la carpeta del panel.
La ruta de datos se pasa siempre como argumento (CONECTA2_A2_DATA).
"""
try:
    import pyodbc
except ImportError:  # muestra un error claro en vez de morir en silencio
    pyodbc = None

CADENA = "DRIVER={DBISAM 4 ODBC Driver};ConnectionType=Local;CatalogName="


def conectar(data: str):
    if pyodbc is None:
        raise RuntimeError("Falta pyodbc en este Python. Instala con: "
                           "python -m pip install pyodbc")
    con = pyodbc.connect(CADENA + str(data), autocommit=True)
    con.setdecoding(pyodbc.SQL_CHAR, encoding="cp1252")
    return con


def _cur(data: str):
    return conectar(data).cursor()


def leer_catalogo(data: str) -> list[dict]:
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


def leer_vendedores(data: str) -> list[dict]:
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


def leer_stock(data: str) -> dict:
    """Existencia por (codigo_producto, deposito)."""
    cur = _cur(data)
    cur.execute("SELECT FT_CODIGOPRODUCTO, FT_CODIGODEPOSITO, SUM(FT_EXISTENCIA) "
                "FROM SinvDep GROUP BY FT_CODIGOPRODUCTO, FT_CODIGODEPOSITO")
    stock = {}
    while True:
        fila = cur.fetchone()
        if fila is None:
            break
        stock[(str(fila[0]), int(fila[1]))] = float(fila[2] or 0)
    return stock


def leer_precios_ultimos(limite: int, data: str) -> dict:
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
        cod = str(fila[0] or "")
        precio = fila[1]
        if precio is not None and precio >= 0 and cod not in precios:
            precios[cod] = float(precio)
    return precios


def leer_clientes(data: str) -> list[dict]:
    """Clientes de A2 (SClientes): código, nombre y NIT."""
    cur = _cur(data)
    cur.execute("SELECT FC_CODIGO, FC_DESCRIPCION, FC_NIT, FC_RIF, "
                "FC_DIRECCION1, FC_TELEFONO FROM SClientes")
    clientes = []
    while True:
        fila = cur.fetchone()
        if fila is None:
            break
        codigo = str(fila[0] or "").strip()
        if not codigo:
            continue
        clientes.append({
            "codigo": codigo,
            "nombre": str(fila[1] or "").strip() or codigo,
            "nit": str(fila[2] or "").strip(),
            "rif": str(fila[3] or "").strip(),
            "direccion": str(fila[4] or "").strip(),
            "telefono": str(fila[5] or "").strip(),
        })
    return clientes


def _texto(valor) -> str:
    """Texto seguro para SQL de DBISAM (escapa comillas)."""
    return str(valor or "").replace("'", "''")


def cliente_existente(data: str, codigo: str) -> dict | None:
    """Devuelve el cliente de A2 con ese código o NIT (o None)."""
    cur = _cur(data)
    cod = _texto(codigo)
    fila = cur.execute(
        f"SELECT FC_CODIGO, FC_DESCRIPCION FROM SClientes "
        f"WHERE FC_CODIGO = '{cod}' OR FC_NIT = '{cod}'").fetchone()
    if fila is None:
        return None
    return {"codigo": str(fila[0] or "").strip(),
            "nombre": str(fila[1] or "").strip()}


def crear_cliente(data: str, cliente: dict) -> None:
    """Inserta un cliente nuevo en SClientes (el código es el NIT)."""
    cur = _cur(data)
    codigo = _texto(cliente.get("codigo") or cliente.get("nit"))
    nombre = _texto(cliente.get("nombre"))
    nit = _texto(cliente.get("nit") or cliente.get("codigo"))
    direccion = _texto(cliente.get("direccion"))
    telefono = _texto(cliente.get("telefono"))
    vendedor = _texto(cliente.get("vendedor")) or "01"
    cur.execute(
        "INSERT INTO SClientes (FC_CODIGO, FC_DESCRIPCION, FC_STATUS, "
        "FC_CLASIFICACION, FC_NIT, FC_RIF, FC_DIRECCION1, FC_TELEFONO, "
        "FC_MONEDA, FC_VENDEDOR, FC_COBRADOR, FC_DIASCREDITO, "
        "FC_LIMITECREDITO, FC_MAXIMODESCUENTO, FC_EXENTO, FC_ESPECIAL) "
        f"VALUES ('{codigo}', '{nombre}', True, '0', '{nit}', '', "
        f"'{direccion}', '{telefono}', '1', '{vendedor}', '{vendedor}', "
        "0, 0, 0, False, False)")


def leer_autorizados(data: str) -> list[dict]:
    """Autorizados de A2 (Sautorizados): direcciones de cada cliente.

    Son solo informativos para la hoja del pedido; el agente nunca escribe
    nada de esto en A2.
    """
    cur = _cur(data)
    cur.execute("SELECT FCA_CODIGOAUTORIZADO, FCA_DESCRIPCION, FCA_DIRECCION, "
                "FCA_CODIGOCLIENTE, FCA_STATUS FROM Sautorizados")
    autorizados = []
    while True:
        fila = cur.fetchone()
        if fila is None:
            break
        codigo = str(fila[0] or "").strip()
        cliente = str(fila[3] or "").strip()
        if not codigo or not cliente:
            continue
        autorizados.append({
            "codigo": codigo,
            "cliente_codigo": cliente,
            "nombre": str(fila[1] or "").strip(),
            "direccion": str(fila[2] or "").strip(),
            "activo": bool(fila[4]),
        })
    return autorizados


def leer_precios_catalogo(data: str) -> dict:
    """Precios de lista por producto, desde SFixed.FX_COSTOS (Precio 1 = índice 27)."""
    import struct
    cur = _cur(data)
    cur.execute("SELECT FX_CODIGO, FX_COSTOS FROM SFixed WHERE FX_TIPO = 'B'")
    precios = {}
    while True:
        fila = cur.fetchone()
        if fila is None:
            break
        codigo = str(fila[0] or "")      # código tal cual (con espacios)
        blob = fila[1]
        if not codigo.strip() or not isinstance(blob, (bytes, bytearray)) or len(blob) < 28 * 8:
            continue
        valor = struct.unpack_from("<q", blob, 27 * 8)[0] / 10000.0
        if valor > 0:
            precios[codigo] = valor
    return precios
