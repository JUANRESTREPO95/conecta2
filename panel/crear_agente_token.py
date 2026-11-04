"""Crea (o renueva) el token del agente para una empresa. Lo muestra UNA vez.

Uso: python crear_agente_token.py --empresa 1
El agente usa ese token en el encabezado: Authorization: Bearer <token>
"""
import argparse
import hashlib
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa", type=int, required=True)
    parser.add_argument("--renovar", action="store_true",
                        help="genera un token nuevo y anula el anterior")
    args = parser.parse_args()
    db.esquema()
    empresa = db.fila("SELECT id, nombre FROM empresas WHERE id = ?", (args.empresa,))
    if empresa is None:
        print(f"ERROR: no existe la empresa {args.empresa}")
        return
    agente = db.fila("SELECT id FROM usuarios WHERE empresa_id = ? AND rol = 'agente'",
                     (args.empresa,))
    token = secrets.token_urlsafe(32)
    huella = "tok$" + hashlib.sha256(token.encode()).hexdigest()
    from app import seguridad
    visible = seguridad.cifrar_clave(token)
    if agente is None:
        db.ejecutar("INSERT INTO usuarios (empresa_id, codigo, clave_hash, nombre, "
                    "rol, clave_visible) VALUES (?, 'AGENTE', ?, 'Agente de A2', "
                    "'agente', ?)", (args.empresa, huella, visible))
    else:
        db.ejecutar("UPDATE usuarios SET clave_hash = ?, activo = 1, "
                    "clave_visible = ? WHERE id = ?",
                    (huella, visible, agente["id"]))
    print(f"Token nuevo para la empresa {empresa['id']} ({empresa['nombre']}):")
    print(token)
    print("(se muestra solo esta vez; guárdalo en la configuración del agente)")


if __name__ == "__main__":
    main()