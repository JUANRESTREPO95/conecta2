# Conecta2 — panel para servidor (Docker / Portainer)

Esta carpeta es la que se sube a GitHub y la que se levanta en el servidor.

## Contenido

```
PARA VPS/
├── panel/     Código del panel (FastAPI + Jinja2 + SQLite)
├── docker/    Dockerfile + docker-compose.yml + README del despliegue
├── agente/    Instalador del agente de A2 + guía de instalación
└── README.md
```

## Docker (línea de comandos)

Desde esta carpeta:

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Queda en `http://IP-del-servidor:8050`.

Variables (están todas en **`.env.example`**):

| Variable | Ejemplo | Nota |
|---|---|---|
| `CONECTA2_CONTENEDOR` | `conecta2-megafantasy` | único por empresa |
| `CONECTA2_PUERTO` | `8051` | uno distinto por panel (el interno siempre es 8050) |
| `CONECTA2_DATOS` | `/opt/conecta2/megafantasy` | ruta **absoluta** y única por panel |
| `CONECTA2_IMAGEN` | `conecta2:latest` | la misma para todos |
| `CONECTA2_TZ` | `America/Bogota` | |

## Varios paneles en el mismo Portainer

Cada empresa es **un stack** con sus propias variables; la imagen se comparte.

En Portainer: **Stacks → Add stack → Repository**, nombre del stack
`conecta2-<empresa>`, mismo repo y compose path, y en **Environment variables**
poner:

```
CONECTA2_CONTENEDOR=conecta2-megafantasy
CONECTA2_PUERTO=8051
CONECTA2_DATOS=/opt/conecta2/megafantasy
CONECTA2_IMAGEN=conecta2:latest
CONECTA2_TZ=America/Bogota
```

La segunda empresa: `conecta2-<otra>`, puerto `8052` y carpeta
`/opt/conecta2/<otra>`. El primer arranque de cada panel crea su propio super
usuario; las bases son independientes.

Desde la línea de comandos es lo mismo con archivos distintos:

```bash
docker compose --env-file .env.megafantasy -p megafantasy up -d --build
docker compose --env-file .env.otra -p otra up -d --build
```

## Portainer

1. **Stacks → Add stack → Repository**
2. URL: `https://github.com/JUANRESTREPO95/conecta2` · branch `main`
3. Compose path: `docker/docker-compose.yml`
4. Variables: `CONECTA2_DATOS=/opt/conecta2/datos` y `CONECTA2_PUERTO=8050`
5. **Deploy the stack**

Primer arranque: abrir la web y crear el super usuario.
Token del agente: **Empresas → Token del agente** (Copiar/Renovar).

## Agente de A2 (PC del negocio)

El agente que monta los pedidos en A2 vive en `agente/`:

- **`agente/Instalador Conecta2.exe`** — el instalador (un solo archivo, trae
  el agente adentro; ~16 MB).
- **`agente/README.md`** — paso a paso de instalación, uso y problemas
  frecuentes.
- **`agente/Leame.txt`** — resumen corto que ve quien instala.

Se descarga desde GitHub (Code → Download ZIP, o entrando a `agente/` y
**Download**), se copia al PC de A2 y se ejecuta como administrador.
Antes de ese PC hay que tener A2 funcionando y el **driver DBISAM ODBC 4.29
de 32 bits** instalado; el instalador pide la URL del panel, el token del
agente y la carpeta `Empre001\Data`.

## Notas

- `datos/` (base, llave de cifrado) nunca se sube al repositorio.
- `agente/` queda fuera del build de Docker (`.dockerignore`): el instalador
  no viaja a la imagen, solo se descarga.
