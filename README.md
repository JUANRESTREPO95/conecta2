# Conecta2 — panel para servidor (Docker / Portainer)

Esta carpeta es la que se sube a GitHub y la que se levanta en el servidor.

## Contenido

```
PARA VPS/
├── panel/     Código del panel (FastAPI + Jinja2 + SQLite)
├── docker/    Dockerfile + docker-compose.yml + README del despliegue
└── README.md
```

## Docker (línea de comandos)

Desde esta carpeta:

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Queda en `http://IP-del-servidor:8050`.

Variables:
- `CONECTA2_PUERTO` — puerto publicado (8050 por defecto)
- `CONECTA2_DATOS` — carpeta del servidor donde viven la base, los logos y la
  llave de claves (usar una ruta **absoluta**, por ejemplo `/opt/conecta2/datos`)

## Portainer

1. **Stacks → Add stack → Repository**
2. URL: `https://github.com/JUANRESTREPO95/conecta2` · branch `main`
3. Compose path: `docker/docker-compose.yml`
4. Variables: `CONECTA2_DATOS=/opt/conecta2/datos` y `CONECTA2_PUERTO=8050`
5. **Deploy the stack**

Primer arranque: abrir la web y crear el super usuario.
Token del agente: **Empresas → Token del agente** (Copiar/Renovar).

## Notas

- `datos/` (base, llave de cifrado) nunca se sube al repositorio.
- El agente que monta pedidos en A2 se instala aparte, en la PC del negocio
  (carpeta `AGENTE` de la distribución).
