"""Base de datos SQLite del panel (multi-empresa)."""
import sqlite3
from pathlib import Path
from threading import local

from app import config

_local = local()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    activa INTEGER NOT NULL DEFAULT 1,
    logo TEXT,
    color_primario TEXT DEFAULT '#1e40af',
    color_secundario TEXT DEFAULT '#64748b',
    deposito_modo TEXT NOT NULL DEFAULT '1',        -- '1', '2' o 'suma'
    ocultar_agotados INTEGER NOT NULL DEFAULT 1,
    creado TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresas(id),
    codigo TEXT NOT NULL,
    clave_hash TEXT NOT NULL,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('super', 'admin', 'vendedor', 'agente')),
    activo INTEGER NOT NULL DEFAULT 1,
    clave_a2 INTEGER DEFAULT NULL,                  -- referencia al FV_CLAVE de A2 (todavía no se usa)
    creado TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE (empresa_id, codigo)
);

CREATE TABLE IF NOT EXISTS sesiones (
    token TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    creado TEXT DEFAULT (datetime('now', 'localtime')),
    expira TEXT NOT NULL
);

-- Catálogo en caché del panel (lo llena el sincronizador/agente)
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    codigo TEXT NOT NULL,                -- código sin espacios (recortado, en mayúscula)
    codigo_a2 TEXT,                      -- código original de A2 (con espacios)
    codigo_busqueda TEXT,                -- código normalizado para buscar por tramos
    descripcion TEXT,
    marca TEXT,
    categoria TEXT,
    unidad TEXT,
    moneda INTEGER DEFAULT 1,
    activo INTEGER DEFAULT 1,
    internet INTEGER DEFAULT 1,
    precio REAL,
    actualizado TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE (empresa_id, codigo)
);
CREATE INDEX IF NOT EXISTS idx_productos_desc ON productos(empresa_id, descripcion);
CREATE INDEX IF NOT EXISTS idx_productos_codigo_a2 ON productos(empresa_id, codigo_a2);

CREATE TABLE IF NOT EXISTS stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    codigo_producto TEXT NOT NULL,
    deposito INTEGER NOT NULL,
    existencia REAL NOT NULL DEFAULT 0,
    actualizado TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE (empresa_id, codigo_producto, deposito)
);

CREATE TABLE IF NOT EXISTS sincronizaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    tipo TEXT NOT NULL,                  -- catalogo / precios
    detalle TEXT,
    hecho TEXT DEFAULT (datetime('now', 'localtime'))
);

-- Pedidos creados en el panel
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    vendedor_id INTEGER NOT NULL REFERENCES usuarios(id),
    numero TEXT NOT NULL,                -- '26-20260001'
    referencia TEXT,
    estado TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente | montado | error
    total REAL NOT NULL DEFAULT 0,       -- sin IVA
    uuid TEXT,                           -- identificador de la app (idempotencia)
    origen TEXT NOT NULL DEFAULT 'panel',-- panel | app
    error_a2 TEXT,                       -- último error al montar (no cambia el estado)
    intentos INTEGER NOT NULL DEFAULT 0, -- intentos fallidos de montaje
    a2_autoincrement INTEGER,            -- FTI_AUTOINCREMENT que quedó en A2
    creado TEXT DEFAULT (datetime('now', 'localtime')),
    montado TEXT,
    UNIQUE (empresa_id, numero)
);
CREATE INDEX IF NOT EXISTS idx_pedidos_vendedor ON pedidos(vendedor_id, creado);

CREATE TABLE IF NOT EXISTS pedido_lineas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL REFERENCES pedidos(id),
    codigo TEXT NOT NULL,
    descripcion TEXT,
    cantidad REAL NOT NULL,
    precio REAL NOT NULL,
    UNIQUE (pedido_id, codigo)
);

-- Clientes de A2 (se eligen en el pedido cuando está activado)
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    codigo TEXT NOT NULL,
    nombre TEXT,
    nit TEXT,
    actualizado TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE (empresa_id, codigo)
);

-- Autorizados de A2 (Sautorizados): direcciones que pertenecen a un cliente.
-- Es solo informativo para la hoja del pedido; NADA de esto se escribe en A2.
CREATE TABLE IF NOT EXISTS autorizados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    codigo TEXT NOT NULL,
    cliente_codigo TEXT NOT NULL,
    nombre TEXT,
    direccion TEXT,
    activo INTEGER DEFAULT 1,
    actualizado TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE (empresa_id, codigo)
);
CREATE INDEX IF NOT EXISTS idx_autorizados_cliente
    ON autorizados(empresa_id, cliente_codigo);

-- Carrito del pedido en curso, por usuario y empresa: no depende de la
-- sesión, así que sobrevive a cerrar la página o volver a iniciar sesión
CREATE TABLE IF NOT EXISTS carritos (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    carrito TEXT,
    actualizado TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (usuario_id, empresa_id)
);

-- Tokens de las apps Android (uno por teléfono; el super los revoca)
CREATE TABLE IF NOT EXISTS app_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    nombre TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT DEFAULT (datetime('now', 'localtime')),
    ultimo_uso TEXT
);

-- Vendedores de A2 (los sube el agente; el panel los importa de aquí)
CREATE TABLE IF NOT EXISTS vendedores_a2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    codigo TEXT NOT NULL,
    nombre TEXT,
    activo INTEGER DEFAULT 1,
    clave_a2 TEXT,
    actualizado TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE (empresa_id, codigo)
);

-- Consecutivo por vendedor y año (número de pedido '26-20260001')
CREATE TABLE IF NOT EXISTS consecutivos (
    empresa_id INTEGER NOT NULL,
    vendedor_id INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    ultimo INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (empresa_id, vendedor_id, anio)
);
"""


def conectar() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is None:
        con = sqlite3.connect(str(config.BD), timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        # WAL: las lecturas no se bloquean mientras el agente escribe
        try:
            con.execute("PRAGMA journal_mode = WAL")
            con.execute("PRAGMA synchronous = NORMAL")
            con.execute("PRAGMA busy_timeout = 30000")
        except sqlite3.DatabaseError:
            pass
        _local.con = con
    return con


def esquema() -> None:  # crea tablas si faltan
    con = conectar()
    con.executescript(ESQUEMA)
    # columnas añadidas después del primer arranque
    for alter in (
        "ALTER TABLE sesiones ADD COLUMN empresa_activa INTEGER DEFAULT NULL",
        "ALTER TABLE empresas ADD COLUMN color_letra TEXT DEFAULT '#ffffff'",
        "ALTER TABLE sesiones ADD COLUMN carrito TEXT DEFAULT NULL",
        "ALTER TABLE productos ADD COLUMN codigo_a2 TEXT",
        "ALTER TABLE empresas ADD COLUMN filtro_existencia TEXT DEFAULT NULL",
        "ALTER TABLE empresas ADD COLUMN existencia_minima INTEGER DEFAULT 0",
        "ALTER TABLE usuarios ADD COLUMN clave_visible TEXT DEFAULT NULL",
        "ALTER TABLE empresas ADD COLUMN usar_clientes INTEGER DEFAULT 0",
        "ALTER TABLE pedidos ADD COLUMN cliente_codigo TEXT",
        "ALTER TABLE pedidos ADD COLUMN cliente_nombre TEXT",
        "ALTER TABLE pedidos ADD COLUMN cliente_nit TEXT",
        "ALTER TABLE empresas ADD COLUMN sync_clientes_pedido INTEGER DEFAULT 0",
        "ALTER TABLE empresas ADD COLUMN formato_numero TEXT",
        "ALTER TABLE empresas ADD COLUMN reinicio_numero TEXT",
        "ALTER TABLE empresas ADD COLUMN digitos_numero INTEGER DEFAULT 4",
        "ALTER TABLE clientes ADD COLUMN rif TEXT",
        "ALTER TABLE empresas ADD COLUMN cliente_predeterminado_codigo TEXT",
        "ALTER TABLE empresas ADD COLUMN cliente_predeterminado_nombre TEXT",
        "ALTER TABLE empresas ADD COLUMN cliente_predeterminado_nit TEXT",
        "ALTER TABLE empresas ADD COLUMN cliente_predeterminado_rif TEXT",
        "ALTER TABLE productos ADD COLUMN codigo_busqueda TEXT",
        "ALTER TABLE empresas ADD COLUMN usar_autorizados INTEGER DEFAULT 0",
        "ALTER TABLE empresas ADD COLUMN sync_autorizados_pedido INTEGER DEFAULT 0",
        "ALTER TABLE pedidos ADD COLUMN autorizado_codigo TEXT",
        "ALTER TABLE pedidos ADD COLUMN autorizado_nombre TEXT",
        "ALTER TABLE pedidos ADD COLUMN autorizado_direccion TEXT",
        "ALTER TABLE pedidos ADD COLUMN intentos INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE pedidos ADD COLUMN uuid TEXT",
        "ALTER TABLE pedidos ADD COLUMN origen TEXT DEFAULT 'panel'",
    ):
        try:
            con.execute(alter)
        except sqlite3.OperationalError:
            pass
    # el UUID de la app es único por empresa (las filas viejas quedan en NULL)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pedidos_uuid "
                "ON pedidos(empresa_id, uuid)")
    # migración del viejo "ocultar agotados" (sí/no) al nuevo modo de 3 opciones
    con.execute("UPDATE empresas SET formato_numero = "
                "'{vendedor}-{anio}{numero}' WHERE formato_numero IS NULL")
    con.execute("UPDATE empresas SET reinicio_numero = 'anual' "
                "WHERE reinicio_numero IS NULL")
    con.execute("UPDATE empresas SET filtro_existencia = "
                "CASE WHEN ocultar_agotados = 1 THEN 'positivo' ELSE 'todo' END "
                "WHERE filtro_existencia IS NULL")
    # un pedido montado no debe conservar el error de un intento anterior
    con.execute("UPDATE pedidos SET error_a2 = NULL, intentos = 0 "
                "WHERE estado = 'montado'")
    # rellena una sola vez el código normalizado (búsqueda por tramos)
    if con.execute("SELECT COUNT(*) FROM productos WHERE codigo_busqueda IS NULL"
                   ).fetchone()[0]:
        con.execute("UPDATE productos SET codigo_busqueda = UPPER(TRIM(codigo))")
    con.commit()


def ejecutar(sql: str, valores: tuple = ()) -> sqlite3.Cursor:
    con = conectar()
    cur = con.execute(sql, valores)
    con.commit()
    return cur


def filas(sql: str, valores: tuple = ()) -> list[sqlite3.Row]:
    return conectar().execute(sql, valores).fetchall()


def fila(sql: str, valores: tuple = ()) -> sqlite3.Row | None:
    return conectar().execute(sql, valores).fetchone()