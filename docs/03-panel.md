# Conecta2 — Diseño del panel

Panel web online, responsive, puerto configurable, detrás de Nginx Proxy
Manager (HTTPS). Arranque: 2026-11-03.

## Stack

- **Backend:** Python 3.11 + FastAPI + Jinja2 (un solo proceso, puerto
  variable por configuración).
- **Base de datos:** SQLite para empezar. Si el negocio crece se pasa a
  PostgreSQL sin reescribir (SQLAlchemy o SQL puro encapsulado).
- **Frontend:** HTML + CSS (plantillas Jinja2), tal para móvil y PC;
  sin framework pesado.
- **Agente:** script Python en la máquina de A2 (32 bits) que:
  1. lee el catálogo y existencias (`Sinventario` + `SinvDep`) y los
     sube al panel cada 5 minutos;
  2. sube los precios (última venta por producto, con caché por
     autoincremento);
  3. baja los pedidos nuevos del panel e los inserta en A2
     (`SOperacionInv` + `SDetalleVenta`), marca "montado" y deja la hoja.

## Roles

| Rol | Entra con | Puede |
|---|---|---|
| Vendedor | su código + clave (panel propio) | catálogo, pedidos, historial, hoja |
| **Admin** (uno por empresa) | su código + clave | vendedores y claves, configuración del negocio, pedidos, estado del agente |
| **Super usuario** (uno global) | su código + clave | **todo**, en **todas las empresas**: logo, nombre y **colores del panel**, cualquier negocio, cualquier vendedor |

- El **super usuario es de Juan solo**: existe para instalar el panel en
  varios negocios y administrarlos todos desde una sola cuenta. Cada
  empresa recibe su panel admin normal de su propia empresa.
  Cambia todo: logo, nombre del negocio, colores del panel, etc., y todo
  lo que puede el admin.
- **No hay usuarios fijos en el código.** El super usuario se crea en el
  primer arranque de cada instalación (creador de primera vez) y la clave
  queda cifrada con hash en la BD del sistema. Lo mismo aplica para los
  admins: los crea el super usuario.
- Las claves de los vendedores son del **panel** (no de A2): el admin
  asigna o cambia cualquiera en el panel.

## Pantallas — Vendedor

1. **Login** — código + clave.
2. **Catálogo / Inicio** — buscador (código, descripción, marca).
   Tarjeta/lista por producto: código, descripción, precio (última venta)
   y existencia según el modo de depósito que el admin fijó.
   Filtros: solo `FI_INTERNET`; y si el admin activó "ocultar agotados",
   se ocultan existencias <= 0.
3. **Pedido** — productos agregados con cantidad editable (+/-),
   precio, subtotal sin IVA y total. Campo **referencia** (libre).
   Botón *Enviar*.
4. **Historial** — pedidos del vendedor (número `17-20260020`, fecha,
   monto, estado: *pendiente* → *montado en A2*).
   Acciones: ver detalle, reenviar la hoja (PDF/PNG por WhatsApp),
   marcar para el agente si está pendiente.
5. **Mi clave** — cambiar clave.

## Pantallas — Administrador

1. **Configuración**
   - Modo de depósito del catálogo: 1, 2 o suma de ambos.
   - Ocultar productos agotados: sí/no (el filtro nuevo pedido hoy).
   - Nombre del negocio y logo para la hoja.
   - (Puerto se fija al arrancar el servidor, no en esta pantalla.)
2. **Vendedores** — lista, crear, activar/desactivar, cambiar clave.
3. **Pedidos** — pedidos de todos los vendedores, filtro por
   vendedor/fecha/estado, **borrar** (solo en Conecta2, nunca en A2).
4. **Estado del agente** — última conexión, última sync de catálogo y
   precios, pedidos montados con error (si falla el inserto en A2).

## Pantallas extra — Super usuario (solo él)

1. **Empresas** — lista de negocios, crear/desactivar una, y entrar a
   administrar cualquiera con el rol de admin.
2. **Estilo del panel** — colores (paleta de la empresa), y logo/nombre
   por empresa si el admin aún no los ha puesto.
3. **Admins** — crear admins por empresa, reponer claves, ver log de
   sesiones si hace falta.

## Flujo de un pedido (de punta a punta)

1. Vendedor crea el pedido en el panel → estado *pendiente*, número
   `VV-AAAANNNN` (ej. `17-20260001`; consecutivo por vendedor, reinicia
   cada año).
2. El agente (cada 30 s) baja el pedido pendiente, lo inserta en A2
   (cabecera tipo 10 + líneas) y marca *montado*, guardando el número
   interno (`FTI_AUTOINCREMENT`) que quedó en A2.
3. La hoja del pedido (PDF + PNG) queda disponible en la pantalla del
   pedido, con el botón compartir a WhatsApp.
4. Si el inserto falla, el pedido queda *pendiente* con el error visible
   en el panel del admin y el agente reintenta.

## Seguridad

- Sesiones con token por usuario (cookie segura vía HTTPS de NPM).
- El agente usa un token propio contra la API del panel.
- Contraseñas con hash (bcrypt), nunca texto plano.
- La API nunca habla directo con A2: solo el agente en la máquina de A2.