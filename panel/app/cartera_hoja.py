"""Cartera desde una hoja de Google publicada (enlace de solo lectura).

La hoja se descarga como CSV, se guarda en la base del panel y se muestra
en Cartera. El vendedor solo ve las filas cuyo valor en la columna de
vendedor coincide con su código o su nombre de A2; admin y super ven todo.
"""
import csv
import io
import json
import re
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from app import db

TIEMPO_CACHE = 300                       # segundos antes de volver a descargar
MAX_BYTES = 12 * 1024 * 1024            # tope de la descarga
MAX_FILAS = 20000
AGENTE = "Mozilla/5.0 (compatible; Conecta2/1.0)"

# una sola descarga a la vez: si varios vendedores abren Cartera con la
# copia vencida, el primero baja la hoja y los demás usan lo que él guardó
_candado = threading.Lock()


# ---------- enlace ----------

def url_csv(url: str) -> str:
    """Convierte un enlace de Google Sheets en su descarga CSV.

    Acepta el enlace normal de edición, el de "publicar en la web" y ya
    convertido a CSV. Devuelve "" si el enlace no sirve.
    """
    url = (url or "").strip()
    if not url:
        return ""
    partes = urllib.parse.urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        return ""
    if "docs.google.com" not in partes.netloc.lower():
        return url                      # otro servidor: se intenta tal cual
    consulta = {k: v[0] for k, v in urllib.parse.parse_qs(partes.query).items()}
    # el "gid" (pestaña) puede venir en la consulta o después del #
    fragmento = {k: v[0] for k, v in urllib.parse.parse_qs(partes.fragment).items()}
    gid = consulta.get("gid") or fragmento.get("gid") or ""
    camino = partes.path
    if "/spreadsheets/d/e/" in camino:
        # enlace publicado: /pubhtml o /pub -> siempre con output=csv
        if camino.endswith("/pubhtml"):
            camino = camino[:-len("pubhtml")] + "pub"
        consulta["output"] = "csv"
        consulta.pop("single", None)
        if gid:
            consulta["gid"] = gid
        return urllib.parse.urlunsplit(("https", "docs.google.com", camino,
                                        urllib.parse.urlencode(consulta), ""))
    libro = re.search(r"/spreadsheets/(?:u/\d+/)?d/([A-Za-z0-9_-]+)", camino)
    if not libro:
        return url
    destino = {"format": "csv"}
    if gid:
        destino["gid"] = gid
    return urllib.parse.urlunsplit((
        "https", "docs.google.com", f"/spreadsheets/d/{libro.group(1)}/export",
        urllib.parse.urlencode(destino), ""))


# ---------- descarga y lectura ----------

def mensaje_error(e) -> str:
    """Explica en palabras del panel por qué no se pudo leer la hoja."""
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (401, 403):
            return ("Google no deja leer la hoja: revisa que esté publicada en "
                    "la web (Archivo → Compartir → Publicar en la web).")
        if e.code == 404:
            return "Google no encontró la hoja: revisa el enlace."
        return f"Google respondió con error {e.code}."
    if isinstance(e, urllib.error.URLError):
        return "No se pudo conectar con Google. Se reintentará en unos minutos."
    if isinstance(e, TimeoutError):
        return "Google tardó demasiado en responder. Se reintentará en unos minutos."
    return str(e) or "No se pudo leer la hoja."


def descargar(url: str, timeout: float = 12.0) -> str:
    """Baja la hoja como texto CSV."""
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
        crudo = respuesta.read(MAX_BYTES + 1)
        tipo = (respuesta.headers.get("Content-Type") or "").lower()
    if len(crudo) > MAX_BYTES:
        raise ValueError("La hoja es muy grande para cargarla en el panel.")
    texto = crudo.decode("utf-8-sig", errors="replace")
    cabeza = texto.lstrip()[:200].lower()
    if "text/html" in tipo or cabeza.startswith("<!doctype") or cabeza.startswith("<html"):
        raise ValueError("El enlace no entrega la hoja en CSV: publícala en la "
                         "web (Archivo → Compartir → Publicar en la web).")
    return texto


def parsear(texto: str) -> dict:
    """Primera fila = títulos; el resto, filas recortadas a ese ancho."""
    texto = (texto or "").lstrip("\ufeff")
    if not texto.strip():
        raise ValueError("La hoja está vacía.")
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
    except csv.Error:
        dialecto = csv.excel
    todas = list(csv.reader(io.StringIO(texto), dialecto))
    # salta filas en blanco al comienzo: los títulos son la primera con datos
    inicio = 0
    while inicio < len(todas) and not any(str(c).strip() for c in todas[inicio]):
        inicio += 1
    if inicio >= len(todas):
        raise ValueError("La hoja está vacía.")
    columnas = [str(c).strip() for c in todas[inicio]]
    while columnas and not columnas[-1]:
        columnas.pop()
    if not columnas:
        raise ValueError("La primera fila de la hoja no tiene títulos.")
    ancho = len(columnas)
    filas = []
    for fila in todas[inicio + 1:MAX_FILAS + 1]:
        valores = [str(c).strip() for c in fila]
        if not any(valores):
            continue
        filas.append((valores + [""] * ancho)[:ancho])
    return {"columnas": columnas, "filas": filas}


# ---------- caché ----------

def _guardar(empresa_id: int, datos: dict | None, error: str = "") -> None:
    db.ejecutar(
        "INSERT INTO cartera (empresa_id, datos, actualizado, error) "
        "VALUES (?, ?, datetime('now','localtime'), ?) "
        "ON CONFLICT(empresa_id) DO UPDATE SET datos = excluded.datos, "
        "actualizado = excluded.actualizado, error = excluded.error",
        (empresa_id, json.dumps(datos, ensure_ascii=False) if datos else None,
         error or None))


def cache(empresa_id: int) -> dict:
    """Lo último guardado: datos, cuándo y el último error (si hubo)."""
    fila = db.fila("SELECT datos, actualizado, error FROM cartera "
                   "WHERE empresa_id = ?", (empresa_id,))
    if fila is None:
        return {"datos": None, "actualizado": None, "error": ""}
    try:
        datos = json.loads(fila["datos"]) if fila["datos"] else None
    except (TypeError, ValueError):
        datos = None
    return {"datos": datos, "actualizado": fila["actualizado"],
            "error": fila["error"] or ""}


def _vencido(actualizado: str | None) -> bool:
    if not actualizado:
        return True
    try:
        cuando = datetime.strptime(actualizado, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return (datetime.now() - cuando).total_seconds() >= TIEMPO_CACHE


def obtener(empresa, forzar: bool = False) -> dict:
    """Hoja guardada; se vuelve a descargar si venció (5 min) o si se fuerza.

    Si Google falla se conserva lo último bueno y se devuelve el aviso.
    """
    url = url_csv(empresa["cartera_url"] or "")
    if not url:
        return {"datos": None, "actualizado": None, "error": ""}
    previo = cache(empresa["id"])
    if previo["datos"] and not forzar and not _vencido(previo["actualizado"]):
        return previo
    with _candado:
        # otro pudo actualizarla mientras se esperaba el turno
        previo = cache(empresa["id"])
        if previo["datos"] and not forzar and not _vencido(previo["actualizado"]):
            return previo
        try:
            _guardar(empresa["id"], parsear(descargar(url)))
        except Exception as e:                              # noqa: BLE001
            _guardar(empresa["id"], previo["datos"], mensaje_error(e))
        return cache(empresa["id"])


def borrar_cache(empresa_id: int) -> None:
    db.ejecutar("DELETE FROM cartera WHERE empresa_id = ?", (empresa_id,))


# ---------- columnas ----------

def sin_tildes(texto: str) -> str:
    """Mayúsculas, sin tildes y con espacios simples (para comparar)."""
    plano = unicodedata.normalize("NFKD", str(texto or ""))
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plano).strip().upper()


def columnas_guardadas(empresa) -> list[str]:
    try:
        elegidas = json.loads(empresa["cartera_columnas"] or "[]")
    except (TypeError, ValueError):
        elegidas = []
    return [str(c) for c in elegidas] if isinstance(elegidas, list) else []


def indices_visibles(empresa, columnas: list[str]) -> list[int]:
    """Posiciones de las columnas elegidas en Configuración.

    Sin selección guardada se muestran todas.
    """
    elegidas = columnas_guardadas(empresa)
    if not elegidas:
        return list(range(len(columnas)))
    indices = []
    for nombre in elegidas:
        for i, titulo in enumerate(columnas):
            if titulo == nombre:
                indices.append(i)
                break
    return indices or list(range(len(columnas)))


def indice_vendedor(empresa, columnas: list[str]) -> int:
    """Posición de la columna del vendedor (la de Configuración o "Vendedor")."""
    objetivo = sin_tildes(empresa["cartera_columna_vendedor"] or "")
    if objetivo:
        for i, titulo in enumerate(columnas):
            if sin_tildes(titulo) == objetivo:
                return i
    for i, titulo in enumerate(columnas):
        if "VENDEDOR" in sin_tildes(titulo):
            return i
    return -1


def nombre_vendedor(columnas: list[str]) -> str:
    for titulo in columnas:
        if "VENDEDOR" in sin_tildes(titulo):
            return titulo
    return ""


# ---------- filtro por vendedor ----------

def _claves_usuario(usuario) -> set[str]:
    """Cómo puede venir escrito el vendedor en la hoja: código y nombre."""
    claves = set()
    for valor in (usuario["codigo"], usuario["nombre"]):
        clave = sin_tildes(valor)
        if clave:
            claves.add(clave)
    fila = db.fila("SELECT nombre FROM vendedores_a2 WHERE empresa_id = ? "
                   "AND codigo = ?", (usuario["empresa_id"], usuario["codigo"]))
    if fila is not None and fila["nombre"]:
        claves.add(sin_tildes(fila["nombre"]))
    return claves


def coincide(celda: str, claves: set[str]) -> bool:
    """¿La celda del vendedor es la de este usuario? ("17", "17 - JUAN")."""
    valor = sin_tildes(celda)
    if not valor:
        return False
    if valor in claves:
        return True
    for clave in claves:
        # "1" y "01" son el mismo vendedor
        if valor.isdigit() and clave.isdigit() and int(valor) == int(clave):
            return True
        if len(clave) >= 2 and valor.startswith(clave + " "):
            return True
        if len(clave) >= 6 and clave in valor:
            return True
    return False


def filas_para(usuario, empresa, datos: dict) -> list[list[str]]:
    """Filas que puede ver el usuario según su rol y la columna de vendedor."""
    if not datos:
        return []
    filas = datos.get("filas") or []
    if usuario["rol"] in ("super", "admin"):
        return filas
    posicion = indice_vendedor(empresa, datos.get("columnas") or [])
    if posicion < 0:
        return []                       # sin columna no se muestra nada al vendedor
    claves = _claves_usuario(usuario)
    return [f for f in filas
            if len(f) > posicion and coincide(f[posicion], claves)]
