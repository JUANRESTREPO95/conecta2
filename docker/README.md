# Conecta2 — panel en Docker

Panel de pedidos (FastAPI + SQLite) listo para correr en un contenedor.
No incluye A2: el A2 se queda en la PC del negocio, donde corre el agente.

## Qué hay

| Archivo | Qué es |
|---|---|
| `Dockerfile` | Imagen con Python 3.11 y el panel |
| `docker-compose.yml` | Servicio `conecta2`, puerto y datos por variables |
| `../panel/` | Código del panel (contexto de compilación: raíz del repo) |

## Cómo se levanta con Docker

Desde la raíz del repositorio:

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Queda en `http://IP-del-servidor:8050`.

Variables del compose:
- `CONECTA2_PUERTO` (por defecto 8050): puerto publicado.
- `CONECTA2_DATOS` (por defecto `./datos`): carpeta del servidor donde viven
  la base, los logos y la llave de claves.
- `CONECTA2_CONTENEDOR` (por defecto `conecta2`): nombre del contenedor. Hay
  que darle uno distinto a cada stack si se corren varias empresas en el mismo
  servidor (por ejemplo `conecta2-e2`, `conecta2-e3`…).

## Cómo se levanta con Portainer (recomendado)

1. **Stacks → Add stack → Repository**
2. Repository URL: `https://github.com/JUANRESTREPO95/conecta2`
3. Branch `main` · Compose path `docker/docker-compose.yml`
4. Environment variables:
   - `CONECTA2_DATOS` = `/opt/conecta2/datos` (ruta **absoluta** del servidor;
     así la BD sobrevive a recrear el contenedor)
   - `CONECTA2_PUERTO` = `8050` (o el que quieras publicar)
   - `CONECTA2_CONTENEDOR` = `conecta2` (cada stack necesita uno distinto)
5. **Deploy the stack**.

Para **varias empresas en el mismo servidor**: un stack por empresa, cada uno
con su `CONECTA2_DATOS` (`/opt/conecta2/e1`, `e2`…), su `CONECTA2_PUERTO`
(`8051`, `8052`…) y su `CONECTA2_CONTENEDOR` (`conecta2-e1`, `conecta2-e2`…).
Docker crea las carpetas solo si no existen.

- **Primera vez:** abrir esa dirección en el navegador → el panel pide crear el
  **super usuario**.
- La base de datos, los logos y la llave de cifrado quedan en `./datos`
  (se crea sola). **Respaldar = copiar esa carpeta.**
- Para actualizar el código: reemplazar `panel/` y ejecutar de nuevo
  `docker compose up -d --build`.
- Para detener: `docker compose down` (los datos se conservan).

## Token del agente (por empresa)

```bash
docker compose exec conecta2 python crear_agente_token.py --empresa 1
```

También se puede ver y copiar desde el panel: **Empresas → Token del agente**
(botón Renovar para cambiarlo).

## Detrás de un proxy con HTTPS

El contenedor escucha en el puerto 8050 en HTTP plano; el certificado HTTPS se
pone delante con el proxy (por ejemplo un reverse proxy con Let's Encrypt).
El agente debe apuntar a la URL `https://...` resultante.

## Notas

- Zona horaria `America/Bogota` (UTC-5).
- El puerto se cambia en `docker-compose.yml` (`"8050:8050"`, la parte izquierda)
  y en `CONECTA2_PUERTO` de la imagen si se cambia el interno.
- No hace falta abrir ninguna base de datos aparte: SQLite va dentro de `datos/`.
