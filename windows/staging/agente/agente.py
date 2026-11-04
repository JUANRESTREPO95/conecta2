"""Agente Conecta2 — corre en la PC de A2 (Python 32 bits + driver DBISAM).

1. Sube el catálogo y existencias al panel (cada 5 minutos).
2. Sube los precios nuevos (última venta, con caché por autoincremento).
3. Baja los pedidos pendientes y los inserta en A2 (cabecera + líneas).

Lee su configuración de `config_agente.json` (junto a este archivo):
  { "api": "https://tu-panel", "token": "...", "a2_data": "C:\\...\\Data",
    "deposito": 1 }
También acepta variables de entorno (CONECTA2_API_URL, CONECTA2_TOKEN,
CONECTA2_A2_DATA, CONECTA2_DEPOSITO, CONECTA2_INTERVALO), que tienen prioridad.

Uso: python agente.py           (corre para siempre)
     python agente.py --una-vez (un solo ciclo)
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

CARPETA = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))

import a2  # lector de A2 autosuficiente (vive junto al agente)


def env(nombre: str, defecto: str = "") -> str:
    return os.environ.get(nombre, defecto)


def _config() -> dict:
    archivo = CARPETA / "config_agente.json"
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except Exception:
        return {}


_CFG = _config()

API = env("CONECTA2_API_URL") or _CFG.get("api") or "http://127.0.0.1:8011"
TOKEN = env("CONECTA2_TOKEN") or _CFG.get("token", "")
A2_DATA = env("CONECTA2_A2_DATA") or _CFG.get("a2_data", "")
DEPOSITO = int(env("CONECTA2_DEPOSITO") or _CFG.get("deposito") or 1)
INTERVALO = int(env("CONECTA2_INTERVALO", "30"))
# cliente por defecto para que A2 no muestre el cliente en blanco
CLIENTE_NIT = env("CONECTA2_CLIENTE_NIT", "2222222222")  # CONSUMIDOR FINAL
CACHE_PRECIOS = CARPETA / "datos" / "precios_cache.json"

ULTIMA_SYNC_CATALOGO = 0.0


def api(ruta: str, carga=None, metodo: str = "GET"):
    req = urllib.request.Request(API + ruta)
    req.add_header("Authorization", "Bearer " + TOKEN)
    if carga is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(carga).encode()
    req.method = metodo
    with urllib.request.urlopen(req, timeout=120) as r:
        respuesta = r.read().decode()
    return json.loads(respuesta) if respuesta else {}


def log(*partes) -> None:
    ahora = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(ahora, *partes, flush=True)
    for cola in COLAS:
        cola.put((ahora, " ".join(str(p) for p in partes)))


# colas conectadas por la versión gráfica (agente_grafico.py)
COLAS: list = []
ESTADO = {"panel": "—", "ultimo_ciclo": None, "montados": 0, "errores": 0}


# ---------- sincronización ----------

def sube_catalogo() -> None:
    productos = a2.leer_catalogo(A2_DATA)
    for i in range(0, len(productos), 1000):
        api("/api/catalogo", {"lote": productos[i:i + 1000]}, "POST")
    stock = a2.leer_stock(A2_DATA)
    lotes = [{"codigo": c, "deposito": d, "existencia": e}
             for (c, d), e in stock.items()]
    for i in range(0, len(lotes), 2000):
        api("/api/stock", {"lote": lotes[i:i + 2000]}, "POST")
    log("catálogo y existencias subidos:", len(productos), "productos,", len(lotes), "existencias")


def sube_precios() -> None:
    cache = {"ultimo": 0, "precios": {}}
    if CACHE_PRECIOS.is_file():
        try:
            cache = json.loads(CACHE_PRECIOS.read_text())
        except Exception:
            pass
    con = a2.conectar(A2_DATA)
    try:
        cur = con.cursor()
        ultimo = int(cache.get("ultimo", 0))
        # el arranque mira hacia atrás 50.000 ventas (para llenar precios)
        if ultimo == 0:
            cur.execute("SELECT MAX(FDI_AUTOINCREMENT) FROM SDetalleVenta")
            fila = cur.fetchone()
            punto = max(0, int(fila[0] or 0)) - 50_000
            condicion = ">="
        else:
            punto = ultimo  # de aquí en adelante solo lo nuevo (>)
            condicion = ">"
        cur.execute(f"SELECT FDI_CODIGO, FDI_PRECIODEVENTA, FDI_AUTOINCREMENT "
                    f"FROM SDetalleVenta WHERE FDI_AUTOINCREMENT {condicion} {punto} "
                    f"ORDER BY FDI_AUTOINCREMENT")
        precios = cache.get("precios", {})
        count = 0
        while True:
            fila = cur.fetchone()
            if fila is None:
                break
            codigo = str(fila[0] or "").strip().upper()
            precio = fila[1]
            if precio is not None and precio >= 0:
                precios[codigo] = float(precio)
                ultimo = max(ultimo, int(fila[2] or 0))
                count += 1
    finally:
        con.close()
    # solo los precios NUEVOS de este ciclo (el resto ya están en el panel)
    viejos = cache.get("precios", {})
    nueva_lote = [{"codigo": c, "precio": p} for c, p in precios.items()
                  if viejos.get(c) != p]
    total = len(viejos) + len(nueva_lote)
    for i in range(0, len(nueva_lote), 2000):
        api("/api/precios", {"lote": nueva_lote[i:i + 2000]}, "POST")
    cache.update({"ultimo": ultimo, "precios": precios})
    CACHE_PRECIOS.parent.mkdir(exist_ok=True)
    CACHE_PRECIOS.write_text(json.dumps(cache))
    log(f"precios: {count} líneas nuevas leídas, {len(nueva_lote)} subidos "
        f"({total} en total)")
    return


# ---------- montar pedidos en A2 ----------

def _sql_texto(t) -> str:
    """Texto seguro para SQL de DBISAM (escapa comillas)."""
    return str(t or "").replace("'", "''")


def montar(pedido: dict) -> None:
    numero = pedido["numero"]
    referencia = (pedido.get("referencia") or "")[:250]
    lineas = pedido["lineas"] or []
    if not lineas:
        api("/api/pedidos/error", {"id": pedido["id"],
                                   "mensaje": "pedido sin líneas"}, "POST")
        return
    hoy = dt.date.today()
    con = a2.conectar(A2_DATA)
    cur = con.cursor()
    total = sum(f["cantidad"] * (f["precio"] or 0) for f in lineas)
    # los códigos de A2 deben conservar sus espacios originales: los pedimos
    # de la BD del panel (columna codigo_a2) si el lote la trae; si no, tal cual
    try:
        # limpiar restos de un intento anterior de este mismo pedido
        # (nuestros números son únicos, así que si ya existe es resto nuestro)
        viejos = cur.execute(
            f"SELECT FDI_AUTOINCREMENT FROM SDetalleVenta "
            f"WHERE FDI_DOCUMENTO = '{_sql_texto(numero)}' "
            f"AND FDI_TIPOOPERACION = 10").fetchall()
        if viejos:
            cur.execute(f"DELETE FROM SDetalleVenta "
                        f"WHERE FDI_DOCUMENTO = '{_sql_texto(numero)}' "
                        f"AND FDI_TIPOOPERACION = 10")
        vieja = cur.execute(
            f"SELECT FTI_AUTOINCREMENT FROM SOperacionInv "
            f"WHERE FTI_DOCUMENTO = '{_sql_texto(numero)}' "
            f"AND FTI_TIPO = 10").fetchone()
        if vieja:
            cur.execute(f"DELETE FROM SOperacionInv "
                        f"WHERE FTI_DOCUMENTO = '{_sql_texto(numero)}' "
                        f"AND FTI_TIPO = 10")

        sql_cab = (
            "INSERT INTO SOperacionInv (FTI_DOCUMENTO, FTI_TIPO, FTI_STATUS, "
            "FTI_VISIBLE, FTI_FECHAEMISION, FTI_DEPOSITOSOURCE, FTI_MONEDA, "
            "FTI_TOTALITEMS, FTI_TOTALPRECIO, FTI_TOTALNETO, "
            "FTI_VENDEDORASIGNADO, FTI_NITCLIENTE, FTI_RIFCLIENTE, "
            "FTI_DETALLECOMENTARIO) "
            f"VALUES ('{_sql_texto(numero)}', 10, 4, True, '{hoy.isoformat()}', "
            f"{DEPOSITO}, 1, {len(lineas)}, {total}, {total}, "
            f"'{_sql_texto(str(pedido['vendedor'])[:30])}', "
            f"'{_sql_texto(CLIENTE_NIT)}', '{_sql_texto(CLIENTE_NIT)}', "
            f"'{_sql_texto(referencia)}')")
        cur.execute(sql_cab)
        autoinc = cur.execute(
            f"SELECT FTI_AUTOINCREMENT FROM SOperacionInv "
            f"WHERE FTI_DOCUMENTO = '{_sql_texto(numero)}' "
            f"AND FTI_TIPO = 10").fetchone()[0]
        for nro, f in enumerate(lineas, start=1):
            codigo_a2 = _sql_texto(f["codigo_a2"] if f.get("codigo_a2") else f["codigo"])
            precio = f["precio"] or 0
            cantidad = f["cantidad"]
            cur.execute(
                "INSERT INTO SDetalleVenta (FDI_TIPOOPERACION, FDI_CODIGO, "
                "FDI_DOCUMENTO, FDI_LINEA, FDI_CANTIDAD, FDI_CANTIDADPENDIENTE, "
                "FDI_UNDDESCARGA, FDI_DECIMALES, FDI_DECIMALESPEN, "
                "FDI_LOTERANDOM, FDI_CLASIFICACION, FDI_PRECIOSINDESCUENTO, "
                "FDI_PRECIOCONDESCUENTO, FDI_PRECIODEVENTA, FDI_PORCENTIMPUESTO1, "
                "FDI_DEPOSITOSOURCE, FDI_USADEPOSITOS, FDI_STATUS, FDI_VISIBLE, "
                "FDI_FECHAOPERACION, FDI_MONEDA, FDI_OPERACION_AUTOINCREMENT) "
                f"VALUES (10, '{codigo_a2}', '{_sql_texto(numero)}', {nro}, "
                f"{cantidad}, {cantidad}, 1.0, False, False, "
                f"0, 0, {precio}, {precio}, {precio}, True, "
                f"{DEPOSITO}, True, 4, True, '{hoy.isoformat()}', 1, {autoinc})")
        con.commit()
        ESTADO["montados"] += 1
        api(f"/api/pedidos/montado?id={pedido['id']}&a2_autoincrement={autoinc}",
            "ok", "POST")
        log("montado en A2:", numero, "(FTI autoinc", autoinc, ")")
    except Exception as e:
        try:
            con.rollback()
        except Exception:
            pass
        api(f"/api/pedidos/error?id={pedido['id']}&mensaje=" +
            urllib.parse.quote(str(e)[:400]), "ok", "POST")
        log("ERROR montando", numero, "->", str(e)[:200])
    finally:
        con.close()


# ---------- ciclo ----------

def ciclo(primera: bool = False) -> None:
    global ULTIMA_SYNC_CATALOGO
    # 1) subir pedidos pendientes → insertar en A2
    try:
        pendientes = api("/api/pedidos/pendientes").get("pedidos", [])
        ESTADO["panel"] = "conectado"
        for pedido in pendientes:
            log("montando", pedido["numero"], f"({len(pedido['lineas'])} líneas)...")
            try:
                montar(pedido)
            except Exception as e:
                ESTADO["errores"] += 1
                log("ERROR con", pedido["numero"], "->", str(e)[:200])
    except urllib.error.HTTPError as e:
        ESTADO["panel"] = "sin conexión"
        log("no pude leer pedidos pendientes:", e.code)
    except urllib.error.URLError:
        ESTADO["panel"] = "sin conexión"
        log("panel no responde")
    ESTADO["ultimo_ciclo"] = dt.datetime.now().strftime("%H:%M:%S")
    # 2) catálogo + existencias cada 5 minutos
    ahora = time.time()
    if primera or ahora - ULTIMA_SYNC_CATALOGO > 300:
        try:
            sube_catalogo()
            ULTIMA_SYNC_CATALOGO = ahora
        except Exception as e:
            log("error subiendo catálogo:", str(e)[:200])
    # 3) precios incrementales
    try:
        sube_precios()
    except Exception as e:
        log("error subiendo precios:", str(e)[:200])


def main() -> None:
    global INTERVALO
    parser = argparse.ArgumentParser()
    parser.add_argument("--una-vez", action="store_true")
    parser.add_argument("--intervalo", type=int, default=INTERVALO)
    args = parser.parse_args()
    INTERVALO = args.intervalo
    for nombre, valor in (("CONECTA2_API_URL", API), ("CONECTA2_TOKEN", TOKEN),
                          ("CONECTA2_A2_DATA", A2_DATA)):
        if not valor:
            print(f"Falta la variable de entorno {nombre}")
            return
    log("agente conécta2 — API:", API, "| A2:", A2_DATA,
        "| depósito:", DEPOSITO)
    saludo = api("/api/saludo")
    if not saludo.get("ok"):
        log("token rechazado por el panel")
        return
    log("conectado al panel — empresa", saludo.get("empresa"))
    if args.una_vez:
        ciclo(primera=True)
        log("ciclo único terminado")
        return
    log(f"corriendo cada {INTERVALO}s — Ctrl+C para parar")
    while True:
        try:
            ciclo()
            time.sleep(INTERVALO)
        except KeyboardInterrupt:
            log("parado por el usuario")
            return
        except urllib.error.URLError as e:
            log("panel no responde:", str(e)[:120], "— reintentando...")
            time.sleep(10)
        except Exception as e:
            log("error del ciclo:", str(e)[:200])
            time.sleep(10)


if __name__ == "__main__":
    main()