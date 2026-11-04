"""Arranca el panel Conecta2. Puerto: variable CONECTA2_PUERTO o --puerto."""
import argparse
import os

import uvicorn

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config, db

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--puerto", type=int, default=None)
    args = parser.parse_args()
    puerto = args.puerto or int(os.environ.get("CONECTA2_PUERTO", "8010"))
    db.esquema()
    print(f"Conecta2 en http://0.0.0.0:{puerto} — BD: {config.BD}")
    dev = os.environ.get("CONECTA2_DEV") == "1"  # auto-recarga mientras desarrollamos
    uvicorn.run("app.main:app", host="0.0.0.0", port=puerto, access_log=False, reload=dev)