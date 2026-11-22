"""Conecta2 — panel web (FastAPI + Jinja2 + SQLite).

Multi-empresa. Roles: super (global), admin (por empresa), vendedor.
El super usuario se crea en el primer arranque, en /primer-vez.
"""
from datetime import datetime

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import a2, config, db, hoja, seguridad

db.esquema()  # garantiza el esquema también cuando uvicorn recarga en modo dev

app = FastAPI(title="Conecta2", docs_url=None, redoc_url=None)
# el catálogo de la app son varios MB: se comprime la respuesta
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def sin_cache(request: Request, call_next):
    """El HTML lleva los colores de la empresa: nunca cachear páginas."""
    respuesta = await call_next(request)
    if (respuesta.headers.get("content-type", "") or "").startswith("text/html"):
        respuesta.headers["Cache-Control"] = "no-store, max-age=0"
    return respuesta


app.mount("/estaticos", StaticFiles(directory=str(config.ESTATICOS)), name="estaticos")
app.mount("/logos", StaticFiles(directory=str(config.LOGOS)), name="logos")
plantillas = Jinja2Templates(directory=str(config.PLANTILLAS))


def num(v) -> str:
    """Número sin decimales y con separador de miles (1.234.567)."""
    if v is None or v == "":
        return "—"
    return f"{int(round(float(v))):,}".replace(",", ".")


plantillas.env.filters["num"] = num

COOKIE_SESION = "conecta2_sesion"


def usuario_actual(request: Request):
    return seguridad.usuario_de_sesion(request.cookies.get(COOKIE_SESION))


def seccion_de_ruta(request: Request):
    """Devuelve la sección si la página pertenece a una; si no, None."""
    ruta = request.url.path
    if ruta == "/cartera" or ruta.startswith("/cartera/"):
        return "cartera"
    if (ruta in ("/catalogo", "/pedido", "/pedidos")
            or ruta.startswith("/pedidos/")):
        return "pedidos"
    return None


def fija_seccion(usuario, seccion: str) -> None:
    """Recuerda en la sesión desde qué sección se está trabajando."""
    if usuario is None or "seccion_actual" not in usuario.keys():
        return
    if (usuario["seccion_actual"] or "pedidos") != seccion:
        db.ejecutar("UPDATE sesiones SET seccion = ? WHERE token = ?",
                    (seccion, usuario["token"]))


def seccion_actual(request: Request, usuario=None) -> str:
    """La de la ruta o, en páginas comunes, la que quedó en la sesión."""
    fija = seccion_de_ruta(request)
    if fija:
        return fija
    if usuario is not None and "seccion_actual" in usuario.keys():
        return usuario["seccion_actual"] or "pedidos"
    return "pedidos"


def colores_para(usuario, seccion: str = "pedidos") -> dict:
    defecto = {"color_primario": "#1e40af", "color_secundario": "#0f172a",
               "color_letra": "#ffffff", "nombre_negocio": "Conecta2", "logo": None,
               "seccion": seccion}
    empresa = None
    if usuario is not None:
        # el super sigue la empresa que está viendo; los demás, la suya
        empresa_id = (usuario["empresa_actual"] if usuario["rol"] == "super"
                      else usuario["empresa_id"])
        if empresa_id:
            empresa = db.fila("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
    if empresa is None:
        # sin empresa resuelta (login, super recién entrado, etc.):
        # se usa el color del negocio configurado — nunca un azul genérico
        empresa = db.fila("SELECT * FROM empresas WHERE activa = 1 ORDER BY id LIMIT 1")
    if empresa is None:
        return defecto
    # Cartera tiene su propio color para distinguirla de Pedidos
    if seccion == "cartera":
        color = (empresa["color_cartera"] or empresa["color_primario"]
                 or "#0f766e")
    else:
        color = empresa["color_primario"] or "#1e40af"
    return {"color_primario": color,
            "color_secundario": empresa["color_secundario"],
            "color_letra": empresa["color_letra"] or "#ffffff",
            "nombre_negocio": empresa["nombre"], "logo": empresa["logo"],
            "seccion": seccion}


def fija_empresa_activa(usuario, empresa_id: int) -> None:
    """El super navega empresas: su sesión recuerda cuál es la actual."""
    if usuario["rol"] == "super" and empresa_id:
        db.ejecutar("UPDATE sesiones SET empresa_activa = ? WHERE token = ?",
                    (empresa_id, usuario["token"]))


def resumen_carrito(carrito: list) -> dict:
    """Unidades, monto e ítems de un carrito (para el indicador flotante)."""
    monto = sum(i["cantidad"] * (i["precio"] or 0) for i in carrito)
    return {"carrito_n": sum(int(i["cantidad"]) for i in carrito),
            "carrito_monto": monto, "carrito_items": len(carrito)}


def datos_carrito(usuario) -> dict:
    """Artículos y monto del carrito del usuario (para el indicador flotante)."""
    if usuario is None or not usuario["carrito"]:
        return {"carrito_n": 0, "carrito_monto": 0.0, "carrito_items": 0}
    try:
        carrito = json.loads(usuario["carrito"] or "[]")
    except Exception:
        carrito = []
    return resumen_carrito(carrito)


def respuesta(request: Request, plantilla: str, contexto: dict):
    usuario = usuario_actual(request)
    seccion = seccion_actual(request, usuario)
    # al entrar a una página de sección se recuerda en la sesión: así
    # Vendedores, Apps y Configuración conservan el color de donde se abren
    if usuario is not None and seccion_de_ruta(request):
        fija_seccion(usuario, seccion)
    ctx = {"usuario": usuario, **colores_para(usuario, seccion),
           **datos_carrito(usuario), **contexto}
    return plantillas.TemplateResponse(request, plantilla, ctx)


def protege(request: Request):
    """Devuelve el usuario o lanza una redirección al login."""
    usuario = usuario_actual(request)
    if usuario is None:
        raise Redirige
    return usuario


class Redirige(Exception):
    pass


@app.exception_handler(Redirige)
async def redirige_al_login(request: Request, exc: Redirige):
    """Sin sesión (o sin permiso para la ruta) siempre se va al login."""
    return RedirectResponse("/login", status_code=303)


@app.get("/")
def raiz(request: Request):
    usuario = usuario_actual(request)
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/inicio", status_code=303)


# ---------- primera vez: crea el super usuario ----------

def hay_super() -> bool:
    return db.fila("SELECT id FROM usuarios WHERE rol = 'super' LIMIT 1") is not None


@app.get("/primer-vez")
def primer_vez_get(request: Request):
    if hay_super():
        return RedirectResponse("/login", status_code=303)
    return respuesta(request, "primer_vez.html", {})


@app.post("/primer-vez")
def primer_vez_post(request: Request, codigo: str = Form(...), nombre: str = Form(...),
                    clave: str = Form(...), clave2: str = Form(...)):
    if hay_super() or clave != clave2 or len(clave) < 6 or not codigo.strip():
        return RedirectResponse("/primer-vez?error=1", status_code=303)
    db.esquema()
    db.ejecutar("INSERT INTO usuarios (empresa_id, codigo, clave_hash, nombre, rol, "
                "clave_visible) VALUES (NULL, ?, ?, ?, 'super', ?)",
                (codigo.strip(), seguridad.hash_clave(clave), nombre.strip() or "Super",
                 seguridad.cifrar_clave(clave)))
    return RedirectResponse("/login?creado=1", status_code=303)


# ---------- login ----------

def _icono_png(tamano: int = 180, fondo: bool = True) -> bytes:
    """Ícono del sitio: logo de la empresa o monograma.

    Con `fondo=True` lleva el color de la empresa (para el ícono del iPhone,
    que no admite transparencia). Con `fondo=False` va transparente, así en la
    pestaña se ve solo el logo y no un cuadro de color.
    """
    import io as _io
    from PIL import Image, ImageDraw, ImageFont

    empresa = db.fila("SELECT * FROM empresas WHERE activa = 1 ORDER BY id LIMIT 1")
    color = (empresa["color_primario"] if empresa else "#1e40af") or "#1e40af"
    color = color.lstrip("#")
    rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    logo_bytes = None
    if empresa:
        try:
            from app.hoja import _logo_bytes as _Logo
            logo_bytes = _Logo(dict(empresa), alto_px=int(tamano))
        except Exception:
            logo_bytes = None
    # sin logo el monograma necesita el color de fondo para verse
    if not fondo and logo_bytes is None:
        fondo = True
    img = Image.new("RGBA", (tamano, tamano),
                    (rgb + (255,)) if fondo else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if logo_bytes:
        lg = Image.open(_io.BytesIO(logo_bytes)).convert("RGBA")
        # recorta el aire transparente para que el logo quede centrado
        caja = lg.getbbox()
        if caja:
            lg = lg.crop(caja)
        # en la pestaña el logo va a todo el cuadro (sin margen)
        limite = max(1, int(tamano * (0.88 if fondo else 1.0)))
        if lg.width > limite or lg.height > limite:
            factor = min(limite / lg.width, limite / lg.height)
            lg = lg.resize((max(1, int(lg.width * factor)),
                            max(1, int(lg.height * factor))))
        x = (tamano - lg.width) // 2
        y = (tamano - lg.height) // 2
        img.paste(lg, (x, y), lg)
    else:
        nombre = (empresa["nombre"] if empresa else "C2") or "C2"
        texto = "".join(p[0] for p in nombre.split()[:2]).upper() or "C2"
        try:
            fuente = ImageFont.truetype("arialbd.ttf", int(tamano * 0.42))
        except OSError:
            fuente = ImageFont.load_default()
        caja = d.textbbox((0, 0), texto, font=fuente)
        d.text(((tamano - (caja[2] - caja[0])) / 2 - caja[0],
                (tamano - (caja[3] - caja[1])) / 2 - caja[1]),
               texto, font=fuente, fill="white")
    buf = _io.BytesIO()
    (img.convert("RGB") if fondo else img).save(buf, "PNG")
    return buf.getvalue()


@app.get("/favicon.png")
def favicon():
    """Icono de la pestaña: el logo solo, sin el cuadro de color."""
    return Response(_icono_png(64, fondo=False), media_type="image/png",
                    headers={"Cache-Control": "max-age=3600"})


@app.get("/apple-touch-icon.png")
def apple_touch_icon():
    return Response(_icono_png(180), media_type="image/png",
                    headers={"Cache-Control": "max-age=3600"})


@app.get("/manifest.webmanifest")
def manifiesto(request: Request):
    empresa = db.fila("SELECT nombre, color_primario FROM empresas "
                      "WHERE activa = 1 ORDER BY id LIMIT 1")
    return {
        "name": (empresa["nombre"] if empresa else "Conecta2"),
        "short_name": ((empresa["nombre"] if empresa else "Conecta2")[:12]),
        "start_url": "/catalogo",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": (empresa["color_primario"] if empresa else "#1e40af"),
        "icons": [
            {"src": "/apple-touch-icon.png", "sizes": "180x180",
             "type": "image/png", "purpose": "any"},
        ],
    }


@app.get("/login")
def login_get(request: Request):
    if not hay_super():
        return RedirectResponse("/primer-vez", status_code=303)
    return respuesta(request, "login.html", {})


# ---------- API para el agente ----------

import hashlib


def usuario_agente(request: Request):
    """Valida el token Bearer del agente (guardado como sha256)."""
    cab = request.headers.get("authorization") or ""
    if not cab.lower().startswith("bearer "):
        return None
    token = cab[7:].strip()
    huella = "tok$" + hashlib.sha256(token.encode()).hexdigest()
    return db.fila("SELECT * FROM usuarios WHERE rol = 'agente' AND "
                   "clave_hash = ? AND activo = 1", (huella,))


@app.get("/api/saludo")
def api_saludo(request: Request):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    return {"ok": True, "empresa": usuario["empresa_id"]}


# ---------- API para la app Android ----------

def usuario_app(request: Request):
    """Valida el token de una app habilitada (sha256 en app_tokens)."""
    cab = request.headers.get("authorization") or ""
    if not cab.lower().startswith("bearer "):
        return None
    token = cab[7:].strip()
    huella = "app$" + hashlib.sha256(token.encode()).hexdigest()
    fila = db.fila("SELECT * FROM app_tokens WHERE token_hash = ? AND activo = 1",
                   (huella,))
    if fila is not None:
        db.ejecutar("UPDATE app_tokens SET ultimo_uso = datetime('now','localtime') "
                    "WHERE id = ?", (fila["id"],))
    return fila


def _empresa_app(token_app):
    if token_app is None:
        return None
    return db.fila("SELECT * FROM empresas WHERE id = ?", (token_app["empresa_id"],))


def _json_error(texto: str, codigo: int = 400) -> Response:
    import json as _json
    return Response(_json.dumps({"error": texto}), status_code=codigo,
                    media_type="application/json")


def sesion_app(request: Request, empresa_id: int):
    """Sesión del vendedor que la app manda en el encabezado X-Sesion."""
    token = (request.headers.get("x-sesion") or "").strip()
    if not token:
        return None
    usuario = seguridad.usuario_de_sesion(token)
    if usuario is None or usuario["empresa_id"] != empresa_id:
        return None
    if usuario["rol"] not in ("vendedor", "admin", "super"):
        return None
    return usuario


@app.get("/api/app/saludo")
def app_saludo(request: Request):
    tok = usuario_app(request)
    if tok is None:
        return _json_error("token inválido", 401)
    empresa = _empresa_app(tok)
    if empresa is None or not empresa["activa"]:
        return _json_error("empresa inactiva", 403)
    return {"ok": True,
            "empresa": {"id": empresa["id"], "nombre": empresa["nombre"]},
            "servidor": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@app.post("/api/app/login")
async def app_login(request: Request):
    tok = usuario_app(request)
    if tok is None:
        return _json_error("token inválido", 401)
    empresa = _empresa_app(tok)
    if empresa is None or not empresa["activa"]:
        return _json_error("empresa inactiva", 403)
    try:
        datos = await request.json()
    except Exception:
        datos = {}
    codigo = str((datos or {}).get("codigo") or "").strip().upper()
    clave = str((datos or {}).get("clave") or "")
    if not codigo or not clave:
        return _json_error("faltan código o clave")
    seg = db.fila(
        "SELECT id, clave_hash, rol, activo, nombre FROM usuarios "
        "WHERE empresa_id = ? AND codigo = ? "
        "AND rol IN ('vendedor', 'admin') LIMIT 1",
        (empresa["id"], codigo))
    if seg is None or not seg["activo"] or \
            not seguridad.verificar_clave(clave, seg["clave_hash"]):
        return _json_error("código o clave incorrectos", 401)
    # sesión larga: la app la guarda para no pedir la clave cada vez
    sesion = seguridad.crear_sesion(seg["id"], horas=24 * 30)
    db.ejecutar("UPDATE sesiones SET empresa_activa = ? WHERE token = ?",
                (empresa["id"], sesion))
    return {"ok": True, "sesion": sesion,
            "usuario": {"id": seg["id"], "codigo": codigo,
                        "nombre": seg["nombre"], "rol": seg["rol"]},
            "empresa": {"id": empresa["id"], "nombre": empresa["nombre"]}}


@app.get("/api/app/datos")
def app_datos(request: Request):
    """Catálogo, existencias, clientes y autorizados para la app.

    Con `desde` (fecha del último sync) solo manda lo que cambió. Las
    existencias van completas porque cambian a cada rato.
    """
    tok = usuario_app(request)
    if tok is None:
        return _json_error("token inválido", 401)
    empresa = _empresa_app(tok)
    if empresa is None or not empresa["activa"]:
        return _json_error("empresa inactiva", 403)
    desde = (request.query_params.get("desde") or "").strip()

    cond_p = "p.empresa_id = ? AND p.internet = 1 AND p.activo = 1"
    vals_p: list = [empresa["id"]]
    if desde:
        cond_p += " AND p.actualizado >= ?"
        vals_p.append(desde)
    productos = [dict(r) for r in db.filas(
        "SELECT p.codigo, p.descripcion, p.unidad, p.precio, p.actualizado "
        "FROM productos p WHERE " + cond_p + " ORDER BY p.descripcion",
        tuple(vals_p))]

    eliminados: list = []
    if desde:
        eliminados = [r["codigo"] for r in db.filas(
            "SELECT codigo FROM productos WHERE empresa_id = ? "
            "AND actualizado >= ? AND (internet = 0 OR activo = 0)",
            (empresa["id"], desde))]

    # existencia visible según el modo de depósito de la empresa
    modo = empresa["deposito_modo"] or "1"
    filas_stock = db.filas(
        "SELECT p.codigo, "
        "MAX(CASE WHEN s.deposito = 1 THEN s.existencia END) AS dep1, "
        "MAX(CASE WHEN s.deposito = 2 THEN s.existencia END) AS dep2 "
        "FROM productos p LEFT JOIN stock s ON s.empresa_id = p.empresa_id "
        "AND s.codigo_producto = p.codigo "
        "WHERE p.empresa_id = ? AND p.internet = 1 AND p.activo = 1 "
        "GROUP BY p.codigo", (empresa["id"],))
    existencias: dict = {}
    for r in filas_stock:
        if modo == "1":
            valor = r["dep1"] or 0
        elif modo == "2":
            valor = r["dep2"] or 0
        else:
            valor = (r["dep1"] or 0) + (r["dep2"] or 0)
        existencias[r["codigo"]] = float(valor)

    cond_c = "empresa_id = ?"
    vals_c: list = [empresa["id"]]
    if desde:
        cond_c += " AND actualizado >= ?"
        vals_c.append(desde)
    clientes = [dict(r) for r in db.filas(
        "SELECT codigo, nombre, nit, rif FROM clientes WHERE " + cond_c,
        tuple(vals_c))]

    cond_a = "empresa_id = ?"
    vals_a: list = [empresa["id"]]
    if desde:
        cond_a += " AND actualizado >= ?"
        vals_a.append(desde)
    autorizados = [dict(r) for r in db.filas(
        "SELECT codigo, cliente_codigo, nombre, direccion, activo "
        "FROM autorizados WHERE " + cond_a, tuple(vals_a))]

    config_empresa = {
        "id": empresa["id"], "nombre": empresa["nombre"],
        "color_primario": empresa["color_primario"],
        "color_cartera": empresa["color_cartera"],
        "color_letra": empresa["color_letra"],
        "logo": empresa["logo"],
        "usar_clientes": empresa["usar_clientes"],
        "usar_autorizados": empresa["usar_autorizados"],
        "usar_clientes_nuevos": empresa["usar_clientes_nuevos"],
        "deposito_modo": empresa["deposito_modo"],
        "filtro_existencia": empresa["filtro_existencia"],
        "existencia_minima": empresa["existencia_minima"],
        "cliente_predeterminado_codigo": empresa["cliente_predeterminado_codigo"],
        "cliente_predeterminado_nombre": empresa["cliente_predeterminado_nombre"],
        "cliente_predeterminado_nit": empresa["cliente_predeterminado_nit"],
    }
    return {
        "ok": True,
        "servidor": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "empresa": config_empresa,
        "productos": productos,
        "existencias": existencias,
        "eliminados": eliminados,
        "clientes": clientes,
        "autorizados": autorizados,
    }


@app.post("/api/app/cliente-nuevo")
async def app_cliente_nuevo(request: Request):
    """Crea un cliente desde la app (igual que en el panel web)."""
    tok = usuario_app(request)
    if tok is None:
        return _json_error("token inválido", 401)
    empresa = _empresa_app(tok)
    if empresa is None or not empresa["activa"]:
        return _json_error("empresa inactiva", 403)
    usuario = sesion_app(request, empresa["id"])
    if usuario is None:
        return _json_error("sesión inválida", 401)
    if not empresa["usar_clientes"] or not empresa["usar_clientes_nuevos"]:
        return _json_error("Crear clientes no está habilitado", 403)
    try:
        cuerpo = await request.json()
    except Exception:
        cuerpo = {}
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    return _crear_cliente(empresa["id"], usuario["codigo"],
                          cuerpo.get("nit"), cuerpo.get("nombre"),
                          cuerpo.get("direccion"), cuerpo.get("telefono"))


@app.get("/api/app/mis-pedidos")
def app_mis_pedidos(request: Request):
    tok = usuario_app(request)
    if tok is None:
        return _json_error("token inválido", 401)
    empresa = _empresa_app(tok)
    if empresa is None:
        return _json_error("empresa inactiva", 403)
    usuario = sesion_app(request, empresa["id"])
    if usuario is None:
        return _json_error("sesión vencida", 401)
    cond = "p.empresa_id = ?"
    vals: list = [empresa["id"]]
    if usuario["rol"] == "vendedor":
        cond += " AND p.vendedor_id = ?"
        vals.append(usuario["id"])
    pedidos = db.filas(
        "SELECT p.id, p.numero, p.referencia, p.estado, p.total, p.creado, "
        "p.montado, p.error_a2, p.intentos, p.uuid, p.cliente_codigo, "
        "p.cliente_nombre, p.cliente_nit, p.autorizado_codigo, "
        "p.autorizado_nombre, p.autorizado_direccion "
        "FROM pedidos p WHERE " + cond + " ORDER BY p.id DESC LIMIT 200",
        tuple(vals))
    salida = []
    for p in pedidos:
        lineas = db.filas(
            "SELECT codigo, descripcion, cantidad, precio FROM pedido_lineas "
            "WHERE pedido_id = ? ORDER BY id", (p["id"],))
        salida.append(dict(p) | {"lineas": [dict(l) for l in lineas]})
    return {"ok": True, "pedidos": salida}


@app.post("/api/app/pedido")
async def app_pedido(request: Request):
    """Crea un pedido enviado desde la app (con UUID para no duplicar)."""
    tok = usuario_app(request)
    if tok is None:
        return _json_error("token inválido", 401)
    empresa = _empresa_app(tok)
    if empresa is None or not empresa["activa"]:
        return _json_error("empresa inactiva", 403)
    usuario = sesion_app(request, empresa["id"])
    if usuario is None:
        return _json_error("sesión vencida", 401)
    try:
        datos = await request.json()
    except Exception:
        return _json_error("datos inválidos")
    datos = datos if isinstance(datos, dict) else {}
    uuid = str(datos.get("uuid") or "").strip()
    if not uuid:
        return _json_error("falta el uuid del pedido")
    previo = db.fila(
        "SELECT id, numero, estado, total, creado FROM pedidos "
        "WHERE empresa_id = ? AND uuid = ?", (empresa["id"], uuid))
    if previo is not None:
        return {"ok": True, "repetido": True, "id": previo["id"],
                "numero": previo["numero"], "estado": previo["estado"],
                "total": previo["total"], "creado": previo["creado"]}

    referencia = " ".join(
        str(datos.get("referencia") or "").replace("\t", " ").splitlines()
    ).strip()[:250]
    cliente_codigo = str(datos.get("cliente_codigo") or "").strip()
    cliente_nombre = str(datos.get("cliente_nombre") or "").strip()
    cliente_nit = str(datos.get("cliente_nit") or "").strip()
    autorizado_codigo = str(datos.get("autorizado_codigo") or "").strip()
    lineas = datos.get("lineas") or []
    if not isinstance(lineas, list) or not lineas:
        return _json_error("el pedido no tiene líneas")
    if empresa["usar_clientes"] and not cliente_codigo:
        return _json_error("falta el cliente")
    if empresa["usar_clientes"]:
        cli = db.fila("SELECT nombre, nit FROM clientes WHERE empresa_id = ? "
                      "AND codigo = ?", (empresa["id"], cliente_codigo))
        if cli is None:
            return _json_error("cliente no encontrado")
        cliente_nombre = (cli["nombre"] or cliente_nombre)
        cliente_nit = (cli["nit"] or cliente_nit)
    else:
        cliente_codigo = cliente_nombre = cliente_nit = ""

    aut_codigo = aut_nombre = aut_direccion = None
    if empresa["usar_clientes"] and empresa["usar_autorizados"] and autorizado_codigo:
        aut = db.fila(
            "SELECT nombre, direccion FROM autorizados WHERE empresa_id = ? "
            "AND cliente_codigo = ? AND codigo = ?",
            (empresa["id"], cliente_codigo, autorizado_codigo))
        if aut is not None:
            aut_codigo = autorizado_codigo
            aut_nombre = aut["nombre"]
            aut_direccion = aut["direccion"]

    items = []
    faltantes = []
    sin_stock = []
    for linea in lineas:
        if not isinstance(linea, dict):
            faltantes.append("(línea inválida)")
            continue
        codigo = str(linea.get("codigo") or "")
        try:
            cantidad = float((linea or {}).get("cantidad") or 0)
        except (TypeError, ValueError):
            cantidad = 0
        if not codigo or cantidad <= 0:
            faltantes.append(codigo or "(sin código)")
            continue
        prod = db.fila(
            "SELECT descripcion, precio FROM productos WHERE empresa_id = ? "
            "AND codigo = ? AND internet = 1 AND activo = 1",
            (empresa["id"], codigo))
        if prod is None:
            faltantes.append(codigo)
            continue
        disponible = existencia_visible(empresa, codigo)
        if cantidad > disponible:
            sin_stock.append(f"{codigo} (hay {int(disponible)})")
            continue
        items.append({"codigo": codigo, "descripcion": prod["descripcion"],
                      "cantidad": cantidad, "precio": float(prod["precio"] or 0)})
    if faltantes:
        return _json_error("productos no disponibles: " + ", ".join(faltantes[:10]))
    if sin_stock:
        return _json_error(
            "Sin existencia suficiente: " + ", ".join(sin_stock[:10]))
    total = sum(i["cantidad"] * i["precio"] for i in items)
    numero = numero_siguiente(empresa["id"], usuario, empresa)

    import sqlite3 as _sqlite3
    con = db.conectar()
    try:
        with con:
            cur = con.execute(
                "INSERT INTO pedidos (empresa_id, vendedor_id, numero, "
                "referencia, estado, total, cliente_codigo, cliente_nombre, "
                "cliente_nit, autorizado_codigo, autorizado_nombre, "
                "autorizado_direccion, uuid, origen) "
                "VALUES (?, ?, ?, ?, 'pendiente', ?, ?, ?, ?, ?, ?, ?, ?, 'app')",
                (empresa["id"], usuario["id"], numero, referencia, total,
                 cliente_codigo or None, cliente_nombre or None,
                 cliente_nit or None, aut_codigo, aut_nombre, aut_direccion,
                 uuid))
            pedido_id = cur.lastrowid
            for it in items:
                con.execute(
                    "INSERT INTO pedido_lineas (pedido_id, codigo, descripcion, "
                    "cantidad, precio) VALUES (?, ?, ?, ?, ?)",
                    (pedido_id, it["codigo"], it["descripcion"],
                     it["cantidad"], it["precio"]))
    except _sqlite3.IntegrityError:
        # dos envíos simultáneos con el mismo UUID: devolver el que ya existe
        previo = db.fila(
            "SELECT id, numero, estado, total, creado FROM pedidos "
            "WHERE empresa_id = ? AND uuid = ?", (empresa["id"], uuid))
        if previo is not None:
            return {"ok": True, "repetido": True, "id": previo["id"],
                    "numero": previo["numero"], "estado": previo["estado"],
                    "total": previo["total"], "creado": previo["creado"]}
        return _json_error("no se pudo crear el pedido", 500)
    fila = db.fila("SELECT creado FROM pedidos WHERE id = ?", (pedido_id,))
    return {"ok": True, "id": pedido_id, "numero": numero,
            "estado": "pendiente", "total": total,
            "creado": fila["creado"] if fila else ""}


_SQL_PRODUCTO = (
    "INSERT INTO productos (empresa_id, codigo, codigo_a2, codigo_busqueda, "
    "descripcion, marca, "
    "categoria, unidad, moneda, activo, internet, actualizado) "
    "VALUES (:e, :codigo, :codigo_a2, :codigo_busqueda, :descripcion, :marca, "
    ":categoria, "
    ":unidad, :moneda, :activo, :internet, datetime('now','localtime')) "
    "ON CONFLICT(empresa_id, codigo) DO UPDATE SET codigo_a2=excluded.codigo_a2, "
    "codigo_busqueda=excluded.codigo_busqueda, "
    "descripcion=excluded.descripcion, marca=excluded.marca, "
    "categoria=excluded.categoria, unidad=excluded.unidad, moneda=excluded.moneda, "
    "activo=excluded.activo, internet=excluded.internet, "
    "actualizado=excluded.actualizado "
    # solo se toca la fecha si algo cambió: así la app sincroniza por cambios
    "WHERE productos.codigo_a2 IS NOT excluded.codigo_a2 "
    "OR productos.codigo_busqueda IS NOT excluded.codigo_busqueda "
    "OR productos.descripcion IS NOT excluded.descripcion "
    "OR productos.marca IS NOT excluded.marca "
    "OR productos.categoria IS NOT excluded.categoria "
    "OR productos.unidad IS NOT excluded.unidad "
    "OR productos.moneda IS NOT excluded.moneda "
    "OR productos.activo IS NOT excluded.activo "
    "OR productos.internet IS NOT excluded.internet")


async def cuerpo_json(request: Request) -> list:
    """Devuelve la lista del cuerpo: acepta [..] o {"lote": [..]}."""
    try:
        datos = await request.json()
    except Exception:
        return []
    if isinstance(datos, dict):
        return datos.get("lote") or []
    return datos if isinstance(datos, list) else []


# Las escrituras del agente se hacen en un hilo aparte (run_in_threadpool)
# para que NO bloqueen el bucle de eventos: si no, mientras sube un lote el
# panel entero queda sin responder para todos los usuarios.
def _error_ocupado(error) -> Response:
    return Response('{"error": "panel ocupado, reintenta en un momento"}',
                    status_code=503, media_type="application/json")


def _guarda_productos(empresa_id: int, lote: list) -> int:
    con = db.conectar()
    with con:
        for p in lote:
            codigo = str(p.get("codigo") or "")     # tal cual, sin recortar
            if not codigo.strip():
                continue
            con.execute(_SQL_PRODUCTO, {
                "e": empresa_id, "codigo": codigo,
                "codigo_a2": str(p.get("codigo_a2") or p.get("codigo") or ""),
                "codigo_busqueda": codigo.strip().upper(),
                "descripcion": p.get("descripcion"), "marca": p.get("marca"),
                "categoria": p.get("categoria"), "unidad": p.get("unidad"),
                "moneda": p.get("moneda") or 1,
                "activo": 1 if p.get("activo") else 0,
                "internet": 1 if p.get("internet") else 0})
    return len(lote)


def _guarda_stock(empresa_id: int, lote: list) -> int:
    con = db.conectar()
    with con:
        for f in lote:
            con.execute(
                "INSERT INTO stock (empresa_id, codigo_producto, deposito, "
                "existencia, actualizado) VALUES (?, ?, ?, ?, datetime('now','localtime')) "
                "ON CONFLICT(empresa_id, codigo_producto, deposito) DO UPDATE SET "
                "existencia=excluded.existencia, actualizado=excluded.actualizado",
                (empresa_id, str(f["codigo"]), int(f["deposito"]),
                 float(f["existencia"] or 0)))
    return len(lote)


def _guarda_precios(empresa_id: int, lote: list, origen: str) -> int:
    """Actualiza precios por código (con índice) sin recorrer toda la tabla."""
    con = db.conectar()
    cur = con.cursor()
    with con:
        for f in lote:
            codigo = str(f["codigo"])
            precio = float(f["precio"])
            if origen == "catalogo":
                # el precio de la lista de A2 manda (solo si cambió)
                sql = ("UPDATE productos SET precio = ?, "
                       "actualizado = datetime('now','localtime') "
                       "WHERE empresa_id = ? AND codigo = ? "
                       "AND (precio IS NULL OR precio <> ?)")
                valores = (precio, empresa_id, codigo, precio)
            else:
                # la última venta solo rellena productos sin precio de lista
                sql = ("UPDATE productos SET precio = ?, "
                       "actualizado = datetime('now','localtime') "
                       "WHERE empresa_id = ? AND codigo = ? "
                       "AND (precio IS NULL OR precio <= 0)")
                valores = (precio, empresa_id, codigo)
            cur.execute(sql, valores)
            if cur.rowcount == 0:
                # el código puede estar solo en codigo_a2 (columna indexada)
                if origen == "catalogo":
                    cur.execute(
                        "UPDATE productos SET precio = ?, "
                        "actualizado = datetime('now','localtime') "
                        "WHERE empresa_id = ? AND codigo_a2 = ? "
                        "AND (precio IS NULL OR precio <> ?)",
                        (precio, empresa_id, codigo, precio))
                else:
                    cur.execute(
                        "UPDATE productos SET precio = ?, "
                        "actualizado = datetime('now','localtime') "
                        "WHERE empresa_id = ? AND codigo_a2 = ? "
                        "AND (precio IS NULL OR precio <= 0)",
                        (precio, empresa_id, codigo))
    return len(lote)


@app.post("/api/catalogo")
async def api_catalogo(request: Request):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    if not usuario["empresa_id"]:
        return Response('{"error": "agente sin empresa"}', status_code=400,
                        media_type="application/json")
    lote = await cuerpo_json(request)
    try:
        guardados = await run_in_threadpool(_guarda_productos,
                                            usuario["empresa_id"], lote)
    except Exception as e:
        return _error_ocupado(e)
    return {"ok": True, "guardados": guardados}


@app.post("/api/stock")
async def api_stock(request: Request):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    if not usuario["empresa_id"]:
        return Response('{"error": "agente sin empresa"}', status_code=400,
                        media_type="application/json")
    lote = await cuerpo_json(request)
    try:
        guardados = await run_in_threadpool(_guarda_stock,
                                            usuario["empresa_id"], lote)
    except Exception as e:
        return _error_ocupado(e)
    return {"ok": True, "guardados": guardados}


@app.get("/api/estado")
def api_estado(request: Request):
    """Estado mínimo para que el agente sepa si le faltan precios por subir."""
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    if not usuario["empresa_id"]:
        return Response('{"error": "agente sin empresa"}', status_code=400,
                        media_type="application/json")
    fila = db.fila(
        "SELECT COUNT(*) AS productos, SUM(CASE WHEN precio IS NULL "
        "OR precio <= 0 THEN 1 ELSE 0 END) AS sin_precio FROM productos "
        "WHERE empresa_id = ?", (usuario["empresa_id"],))
    return {"empresa": usuario["empresa_id"],
            "productos": fila["productos"] or 0,
            "sin_precio": fila["sin_precio"] or 0}


@app.post("/api/precios")
async def api_precios(request: Request, origen: str = "venta"):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    lote = await cuerpo_json(request)
    try:
        total = await run_in_threadpool(_guarda_precios,
                                        usuario["empresa_id"], lote, origen)
    except Exception as e:
        return _error_ocupado(e)
    return {"ok": True, "precios": total}


def _guarda_clientes(empresa_id: int, lote: list) -> int:
    con = db.conectar()
    with con:
        for c in lote:
            codigo = str(c.get("codigo") or "").strip()
            if not codigo:
                continue
            con.execute(
                "INSERT INTO clientes (empresa_id, codigo, nombre, nit, rif, "
                "direccion, telefono, actualizado) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime')) "
                "ON CONFLICT(empresa_id, codigo) DO UPDATE SET "
                "nombre=excluded.nombre, nit=excluded.nit, rif=excluded.rif, "
                "direccion=COALESCE(excluded.direccion, clientes.direccion), "
                "telefono=COALESCE(excluded.telefono, clientes.telefono), "
                "actualizado=excluded.actualizado "
                "WHERE clientes.nombre IS NOT excluded.nombre "
                "OR clientes.nit IS NOT excluded.nit "
                "OR clientes.rif IS NOT excluded.rif "
                "OR clientes.direccion IS NOT excluded.direccion "
                "OR clientes.telefono IS NOT excluded.telefono",
                (empresa_id, codigo, c.get("nombre"), c.get("nit"),
                 c.get("rif"), c.get("direccion"), c.get("telefono")))
    return len(lote)


def _guarda_autorizados(empresa_id: int, lote: list) -> int:
    con = db.conectar()
    with con:
        for a in lote:
            codigo = str(a.get("codigo") or "").strip()
            cliente = str(a.get("cliente_codigo") or "").strip()
            if not codigo or not cliente:
                continue
            con.execute(
                "INSERT INTO autorizados (empresa_id, codigo, cliente_codigo, "
                "nombre, direccion, activo, actualizado) VALUES (?, ?, ?, ?, ?, ?, "
                "datetime('now','localtime')) "
                "ON CONFLICT(empresa_id, codigo) DO UPDATE SET "
                "cliente_codigo=excluded.cliente_codigo, nombre=excluded.nombre, "
                "direccion=excluded.direccion, activo=excluded.activo, "
                "actualizado=excluded.actualizado "
                "WHERE autorizados.cliente_codigo IS NOT excluded.cliente_codigo "
                "OR autorizados.nombre IS NOT excluded.nombre "
                "OR autorizados.direccion IS NOT excluded.direccion "
                "OR autorizados.activo IS NOT excluded.activo",
                (empresa_id, codigo, cliente, a.get("nombre"),
                 a.get("direccion"), 1 if a.get("activo", True) else 0))
    return len(lote)


def _guarda_vendedores(empresa_id: int, lote: list) -> int:
    con = db.conectar()
    with con:
        for v in lote:
            codigo = str(v.get("codigo") or "").strip()
            if not codigo:
                continue
            con.execute(
                "INSERT INTO vendedores_a2 (empresa_id, codigo, nombre, activo, "
                "clave_a2, actualizado) VALUES (?, ?, ?, ?, ?, "
                "datetime('now','localtime')) "
                "ON CONFLICT(empresa_id, codigo) DO UPDATE SET "
                "nombre=excluded.nombre, activo=excluded.activo, "
                "clave_a2=excluded.clave_a2, actualizado=excluded.actualizado",
                (empresa_id, codigo, v.get("nombre"),
                 1 if v.get("activo") else 0, v.get("clave_a2")))
    return len(lote)


@app.post("/api/clientes")
async def api_clientes(request: Request):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    if not usuario["empresa_id"]:
        return Response('{"error": "agente sin empresa"}', status_code=400,
                        media_type="application/json")
    lote = await cuerpo_json(request)
    try:
        guardados = await run_in_threadpool(_guarda_clientes,
                                            usuario["empresa_id"], lote)
    except Exception as e:
        return _error_ocupado(e)
    return {"ok": True, "guardados": guardados}


@app.post("/api/autorizados")
async def api_autorizados(request: Request):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    if not usuario["empresa_id"]:
        return Response('{"error": "agente sin empresa"}', status_code=400,
                        media_type="application/json")
    lote = await cuerpo_json(request)
    try:
        guardados = await run_in_threadpool(_guarda_autorizados,
                                            usuario["empresa_id"], lote)
    except Exception as e:
        return _error_ocupado(e)
    return {"ok": True, "guardados": guardados}


@app.post("/api/vendedores")
async def api_vendedores(request: Request):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    if not usuario["empresa_id"]:
        return Response('{"error": "agente sin empresa"}', status_code=400,
                        media_type="application/json")
    lote = await cuerpo_json(request)
    try:
        guardados = await run_in_threadpool(_guarda_vendedores,
                                            usuario["empresa_id"], lote)
    except Exception as e:
        return _error_ocupado(e)
    return {"ok": True, "guardados": guardados}


@app.get("/clientes/buscar")
def clientes_buscar(request: Request, q: str = "", limite: int = 15):
    """Busca clientes de la empresa para elegirlos en el pedido."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return {"items": []}
    empresa = empresa_del(usuario, None)
    if empresa is None:
        return {"items": []}
    patron = f"%{q.strip().upper()}%"
    filas_cli = db.filas(
        "SELECT codigo, nombre, nit, rif FROM clientes WHERE empresa_id = ? "
        "AND (UPPER(nombre) LIKE ? OR UPPER(codigo) LIKE ? OR nit LIKE ?) "
        "ORDER BY nombre LIMIT ?",
        (empresa["id"], patron, patron, patron, limite))
    return {"items": [dict(f) for f in filas_cli]}


def _crear_cliente(empresa_id: int, vendedor_codigo: str, nit: str,
                   nombre: str, direccion: str, telefono: str) -> dict:
    """Crea el cliente en el panel y en la cola para A2 (lo usan web y app).

    Si el NIT ya existe no crea nada: devuelve el cliente que ya estaba.
    """
    nit = str(nit or "").strip()
    nombre = " ".join(str(nombre or "").split())
    direccion = " ".join(str(direccion or "").split())
    telefono = " ".join(str(telefono or "").split())
    # el NIT es el código del cliente: solo números, máximo 10 (sin letras)
    if not nit.isdigit() or not 1 <= len(nit) <= 10:
        return {"ok": False, "error": "El NIT debe ser solo números (máximo 10)."}
    if not nombre or not direccion or not telefono:
        return {"ok": False, "error": "Nombre, dirección y teléfono son obligatorios."}
    existente = db.fila(
        "SELECT codigo, nombre, nit, rif FROM clientes WHERE empresa_id = ? "
        "AND (codigo = ? OR nit = ?) LIMIT 1", (empresa_id, nit, nit))
    if existente is not None:
        return {"ok": True, "nuevo": False, "cliente": dict(existente),
                "aviso": "Ese NIT ya existe: se usa el cliente que ya estaba creado."}
    try:
        db.ejecutar(
            "INSERT INTO clientes (empresa_id, codigo, nombre, nit, direccion, "
            "telefono, actualizado) VALUES (?, ?, ?, ?, ?, ?, "
            "datetime('now','localtime'))",
            (empresa_id, nit, nombre, nit, direccion, telefono))
        db.ejecutar(
            "INSERT INTO clientes_nuevos (empresa_id, codigo, nombre, nit, "
            "direccion, telefono, vendedor) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (empresa_id, nit, nombre, nit, direccion, telefono,
             vendedor_codigo))
    except Exception:
        # si otro lo creó en ese instante, se usa el existente
        existente = db.fila(
            "SELECT codigo, nombre, nit, rif FROM clientes WHERE empresa_id = ? "
            "AND (codigo = ? OR nit = ?) LIMIT 1", (empresa_id, nit, nit))
        if existente is not None:
            return {"ok": True, "nuevo": False, "cliente": dict(existente)}
        return {"ok": False, "error": "No se pudo crear el cliente."}
    return {"ok": True, "nuevo": True,
            "cliente": {"codigo": nit, "nombre": nombre, "nit": nit},
            "aviso": "Cliente creado. Se guardará en A2 en el próximo ciclo."}


@app.post("/pedido/cliente-nuevo")
def pedido_cliente_nuevo(request: Request, nit: str = Form(""),
                         nombre: str = Form(""), direccion: str = Form(""),
                         telefono: str = Form("")):
    """Crea un cliente desde el pedido del panel web."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return {"ok": False, "error": "Se cerró la sesión."}
    empresa = empresa_del(usuario, None)
    if empresa is None or not empresa["usar_clientes"] or \
            not empresa["usar_clientes_nuevos"]:
        return {"ok": False, "error": "Crear clientes no está habilitado."}
    return _crear_cliente(empresa["id"], usuario["codigo"], nit, nombre,
                          direccion, telefono)


@app.get("/api/clientes/nuevos")
def api_clientes_nuevos(request: Request):
    """Clientes creados desde el pedido que el agente debe insertar en A2."""
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    filas = db.filas(
        "SELECT id, codigo, nombre, nit, direccion, telefono, vendedor "
        "FROM clientes_nuevos WHERE empresa_id = ? AND estado = 'pendiente' "
        "ORDER BY id", (usuario["empresa_id"],))
    return {"clientes": [dict(f) for f in filas]}


@app.post("/api/clientes/nuevos/estado")
def api_cliente_nuevo_estado(request: Request, id: int, estado: str,
                             error: str = ""):
    """El agente reporta si pudo insertar el cliente en A2."""
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    if estado not in ("creado", "duplicado", "error"):
        estado = "error"
    db.ejecutar(
        "UPDATE clientes_nuevos SET estado = ?, error = ?, "
        "procesado = datetime('now','localtime') WHERE id = ? AND empresa_id = ?",
        (estado, (error or "")[:500] or None, id, usuario["empresa_id"]))
    return {"ok": True}


@app.get("/autorizados/cliente")
def autorizados_cliente(request: Request, codigo: str = ""):
    """Autorizados (direcciones) del cliente elegido en el pedido."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return {"items": []}
    empresa = empresa_del(usuario, None)
    if empresa is None or not empresa["usar_clientes"] \
            or not empresa["usar_autorizados"]:
        return {"items": []}
    codigo = codigo.strip()
    if not codigo:
        return {"items": []}
    filas_aut = db.filas(
        "SELECT codigo, nombre, direccion FROM autorizados "
        "WHERE empresa_id = ? AND cliente_codigo = ? "
        "ORDER BY nombre, codigo", (empresa["id"], codigo))
    return {"items": [dict(f) for f in filas_aut]}


@app.post("/clientes/refrescar")
def clientes_refrescar(request: Request):
    """Pide al agente que vuelva a leer los clientes de A2 ya mismo."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return {"ok": False}
    empresa = empresa_del(usuario, None)
    if empresa is None:
        return {"ok": False}
    db.ejecutar("UPDATE empresas SET sync_clientes_pedido = 1 WHERE id = ?",
                (empresa["id"],))
    return {"ok": True}


@app.get("/api/sync/clientes")
def api_sync_clientes(request: Request):
    """El agente pregunta si hay que refrescar los clientes (y se limpia)."""
    usuario = usuario_agente(request)
    if usuario is None:
        return {"pedido": False}
    empresa = db.fila("SELECT sync_clientes_pedido FROM empresas WHERE id = ?",
                      (usuario["empresa_id"],))
    pedido = bool(empresa and empresa["sync_clientes_pedido"])
    if pedido:
        db.ejecutar("UPDATE empresas SET sync_clientes_pedido = 0 WHERE id = ?",
                    (usuario["empresa_id"],))
    return {"pedido": pedido}


@app.get("/api/sync/autorizados")
def api_sync_autorizados(request: Request):
    """El agente pregunta si hay que refrescar los autorizados (y se limpia)."""
    usuario = usuario_agente(request)
    if usuario is None:
        return {"pedido": False}
    empresa = db.fila(
        "SELECT sync_autorizados_pedido FROM empresas WHERE id = ?",
        (usuario["empresa_id"],))
    pedido = bool(empresa and empresa["sync_autorizados_pedido"])
    if pedido:
        db.ejecutar("UPDATE empresas SET sync_autorizados_pedido = 0 "
                    "WHERE id = ?", (usuario["empresa_id"],))
    return {"pedido": pedido}


@app.get("/api/pedidos/pendientes")
def api_pendientes(request: Request):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    lista = db.filas(
        "SELECT p.id, p.numero, p.referencia, p.cliente_codigo, "
        "p.cliente_nit, p.cliente_nombre, "
        "u.codigo AS vendedor, u.nombre AS vendedor_nombre FROM pedidos p "
        "JOIN usuarios u ON u.id = p.vendedor_id "
        "WHERE p.empresa_id = ? AND p.estado = 'pendiente' ORDER BY p.id",
        (usuario["empresa_id"],))
    # cliente predeterminado de la empresa (cuando el vendedor no elige uno)
    predeterminado = db.fila(
        "SELECT cliente_predeterminado_codigo, cliente_predeterminado_nombre, "
        "cliente_predeterminado_nit, cliente_predeterminado_rif FROM empresas "
        "WHERE id = ?", (usuario["empresa_id"],))
    def_nombre = ((predeterminado["cliente_predeterminado_nombre"]
                   if predeterminado else "") or "").strip()
    def_nit = ((predeterminado["cliente_predeterminado_nit"]
                if predeterminado else "") or "").strip()
    def_rif = ((predeterminado["cliente_predeterminado_rif"]
                if predeterminado else "") or "").strip()
    de_vuelta = []
    for p in lista:
        lineas = db.filas(
            "SELECT l.codigo, COALESCE(pr.codigo_a2, l.codigo) AS codigo_a2, "
            "l.cantidad, l.precio FROM pedido_lineas l "
            "LEFT JOIN productos pr ON pr.empresa_id = (SELECT empresa_id FROM "
            "pedidos WHERE id = l.pedido_id) AND pr.codigo = l.codigo "
            "WHERE l.pedido_id = ? ORDER BY l.id", (p["id"],))
        pedido = {k: p[k] for k in p.keys()}
        pedido["cliente_nombre"] = (p["cliente_nombre"] or "").strip() or \
            def_nombre
        pedido["cliente_nit"] = (p["cliente_nit"] or "").strip() or def_nit
        pedido["cliente_codigo"] = (p["cliente_codigo"] or "").strip() or \
            ((predeterminado["cliente_predeterminado_codigo"]
              if predeterminado else "") or "").strip()
        rif = def_rif
        if p["cliente_codigo"]:
            fila_cli = db.fila(
                "SELECT rif FROM clientes WHERE empresa_id = ? AND codigo = ?",
                (usuario["empresa_id"], p["cliente_codigo"]))
            rif = ((fila_cli["rif"] if fila_cli else "") or "").strip()
        pedido["cliente_rif"] = rif
        de_vuelta.append(pedido | {"lineas": [dict(l) for l in lineas]})
    return {"pedidos": de_vuelta}


@app.post("/api/pedidos/montado")
def api_montado(request: Request, id: int, a2_autoincrement: int,
                numero_a2: str = ""):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    db.ejecutar("UPDATE pedidos SET estado = 'montado', montado = "
                "datetime('now','localtime'), a2_autoincrement = ?, "
                "error_a2 = NULL, intentos = 0 WHERE id = ?",
                (a2_autoincrement, id))
    return {"ok": True}


@app.post("/api/pedidos/error")
def api_error(request: Request, id: int, mensaje: str):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    db.ejecutar("UPDATE pedidos SET estado = 'error', error_a2 = ? WHERE id = ?",
                (mensaje[:500], id))
    return {"ok": True}


@app.post("/api/pedidos/reintento")
def api_reintento(request: Request, id: int, mensaje: str = ""):
    """El agente no pudo montar el pedido: se queda PENDIENTE y se reintenta.

    Solo se guarda el último error y se cuenta el intento; el estado no cambia.
    """
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    db.ejecutar(
        "UPDATE pedidos SET error_a2 = ?, "
        "intentos = COALESCE(intentos, 0) + 1, montado = NULL "
        "WHERE id = ? AND estado = 'pendiente'",
        (mensaje[:500], id))
    return {"ok": True}


@app.post("/login")
def login_post(request: Request, codigo: str = Form(...), clave: str = Form(...)):
    seg = db.fila("SELECT id, clave_hash, rol, activo FROM usuarios "
                  "WHERE codigo = ? AND (rol = 'super' OR rol = 'admin' "
                  "OR rol = 'vendedor') LIMIT 1", (codigo.strip(),))
    if seg is None or not seg["activo"] or \
            not seguridad.verificar_clave(clave, seg["clave_hash"]):
        return RedirectResponse("/login?error=1", status_code=303)
    token = seguridad.crear_sesion(seg["id"])
    resp = RedirectResponse("/inicio", status_code=303)
    resp.set_cookie(COOKIE_SESION, token, httponly=True, samesite="lax", max_age=60 * 60 * 12)
    return resp


@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get(COOKIE_SESION)
    if token:
        seguridad.cerrar_sesion(token)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_SESION)
    return resp


# ---------- inicio ----------

@app.get("/inicio")
def inicio(request: Request):
    try:
        usuario = protege(request)
    except Redirige:
        return RedirectResponse("/login", status_code=303)
    return respuesta(request, "inicio.html",
                     {"hora": datetime.now().strftime("%Y-%m-%d %H:%M")})


@app.get("/cartera")
def cartera(request: Request):
    """Apartado de Cartera (por ahora sin datos; se conectará al panel)."""
    try:
        protege(request)
    except Redirige:
        return RedirectResponse("/login", status_code=303)
    return respuesta(request, "cartera.html", {})


# ---------- empresas (solo super) ----------

def requiere_rol(request: Request, roles):
    usuario = usuario_actual(request)
    if usuario is None:
        raise Redirige
    if usuario["rol"] not in roles:
        return None
    return usuario


def datos_empresas() -> dict:
    """Empresas con sus vendedores, última sincronización y token del agente."""
    lista = db.filas("SELECT e.*, (SELECT COUNT(*) FROM usuarios u WHERE "
                     "u.empresa_id = e.id AND u.rol = 'vendedor') AS vendedores "
                     "FROM empresas e ORDER BY e.id")
    sincs = {s["empresa_id"]: s["hecho"] for s in db.filas(
        "SELECT empresa_id, MAX(hecho) AS hecho FROM sincronizaciones GROUP BY empresa_id")}
    tokens = {a["empresa_id"]: seguridad.descifrar_clave(a["clave_visible"])
              for a in db.filas("SELECT empresa_id, clave_visible FROM usuarios "
                                "WHERE rol = 'agente'")}
    return {"lista": lista, "sincs": sincs, "tokens": tokens}


@app.get("/empresas")
def empresas(request: Request):
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/inicio", status_code=303)
    return respuesta(request, "empresas.html",
                     {**datos_empresas(), "volver": "/empresas"})


@app.post("/empresas/token")
def empresas_token(request: Request, empresa_id: int = Form(...),
                   volver: str = Form("/empresas")):
    """Crea o renueva el token del agente de una empresa (lo anula anterior)."""
    import hashlib
    import secrets as _secrets

    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    token = _secrets.token_urlsafe(32)
    huella = "tok$" + hashlib.sha256(token.encode()).hexdigest()
    agente = db.fila("SELECT id FROM usuarios WHERE empresa_id = ? AND rol = 'agente'",
                     (empresa_id,))
    if agente:
        db.ejecutar("UPDATE usuarios SET clave_hash = ?, activo = 1, "
                    "clave_visible = ? WHERE id = ?",
                    (huella, seguridad.cifrar_clave(token), agente["id"]))
    else:
        db.ejecutar("INSERT INTO usuarios (empresa_id, codigo, clave_hash, nombre, "
                    "rol, clave_visible) VALUES (?, 'AGENTE', ?, 'Agente de A2', "
                    "'agente', ?)", (empresa_id, huella,
                                     seguridad.cifrar_clave(token)))
    if volver.startswith("/configuracion"):
        return RedirectResponse(f"/configuracion?empresa={empresa_id}&ok=token",
                                status_code=303)
    return RedirectResponse("/empresas?ok=token", status_code=303)


@app.post("/empresas/crear")
def empresas_crear(request: Request, nombre: str = Form(...),
                   volver: str = Form("/empresas")):
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    if nombre.strip():
        db.ejecutar("INSERT INTO empresas (nombre) VALUES (?)", (nombre.strip(),))
    destino = volver if volver.startswith("/") else "/empresas"
    return RedirectResponse(f"{destino}?ok=empresa", status_code=303)


# ---------- apps habilitadas (tokens de la app Android) ----------

def _empresa_apps(usuario, empresa_id: int | None = None):
    """Empresa sobre la que puede operar el usuario en Apps.

    El administrativo solo maneja las apps de su propia empresa; el super
    puede elegir cualquier empresa.
    """
    if usuario["rol"] == "admin":
        if not usuario["empresa_id"]:
            return None
        if empresa_id is not None and empresa_id != usuario["empresa_id"]:
            return None
        return db.fila("SELECT * FROM empresas WHERE id = ?",
                       (usuario["empresa_id"],))
    return empresa_del(usuario, empresa_id)


@app.get("/apps")
def apps(request: Request, empresa: int | None = None):
    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/inicio", status_code=303)
    if usuario["rol"] == "super" and empresa:
        fija_empresa_activa(usuario, empresa)
    emp = _empresa_apps(usuario, empresa if usuario["rol"] == "super" else None)
    if emp is None:
        return RedirectResponse("/inicio", status_code=303)
    lista = db.filas("SELECT * FROM app_tokens WHERE empresa_id = ? "
                     "ORDER BY id DESC", (emp["id"],))
    return respuesta(request, "apps.html",
                     {"e": emp, "apps": lista, "token_nuevo": None})


@app.post("/apps/crear")
def apps_crear(request: Request, empresa_id: int = Form(...),
               nombre: str = Form("")):
    import secrets as _secrets

    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    emp = _empresa_apps(usuario, empresa_id)
    if emp is None:
        return RedirectResponse("/apps?error=permiso", status_code=303)
    token = _secrets.token_urlsafe(32)
    huella = "app$" + hashlib.sha256(token.encode()).hexdigest()
    db.ejecutar("INSERT INTO app_tokens (empresa_id, nombre, token_hash) "
                "VALUES (?, ?, ?)",
                (emp["id"], nombre.strip() or "Teléfono", huella))
    lista = db.filas("SELECT * FROM app_tokens WHERE empresa_id = ? "
                     "ORDER BY id DESC", (emp["id"],))
    return respuesta(request, "apps.html",
                     {"e": emp, "apps": lista, "token_nuevo": token})


def _volver_apps(usuario, empresa) -> RedirectResponse:
    if usuario["rol"] != "super":
        return RedirectResponse("/apps", status_code=303)
    return RedirectResponse(f"/apps?empresa={empresa['id']}", status_code=303)


@app.post("/apps/revocar")
def apps_revocar(request: Request, app_id: int = Form(...),
                 empresa_id: int = Form(...)):
    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    emp = _empresa_apps(usuario, empresa_id)
    if emp is None:
        return RedirectResponse("/apps?error=permiso", status_code=303)
    db.ejecutar("UPDATE app_tokens SET activo = 0 "
                "WHERE id = ? AND empresa_id = ?", (app_id, emp["id"]))
    return _volver_apps(usuario, emp)


@app.post("/apps/reactivar")
def apps_reactivar(request: Request, app_id: int = Form(...),
                   empresa_id: int = Form(...)):
    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    emp = _empresa_apps(usuario, empresa_id)
    if emp is None:
        return RedirectResponse("/apps?error=permiso", status_code=303)
    db.ejecutar("UPDATE app_tokens SET activo = 1 "
                "WHERE id = ? AND empresa_id = ?", (app_id, emp["id"]))
    return _volver_apps(usuario, emp)


@app.post("/apps/eliminar")
def apps_eliminar(request: Request, app_id: int = Form(...),
                  empresa_id: int = Form(...)):
    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    emp = _empresa_apps(usuario, empresa_id)
    if emp is None:
        return RedirectResponse("/apps?error=permiso", status_code=303)
    db.ejecutar("DELETE FROM app_tokens WHERE id = ? AND empresa_id = ?",
                (app_id, emp["id"]))
    return _volver_apps(usuario, emp)


# ---------- vendedores ----------

@app.get("/vendedores")
def vendedores(request: Request):
    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    pedir = request.query_params.get("empresa")
    if usuario["rol"] == "super" and pedir:
        fija_empresa_activa(usuario, int(pedir))
    empresa = empresa_del(usuario, pedir and int(pedir))
    if empresa is None:
        return respuesta(request, "vendedores.html", {"sin_empresa": True})
    lista = db.filas("SELECT id, codigo, nombre, rol, activo, creado, clave_visible "
                     "FROM usuarios WHERE empresa_id = ? AND rol = 'vendedor' "
                     "ORDER BY codigo", (empresa["id"],))
    lista = [{**dict(u), "clave": seguridad.descifrar_clave(u["clave_visible"])}
             for u in lista]
    admins = []
    superusuarios = []
    if usuario["rol"] == "super":
        admins = db.filas(
            "SELECT id, codigo, nombre, rol, activo, creado, clave_visible "
            "FROM usuarios WHERE empresa_id = ? AND rol = 'admin' ORDER BY codigo",
            (empresa["id"],))
        admins = [{**dict(u), "clave": seguridad.descifrar_clave(u["clave_visible"])}
                  for u in admins]
        superusuarios = db.filas(
            "SELECT id, codigo, nombre, rol, activo, creado, clave_visible "
            "FROM usuarios WHERE rol = 'super' ORDER BY codigo")
        superusuarios = [{**dict(u),
                          "clave": seguridad.descifrar_clave(u["clave_visible"])}
                         for u in superusuarios]
    return respuesta(request, "vendedores.html",
                     {"e": empresa, "lista": lista, "admins": admins,
                      "superusuarios": superusuarios})


@app.post("/vendedores/importar")
def vendedores_importar(request: Request):
    """Trae todos los vendedores de A2 (Svendedores) a la empresa actual."""
    import secrets as _secrets

    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    empresa = empresa_del(usuario, None)
    if empresa is None:
        return RedirectResponse("/vendedores?error=permiso", status_code=303)
    filas_a2 = db.filas("SELECT codigo, nombre, activo, clave_a2 "
                        "FROM vendedores_a2 WHERE empresa_id = ?", (empresa["id"],))
    if not filas_a2:
        return RedirectResponse("/vendedores?error=sin_datos", status_code=303)
    desde_a2 = [{"codigo": f["codigo"], "nombre": f["nombre"],
                 "activo": bool(f["activo"]), "clave_a2": f["clave_a2"] or ""}
                for f in filas_a2]
    nuevos = actualizados = 0
    generadas = []
    for v in desde_a2:
        codigo = v["codigo"].strip().upper()
        existente = db.fila("SELECT id FROM usuarios WHERE empresa_id = ? AND codigo = ?",
                            (empresa["id"], codigo))
        if existente:
            db.ejecutar("UPDATE usuarios SET nombre = ? WHERE id = ?",
                        (v["nombre"], existente["id"]))
            actualizados += 1
            continue
        clave = v["clave_a2"] if len(v["clave_a2"]) >= 2 else None
        if clave is None:
            clave = _secrets.token_urlsafe(4)[:6]
            generadas.append((codigo, v["nombre"], clave))
        db.ejecutar("INSERT INTO usuarios (empresa_id, codigo, clave_hash, nombre, "
                    "rol, activo, clave_visible) VALUES (?, ?, ?, ?, 'vendedor', ?, ?)",
                    (empresa["id"], codigo, seguridad.hash_clave(clave),
                     v["nombre"], 1 if v["activo"] else 0,
                     seguridad.cifrar_clave(clave)))
        nuevos += 1
    lista = db.filas("SELECT id, codigo, nombre, rol, activo, creado FROM usuarios "
                     "WHERE empresa_id = ? AND rol = 'vendedor' ORDER BY codigo",
                     (empresa["id"],))
    return respuesta(request, "vendedores.html", {
        "e": empresa, "lista": lista, "importadas": generadas,
        "import_resumen": (nuevos, actualizados, len(desde_a2))})


@app.post("/vendedores/crear")
def vendedores_crear(request: Request, empresa_id: int = Form(...),
                     codigo: str = Form(...), nombre: str = Form(...),
                     clave: str = Form(...), rol: str = Form("vendedor")):
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    pid = empresa_id if usuario["rol"] == "super" else usuario["empresa_id"]
    if pid is None or (usuario["rol"] == "admin" and pid != usuario["empresa_id"]):
        return RedirectResponse("/vendedores?error=permiso", status_code=303)
    codigo = codigo.strip().upper()
    if rol not in ("vendedor", "admin"):
        rol = "vendedor"
    if not codigo or not nombre.strip() or len(clave) < 2:
        return RedirectResponse(f"/vendedores?error=datos", status_code=303)
    if db.fila("SELECT id FROM usuarios WHERE empresa_id = ? AND codigo = ?",
               (pid, codigo)):
        return RedirectResponse(f"/vendedores?error=duplicado", status_code=303)
    db.ejecutar("INSERT INTO usuarios (empresa_id, codigo, clave_hash, nombre, rol, "
                "clave_visible) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, codigo, seguridad.hash_clave(clave), nombre.strip(), rol,
                 seguridad.cifrar_clave(clave)))
    return RedirectResponse(f"/vendedores?ok=creado", status_code=303)


@app.post("/vendedores/clave")
def vendedores_clave(request: Request, vendedor_id: int = Form(...),
                     clave: str = Form(...)):
    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    objetivo = db.fila("SELECT * FROM usuarios WHERE id = ? "
                       "AND rol IN ('vendedor', 'admin')", (vendedor_id,))
    if objetivo is None or len(clave) < 2:
        return RedirectResponse("/vendedores?error=permiso", status_code=303)
    # el super puede con cualquiera; el admin solo con vendedores de su empresa
    if usuario["rol"] == "admin" and (
            objetivo["rol"] != "vendedor"
            or objetivo["empresa_id"] != usuario["empresa_id"]):
        return RedirectResponse("/vendedores?error=permiso", status_code=303)
    db.ejecutar("UPDATE usuarios SET clave_hash = ?, clave_visible = ? WHERE id = ?",
                (seguridad.hash_clave(clave), seguridad.cifrar_clave(clave),
                 vendedor_id))
    return RedirectResponse(f"/vendedores?ok=clave", status_code=303)


@app.post("/super/clave")
def super_clave(request: Request, clave: str = Form(...)):
    """El super usuario fija su propia clave (queda visible en la lista)."""
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    if len(clave) < 2:
        return RedirectResponse("/vendedores?error=datos", status_code=303)
    db.ejecutar("UPDATE usuarios SET clave_hash = ?, clave_visible = ? WHERE id = ?",
                (seguridad.hash_clave(clave), seguridad.cifrar_clave(clave),
                 usuario["id"]))
    return RedirectResponse("/vendedores?ok=clave", status_code=303)


@app.post("/vendedores/estado")
def vendedores_estado(request: Request, vendedor_id: int = Form(...)):
    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    objetivo = db.fila("SELECT * FROM usuarios WHERE id = ? "
                       "AND rol IN ('vendedor', 'admin')", (vendedor_id,))
    if objetivo is None:
        return RedirectResponse("/vendedores?error=permiso", status_code=303)
    # el super con cualquiera; el admin solo con vendedores de su empresa
    if usuario["rol"] == "admin" and (
            objetivo["rol"] != "vendedor"
            or objetivo["empresa_id"] != usuario["empresa_id"]):
        return RedirectResponse("/vendedores?error=permiso", status_code=303)
    db.ejecutar("UPDATE usuarios SET activo = 1 - activo WHERE id = ?", (vendedor_id,))
    return RedirectResponse(f"/vendedores?ok=estado", status_code=303)


# ---------- configuración del negocio ----------

def empresa_del(usuario, empresa_id: int | None):
    """La empresa con la que se trabaja. Los usuarios de una empresa solo ven
    la suya; el super puede pedir cualquiera (o la marcada en su sesión)."""
    if usuario["rol"] != "super" and usuario["empresa_id"]:
        return db.fila("SELECT * FROM empresas WHERE id = ?",
                       (usuario["empresa_id"],))
    pid = empresa_id or usuario["empresa_actual"]
    if pid:
        return db.fila("SELECT * FROM empresas WHERE id = ?", (pid,))
    return db.fila("SELECT * FROM empresas WHERE activa = 1 ORDER BY id LIMIT 1")


@app.get("/configuracion")
def configuracion(request: Request):
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    pedir = request.query_params.get("empresa")
    if pedir:
        fija_empresa_activa(usuario, int(pedir))
    empresa = empresa_del(usuario, pedir and int(pedir))
    return respuesta(request, "configuracion.html",
                     {"e": empresa, **datos_empresas(),
                      "volver": "/configuracion"})


def guardar_logo(empresa_id: int, archivo: UploadFile | None) -> tuple[str, str]:
    """Guarda la imagen subida. Devuelve (ruta web, mensaje de error)."""
    import io
    import os
    import uuid

    if archivo is None or not archivo.filename:
        return "", ""
    ext = os.path.splitext(archivo.filename)[1].lower()
    permitidas = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    if ext not in permitidas:
        return "", "Formato no permitido: usa PNG, JPG, WEBP o GIF."
    # si pesa más del límite se avisa (antes se guardaba cortada y salía rota)
    datos = archivo.file.read(5 * 1024 * 1024 + 1)
    if len(datos) > 5 * 1024 * 1024:
        return "", "La imagen es muy grande (máximo 5 MB)."
    if len(datos) < 10:
        return "", "La imagen llegó vacía. Intenta de nuevo."
    try:
        from PIL import Image
        Image.open(io.BytesIO(datos)).verify()
    except Exception:
        return "", "El archivo no parece una imagen válida."
    nombre = f"empresa-{empresa_id}-{uuid.uuid4().hex[:8]}{ext}"
    try:
        (config.LOGOS / nombre).write_bytes(datos)
    except OSError as e:
        return "", f"No se pudo guardar el logo en el servidor ({e.__class__.__name__})."
    return f"/logos/{nombre}", ""


@app.post("/configuracion")
def configuracion_post(request: Request, empresa_id: int = Form(...),
                       nombre: str = Form(""), deposito: str = Form("1"),
                       color_primario: str = Form("#1e40af"),
                       color_cartera: str = Form("#0f766e"),
                       color_letra: str = Form("#ffffff"),
                       logo_file: UploadFile | str = File(None),
                       quitar_logo: str = Form(""),
                       filtro: str = Form("todo"),
                       minimo: int = Form(0),
                       usar_clientes: str = Form(""),
                       usar_autorizados: str = Form(""),
                       usar_clientes_nuevos: str = Form(""),
                       cliente_predeterminado: str = Form(""),
                       formato_numero: str = Form("{vendedor}-{anio}{numero}"),
                       reinicio_numero: str = Form("anual"),
                       digitos_numero: int = Form(4)):
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    actual = db.fila("SELECT logo FROM empresas WHERE id = ?", (empresa_id,))
    logo = (actual or {"logo": None})["logo"]
    if quitar_logo:
        logo = None
    if isinstance(logo_file, str):
        # la página venía sin "multipart" (versión vieja): no es un archivo
        subido, error_logo = "", ("Vuelve a elegir la imagen: la página estaba "
                                  "desactualizada.")
    else:
        subido, error_logo = guardar_logo(empresa_id, logo_file)
    if subido:
        logo = subido
    # la barra usa el color principal; ya no se pide un color aparte
    if filtro not in ("todo", "positivo", "personalizado"):
        filtro = "todo"
    actual = db.fila("SELECT formato_numero, reinicio_numero, digitos_numero "
                     "FROM empresas WHERE id = ?", (empresa_id,))
    if not formato_numero_valido(formato_numero.strip()):
        formato_numero = (actual["formato_numero"] if actual else
                          "{vendedor}-{anio}{numero}")
    if reinicio_numero not in ("anual", "mensual", "diario"):
        reinicio_numero = "anual"
    digitos_numero = max(1, min(6, digitos_numero or 4))
    # los autorizados dependen de los clientes: sin clientes no hay autorizados
    usar_clientes_on = 1 if usar_clientes else 0
    usar_autorizados_on = 1 if (usar_clientes_on and usar_autorizados) else 0
    # crear clientes depende de que los clientes estén activados
    usar_clientes_nuevos_on = 1 if (usar_clientes_on and usar_clientes_nuevos) else 0
    # cliente predeterminado: se guarda el nombre/NIT/RIF del código elegido
    codigo_def = cliente_predeterminado.strip()
    nombre_def = nit_def = rif_def = None
    if codigo_def:
        elegido = db.fila(
            "SELECT nombre, nit, rif FROM clientes WHERE empresa_id = ? "
            "AND codigo = ?", (empresa_id, codigo_def))
        if elegido:
            nombre_def = elegido["nombre"]
            nit_def = elegido["nit"]
            rif_def = elegido["rif"]
        else:
            codigo_def = ""
    db.ejecutar("UPDATE empresas SET nombre = ?, deposito_modo = ?, "
                "ocultar_agotados = ?, color_primario = ?, color_cartera = ?, "
                "color_secundario = ?, "
                "color_letra = ?, logo = ?, filtro_existencia = ?, "
                "existencia_minima = ?, usar_clientes = ?, "
                "usar_autorizados = ?, usar_clientes_nuevos = ?, "
                "cliente_predeterminado_codigo = ?, "
                "cliente_predeterminado_nombre = ?, "
                "cliente_predeterminado_nit = ?, "
                "cliente_predeterminado_rif = ?, formato_numero = ?, "
                "reinicio_numero = ?, digitos_numero = ? WHERE id = ?",
                (nombre.strip() or "-", deposito, 1 if filtro != "todo" else 0,
                 color_primario, color_cartera, color_primario, color_letra, logo,
                 filtro, max(0, minimo), usar_clientes_on,
                 usar_autorizados_on, usar_clientes_nuevos_on,
                 codigo_def or None, nombre_def, nit_def, rif_def,
                 formato_numero.strip(), reinicio_numero, digitos_numero,
                 empresa_id))
    fija_empresa_activa(usuario, empresa_id)  # conserva el contexto tras guardar
    if error_logo:
        # el resto de la configuración sí se guardó; se avisa del logo
        import urllib.parse
        return RedirectResponse(
            f"/configuracion?empresa={empresa_id}&error={urllib.parse.quote(error_logo)}",
            status_code=303)
    return RedirectResponse(f"/configuracion?ok=1&empresa={empresa_id}", status_code=303)


# ---------- catálogo ----------

def _normaliza_busqueda(texto: str) -> str:
    """Texto de búsqueda en mayúsculas y sin espacios en los extremos."""
    return str(texto or "").strip().upper()


def _like(texto: str) -> str:
    """Escapa los comodines de LIKE para que lo escrito se busque literal."""
    return (str(texto).replace("\\", "\\\\").replace("%", "\\%")
            .replace("_", "\\_"))


def _patrones_codigo(qn: str) -> list:
    """Patrones de código: al comienzo y al comienzo de cada tramo."""
    q = _like(qn)
    return [f"{q}%", f"%-{q}%", f"%.{q}%", f"% {q}%", f"%/{q}%"]


def condicion_catalogo(empresa, q: str):
    """Condiciones SQL comunes del catálogo (internet + activo + búsqueda).

    Devuelve (condición, valores, orden, valores_del_orden). El orden deja
    primero el código exacto, luego el que empieza por lo escrito, luego el
    que lo tiene al comienzo de un tramo (58320 → GG-58320) y al final los que
    solo coinciden por la descripción.
    """
    condicion = "p.empresa_id = ? AND p.internet = 1 AND p.activo = 1"
    valores: list = [empresa["id"]]
    orden, orden_valores = "p.descripcion", []
    qn = _normaliza_busqueda(q)
    if qn:
        patrones = _patrones_codigo(qn)
        marcas = " OR ".join(["p.codigo_busqueda LIKE ? ESCAPE '\\'"] * len(patrones))
        condicion += (f" AND ({marcas} OR "
                      "UPPER(p.descripcion) LIKE ? ESCAPE '\\')")
        valores += patrones + [f"%{_like(qn)}%"]
        # el orden usa los mismos patrones (el primero es el "empieza por")
        orden = ("CASE WHEN p.codigo_busqueda = ? THEN 0 "
                 "WHEN p.codigo_busqueda LIKE ? ESCAPE '\\' THEN 1 "
                 "WHEN p.codigo_busqueda LIKE ? ESCAPE '\\' "
                 "OR p.codigo_busqueda LIKE ? ESCAPE '\\' "
                 "OR p.codigo_busqueda LIKE ? ESCAPE '\\' "
                 "OR p.codigo_busqueda LIKE ? ESCAPE '\\' THEN 2 "
                 "ELSE 3 END")
        orden_valores = [qn] + patrones
    # existencia según el modo de depósito de la empresa
    dep1 = ("(SELECT s.existencia FROM stock s WHERE s.empresa_id = p.empresa_id "
            "AND s.codigo_producto = p.codigo AND s.deposito = 1)")
    dep2 = ("(SELECT s.existencia FROM stock s WHERE s.empresa_id = p.empresa_id "
            "AND s.codigo_producto = p.codigo AND s.deposito = 2)")
    if empresa["deposito_modo"] == "1":
        visible = f"COALESCE({dep1}, 0)"
    elif empresa["deposito_modo"] == "2":
        visible = f"COALESCE({dep2}, 0)"
    else:
        visible = f"(COALESCE({dep1}, 0) + COALESCE({dep2}, 0))"
    modo_filtro = empresa["filtro_existencia"] or \
        ("positivo" if empresa["ocultar_agotados"] else "todo")
    if modo_filtro == "positivo":
        condicion += f" AND {visible} > 0"
    elif modo_filtro == "personalizado":
        minimo = int(empresa["existencia_minima"] or 0)
        condicion += f" AND {visible} >= ?"
        valores.append(minimo)
    return condicion, valores, orden, orden_valores


def productos_de(empresa, condicion: str, valores: list, limite: int,
                 desplaz: int = 0, orden: str = "p.descripcion",
                 orden_valores: list | tuple = ()):
    filas_p = db.filas(
        f"SELECT p.codigo, p.descripcion, p.marca, p.precio, "
        f"(SELECT s.existencia FROM stock s WHERE s.empresa_id = p.empresa_id "
        f"  AND s.codigo_producto = p.codigo AND s.deposito = 1) AS dep1, "
        f"(SELECT s.existencia FROM stock s WHERE s.empresa_id = p.empresa_id "
        f"  AND s.codigo_producto = p.codigo AND s.deposito = 2) AS dep2 "
        f"FROM productos p WHERE {condicion} "
        f"ORDER BY {orden}, p.descripcion LIMIT ? OFFSET ?",
        tuple(valores) + tuple(orden_valores) + (limite, desplaz))

    def existencia_que_ve(r):
        if empresa["deposito_modo"] == "1":
            return r["dep1"] or 0
        if empresa["deposito_modo"] == "2":
            return r["dep2"] or 0
        return (r["dep1"] or 0) + (r["dep2"] or 0)

    return [{**dict(r), "existencia": existencia_que_ve(r)} for r in filas_p]


@app.get("/catalogo")
def catalogo(request: Request, q: str = "", pagina: int = 1):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    pedir = request.query_params.get("empresa")
    if pedir:
        fija_empresa_activa(usuario, int(pedir))
    empresa = empresa_del(usuario, pedir and int(pedir))
    if empresa is None:
        return respuesta(request, "catalogo.html", {"sin_empresa": True, "q": q})
    por_pagina = 100
    condicion, valores, orden, orden_valores = condicion_catalogo(empresa, q)
    total = db.fila(f"SELECT COUNT(*) AS c FROM productos p WHERE {condicion}", tuple(valores))["c"]
    items = productos_de(empresa, condicion, valores, por_pagina,
                         max(0, pagina - 1) * por_pagina, orden, orden_valores)
    return respuesta(request, "catalogo.html", {
        "empresa": empresa, "items": items, "q": q, "total": total,
        "pagina": pagina, "paginas": (total + por_pagina - 1) // por_pagina or 1})


@app.get("/catalogo/buscar")
def catalogo_buscar(request: Request, q: str = "", limite: int = 100):
    """Búsqueda dinámica para el catálogo (se consulta mientras se escribe)."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return {"items": [], "total": 0, "sin_sesion": True}
    empresa = empresa_del(usuario, request.query_params.get("empresa") and
                          int(request.query_params["empresa"]))
    if empresa is None:
        return {"items": [], "total": 0}
    condicion, valores, orden, orden_valores = condicion_catalogo(empresa, q)
    total = db.fila(f"SELECT COUNT(*) AS c FROM productos p WHERE {condicion}", tuple(valores))["c"]
    items = productos_de(empresa, condicion, valores, limite, 0, orden, orden_valores)
    return {"total": total, "items": items}


# ---------- pedidos ----------

import json


def carrito_obtener(usuario) -> list:
    if not usuario["carrito"]:
        return []
    return json.loads(usuario["carrito"])


def carrito_guardar(usuario, carrito: list) -> None:
    """Guarda el carrito por usuario y empresa (no por sesión).

    Así el pedido en curso no se pierde al cerrar la página: al volver a
    entrar, con la sesión que sea, aparece lo que había agregado.
    """
    db.ejecutar(
        "INSERT INTO carritos (usuario_id, empresa_id, carrito, actualizado) "
        "VALUES (?, ?, ?, datetime('now','localtime')) "
        "ON CONFLICT(usuario_id, empresa_id) DO UPDATE SET "
        "carrito = excluded.carrito, actualizado = excluded.actualizado",
        (usuario["id"], usuario["empresa_actual"],
         json.dumps(carrito, ensure_ascii=False)))
    # deja limpia la copia vieja que vivía en la sesión
    db.ejecutar("UPDATE sesiones SET carrito = NULL WHERE token = ?",
                (usuario["token"],))


def existencia_visible(empresa, codigo: str) -> float:
    """Existencia que ve el vendedor, según el modo de depósito de la empresa."""
    filas = db.filas(
        "SELECT deposito, existencia FROM stock WHERE empresa_id = ? "
        "AND codigo_producto = ?", (empresa["id"], codigo))
    por_dep = {int(r["deposito"]): float(r["existencia"] or 0) for r in filas}
    modo = empresa["deposito_modo"] or "1"
    if modo == "2":
        return por_dep.get(2, 0.0)
    if modo == "suma":
        return por_dep.get(1, 0.0) + por_dep.get(2, 0.0)
    return por_dep.get(1, 0.0)


@app.post("/pedido/agregar")
def pedido_agregar(request: Request, codigo: str = Form(...), cantidad: float = Form(1)):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    empresa = empresa_del(usuario, None)
    if empresa is None:
        return RedirectResponse("/catalogo", status_code=303)
    cantidad = max(1, int(cantidad or 1))
    producto = db.fila("SELECT codigo, descripcion, precio FROM productos "
                       "WHERE empresa_id = ? AND codigo = ? AND internet = 1 AND activo = 1",
                       (empresa["id"], codigo))
    if producto is None:
        return RedirectResponse("/catalogo?aviso=producto", status_code=303)
    disponible = int(existencia_visible(empresa, producto["codigo"]))
    carrito = carrito_obtener(usuario)
    actual = next((int(i["cantidad"]) for i in carrito
                   if i["codigo"] == producto["codigo"]), 0)
    if disponible <= 0 or actual >= disponible:
        if request.headers.get("x-requested-with") == "fetch":
            return {"ok": False,
                    "mensaje": "No hay existencia suficiente de este producto.",
                    **resumen_carrito(carrito)}
        return RedirectResponse("/catalogo?aviso=sin_stock", status_code=303)
    sumar = min(cantidad, disponible - actual)
    for item in carrito:
        if item["codigo"] == producto["codigo"]:
            item["cantidad"] += sumar
            break
    else:
        carrito.append({"codigo": producto["codigo"], "descripcion": producto["descripcion"],
                        "precio": producto["precio"], "cantidad": sumar})
    carrito_guardar(usuario, carrito)
    if request.headers.get("x-requested-with") == "fetch":
        respuesta = {"ok": True, **resumen_carrito(carrito)}
        if sumar < cantidad:
            respuesta["tope"] = True
            respuesta["mensaje"] = f"Solo hay {disponible} en existencia."
        return respuesta
    return RedirectResponse("/pedido", status_code=303)


@app.post("/pedido/cantidad")
def pedido_cantidad(request: Request, codigo: str = Form(...), cantidad: float = Form(1)):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    empresa = empresa_del(usuario, None)
    if empresa is None:
        return RedirectResponse("/pedido", status_code=303)
    carrito = carrito_obtener(usuario)
    cantidad = int(cantidad or 0)
    item = next((i for i in carrito if i["codigo"] == codigo), None)
    if item is not None:
        disponible = int(existencia_visible(empresa, codigo))
        if cantidad <= 0 or disponible <= 0:
            carrito = [i for i in carrito if i["codigo"] != codigo]
        else:
            item["cantidad"] = min(cantidad, disponible)
    carrito_guardar(usuario, carrito)
    return RedirectResponse("/pedido", status_code=303)


@app.post("/pedido/quitar")
def pedido_quitar(request: Request, codigo: str = Form(...)):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    carrito_guardar(usuario, [i for i in carrito_obtener(usuario) if i["codigo"] != codigo])
    return RedirectResponse("/pedido", status_code=303)


VARIABLES_NUMERO = ("vendedor", "anio", "mes", "dia", "numero")


def formato_numero_valido(formato: str) -> bool:
    """El formato solo admite las variables conocidas y caracteres seguros."""
    import re
    if not formato or len(formato) > 30 or "{numero}" not in formato:
        return False
    limpio = re.sub(r"\{(vendedor|anio|mes|dia|numero)\}", "", formato)
    return re.fullmatch(r"[A-Za-z0-9_\-.]*", limpio) is not None


def numero_siguiente(empresa_id: int, vendedor, empresa=None) -> str:
    """Arma el número según el formato de la empresa (configurable por el super).

    Variables: {vendedor} {anio} {mes} {dia} {numero}
    Reinicio del consecutivo: anual, mensual o diario.
    """
    import datetime as _dt
    hoy = _dt.date.today()
    cfg = empresa or db.fila("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
    formato = (cfg["formato_numero"] if cfg and cfg["formato_numero"]
               else "{vendedor}-{anio}{numero}")
    reinicio = (cfg["reinicio_numero"] if cfg and cfg["reinicio_numero"] else "anual")
    digitos = max(1, min(6, int((cfg["digitos_numero"] if cfg and cfg["digitos_numero"] else 4))))
    if reinicio == "mensual":
        periodo = hoy.year * 100 + hoy.month
    elif reinicio == "diario":
        periodo = hoy.year * 10000 + hoy.month * 100 + hoy.day
    else:
        periodo = hoy.year
    db.ejecutar("INSERT INTO consecutivos (empresa_id, vendedor_id, anio, ultimo) "
                "VALUES (?, ?, ?, 0) ON CONFLICT(empresa_id, vendedor_id, anio) "
                "DO NOTHING", (empresa_id, vendedor["id"], periodo))
    con = db.conectar()
    cur = con.execute("UPDATE consecutivos SET ultimo = ultimo + 1 "
                      "WHERE empresa_id = ? AND vendedor_id = ? AND anio = ? "
                      "RETURNING ultimo", (empresa_id, vendedor["id"], periodo))
    nuevo = cur.fetchone()[0]
    con.commit()
    reemplazos = {
        "{vendedor}": str(vendedor["codigo"]),
        "{anio}": f"{hoy.year:04d}",
        "{mes}": f"{hoy.month:02d}",
        "{dia}": f"{hoy.day:02d}",
        "{numero}": str(nuevo).zfill(digitos),
    }
    numero = formato
    for token, valor in reemplazos.items():
        numero = numero.replace(token, valor)
    return numero


@app.get("/pedido")
def pedido(request: Request):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    carrito = carrito_obtener(usuario)
    total = sum(i["cantidad"] * (i["precio"] or 0) for i in carrito)
    empresa = empresa_del(usuario, None)
    return respuesta(request, "pedido.html",
                     {"carrito": carrito, "total": total, "empresa": empresa,
                      "cliente_defecto": "CONSUMIDOR FINAL"})


@app.post("/pedido/enviar")
def pedido_enviar(request: Request, referencia: str = Form(""),
                  cliente_codigo: str = Form(""), cliente_nombre: str = Form(""),
                  cliente_nit: str = Form(""),
                  autorizado_codigo: str = Form("")):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    carrito = carrito_obtener(usuario)
    if not carrito:
        return RedirectResponse("/pedido?vacio=1", status_code=303)
    empresa = empresa_del(usuario, None)
    # la referencia es un textarea: A2 no acepta saltos de línea en el INSERT
    referencia = " ".join(
        referencia.replace("\t", " ").splitlines()).strip()[:250]
    # con Clientes activado, el vendedor TIENE que elegir un cliente
    if empresa["usar_clientes"] and not cliente_codigo.strip():
        return RedirectResponse("/pedido?falta_cliente=1", status_code=303)
    # re-lee los precios de la BD (no confía en lo que vino del navegador)
    for item in carrito:
        p = db.fila("SELECT precio, descripcion FROM productos "
                    "WHERE empresa_id = ? AND codigo = ?",
                    (empresa["id"], item["codigo"]))
        if p is not None:
            item["precio"] = p["precio"]
            item["descripcion"] = p["descripcion"]
    # no permitir más cantidad que la existencia visible de cada producto
    for item in carrito:
        if item["cantidad"] > existencia_visible(empresa, item["codigo"]):
            return RedirectResponse("/pedido?sin_stock=1", status_code=303)
    numero = numero_siguiente(empresa["id"], usuario, empresa)
    total = sum(i["cantidad"] * (i["precio"] or 0) for i in carrito)
    if not empresa["usar_clientes"]:
        cliente_codigo, cliente_nombre, cliente_nit = "", "", ""
    # si no se eligió cliente se deja vacío: el agente usa el predeterminado
    # configurado para la empresa (o CONSUMIDOR FINAL si no hay ninguno)
    # autorizado: opcional, siempre de ese cliente; NUNCA se manda a A2,
    # solo se imprime en la hoja.
    aut_codigo = aut_nombre = aut_direccion = None
    if empresa["usar_clientes"] and empresa["usar_autorizados"]:
        cod_aut = autorizado_codigo.strip()
        if cod_aut:
            aut = db.fila(
                "SELECT nombre, direccion FROM autorizados WHERE empresa_id = ? "
                "AND cliente_codigo = ? AND codigo = ?",
                (empresa["id"], cliente_codigo.strip(), cod_aut))
            if aut is not None:
                aut_codigo = cod_aut
                aut_nombre = aut["nombre"]
                aut_direccion = aut["direccion"]
    cur = db.ejecutar(
        "INSERT INTO pedidos (empresa_id, vendedor_id, numero, referencia, estado, "
        "total, cliente_codigo, cliente_nombre, cliente_nit, "
        "autorizado_codigo, autorizado_nombre, autorizado_direccion) "
        "VALUES (?, ?, ?, ?, 'pendiente', ?, ?, ?, ?, ?, ?, ?)",
        (empresa["id"], usuario["id"], numero, referencia, total,
         cliente_codigo.strip() or None, cliente_nombre.strip() or None,
         cliente_nit.strip() or None, aut_codigo, aut_nombre, aut_direccion))
    pedido_id = cur.lastrowid
    for item in carrito:
        db.ejecutar("INSERT INTO pedido_lineas (pedido_id, codigo, descripcion, "
                    "cantidad, precio) VALUES (?, ?, ?, ?, ?)",
                    (pedido_id, item["codigo"], item["descripcion"],
                     item["cantidad"], item["precio"] or 0))
    carrito_guardar(usuario, [])
    return RedirectResponse(f"/pedidos/{pedido_id}?creado=1", status_code=303)


@app.get("/pedidos")
def pedidos(request: Request, pagina: int = 1, estado: str = ""):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    por_pagina = 50
    condicion = "1=1"
    valores: list = []
    if usuario["rol"] == "vendedor":
        condicion += " AND p.vendedor_id = ?"
        valores.append(usuario["id"])
    else:
        empresa = empresa_del(usuario, request.query_params.get("empresa") and
                              int(request.query_params["empresa"]))
        if empresa:
            condicion += " AND p.empresa_id = ?"
            valores.append(empresa["id"])
    if estado in ("pendiente", "montado", "error"):
        condicion += " AND p.estado = ?"
        valores.append(estado)
    total_reg = db.fila(f"SELECT COUNT(*) AS c FROM pedidos p WHERE {condicion}", tuple(valores))["c"]
    lista = db.filas(
        f"SELECT p.*, u.codigo AS vend_codigo, u.nombre AS vend_nombre "
        f"FROM pedidos p JOIN usuarios u ON u.id = p.vendedor_id "
        f"WHERE {condicion} ORDER BY p.id DESC LIMIT ? OFFSET ?",
        tuple(valores) + (por_pagina, max(0, pagina - 1) * por_pagina))
    vendedores = []
    if usuario["rol"] == "super":
        emp = empresa_del(usuario, None)
        if emp:
            vendedores = db.filas(
                "SELECT id, codigo, nombre FROM usuarios WHERE empresa_id = ? "
                "AND rol = 'vendedor' ORDER BY codigo", (emp["id"],))
    return respuesta(request, "pedidos.html", {
        "lista": lista, "total_reg": total_reg, "pagina": pagina,
        "paginas": (total_reg + por_pagina - 1) // por_pagina or 1,
        "estado": estado, "vendedores": vendedores})


def _acceso_pedido(usuario) -> tuple[str, tuple]:
    """Quién puede ver un pedido: el vendedor solo los suyos; el administrativo
    los de su empresa; el super, todos."""
    if usuario["rol"] == "vendedor":
        return " AND p.vendedor_id = ?", (usuario["id"],)
    if usuario["rol"] == "admin":
        return " AND p.empresa_id = ?", (usuario["empresa_id"],)
    return "", ()


@app.get("/pedidos/estados")
def pedidos_estados(request: Request, pagina: int = 1, estado: str = ""):
    """Estados de los pedidos de la página visible (refresco sin recargar)."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return {"items": []}
    por_pagina = 50
    condicion = "1=1"
    valores: list = []
    if usuario["rol"] == "vendedor":
        condicion += " AND p.vendedor_id = ?"
        valores.append(usuario["id"])
    else:
        empresa = empresa_del(usuario, request.query_params.get("empresa") and
                              int(request.query_params["empresa"]))
        if empresa:
            condicion += " AND p.empresa_id = ?"
            valores.append(empresa["id"])
    if estado in ("pendiente", "montado", "error"):
        condicion += " AND p.estado = ?"
        valores.append(estado)
    filas_estado = db.filas(
        f"SELECT p.id, p.estado, p.montado, p.error_a2, p.intentos FROM pedidos p "
        f"WHERE {condicion} ORDER BY p.id DESC LIMIT ? OFFSET ?",
        tuple(valores) + (por_pagina, max(0, pagina - 1) * por_pagina))
    return {"items": [dict(f) for f in filas_estado]}


@app.post("/pedidos/{pedido_id}/borrar")
def pedidos_borrar(request: Request, pedido_id: int):
    """Borra un pedido del panel (no toca A2). Admin: de a uno, de su empresa."""
    usuario = requiere_rol(request, ("admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    condicion, extra = _acceso_pedido(usuario)
    existe = db.fila(f"SELECT p.id FROM pedidos p WHERE p.id = ? {condicion}",
                     (pedido_id,) + extra)
    if existe is None:
        return RedirectResponse("/pedidos", status_code=303)
    db.ejecutar("DELETE FROM pedido_lineas WHERE pedido_id = ?", (pedido_id,))
    db.ejecutar("DELETE FROM pedidos WHERE id = ?", (pedido_id,))
    return RedirectResponse("/pedidos?ok=borrado", status_code=303)


@app.post("/pedidos/borrar-vendedor")
def pedidos_borrar_vendedor(request: Request, vendedor_id: int = Form(...)):
    """Super usuario: borra TODOS los pedidos de un vendedor (solo en el panel)."""
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    empresa = empresa_del(usuario, None)
    if empresa is None:
        return RedirectResponse("/pedidos", status_code=303)
    objetivo = db.fila("SELECT id FROM usuarios WHERE id = ? AND empresa_id = ?",
                       (vendedor_id, empresa["id"]))
    if objetivo is None:
        return RedirectResponse("/pedidos?error=permiso", status_code=303)
    con = db.conectar()
    ids = [r["id"] for r in con.execute(
        "SELECT id FROM pedidos WHERE empresa_id = ? AND vendedor_id = ?",
        (empresa["id"], vendedor_id)).fetchall()]
    for pid in ids:
        con.execute("DELETE FROM pedido_lineas WHERE pedido_id = ?", (pid,))
    con.execute("DELETE FROM pedidos WHERE empresa_id = ? AND vendedor_id = ?",
                (empresa["id"], vendedor_id))
    con.commit()
    return RedirectResponse(f"/pedidos?ok=borrados&n={len(ids)}", status_code=303)


@app.get("/pedidos/{pedido_id}/estado")
def pedido_estado(request: Request, pedido_id: int):
    """Estado de un pedido (para el detalle, sin recargar)."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return {"ok": False}
    condicion, extra = _acceso_pedido(usuario)
    fila_estado = db.fila(
        f"SELECT p.id, p.estado, p.montado, p.error_a2, p.intentos FROM pedidos p "
        f"WHERE p.id = ? {condicion}", (pedido_id,) + extra)
    return {"ok": True, **dict(fila_estado)} if fila_estado else {"ok": False}


@app.get("/pedidos/{pedido_id}/hoja.pdf")
def pedidos_hoja_pdf(request: Request, pedido_id: int):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    condicion, extra = _acceso_pedido(usuario)
    if db.fila(f"SELECT p.id FROM pedidos p WHERE p.id = ? {condicion}",
               (pedido_id,) + extra) is None:
        return RedirectResponse("/pedidos", status_code=303)
    contenido = hoja.hoja_pdf(pedido_id)
    if contenido is None:
        return RedirectResponse(f"/pedidos/{pedido_id}", status_code=303)
    numero = db.fila("SELECT numero FROM pedidos WHERE id = ?", (pedido_id,))["numero"]
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="pedido-{numero}.pdf"'})


@app.get("/pedidos/{pedido_id}/hoja.jpg")
def pedidos_hoja_jpg(request: Request, pedido_id: int):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    condicion, extra = _acceso_pedido(usuario)
    if db.fila(f"SELECT p.id FROM pedidos p WHERE p.id = ? {condicion}",
               (pedido_id,) + extra) is None:
        return RedirectResponse("/pedidos", status_code=303)
    contenido = hoja.hoja_jpg(pedido_id)
    if contenido is None:
        return RedirectResponse(f"/pedidos/{pedido_id}", status_code=303)
    return Response(contenido, media_type="image/jpeg")


@app.post("/pedidos/{pedido_id}/reenviar")
def pedidos_reenviar(request: Request, pedido_id: int):
    """Carga las líneas del pedido en el carrito para modificarlo y enviarlo
    de nuevo (será un pedido nuevo: fecha y numeración nuevas)."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    condicion, extra = _acceso_pedido(usuario)
    pedido_r = db.fila(f"SELECT p.* FROM pedidos p WHERE p.id = ? {condicion}",
                       (pedido_id,) + extra)
    if pedido_r is None:
        return RedirectResponse("/pedidos", status_code=303)
    lineas = db.filas("SELECT codigo, descripcion, cantidad, precio FROM pedido_lineas "
                      "WHERE pedido_id = ? ORDER BY id", (pedido_id,))
    carrito = []
    for l in lineas:
        prod = db.fila("SELECT descripcion, precio FROM productos WHERE empresa_id = ? "
                       "AND codigo = ?", (pedido_r["empresa_id"], l["codigo"]))
        carrito.append({
            "codigo": l["codigo"],
            "descripcion": (prod["descripcion"] if prod and prod["descripcion"]
                            else l["descripcion"]),
            "precio": (prod["precio"] if prod and prod["precio"] is not None
                       else l["precio"]),
            "cantidad": l["cantidad"],
        })
    carrito_guardar(usuario, carrito)
    return RedirectResponse("/pedido", status_code=303)


@app.post("/pedidos/{pedido_id}/reintentar")
def pedidos_reintentar(request: Request, pedido_id: int):
    """Vuelve a poner en cola un pedido que quedó en error (no toca A2)."""
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    condicion, extra = _acceso_pedido(usuario)
    existe = db.fila(f"SELECT p.id FROM pedidos p WHERE p.id = ? {condicion}",
                     (pedido_id,) + extra)
    if existe is None:
        return RedirectResponse("/pedidos", status_code=303)
    db.ejecutar(
        "UPDATE pedidos SET estado = 'pendiente', error_a2 = NULL, "
        "intentos = 0, montado = NULL, a2_autoincrement = NULL "
        "WHERE id = ? AND estado = 'error'", (pedido_id,))
    return RedirectResponse(f"/pedidos/{pedido_id}", status_code=303)


@app.get("/pedidos/{pedido_id}")
def pedidos_ver(request: Request, pedido_id: int):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    condicion, extra = _acceso_pedido(usuario)
    pedido_r = db.fila(
        f"SELECT p.*, u.codigo AS vend_codigo, u.nombre AS vend_nombre FROM pedidos p "
        f"JOIN usuarios u ON u.id = p.vendedor_id WHERE p.id = ? {condicion}",
        (pedido_id,) + extra)
    if pedido_r is None:
        return RedirectResponse("/pedidos", status_code=303)
    lineas = db.filas("SELECT * FROM pedido_lineas WHERE pedido_id = ? ORDER BY id",
                      (pedido_id,))
    return respuesta(request, "pedido_ver.html",
                     {"pedido": pedido_r, "lineas": lineas})