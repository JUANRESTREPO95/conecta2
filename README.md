# Conecta2

Panel web de pedidos para mayoristas más un agente que inserta esos pedidos en
**A2** (DBISAM). Reemplaza al Conector (nube `sitio24x.com` + APK Android).

- **Panel:** web responsive (iPhone, Android, PC) con catálogo, pedidos,
  historial, hojas PDF/JPG y administración multi-empresa.
- **Agente:** corre en la PC del negocio (donde está A2), sube catálogo,
  existencias y precios, y monta los pedidos pendientes en A2.

## Estructura

```
conecta2/
├── panel/        Panel web: FastAPI + Jinja2 + SQLite (puerto configurable)
├── agente/       Agente de A2: Python 32 bits + pyodbc + driver DBISAM
├── docs/         Análisis y diseño (modelo de datos de A2, API, despliegue)
├── docker/       Panel empaquetado para Docker (Dockerfile + docker-compose)
└── windows/      Instalador .exe del agente para Windows (Python + DBISAM + agente)
```

## Roles

| Rol | Puede |
|---|---|
| Super usuario | Todo: empresas, colores, nombre, logo, usuarios, tokens |
| Administrativo (por empresa) | Igual que un vendedor + ver todo el historial de la empresa + ver y cambiar claves de vendedores |
| Vendedor | Catálogo, pedidos e historial solo suyos |

## Panel

```bash
cd panel
python -m venv .venv && .venv/bin/pip install -r requirements.txt
python run.py --puerto 8050        # o CONECTA2_PUERTO=8050
```

- Primer arranque: abrir la web y crear el super usuario.
- La base, los logos y la llave de cifrado de claves quedan en `panel/datos/`.
- Token del agente por empresa: `python crear_agente_token.py --empresa N`
  (también se ve y copia en el panel: **Empresas → Token del agente**).

## Panel en Docker

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Queda en `http://IP-del-servidor:8050`; los datos persisten en `./datos`.
Ver `docker/README.md`.

## Agente en Windows

Se entrega con **`windows/Instalador Conecta2.exe`**: instala Python 32 bits,
el driver DBISAM, el agente y un acceso directo; pide la URL del panel, el
token y la carpeta `Empre001\Data` de A2. Ver `windows/README.md`.

La configuración también se edita desde el propio agente (ventana
**Configuración**: URL, token, carpeta de A2, depósito, con "Probar conexión").

## Notas de seguridad

- `panel/datos/` (base de datos, llave de cifrado), `config_agente.json`
  (token del agente) y los instaladores binarios **no van al repositorio**
  (ver `.gitignore`).
- Las claves de los usuarios se guardan con hash y, para poder consultarlas
  desde el panel, también cifradas con una llave local del servidor.
