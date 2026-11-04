# Conecta2 — Despliegue

## Piezas

| Pieza | Dónde | Qué correr |
|---|---|---|
| Panel | VPS Linux (puerto a elección) | `uvicorn`/panel detrás de Nginx Proxy Manager |
| Agente | PC Windows del negocio (junto a A2) | `agente.py` en Python 3.11 de 32 bits, continuo |

## Panel en el VPS

1. Copiar la carpeta `conecta2\panel\` al VPS.
2. `python3 -m venv venv && venv/bin/pip install -r requirements.txt`.
3. Arrancar con puerto: `venv/bin/python run.py --puerto 8050`
   (o `CONECTA2_PUERTO=8050`). Sin `CONECTA2_A2_DATA` — en el VPS no hay A2.
4. Servicio con `systemd` (unidad `conecta2.service`) para que levante al
   reiniciar y se recupere solo.
5. En Nginx Proxy Manager: proxy host → `http://127.0.0.1:8050`, con el
   dominio y Let's Encrypt (HTTPS). Con eso "Compartir por WhatsApp"
   funciona bien en iPhone.
6. Primer arranque: abrir la web y crear el **super usuario** de esa
   instalación → luego crear la empresa y los admins.
7. **Token del agente para cada empresa**: en el VPS correr
   `python3 crear_agente_token.py --empresa <n>` y pasárselo al agente.

## Agente en Windows (máquina de A2)

Requisitos (ya probado en esta máquina):
- Driver DBISAM ODBC 4.29b **32 bits** (instalador en `instaladores\`).
- Python 3.11 **32 bits** + `pyodbc` (instalador guardado).
- Archivo `_config.txt` del agente con: URL del panel, TOKEN del agente,
  ruta `Empre001\Data` de A2, depósito, cliente por defecto.

En este PC de pruebas hay `conecta2\agente\correr_agente.bat` con todo
incluido (incluye el token en texto: archivo local, no va ni al panel ni
a la memoria). Para producción en la máquina del negocio:

1. Copiar carpeta `agente\` e instalar Python/driver si faltan.
2. Editar `correr_agente.bat` con la URL del VPS y el token de la empresa.
3. Arranque automático: tarea programada de Windows al iniciar sesión
   (comando que se usará, requiere aceptar en la pantalla de permisos):
   `schtasks /Create /TN "Conecta2 Agente" /TR "<ruta>\correr_agente.bat" /SC ONLOGON /F`
4. El agente escribe en `agente\log_agente.txt`.

## Comportamiento

- Pedidos: el panel guarda `pendiente`; el agente los baja y monta en
  A2, luego marca `montado` con el autoincremento de A2.
- Catálogo/existencias cada 5 min; precios de forma incremental
  (caché por `FDI_AUTOINCREMENT` en `agente\datos\precios_cache.json`).
- Si se cae la conexión con el panel o A2, reintenta a los 10 s.
- Los pedidos que el agente no logra montar quedan `error` con el
  mensaje visible en el panel (admin puede verlo).
- Insert en A2: cabecera tipo 10 estado 4 con CONSUMIDOR FINAL
  (NIT `2222222222`, variable `CONECTA2_CLIENTE_NIT`), líneas con
  `FDI_LINEA` secuencial y `FDI_*` igual al Conector (CANTIDADPENDIENTE,
  UNDDESCARGA, DECIMALES...) para que A2 muestre las cantidades bien.
- Antes de insertar, el agente limpia restos de un intento anterior del
  mismo número de pedido (evita duplicados).

## Pendientes abiertos

- [ ] Prueba de facturación en A2 (que el pedido montado se facture con IVA).
- [ ] Revisar el tema del cliente en A2 (Juan dice que los clientes no
  salen bien — revisar con captura).
- [ ] Logo real y nombre exacto del negocio.
- [ ] Instalar agente como servicio 24/7 (tarea programada pendiente de
  aprobación de Juan).
- [ ] Panel al VPS + NPM + HTTPS.
- [ ] Respaldos de la BD del panel.