"""Claves hash y sesiones de usuario."""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from app import config, db

_PBKDF2 = 200_000


def hash_clave(clave: str) -> str:
    sal = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), _PBKDF2).hex()
    return f"{sal}${h}"


def verificar_clave(clave: str, guardada: str) -> bool:
    sal, h = guardada.split("$", 1)
    calc = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), _PBKDF2).hex()
    return hmac.compare_digest(calc, h)


# ---------- clave visible (reversible, para que el admin la consulte) ----------

def _llave() -> bytes:
    archivo = config.BD.parent / "clave_cifrado.key"
    if not archivo.is_file():
        archivo.write_bytes(secrets.token_bytes(32))
    return archivo.read_bytes()


def cifrar_clave(clave: str) -> str:
    """Guarda la clave de forma reversible (XOR + base64) para poder verla."""
    llave = _llave()
    datos = clave.encode()
    cifrado = bytes(b ^ llave[i % len(llave)] for i, b in enumerate(datos))
    return base64.b64encode(cifrado).decode()


def descifrar_clave(guardada: str) -> str:
    if not guardada:
        return ""
    try:
        llave = _llave()
        datos = base64.b64decode(guardada.encode())
        return bytes(b ^ llave[i % len(llave)] for i, b in enumerate(datos)).decode()
    except Exception:
        return ""


def crear_sesion(usuario_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expira = (datetime.now() + timedelta(hours=config.SESION_HORAS)).isoformat(timespec="seconds")
    db.ejecutar("INSERT INTO sesiones (token, usuario_id, expira) VALUES (?, ?, ?)",
                (token, usuario_id, expira))
    return token


def usuario_de_sesion(token: str):
    if not token:
        return None
    fila = db.fila("SELECT u.*, s.token AS token, s.carrito AS carrito, "
                   "COALESCE(s.empresa_activa, u.empresa_id) AS empresa_actual "
                   "FROM usuarios u JOIN sesiones s ON s.usuario_id = u.id "
                   "WHERE s.token = ? AND s.expira > datetime('now', 'localtime') "
                   "AND u.activo = 1", (token,))
    return fila


def cerrar_sesion(token: str) -> None:
    db.ejecutar("DELETE FROM sesiones WHERE token = ?", (token,))


def limpiar_sesiones() -> None:
    db.ejecutar("DELETE FROM sesiones WHERE expira <= datetime('now', 'localtime')")