"""Hoja del pedido en PDF y JPG.

5 campos decididos: Pedido, Fecha, Referencia, Vendedor, Monto (sin IVA).
Se dibuja dos veces: con fpdf2 (PDF) y con Pillow (JPG) respetando la
misma disposición.
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
            ruta = str(local)
    if ruta.startswith("/") or ruta.startswith("http"):
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


# ------- PDF -------

def hoja_pdf(pedido_id: int) -> bytes | None:
    from fpdf import FPDF

    pedido, empresa = datos_de(pedido_id)
    if pedido is None:
        return None
    primario = (empresa or {}).get("color_primario") or "#1e40af"

    pdf = FPDF(orientation="L", format="A4")  # horizontal, igual que la hoja JPG
    pdf.add_page()
    ancho_util = 273  # 297 - 2x12 de margen

    pdf.set_font("helvetica", "B", 22)
    pdf.set_text_color(*_rgb(primario))
    logo = _logo_bytes(empresa or {})
    nombre = (empresa or {}).get("nombre") or pedido["empresa_nombre"]
    if logo:
        tmp = io.BytesIO(logo)
        pdf.image(tmp, x=12, y=12, h=18)
        pdf.set_xy(36, 14)
    else:
        pdf.set_xy(12, 14)
    pdf.cell(0, 10, _l1(nombre), new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(12, pdf.get_y() + 4)
    pdf.set_font("helvetica", "", 13)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, _l1("Hoja de pedido"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*_rgb(primario))
    pdf.set_line_width(0.6)
    pdf.line(12, pdf.get_y() + 2, 285, pdf.get_y() + 2)
    pdf.ln(9)

    MARGEN = 12
    mitad = 136  # mm: mitad de la hoja horizontal menos margen

    def titulo(t: str, ancho: float):
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(110, 110, 110)
        pdf.cell(ancho, 6, _l1(t))

    def valor(v: str, ancho: float, alto: float = 12):
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(ancho, alto, _l1(v))

    # fila 1: PEDIDO (izquierda) | FECHA (derecha), valor debajo de cada título
    y0 = pdf.get_y()
    titulo("PEDIDO", mitad)
    pdf.set_xy(MARGEN + mitad, y0)
    titulo("FECHA", mitad)
    pdf.set_xy(MARGEN, y0 + 6)
    valor(pedido["numero"], mitad)
    pdf.set_xy(MARGEN + mitad, y0 + 6)
    valor(_fecha(pedido["creado"]), mitad)
    pdf.set_y(y0 + 20)

    # VENDEDOR a todo lo ancho, valor debajo
    pdf.cell(ancho_util, 6, _l1("VENDEDOR"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(ancho_util, 9, _l1(f"{pedido['vend_codigo']} - {pedido['vend_nombre']}"),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # REFERENCIA: título por fuera y texto quebrado por palabras
    pdf.cell(ancho_util, 6, _l1("REFERENCIA"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(ancho_util, 7, _l1(pedido["referencia"] or "-"),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # MONTO
    pdf.cell(ancho_util, 6, _l1("MONTO (SIN IVA)"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(ancho_util, 12, _l1(_num(pedido["total"])), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _rgb(hexcolor: str) -> tuple[int, int, int]:
    hexcolor = hexcolor.lstrip("#")
    return tuple(int(hexcolor[i:i + 2], 16) for i in (0, 2, 4))


# ------- JPG -------

def _fuente(size: int, negrita: bool = False):
    for nombre in (_NEGRITAS if negrita else _NORMALES):
        try:
            return ImageFont.truetype(nombre, size)
        except OSError:
            continue
    return ImageFont.load_default()


_NORMALES, _NEGRITAS = ["arial.ttf"], ["arialbd.ttf", "Arial Bold.ttf"]


def _trozado(texto: str, ancho: int) -> list[str]:
    """Parte un texto en líneas del ancho indicado (por palabras, sin cortar)."""
    trozos, actual = [], ""
    for palabra in (texto or "").split():
        prueba = (actual + " " + palabra).strip()
        if len(prueba) > ancho:
            trozos.append(actual)
            actual = palabra
        else:
            actual = prueba
    if actual:
        trozos.append(actual)
    return trozos[:4]


def hoja_jpg(pedido_id: int) -> bytes | None:
    pedido, empresa = datos_de(pedido_id)
    if pedido is None:
        return None
    primario = (empresa or {}).get("color_primario") or "#1e40af"

    ref = (pedido["referencia"] or "-").strip() or "-"
    lineas_ref = _trozado(ref, 60)
    vendedor = f"{pedido['vend_codigo']} — {pedido['vend_nombre']}"
    if len(vendedor) > 50:
        vendedor = vendedor[:47] + "..."

    alto_total = 620 + max(0, len(lineas_ref) - 1) * 36
    img = Image.new("RGB", (1000, alto_total), "white")
    d = ImageDraw.Draw(img)
    px = 40
    x, y = px, px

    logo = _logo_bytes(empresa or {}, alto_px=76)
    nombre = (empresa or {}).get("nombre") or pedido["empresa_nombre"]
    if logo:
        lg = Image.open(io.BytesIO(logo))
        img.paste(lg, (x, y), lg)
        # centrar el nombre verticalmente respecto del logo
        centro = y + lg.height // 2
        d.text((x + lg.width + 14, centro - 26), nombre,
               font=_fuente(40, True), fill=_rgb(primario))
        y = max(y + 62, y + lg.height + 8)
    else:
        d.text((x, y), nombre, font=_fuente(40, True), fill=_rgb(primario))
        y += 62
    d.text((x, y), "Hoja de pedido", font=_fuente(22), fill=(90, 90, 90))
    y += 40
    d.line((x, y, 1000 - px, y), fill=_rgb(primario), width=3)
    y += 26

    def campo(titulo: str, valor: str, dy_valor: int):
        nonlocal y
        d.text((x, y), titulo, font=_fuente(18), fill=(130, 130, 130))
        d.text((x, y + dy_valor), valor, font=_fuente(30, True), fill=(25, 25, 25))
        y += dy_valor + 46

    mitad = 460
    campo("PEDIDO", pedido["numero"], 40)
    d.text((x + mitad, y - 86), "FECHA", font=_fuente(18), fill=(130, 130, 130))
    d.text((x + mitad, y - 46), _fecha(pedido["creado"]), font=_fuente(30, True), fill=(25, 25, 25))
    campo("VENDEDOR", vendedor, 40)
    d.text((x, y), "REFERENCIA", font=_fuente(18), fill=(130, 130, 130))
    y += 30
    if len(lineas_ref) == 1:
        d.text((x, y), lineas_ref[0], font=_fuente(26, True), fill=(25, 25, 25))
        y += 44
    else:
        for linea in lineas_ref:
            d.text((x, y), linea, font=_fuente(24), fill=(25, 25, 25))
            y += 34
        y += 6
    d.line((x, y, 1000 - px, y), fill=(230, 230, 230), width=2)
    y += 20
    campo("MONTO (SIN IVA)", _num(pedido["total"]), 44)
    y += 30

    # imagen a la altura exacta del contenido (sin vacía abajo)
    img = img.crop((0, 0, 1000, min(alto_total, max(y, 620))))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()