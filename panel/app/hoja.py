"""Hoja del pedido en PDF y JPG.

Campos: Pedido, Fecha, Vendedor, Referencia y Monto (sin IVA).
Se dibuja como una tabla con bordes, con una fila por campo.
"""
import io
import os
from datetime import date

from PIL import Image, ImageDraw, ImageFont

from app.db import fila


# ------- helpers -------

def _num(v) -> str:
    return f"{int(round(float(v))):,}".replace(",", ".")


def _l1(s) -> str:
    """Texto seguro para las fuentes básicas del PDF (latin-1)."""
    if s is None:
        return ""
    return str(s).replace("—", "-").replace("–", "-") \
        .encode("latin-1", "replace").decode("latin-1")


def _cliente_texto(pedido: dict) -> str:
    nombre = (pedido.get("cliente_nombre") or "CONSUMIDOR FINAL").strip()
    nit = (pedido.get("cliente_nit") or "").strip()
    return f"{nombre} - NIT {nit}" if nit else nombre


def _autorizado_texto(pedido: dict) -> str:
    """Nombre y dirección del autorizado (solo para la hoja; no va a A2)."""
    nombre = (pedido.get("autorizado_nombre") or "").strip()
    direccion = (pedido.get("autorizado_direccion") or "").strip()
    if nombre and direccion:
        return f"{nombre} - {direccion}"
    return nombre or direccion


def _fecha(creado: str) -> str:
    if not creado:
        return date.today().isoformat()
    return str(creado)[:10]


def _logo_bytes(empresa: dict, alto_px: int = 80):
    """Devuelve bytes PNG/JPG del logo subido (ruta /logos/...) o local."""
    ruta = (empresa["logo"] or "").strip()
    if not ruta:
        return None
    if ruta.startswith("/logos/"):
        from app import config
        local = config.LOGOS / ruta[len("/logos/"):]
        if local.is_file():
            # en Linux/Docker esta ruta empieza por "/" (no es una URL)
            ruta = str(local)
        else:
            return None
    if ruta.startswith("http"):
        return None
    if os.path.isfile(ruta):
        with open(ruta, "rb") as fh:
            data = fh.read()
        try:
            img = Image.open(io.BytesIO(data))
            ancho = int(img.width * alto_px / img.height)
            img = img.convert("RGBA").resize((ancho, alto_px))
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return buf.getvalue()
        except Exception:
            return None
    return None


def datos_de(pedido_id: int):
    pedido = fila("SELECT p.*, u.codigo AS vend_codigo, u.nombre AS vend_nombre, "
                  "e.nombre AS empresa_nombre FROM pedidos p JOIN usuarios u "
                  "ON u.id = p.vendedor_id JOIN empresas e ON e.id = p.empresa_id "
                  "WHERE p.id = ?", (pedido_id,))
    if pedido is None:
        return None, None
    empresa = fila("SELECT * FROM empresas WHERE id = ?", (pedido["empresa_id"],))
    return dict(pedido), dict(empresa) if empresa else None


def _rgb(hexcolor: str) -> tuple[int, int, int]:
    hexcolor = hexcolor.lstrip("#")
    return tuple(int(hexcolor[i:i + 2], 16) for i in (0, 2, 4))


# ------- PDF -------

def hoja_pdf(pedido_id: int) -> bytes | None:
    from fpdf import FPDF

    pedido, empresa = datos_de(pedido_id)
    if pedido is None:
        return None
    primario = (empresa or {}).get("color_primario") or "#1e40af"

    pdf = FPDF(orientation="L", format="A4")
    pdf.add_page()

    # ---- encabezado ----
    pdf.set_font("helvetica", "B", 20)
    pdf.set_text_color(*_rgb(primario))
    logo = _logo_bytes(empresa or {})
    nombre = (empresa or {}).get("nombre") or pedido["empresa_nombre"]
    if logo:
        pdf.image(io.BytesIO(logo), x=12, y=12, h=16)
        pdf.set_xy(34, 13)
    else:
        pdf.set_xy(12, 13)
    pdf.cell(0, 9, _l1(nombre), new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(12, pdf.get_y() + 2)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 7, _l1("Hoja de pedido"), new_x="LMARGIN", new_y="NEXT")

    # ---- tabla con bordes ----
    X0 = 12.0
    X_FIN = 285.0
    ANCHO_ETIQUETA = 42.0
    X_VALOR = X0 + ANCHO_ETIQUETA
    BORDE = (60, 60, 60)

    referencia = _l1(pedido["referencia"] or "-")
    pdf.set_font("helvetica", "", 12)
    # líneas que ocupará la referencia dentro de su celda
    ancho_texto = X_FIN - X_VALOR - 4
    pdf.set_font("helvetica", "", 12)
    lineas_ref = pdf.multi_cell(ancho_texto, 6, referencia, split_only=True)
    alto_ref = max(16.0, 4 + 6 * len(lineas_ref))

    filas = [
        ("PEDIDO", _l1(pedido["numero"]), 11.0, "", 14),
        ("FECHA", _l1(_fecha(pedido["creado"])), 11.0, "", 14),
        ("VENDEDOR", _l1(f"{pedido['vend_codigo']} - {pedido['vend_nombre']}"),
         11.0, "", 14),
    ]
    if (empresa or {}).get("usar_clientes"):
        cliente_txt = _cliente_texto(pedido)
        filas.append(("CLIENTE", _l1(cliente_txt), 11.0, "", 13))
    if (empresa or {}).get("usar_autorizados"):
        aut_txt = _l1(_autorizado_texto(pedido))
        lineas_aut = (pdf.multi_cell(ancho_texto, 6, aut_txt, split_only=True)
                      if aut_txt else [])
        alto_aut = max(13.0, 4 + 6 * len(lineas_aut))
        filas.append(("AUTORIZADO", aut_txt, alto_aut, "", 11))
    filas += [
        ("REFERENCIA", referencia, alto_ref, "", 12),
        ("MONTO", _l1(_num(pedido["total"])), 13.0, "", 15),
    ]

    y = pdf.get_y() + 6
    pdf.set_draw_color(*BORDE)
    pdf.set_line_width(0.35)
    for etiqueta, valor, alto, estilo, tamano in filas:
        # marco de la fila y separación etiqueta | valor
        pdf.rect(X0, y, X_FIN - X0, alto)
        pdf.line(X_VALOR, y, X_VALOR, y + alto)
        # etiqueta (en negrita)
        pdf.set_font("helvetica", "B", 9)
        pdf.set_text_color(85, 85, 85)
        pdf.set_xy(X0 + 2.5, y + 2.5)
        pdf.cell(ANCHO_ETIQUETA - 5, 6, _l1(etiqueta))
        # valor
        pdf.set_font("helvetica", estilo, tamano)
        pdf.set_text_color(25, 25, 25)
        if etiqueta in ("REFERENCIA", "AUTORIZADO"):
            if valor:
                pdf.set_xy(X_VALOR + 2.5, y + 2)
                pdf.set_font("helvetica", "", 12 if etiqueta == "REFERENCIA" else 11)
                pdf.multi_cell(ancho_texto, 6, valor)
        else:
            pdf.set_xy(X_VALOR + 2.5, y + alto / 2 - 4)
            pdf.cell(X_FIN - X_VALOR - 4, 8, valor)
        y += alto

    return bytes(pdf.output())


# ------- JPG -------

def _fuente(size: int, negrita: bool = False):
    for nombre in (_NEGRITAS if negrita else _NORMALES):
        try:
            return ImageFont.truetype(nombre, size)
        except OSError:
            continue
    return ImageFont.load_default()


_NORMALES, _NEGRITAS = ["arial.ttf"], ["arialbd.ttf", "Arial Bold.ttf"]


_MEDIDOR = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def _trozado(texto: str, ancho_px: float, fuente) -> list[str]:
    """Parte un texto en líneas que quepan en el ancho real (píxeles)."""
    trozos, actual = [], ""
    for palabra in (texto or "").split():
        prueba = (actual + " " + palabra).strip()
        if _MEDIDOR.textlength(prueba, font=fuente) > ancho_px and actual:
            trozos.append(actual)
            actual = palabra
        else:
            actual = prueba
    if actual:
        trozos.append(actual)
    return trozos[:12]


def hoja_jpg(pedido_id: int) -> bytes | None:
    pedido, empresa = datos_de(pedido_id)
    if pedido is None:
        return None
    primario = (empresa or {}).get("color_primario") or "#1e40af"

    ref = (pedido["referencia"] or "-").strip() or "-"
    vendedor = f"{pedido['vend_codigo']} — {pedido['vend_nombre']}"
    if len(vendedor) > 46:
        vendedor = vendedor[:43] + "..."

    ANCHO = 1000
    PX = 40
    X0, X_FIN = PX, ANCHO - PX
    ANCHO_ETIQ = 205
    X_VALOR = X0 + ANCHO_ETIQ
    ANCHO_TEXTO = X_FIN - X_VALOR - 28
    fuente_ref = _fuente(26)
    lineas_ref = _trozado(ref, ANCHO_TEXTO, fuente_ref)
    BORDE = (55, 55, 55)

    alto_ref = max(96, 26 + 34 * len(lineas_ref))
    filas = [
        ("PEDIDO", pedido["numero"], 56, False, 30),
        ("FECHA", _fecha(pedido["creado"]), 56, False, 30),
        ("VENDEDOR", vendedor, 56, False, 30),
    ]
    if (empresa or {}).get("usar_clientes"):
        fuente_cli = _fuente(26, True)
        lineas_cli = _trozado(_cliente_texto(pedido), ANCHO_TEXTO, fuente_cli)
        alto_cli = max(56, 22 + 32 * len(lineas_cli))
        filas.append(("CLIENTE", lineas_cli, alto_cli, False, 26))
    if (empresa or {}).get("usar_autorizados"):
        lineas_aut = _trozado(_autorizado_texto(pedido), ANCHO_TEXTO,
                              _fuente(26))
        alto_aut = max(56, 22 + 32 * len(lineas_aut))
        filas.append(("AUTORIZADO", lineas_aut, alto_aut, False, 26))
    filas += [
        ("REFERENCIA", lineas_ref, alto_ref, False, 26),
        ("MONTO", _num(pedido["total"]), 64, False, 32),
    ]
    alto_tabla = sum(f[2] for f in filas)
    alto_total = int(180 + alto_tabla + 40)

    img = Image.new("RGB", (ANCHO, alto_total), "white")
    d = ImageDraw.Draw(img)

    # ---- encabezado ----
    x, y = X0, PX
    logo = _logo_bytes(empresa or {}, alto_px=76)
    nombre = (empresa or {}).get("nombre") or pedido["empresa_nombre"]
    if logo:
        lg = Image.open(io.BytesIO(logo))
        img.paste(lg, (x, y), lg)
        centro = y + lg.height // 2
        d.text((x + lg.width + 14, centro - 26), nombre,
               font=_fuente(40, True), fill=_rgb(primario))
        y = max(y + 62, y + lg.height + 8)
    else:
        d.text((x, y), nombre, font=_fuente(40, True), fill=_rgb(primario))
        y += 62
    d.text((x, y), "Hoja de pedido", font=_fuente(22), fill=(90, 90, 90))
    y += 34
    d.line((X0, y, X_FIN, y), fill=_rgb(primario), width=3)
    y += 18

    # ---- tabla con bordes ----
    for etiqueta, valor, alto, negrita, tamano in filas:
        d.rectangle((X0, y, X_FIN, y + alto), outline=BORDE, width=2)
        d.line((X_VALOR, y, X_VALOR, y + alto), fill=BORDE, width=2)
        d.text((X0 + 14, y + 12), etiqueta, font=_fuente(18, True), fill=(70, 70, 70))
        if etiqueta in ("CLIENTE", "AUTORIZADO"):
            fy = y + 14
            f_cli = _fuente(26)
            for linea in valor:
                d.text((X_VALOR + 14, fy), linea, font=f_cli, fill=(25, 25, 25))
                fy += 32
        elif etiqueta == "REFERENCIA":
            fy = y + 14
            for linea in valor:
                d.text((X_VALOR + 14, fy), linea, font=fuente_ref, fill=(25, 25, 25))
                fy += 34
        else:
            f = _fuente(tamano, negrita)
            caja = d.textbbox((0, 0), valor, font=f)
            alto_texto = caja[3] - caja[1]
            d.text((X_VALOR + 14, y + (alto - alto_texto) / 2 - caja[1]),
                   valor, font=f, fill=(25, 25, 25))
        y += alto

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()
