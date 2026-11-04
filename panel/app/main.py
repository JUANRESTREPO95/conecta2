"""Conecta2 — panel web (FastAPI + Jinja2 + SQLite).

Multi-empresa. Roles: super (global), admin (por empresa), vendedor.
El super usuario se crea en el primer arranque, en /primer-vez.
"""
from datetime import datetime

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import a2, config, db, hoja, seguridad

db.esquema()  # garantiza el esquema también cuando uvicorn recarga en modo dev

app = FastAPI(title="Conecta2", docs_url=None, redoc_url=None)


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


def colores_para(usuario) -> dict:
    defecto = {"color_primario": "#1e40af", "color_secundario": "#0f172a",
               "color_letra": "#ffffff", "nombre_negocio": "Conecta2", "logo": None}
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
    return {"color_primario": empresa["color_primario"],
            "color_secundario": empresa["color_secundario"],
            "color_letra": empresa["color_letra"] or "#ffffff",
            "nombre_negocio": empresa["nombre"], "logo": empresa["logo"]}


def fija_empresa_activa(usuario, empresa_id: int) -> None:
    """El super navega empresas: su sesión recuerda cuál es la actual."""
    if usuario["rol"] == "super" and empresa_id:
        db.ejecutar("UPDATE sesiones SET empresa_activa = ? WHERE token = ?",
                    (empresa_id, usuario["token"]))


def datos_carrito(usuario) -> dict:
    """Artículos y monto del carrito de la sesión (para el indicador flotante)."""
    if usuario is None or not usuario["carrito"]:
        return {"carrito_n": 0, "carrito_monto": 0.0, "carrito_items": 0}
    try:
        carrito = json.loads(usuario["carrito"] or "[]")
    except Exception:
        carrito = []
    monto = sum(i["cantidad"] * (i["precio"] or 0) for i in carrito)
    return {"carrito_n": sum(int(i["cantidad"]) for i in carrito),
            "carrito_monto": monto, "carrito_items": len(carrito)}


def respuesta(request: Request, plantilla: str, contexto: dict):
    usuario = usuario_actual(request)
    ctx = {"usuario": usuario, **colores_para(usuario), **datos_carrito(usuario), **contexto}
    return plantillas.TemplateResponse(request, plantilla, ctx)


def protege(request: Request):
    """Devuelve el usuario o lanza una redirección al login."""
    usuario = usuario_actual(request)
    if usuario is None:
        raise Redirige
    return usuario


class Redirige(Exception):
    pass


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


_SQL_PRODUCTO = (
    "INSERT INTO productos (empresa_id, codigo, codigo_a2, descripcion, marca, "
    "categoria, unidad, moneda, activo, internet, actualizado) "
    "VALUES (:e, :codigo, :codigo_a2, :descripcion, :marca, :categoria, "
    ":unidad, :moneda, :activo, :internet, datetime('now','localtime')) "
    "ON CONFLICT(empresa_id, codigo) DO UPDATE SET codigo_a2=excluded.codigo_a2, "
    "descripcion=excluded.descripcion, marca=excluded.marca, "
    "categoria=excluded.categoria, unidad=excluded.unidad, moneda=excluded.moneda, "
    "activo=excluded.activo, internet=excluded.internet, "
    "actualizado=excluded.actualizado")


async def cuerpo_json(request: Request) -> list:
    """Devuelve la lista del cuerpo: acepta [..] o {"lote": [..]}."""
    try:
        datos = await request.json()
    except Exception:
        return []
    if isinstance(datos, dict):
        return datos.get("lote") or []
    return datos if isinstance(datos, list) else []


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
    con = db.conectar()
    for p in lote:
        codigo = str(p.get("codigo") or "")     # tal cual, sin recortar
        if not codigo.strip():
            continue
        con.execute(_SQL_PRODUCTO, {
            "e": usuario["empresa_id"], "codigo": codigo,
            "codigo_a2": str(p.get("codigo_a2") or p.get("codigo") or ""),
            "descripcion": p.get("descripcion"), "marca": p.get("marca"),
            "categoria": p.get("categoria"), "unidad": p.get("unidad"),
            "moneda": p.get("moneda") or 1,
            "activo": 1 if p.get("activo") else 0,
            "internet": 1 if p.get("internet") else 0})
    con.commit()
    return {"ok": True, "guardados": len(lote)}


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
    con = db.conectar()
    for f in lote:
        con.execute(
            "INSERT INTO stock (empresa_id, codigo_producto, deposito, "
            "existencia, actualizado) VALUES (?, ?, ?, ?, datetime('now','localtime')) "
            "ON CONFLICT(empresa_id, codigo_producto, deposito) DO UPDATE SET "
            "existencia=excluded.existencia, actualizado=excluded.actualizado",
            (usuario["empresa_id"], str(f["codigo"]), int(f["deposito"]),
             float(f["existencia"] or 0)))
    con.commit()
    return {"ok": True, "guardados": len(lote)}


@app.post("/api/precios")
async def api_precios(request: Request, origen: str = "venta"):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    lote = await cuerpo_json(request)
    con = db.conectar()
    for f in lote:
        codigo = str(f["codigo"])
        if origen == "catalogo":
            # el precio de la lista de A2 manda
            sql = ("UPDATE productos SET precio = ?, "
                   "actualizado = datetime('now','localtime') "
                   "WHERE empresa_id = ? AND (codigo = ? OR codigo_a2 = ?)")
            valores = (float(f["precio"]), usuario["empresa_id"], codigo, codigo)
        else:
            # la última venta solo rellena productos sin precio de lista
            sql = ("UPDATE productos SET precio = ?, "
                   "actualizado = datetime('now','localtime') "
                   "WHERE empresa_id = ? AND (codigo = ? OR codigo_a2 = ?) "
                   "AND (precio IS NULL OR precio <= 0)")
            valores = (float(f["precio"]), usuario["empresa_id"], codigo, codigo)
        con.execute(sql, valores)
    con.commit()
    return {"ok": True, "precios": len(lote)}


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
    con = db.conectar()
    for c in lote:
        codigo = str(c.get("codigo") or "").strip()
        if not codigo:
            continue
        con.execute(
            "INSERT INTO clientes (empresa_id, codigo, nombre, nit, actualizado) "
            "VALUES (?, ?, ?, ?, datetime('now','localtime')) "
            "ON CONFLICT(empresa_id, codigo) DO UPDATE SET "
            "nombre=excluded.nombre, nit=excluded.nit, "
            "actualizado=excluded.actualizado",
            (usuario["empresa_id"], codigo, c.get("nombre"), c.get("nit")))
    con.commit()
    return {"ok": True, "guardados": len(lote)}


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
    con = db.conectar()
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
            (usuario["empresa_id"], codigo, v.get("nombre"),
             1 if v.get("activo") else 0, v.get("clave_a2")))
    con.commit()
    return {"ok": True, "guardados": len(lote)}


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
        "SELECT codigo, nombre, nit FROM clientes WHERE empresa_id = ? "
        "AND (UPPER(nombre) LIKE ? OR UPPER(codigo) LIKE ? OR nit LIKE ?) "
        "ORDER BY nombre LIMIT ?",
        (empresa["id"], patron, patron, patron, limite))
    return {"items": [dict(f) for f in filas_cli]}


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


@app.get("/api/pedidos/pendientes")
def api_pendientes(request: Request):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    lista = db.filas(
        "SELECT p.id, p.numero, p.referencia, p.cliente_nit, p.cliente_nombre, "
        "u.codigo AS vendedor, u.nombre AS vendedor_nombre FROM pedidos p "
        "JOIN usuarios u ON u.id = p.vendedor_id "
        "WHERE p.empresa_id = ? AND p.estado = 'pendiente' ORDER BY p.id",
        (usuario["empresa_id"],))
    de_vuelta = []
    for p in lista:
        lineas = db.filas(
            "SELECT l.codigo, COALESCE(pr.codigo_a2, l.codigo) AS codigo_a2, "
            "l.cantidad, l.precio FROM pedido_lineas l "
            "LEFT JOIN productos pr ON pr.empresa_id = (SELECT empresa_id FROM "
            "pedidos WHERE id = l.pedido_id) AND pr.codigo = l.codigo "
            "WHERE l.pedido_id = ? ORDER BY l.id", (p["id"],))
        de_vuelta.append({k: p[k] for k in p.keys()} |
                         {"lineas": [dict(l) for l in lineas]})
    return {"pedidos": de_vuelta}


@app.post("/api/pedidos/montado")
def api_montado(request: Request, id: int, a2_autoincrement: int,
                numero_a2: str = ""):
    usuario = usuario_agente(request)
    if usuario is None:
        return Response('{"error": "token inválido"}', status_code=401,
                        media_type="application/json")
    db.ejecutar("UPDATE pedidos SET estado = 'montado', montado = "
                "datetime('now','localtime'), a2_autoincrement = ? WHERE id = ?",
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


# ---------- empresas (solo super) ----------

def requiere_rol(request: Request, roles):
    usuario = usuario_actual(request)
    if usuario is None:
        raise Redirige
    if usuario["rol"] not in roles:
        return None
    return usuario


@app.get("/empresas")
def empresas(request: Request):
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/inicio", status_code=303)
    lista = db.filas("SELECT e.*, (SELECT COUNT(*) FROM usuarios u WHERE "
                     "u.empresa_id = e.id AND u.rol = 'vendedor') AS vendedores "
                     "FROM empresas e ORDER BY e.id")
    sincs = {s["empresa_id"]: s["hecho"] for s in db.filas(
        "SELECT empresa_id, MAX(hecho) AS hecho FROM sincronizaciones GROUP BY empresa_id")}
    tokens = {a["empresa_id"]: seguridad.descifrar_clave(a["clave_visible"])
              for a in db.filas("SELECT empresa_id, clave_visible FROM usuarios "
                                "WHERE rol = 'agente'")}
    return respuesta(request, "empresas.html",
                     {"lista": lista, "sincs": sincs, "tokens": tokens})


@app.post("/empresas/token")
def empresas_token(request: Request, empresa_id: int = Form(...)):
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
    return RedirectResponse("/empresas?ok=token", status_code=303)


@app.post("/empresas/crear")
def empresas_crear(request: Request, nombre: str = Form(...)):
    usuario = requiere_rol(request, ("super",))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    if nombre.strip():
        db.ejecutar("INSERT INTO empresas (nombre) VALUES (?)", (nombre.strip(),))
    return RedirectResponse("/empresas", status_code=303)


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
    return respuesta(request, "configuracion.html", {"e": empresa})


def guardar_logo(empresa_id: int, archivo: UploadFile | None) -> str:
    """Guarda la imagen subida y devuelve su ruta web /logos/... (o vacío)."""
    import os
    import uuid

    if archivo is None or not archivo.filename:
        return ""
    if (archivo.content_type or "") not in ("image/png", "image/jpeg", "image/webp",
                                            "image/gif"):
        return ""
    datos = archivo.file.read(5 * 1024 * 1024)
    if len(datos) < 10:
        return ""
    ext = os.path.splitext(archivo.filename)[1].lower() or ".png"
    nombre = f"empresa-{empresa_id}-{uuid.uuid4().hex[:8]}{ext}"
    (config.LOGOS / nombre).write_bytes(datos)
    return f"/logos/{nombre}"


@app.post("/configuracion")
def configuracion_post(request: Request, empresa_id: int = Form(...),
                       nombre: str = Form(""), deposito: str = Form("1"),
                       color_primario: str = Form("#1e40af"),
                       color_letra: str = Form("#ffffff"),
                       logo_file: UploadFile = File(None),
                       quitar_logo: str = Form(""),
                       filtro: str = Form("todo"),
                       minimo: int = Form(0),
                       usar_clientes: str = Form(""),
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
    subido = guardar_logo(empresa_id, logo_file)
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
    db.ejecutar("UPDATE empresas SET nombre = ?, deposito_modo = ?, "
                "ocultar_agotados = ?, color_primario = ?, color_secundario = ?, "
                "color_letra = ?, logo = ?, filtro_existencia = ?, "
                "existencia_minima = ?, usar_clientes = ?, formato_numero = ?, "
                "reinicio_numero = ?, digitos_numero = ? WHERE id = ?",
                (nombre.strip() or "-", deposito, 1 if filtro != "todo" else 0,
                 color_primario, color_primario, color_letra, logo,
                 filtro, max(0, minimo), 1 if usar_clientes else 0,
                 formato_numero.strip(), reinicio_numero, digitos_numero,
                 empresa_id))
    fija_empresa_activa(usuario, empresa_id)  # conserva el contexto tras guardar
    return RedirectResponse(f"/configuracion?ok=1&empresa={empresa_id}", status_code=303)


# ---------- catálogo ----------

def condicion_catalogo(empresa, q: str):
    """Condiciones SQL comunes del catálogo (internet + activo + búsqueda)."""
    patron_p = f"{q.strip().upper()}%"       # código: por el comienzo
    patron_d = f"%{q.strip().upper()}%"      # descripción/marca: contiene
    condicion = "p.empresa_id = ? AND p.internet = 1 AND p.activo = 1"
    valores: list = [empresa["id"]]
    if q.strip():
        condicion += (" AND (UPPER(TRIM(p.codigo)) LIKE ? "
                      "OR UPPER(p.descripcion) LIKE ?)")
        valores += [patron_p, patron_d]
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
    return condicion, valores


def productos_de(empresa, condicion: str, valores: list, limite: int, desplaz: int = 0):
    filas_p = db.filas(
        f"SELECT p.codigo, p.descripcion, p.marca, p.precio, "
        f"(SELECT s.existencia FROM stock s WHERE s.empresa_id = p.empresa_id "
        f"  AND s.codigo_producto = p.codigo AND s.deposito = 1) AS dep1, "
        f"(SELECT s.existencia FROM stock s WHERE s.empresa_id = p.empresa_id "
        f"  AND s.codigo_producto = p.codigo AND s.deposito = 2) AS dep2 "
        f"FROM productos p WHERE {condicion} "
        f"ORDER BY p.descripcion LIMIT ? OFFSET ?",
        tuple(valores) + (limite, desplaz))

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
    condicion, valores = condicion_catalogo(empresa, q)
    total = db.fila(f"SELECT COUNT(*) AS c FROM productos p WHERE {condicion}", tuple(valores))["c"]
    items = productos_de(empresa, condicion, valores,
                         por_pagina, max(0, pagina - 1) * por_pagina)
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
    condicion, valores = condicion_catalogo(empresa, q)
    total = db.fila(f"SELECT COUNT(*) AS c FROM productos p WHERE {condicion}", tuple(valores))["c"]
    items = productos_de(empresa, condicion, valores, limite)
    return {"total": total, "items": items}


# ---------- pedidos ----------

import json


def carrito_obtener(usuario) -> list:
    if not usuario["carrito"]:
        return []
    return json.loads(usuario["carrito"])


def carrito_guardar(usuario, carrito: list) -> None:
    db.ejecutar("UPDATE sesiones SET carrito = ? WHERE token = ?",
                (json.dumps(carrito, ensure_ascii=False), usuario["token"]))


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
    carrito = carrito_obtener(usuario)
    for item in carrito:
        if item["codigo"] == producto["codigo"]:
            item["cantidad"] += cantidad
            break
    else:
        carrito.append({"codigo": producto["codigo"], "descripcion": producto["descripcion"],
                        "precio": producto["precio"], "cantidad": cantidad})
    carrito_guardar(usuario, carrito)
    if request.headers.get("x-requested-with") == "fetch":
        # releer para devolver el acumulado fresco (la fila estaba en memoria)
        ses_fresca = db.fila("SELECT carrito FROM sesiones WHERE token = ?",
                             (usuario["token"],))
        d = datos_carrito(ses_fresca)
        return {"ok": True, **d}
    return RedirectResponse("/pedido", status_code=303)


@app.post("/pedido/cantidad")
def pedido_cantidad(request: Request, codigo: str = Form(...), cantidad: float = Form(1)):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    carrito = carrito_obtener(usuario)
    cantidad = int(cantidad or 0)
    nuevo = [i for i in carrito if i["codigo"] != codigo]
    if cantidad > 0:
        for item in nuevo:
            if item["codigo"] == codigo:
                item["cantidad"] = cantidad
        if not any(i["codigo"] == codigo for i in nuevo):
            viejo = next(i for i in carrito if i["codigo"] == codigo)
            nuevo.append({**viejo, "cantidad": cantidad})
    carrito_guardar(usuario, nuevo)
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
                  cliente_nit: str = Form("")):
    usuario = requiere_rol(request, ("vendedor", "admin", "super"))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    carrito = carrito_obtener(usuario)
    if not carrito:
        return RedirectResponse("/pedido?vacio=1", status_code=303)
    empresa = empresa_del(usuario, None)
    # re-lee los precios de la BD (no confía en lo que vino del navegador)
    for item in carrito:
        p = db.fila("SELECT precio, descripcion FROM productos "
                    "WHERE empresa_id = ? AND codigo = ?",
                    (empresa["id"], item["codigo"]))
        if p is not None:
            item["precio"] = p["precio"]
            item["descripcion"] = p["descripcion"]
    numero = numero_siguiente(empresa["id"], usuario, empresa)
    total = sum(i["cantidad"] * (i["precio"] or 0) for i in carrito)
    if not empresa["usar_clientes"]:
        cliente_codigo, cliente_nombre, cliente_nit = "", "", ""
    cliente_nit = cliente_nit.strip() or "2222222222"
    if not cliente_nombre.strip():
        cliente_nombre = "CONSUMIDOR FINAL" if cliente_nit == "2222222222" else ""
    cur = db.ejecutar(
        "INSERT INTO pedidos (empresa_id, vendedor_id, numero, referencia, estado, "
        "total, cliente_codigo, cliente_nombre, cliente_nit) "
        "VALUES (?, ?, ?, ?, 'pendiente', ?, ?, ?, ?)",
        (empresa["id"], usuario["id"], numero, referencia.strip(), total,
         cliente_codigo.strip() or None, cliente_nombre.strip() or None,
         cliente_nit))
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
        f"SELECT p.id, p.estado, p.montado, p.error_a2 FROM pedidos p "
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
        f"SELECT p.id, p.estado, p.montado, p.error_a2 FROM pedidos p "
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