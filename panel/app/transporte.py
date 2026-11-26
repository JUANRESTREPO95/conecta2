"""Transportadoras: hoja BD de despacho (lectura) y escritura del flete.

La hoja se arma desde la hoja de Cartera (factura, fecha, cliente, dirección,
ciudad, teléfono, vendedor). El panel escribe cajas, flete, transportadora y
guía en la fila de esa factura usando un Apps Script con el token del agente.
"""
import csv
import io
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime

from app import cartera_hoja, db, seguridad

TIEMPO_CACHE = 600
MAX_FILAS = 30000
CAMPOS = ("factura", "fecha", "cliente", "direccion", "ciudad",
          "telefono", "vendedor", "cajas", "flete", "transportadora",
          "guia", "fecha_confirmacion")
ESCRIBE = ("cajas", "flete", "transportadora", "guia")
_candado = threading.Lock()


# ---------- lectura de la hoja ----------

def parsear(texto: str, inicio: int = 2) -> dict:
    """Fila 1 = títulos; los datos empiezan en la fila indicada (1-based)."""
    texto = (texto or "").lstrip("\ufeff")
    if not texto.strip():
        raise ValueError("La hoja BD está vacía.")
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
    except csv.Error:
        dialecto = csv.excel
    todas = list(csv.reader(io.StringIO(texto), dialecto))
    if not todas:
        raise ValueError("La hoja BD está vacía.")
    headers = [str(c).strip() for c in todas[0]]
    inicio = max(2, int(inicio or 2))
    filas = []
    for fila in todas[inicio - 1:inicio - 1 + MAX_FILAS]:
        valores = [str(c).strip() for c in fila]
        if not any(valores):
            continue
        filas.append(valores)
    return {"headers": headers, "filas": filas}


def _guardar(empresa_id: int, datos: dict | None, error: str = "") -> None:
    db.ejecutar(
        "INSERT INTO cartera_bd (empresa_id, datos, actualizado, error) "
        "VALUES (?, ?, datetime('now','localtime'), ?) "
        "ON CONFLICT(empresa_id) DO UPDATE SET datos = excluded.datos, "
        "actualizado = excluded.actualizado, error = excluded.error",
        (empresa_id, json.dumps(datos, ensure_ascii=False) if datos else None,
         error or None))


def cache(empresa_id: int) -> dict:
    fila = db.fila("SELECT datos, actualizado, error FROM cartera_bd "
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


def leer(empresa, forzar: bool = False) -> dict:
    url = cartera_hoja.url_csv(empresa["bd_url"] or "")
    if not url:
        return {"datos": None, "actualizado": None, "error": ""}
    previo = cache(empresa["id"])
    if previo["datos"] and not forzar and not _vencido(previo["actualizado"]):
        return previo
    with _candado:
        previo = cache(empresa["id"])
        if previo["datos"] and not forzar and not _vencido(previo["actualizado"]):
            return previo
        try:
            _guardar(empresa["id"], parsear(cartera_hoja.descargar(url),
                                            empresa["bd_fila_inicio"] or 2))
        except Exception as e:                              # noqa: BLE001
            _guardar(empresa["id"], previo["datos"],
                     cartera_hoja.mensaje_error(e))
        return cache(empresa["id"])


def borrar_cache(empresa_id: int) -> None:
    db.ejecutar("DELETE FROM cartera_bd WHERE empresa_id = ?", (empresa_id,))


def marcar_confirmada(empresa, datos: dict | None, indices: dict, factura: str,
                      fecha_bd: str) -> None:
    """Refleja la fecha en la caché local sin esperar a que Google la exporte.

    Así la fila sale de Registrado de una vez; el refresco de fondo trae la
    hoja real más adelante.
    """
    columna = indices.get("fecha_confirmacion", -1)
    if not datos or columna < 0:
        return
    buscada = str(factura or "").strip()
    for fila in datos.get("filas") or []:
        if str(valores_de(fila, indices).get("factura") or "").strip() != buscada:
            continue
        if columna >= len(fila):
            fila.extend([""] * (columna + 1 - len(fila)))
        fila[columna] = fecha_bd
        _guardar(empresa["id"], datos)
        return


def refrescar_todas() -> None:
    filas = db.filas("SELECT * FROM empresas "
                     "WHERE TRIM(COALESCE(bd_url, '')) <> ''")
    for empresa in filas:
        try:
            leer(empresa, forzar=True)
        except Exception:                                   # noqa: BLE001
            pass


# ---------- columnas y mapeo ----------

def letra_columna(indice: int) -> str:
    """0 -> A, 7 -> H, 26 -> AA."""
    numero = indice + 1
    salida = ""
    while numero:
        numero, resto = divmod(numero - 1, 26)
        salida = chr(65 + resto) + salida
    return salida


def _normal(texto) -> str:
    return cartera_hoja.sin_tildes(texto)


def auto_campo(campo: str, headers: list[str]) -> str:
    """Sugiere el título de la hoja que corresponde a cada campo."""
    titulos = [(h, _normal(h)) for h in headers]

    def primero(*claves, excluir=()):
        for clave in claves:
            for original, norm in titulos:
                if clave in norm and not any(x in norm for x in excluir):
                    return original
        return ""

    if campo == "factura":
        return primero("FACTURA", "DOCUMENTO", "NUMERO")
    if campo == "fecha":
        return primero("FECHA")
    if campo == "cliente":
        return primero("CLIENTE", "NOMBRE")
    if campo == "direccion":
        return primero("DIRECCION")
    if campo == "ciudad":
        return primero("CIUDAD")
    if campo == "telefono":
        return primero("TELEFONO", "CELULAR")
    if campo == "vendedor":
        return primero("VENDEDOR")
    if campo == "cajas":
        return primero("CAJAS")
    if campo == "flete":
        return primero("FLETE", "PRECIO",
                       excluir=("VENTA", "PRODUCTO", "TOTAL"))
    if campo == "transportadora":
        return primero("TRANSPORTADORA", "TRANSPORTE")
    if campo == "guia":
        return primero("GUIA")
    if campo == "fecha_confirmacion":
        return primero("FECHA CONFIRMACION", "FECHA DE CONFIRMACION",
                       "FECHA ENTREGA", "FECHA DE ENTREGA",
                       "FECHA RECIBIDO", "CONFIRMADO")
    return ""


def sugerencias(headers: list[str]) -> dict:
    return {campo: auto_campo(campo, headers) for campo in CAMPOS}


def mapa_indices(empresa, headers: list[str]) -> dict:
    """Campo -> posición en la fila (según lo guardado o lo detectado)."""
    try:
        guardado = json.loads(empresa["bd_columnas"] or "{}")
    except (TypeError, ValueError):
        guardado = {}
    if not isinstance(guardado, dict):
        guardado = {}
    indices: dict[str, int] = {}
    for campo in CAMPOS:
        elegido = str(guardado.get(campo) or "").strip()
        indice = -1
        if elegido:
            for i, titulo in enumerate(headers):
                if titulo == elegido:
                    indice = i
                    break
            if indice < 0:
                for i, titulo in enumerate(headers):
                    if _normal(titulo) == _normal(elegido):
                        indice = i
                        break
        if indice < 0:
            sugerido = auto_campo(campo, headers)
            if sugerido:
                indice = headers.index(sugerido)
        indices[campo] = indice
    return indices


def valores_de(fila: list[str], indices: dict) -> dict:
    valores = {}
    for campo, indice in indices.items():
        valores[campo] = fila[indice] if 0 <= indice < len(fila) else ""
    return valores


def completa(valores: dict, indices: dict) -> bool:
    for campo in ESCRIBE:
        if indices.get(campo, -1) < 0:
            return False
        if not str(valores.get(campo) or "").strip():
            return False
    return True


def distintos(datos: dict, indices: dict, campo: str, tope: int = 100) -> list[str]:
    vistos = set()
    indice = indices.get(campo, -1)
    if indice < 0 or not datos:
        return []
    for fila in datos.get("filas") or []:
        if indice < len(fila):
            valor = (fila[indice] or "").strip()
            if valor:
                vistos.add(valor)
    return sorted(vistos, key=_normal)[:tope]


# ---------- fechas, filtros y vendedor ----------

def fecha_de(valor) -> datetime | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def fecha_ddmmaaaa(texto) -> str:
    """dd/mm/aaaa para la hoja (acepta el valor de un input date)."""
    fecha = fecha_de(texto)
    return fecha.strftime("%d/%m/%Y") if fecha else ""


def _claves_usuario(usuario) -> set[str]:
    claves = set()
    for valor in (usuario["codigo"], usuario["nombre"]):
        clave = _normal(valor)
        if clave:
            claves.add(clave)
    fila = db.fila("SELECT nombre FROM vendedores_a2 WHERE empresa_id = ? "
                   "AND codigo = ?", (usuario["empresa_id"], usuario["codigo"]))
    if fila is not None and fila["nombre"]:
        claves.add(_normal(fila["nombre"]))
    return claves


def _coincide(celda: str, claves: set[str]) -> bool:
    valor = _normal(celda)
    if not valor:
        return False
    if valor in claves:
        return True
    for clave in claves:
        if valor.isdigit() and clave.isdigit() and int(valor) == int(clave):
            return True
        if len(clave) >= 2 and valor.startswith(clave + " "):
            return True
        if len(clave) >= 6 and clave in valor:
            return True
    return False


def filas_lista(usuario, datos: dict | None, indices: dict, estado: str,
                filtros: dict) -> list[dict]:
    """Filas para la pestaña, ya filtradas, completas y ordenadas.

    El vendedor solo ve sus filas registradas (completas).
    """
    if not datos:
        return []
    vendedor = usuario["rol"] == "vendedor"
    claves = _claves_usuario(usuario) if vendedor else set()
    q = _normal(filtros.get("q") or "")
    vendedor_filtro = _normal(filtros.get("vendedor") or "")
    desde = fecha_de(filtros.get("desde"))
    hasta = fecha_de(filtros.get("hasta"))
    fecha_idx = indices.get("fecha_confirmacion", -1)
    salida = []
    for fila in datos.get("filas") or []:
        valores = valores_de(fila, indices)
        factura = str(valores.get("factura") or "").strip()
        if not factura:
            continue
        llena = completa(valores, indices)
        confirmada = (fecha_idx >= 0 and
                      str(valores.get("fecha_confirmacion") or "").strip() != "")
        if vendedor:
            # el vendedor solo ve sus registradas (sin confirmar)
            if not llena or confirmada:
                continue
            if not _coincide(valores.get("vendedor") or "", claves):
                continue
        else:
            if estado == "confirmada":
                if not confirmada:
                    continue
            elif estado == "registrado":
                if not llena or confirmada:
                    continue
            else:  # pendiente
                if llena or confirmada:
                    continue
            if vendedor_filtro and _normal(
                    valores.get("vendedor") or "") != vendedor_filtro:
                continue
        if q and q not in _normal(factura) and q not in _normal(
                valores.get("cliente") or ""):
            continue
        fecha = fecha_de(valores.get("fecha"))
        if desde is not None and fecha is not None and fecha < desde:
            continue
        if hasta is not None and fecha is not None and fecha > hasta:
            continue
        salida.append({**valores, "factura": factura, "completa": llena,
                       "confirmada": confirmada,
                       "fecha_orden": fecha or datetime.min})
    salida.sort(key=lambda f: (f["fecha_orden"], f["factura"]), reverse=True)
    return salida


def es_de_vendedor(usuario, fila: dict) -> bool:
    """¿La fila pertenece al vendedor que la está mirando?"""
    return _coincide(fila.get("vendedor") or "", _claves_usuario(usuario))


def buscar_fila(datos: dict | None, indices: dict, factura: str) -> dict | None:
    if not datos:
        return None
    buscada = str(factura or "").strip()
    for fila in datos.get("filas") or []:
        valores = valores_de(fila, indices)
        if str(valores.get("factura") or "").strip() == buscada:
            return valores
    return None


# ---------- escritura en la hoja ----------

def token_agente(empresa_id: int) -> str:
    fila = db.fila("SELECT clave_visible FROM usuarios WHERE empresa_id = ? "
                   "AND rol = 'agente' LIMIT 1", (empresa_id,))
    if fila is None or not fila["clave_visible"]:
        return ""
    return seguridad.descifrar_clave(fila["clave_visible"])


def escribir(empresa, factura: str, valores: dict, indices: dict,
             campos=None):
    """Escribe los campos indicados en la fila de esa factura en BD.

    Por defecto guarda cajas/flete/transportadora/guía. Para confirmar una
    entrega se llama con campos=("fecha_confirmacion",).
    Devuelve (ok, mensaje). No toca la hoja de cartera.
    """
    campos = tuple(campos or ESCRIBE)
    url = (empresa["bd_script_url"] or "").strip()
    token = token_agente(empresa["id"])
    if not url:
        return False, "Falta la URL del script de la hoja BD."
    if not token:
        return False, ("Falta el token del agente. Renuévalo en Empresas "
                       "para poder escribir en la hoja BD.")
    letras = {}
    for campo in campos + ("factura",):
        indice = indices.get(campo, -1)
        if indice < 0:
            return False, f"Falta configurar la columna de {campo}."
        letras[campo] = letra_columna(indice)
    enviar = {}
    for campo in campos:
        valor = valores.get(campo)
        if valor is None:
            continue
        if campo == "cajas":
            enviar[campo] = int(valor)
        elif campo == "flete":
            enviar[campo] = float(valor)
        else:
            enviar[campo] = str(valor).strip()
    carga = {
        "token": token,
        "hoja": (empresa["bd_hoja"] or "BD"),
        "inicio": max(2, int(empresa["bd_fila_inicio"] or 2)),
        "factura": str(factura).strip(),
        "columnas": letras,
        "valores": enviar,
    }
    pedido = urllib.request.Request(
        url, data=json.dumps(carga).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "Conecta2/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=25) as respuesta:
            cuerpo = respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"El script respondió con error {e.code}."
    except urllib.error.URLError:
        return False, "No se pudo conectar con el script de la hoja BD."
    except Exception as e:                                  # noqa: BLE001
        return False, f"No se pudo escribir en la hoja BD: {e}"
    try:
        datos = json.loads(cuerpo)
    except ValueError:
        return False, "El script no devolvió una respuesta válida."
    if not datos.get("ok"):
        return False, str(datos.get("mensaje") or "No se pudo guardar.")
    return True, ""
