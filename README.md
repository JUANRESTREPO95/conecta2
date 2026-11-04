# Conecta2

Panel web de pedidos para mayoristas. Este repositorio contiene **solo el
panel** (el que se levanta con Docker / Portainer).

- **Panel:** web responsive (iPhone, Android, PC) con catálogo, pedidos,
  historial, hojas PDF/JPG y administración multi-empresa.
- El **agente** que inserta los pedidos en A2 (programa de Windows) se
  distribuye por separado, no vive en este repositorio.

## Estructura

```
panel/     Código del panel: FastAPI + Jinja2 + SQLite
docker/    Dockerfile y docker-compose para el panel
docs/      Análisis y diseño (modelo de datos de A2, API, despliegue)
```

## Levantarlo con Docker

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Queda en `http://IP-del-servidor:8050`. La base, los logos y la llave de
cifrado viven en el volumen (`./datos` por defecto).

## Levantarlo con Portainer

1. **Stacks → Add stack → Repository**
2. Repository URL: `https://github.com/JUANRESTREPO95/conecta2`
3. Branch: `main` · Compose path: `docker/docker-compose.yml`
4. En *Environment variables*:
   - `CONECTA2_DATOS` = ruta absoluta del servidor para los datos
     (ej. `/opt/conecta2/datos`) — **importante** para que la BD no se pierda
     al recrear el contenedor
   - `CONECTA2_PUERTO` = puerto publicado (8050 por defecto)
5. **Deploy the stack**.

Primer arranque: abrir la web y crear el super usuario.
Token del agente por empresa: **Empresas → Token del agente** (Copiar/Renovar)
o `docker exec conecta2 python crear_agente_token.py --empresa N`.

## Roles

| Rol | Puede |
|---|---|
| Super usuario | Todo: empresas, colores, nombre, logo, usuarios, tokens |
| Administrativo (por empresa) | Igual que un vendedor + historial completo de la empresa + ver y cambiar claves de vendedores |
| Vendedor | Catálogo, pedidos e historial solo suyos |

## Notas de seguridad

- `datos/` (base de datos, llave de cifrado) **no va al repositorio**.
- Las claves se guardan con hash y, para consultarlas desde el panel, cifradas
  con una llave local del servidor.
