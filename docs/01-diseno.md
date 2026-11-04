# Conecta2 — Decisiones de diseño (arranque nuevo)

Arrancada: 2026-11-03. Estas decisiones parten de cero y se validan sobre el
A2 real de `a2HAC_BigStar`.

## Requisitos base (definidos por Juan)

- **Panel web online**, accesible desde cualquier dispositivo (iPhone,
  Android, PC), **responsive**.
- Se levanta **en el puerto que Juan elija** (configurable, no fijo).
- Se instala detrás de su **Nginx Proxy Manager**, que aporta el dominio y
  el **HTTPS** (clave para "Compartir por WhatsApp" en iPhone).
- Todo el trabajo y la documentación vive en
  `C:\Users\juanp\Documents\CLAUDE\CONECTOR\conecta2\`.

## Kit de trabajo (instalado y probado)

| Pieza | Versión | Estado |
|---|---|---|
| Driver ODBC DBISAM | 4.29b 32 bits | ✅ instalado |
| Python | 3.11.9 **32 bits** (`C:\Users\juanp\Python311-32`) | ✅ instalado |
| pyodbc | 5.3.0 | ✅ probado |
| A2 copia real | Empre001 | ✅ abre y funciona |
| Instaladores guardados | `..\\instaladores\\` y `..\\dbisam-odbc\\` | ✅ |

### Por qué Python de 32 bits

El driver ODBC de DBISAM solo existe en 32 bits; un proceso de 64 bits no
puede cargar una DLL de 32, así que Python tiene que ser 32.

## Acceso a datos (probado 2026-11-03)

Conexión local:
`DRIVER={DBISAM 4 ODBC Driver};ConnectionType=Local;CatalogName=<ruta Empre001\Data>`

- `SInventario`: 28.550 filas (productos).
- `SClientes`: 3.668 filas.
- `SDetalleVenta`: 1.073.989 filas (líneas vendidas; ahí vive el precio real).

Script de prueba: `prueba_conexion.py`.

## Por definir con Juan (en el diseño)

- (ninguno mayor; quedan detalles de implementación: logo, nombre exacto
  del negocio, qué hacer con vendedores sin clave en A2)

## Decididas con Juan (2026-11-03)

- **Numeración de pedido: `vendedor-año+consecutivo` (`17-20260020`).**
  Razón de Juan: se sabe de qué año es y se puede localizar más fácil.
- **Filtro del catálogo: solo productos con `FI_INTERNET = True`**, y
  encima un filtro adicional configurable: no mostrar los que tengan
  existencia 0 o menor. Ese filtro (ocultar agotados) se activa/desactiva
  **desde el panel administrativo** (opción del admin, no código).
- **Dónde corre qué (2026-11-03):**
  - **Panel (web + API + BD): VPS Linux**, 24/7, puerto configurable,
    HTTPS con Nginx Proxy Manager de Juan.
  - **Agente: PC Windows de la empresa** (Python 32 bits + driver DBISAM),
    junto al A2. Sincroniza por la API con HTTPS.
  - Si la PC de A2 se apaga, los pedidos quedan en cola (*pendientes*) en
    el panel y el agente los monta al volver. Nada se pierde.
- **Multi-empresa desde el diseño** (2026-11-03): el panel sirve a varios
  negocios. Cada negocio tiene su admin **normal**; Juan tiene un
  **super usuario** global que administra todos (logo, nombre, **colores**
  del panel, empresas, etc.). Sin usuarios fijos en el código: super
  usuario y admins se crean en el primer arranque, claves cifradas.
- **Personalización por empresa:** nombre, logo y colores de la hoja y
  del panel, editables por el super usuario (y el nombre/logo por el admin).