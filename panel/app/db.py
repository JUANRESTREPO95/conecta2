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
    error_a2 TEXT,                       -- mensaje si el inserto en A2 falla
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
    ):
        try:
            con.execute(alter)
        except sqlite3.OperationalError:
            pass
    # migración del viejo "ocultar agotados" (sí/no) al nuevo modo de 3 opciones
    con.execute("UPDATE empresas SET filtro_existencia = "
                "CASE WHEN ocultar_agotados = 1 THEN 'positivo' ELSE 'todo' END "
                "WHERE filtro_existencia IS NULL")
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