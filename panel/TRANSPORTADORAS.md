# Transportadoras — puesta en marcha

## 1. Hoja BD (columnas)

La pestaña se llama **BD** (o el nombre que pongas en Configuración).
La **fila 1 son los títulos** y los datos empiezan en la fila que elijas
(por defecto la 2). Lo que esté por encima de esa fila se ignora.

| Col | Campo | Lo llena |
|---|---|---|
| A | factura | Cartera (automático) |
| B | fecha | Cartera |
| C | cliente | Cartera |
| D | dirección | Cartera |
| E | ciudad | Cartera |
| F | teléfono | Cartera |
| G | vendedor | Cartera |
| H | cajas | **Panel** |
| I | flete (precio del envío) | **Panel** |
| J | transportadora | **Panel** |
| K | guía | **Panel** |
| L | fecha de confirmación | **Panel** (al confirmar la entrega) |
| M+ | — | se ignora |

- Sin celdas combinadas ni fórmulas en H–L (el script las escribe).
- La columna A debe ser única por factura (es la llave para actualizar).
- Deja la hoja en **“Cualquiera con el enlace puede ver”**. No hace falta
  que sea editable por cualquiera: la escritura va por Apps Script.

## 2. Apps Script

1. Abre la hoja → **Extensiones → Apps Script**.
2. Pega el script de abajo.
3. Cambia `TOKEN` por el **token del agente** de la empresa (el mismo que
   usa el agente de A2; lo ves/renuevas en Empresas).
4. **Implementar → Nueva implementación → Aplicación web**:
   - Ejecutar como: **yo**.
   - Quién tiene acceso: **cualquiera** (el script exige el token).
5. Copia la URL que termina en `/exec`.

> Si algún día renuevas el token del agente, cambia también `TOKEN` aquí y
> vuelve a implementar (Nueva versión).

```javascript
/**
 * Conecta2 — escribe en la hoja BD los campos que mande el panel
 * (cajas, flete, transportadora, guía y fecha de confirmación).
 * El panel manda el token del agente y las letras de las columnas.
 */
const TOKEN = 'PEGA_AQUI_EL_TOKEN_DEL_AGENTE';

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return responder({ ok: false, mensaje: 'sin datos' });
    }
    const cuerpo = JSON.parse(e.postData.contents);
    if (String(cuerpo.token || '') !== TOKEN) {
      return responder({ ok: false, mensaje: 'token inválido' });
    }
    const libro = SpreadsheetApp.getActive();
    const hoja = libro.getSheetByName(cuerpo.hoja || 'BD');
    if (!hoja) {
      return responder({ ok: false, mensaje: 'no existe la pestaña ' + (cuerpo.hoja || 'BD') });
    }
    const columnas = cuerpo.columnas || {};
    const inicio = Math.max(2, Number(cuerpo.inicio) || 2);
    const colFactura = numeroDeLetra(columnas.factura);
    if (!colFactura) {
      return responder({ ok: false, mensaje: 'falta la columna de factura' });
    }
    const factura = String(cuerpo.factura || '').trim();
    if (!factura) {
      return responder({ ok: false, mensaje: 'falta la factura' });
    }
    const ultima = hoja.getLastRow();
    let fila = -1;
    for (let r = inicio; r <= ultima; r++) {
      const valor = String(hoja.getRange(r, colFactura).getDisplayValue()).trim();
      if (valor === factura) {
        fila = r;
        break;
      }
    }
    if (fila < 0) {
      return responder({ ok: false, mensaje: 'factura no encontrada en la hoja BD' });
    }
    const valores = cuerpo.valores || {};
    // escribe solo los campos que llegaron (guardar escribe 4; confirmar, 1)
    Object.keys(valores).forEach(function (campo) {
      const columna = numeroDeLetra(columnas[campo]);
      if (!columna) return;
      if (valores[campo] === undefined || valores[campo] === null) return;
      hoja.getRange(fila, columna).setValue(valores[campo]);
    });
    return responder({ ok: true, fila: fila });
  } catch (error) {
    return responder({ ok: false, mensaje: String(error) });
  }
}

function numeroDeLetra(letra) {
  if (!letra) return 0;
  let numero = 0;
  const texto = String(letra).toUpperCase();
  for (let i = 0; i < texto.length; i++) {
    const codigo = texto.charCodeAt(i);
    if (codigo < 65 || codigo > 90) return 0;
    numero = numero * 26 + (codigo - 64);
  }
  return numero;
}

function responder(objeto) {
  return ContentService.createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}
```

## 3. Configuración en el panel (super)

Cartera → Configuración → columna Cartera → **Hoja BD de transportadoras**:

1. Pega el enlace de la hoja BD.
2. **Traer columnas de la BD** (autodetecta los campos; ajusta si hace falta).
3. **Los datos empiezan en la fila**: por ejemplo 2, o la fila donde quieras
   iniciar el trámite.
4. Mapea cada campo con su columna (factura, fecha, cliente, dirección,
   ciudad, teléfono, vendedor, cajas, flete, transportadora, guía y
   **fecha de confirmación**). Si la hoja todavía no tiene esa columna,
   créala (por ejemplo `FECHA CONFIRMACION`); al traer las columnas se
   detecta sola.
5. Pega la **URL del script** (`/exec`).
6. Nombre de la pestaña (por defecto `BD`).
7. Guardar.

En el panel, en el **menú de Cartera → Transportadora**:
- Admin/super: Pendiente, Registrado y Confirmadas, con Editar y
  “Sin envío / Retiro en bodega”.
- Vendedor: solo sus filas registradas, con el botón **Confirmar**.

**Confirmar** (panel y app): abre la fecha de hoy (editable) y la escribe
como `dd/mm/aaaa` en la columna de fecha de confirmación; solo se escribe
esa celda. La fila sale de Registrado y pasa a **Confirmadas**, que solo
ven admin y super. Si la fila ya tiene fecha en la hoja, no aparece en
Registrado.

> El flete (I) es el valor que se lleva a la hoja de Cartera. El panel no
> toca la hoja de Cartera; esa relación la mantiene la hoja.
