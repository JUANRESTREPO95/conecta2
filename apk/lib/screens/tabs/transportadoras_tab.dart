import 'dart:convert';

import 'package:material_ui/material_ui.dart';

import '../../state.dart';

/// Transportadoras: registradas del vendedor y, para admin, las confirmadas.
/// El panel entrega solo las filas que corresponden a cada uno.
class TransportadorasTab extends StatefulWidget {
  const TransportadorasTab({super.key});

  @override
  State<TransportadorasTab> createState() => _TransportadorasTabState();
}

class _TransportadorasTabState extends State<TransportadorasTab> {
  Map<String, dynamic>? _datos;
  bool _cargando = true;
  bool _desdeCache = false;
  bool _vistaConfirmadas = false;
  String? _confirmando;
  String? _error;

  static const _campos = <String, String>{
    'factura': 'Factura',
    'fecha': 'Fecha',
    'cliente': 'Cliente',
    'ciudad': 'Ciudad',
    'telefono': 'Teléfono',
    'vendedor': 'Vendedor',
    'cajas': 'Cajas',
    'flete': 'Flete',
    'transportadora': 'Transportadora',
    'guia': 'Guía',
  };

  bool get _esAdmin =>
      appState.usuarioRol == 'admin' || appState.usuarioRol == 'super';

  @override
  void initState() {
    super.initState();
    Future.microtask(_cargar);
  }

  Future<void> _cambiarVista(bool confirmadas) async {
    if (_vistaConfirmadas == confirmadas) return;
    setState(() {
      _vistaConfirmadas = confirmadas;
      _datos = null;
      _desdeCache = false;
      _error = null;
      _cargando = true;
    });
    await _cargar();
  }

  Future<void> _cargar() async {
    final api = appState.api;
    if (api == null) {
      if (mounted) {
        setState(() {
          _cargando = false;
          _error = 'Falta configurar la app.';
        });
      }
      return;
    }
    if (mounted) {
      setState(() {
        _cargando = true;
        _error = null;
      });
    }
    final cacheArriba = !_vistaConfirmadas;
    try {
      final datos = await api.get(
        '/api/app/transportadoras',
        query: _vistaConfirmadas ? const {'estado': 'confirmada'} : null,
        timeout: const Duration(seconds: 90),
      );
      if (cacheArriba) {
        try {
          await appState.db.setConfig('transporte_cache', jsonEncode(datos));
        } catch (_) {}
      }
      if (!mounted) return;
      setState(() {
        _datos = datos;
        _desdeCache = false;
        _cargando = false;
      });
    } catch (e) {
      String? guardado;
      if (cacheArriba) {
        try {
          guardado = await appState.db.getConfig('transporte_cache');
        } catch (_) {}
      }
      if (guardado != null && guardado.isNotEmpty) {
        try {
          final cache = jsonDecode(guardado) as Map<String, dynamic>;
          if (!mounted) return;
          setState(() {
            _datos = cache;
            _desdeCache = true;
            _cargando = false;
            _error = e.toString();
          });
          return;
        } catch (_) {}
      }
      if (!mounted) return;
      setState(() {
        _cargando = false;
        _error = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando && _datos == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final datos = _datos;
    if (datos == null) {
      return _aviso('No se pudo cargar la transportadora.\n${_error ?? ''}');
    }
    if (datos['configurada'] != true) {
      return _aviso('La transportadora todavía no está configurada.\n'
          'El administrador debe configurar la hoja BD en el panel.');
    }
    final hayFecha = datos['hay_fecha'] == true;
    final filas = (datos['filas'] as List? ?? const [])
        .whereType<Map>()
        .map((f) => f.cast<String, dynamic>())
        .toList();
    final actualizado = (datos['actualizado'] ?? '').toString();
    final cabecera = <Widget>[
      if (_desdeCache) _avisoCache(actualizado),
      Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
          _vistaConfirmadas
              ? '${filas.length} confirmada${filas.length == 1 ? '' : 's'}'
                  '${actualizado.isNotEmpty ? ' · $actualizado' : ''}'
              : '${filas.length} registrada${filas.length == 1 ? '' : 's'}'
                  '${actualizado.isNotEmpty ? ' · $actualizado' : ''}',
          style: const TextStyle(fontSize: 12, color: Colors.black54),
        ),
      ),
      if (filas.isEmpty)
        Padding(
          padding: const EdgeInsets.all(24),
          child: Center(
            child: Text(
              _vistaConfirmadas
                  ? 'No hay entregas confirmadas.'
                  : 'No hay transportadoras registradas.',
              textAlign: TextAlign.center,
            ),
          ),
        ),
    ];
    final lista = RefreshIndicator(
      onRefresh: _cargar,
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
        itemCount: cabecera.length + filas.length,
        itemBuilder: (context, i) {
          if (i < cabecera.length) return cabecera[i];
          return _ficha(filas[i - cabecera.length],
              puedeConfirmar: hayFecha && !_vistaConfirmadas);
        },
      ),
    );
    if (!(_esAdmin && hayFecha)) return lista;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
          child: Row(
            children: [
              ChoiceChip(
                label: const Text('Registrado'),
                selected: !_vistaConfirmadas,
                onSelected: (_) => _cambiarVista(false),
              ),
              const SizedBox(width: 8),
              ChoiceChip(
                label: const Text('Confirmadas'),
                selected: _vistaConfirmadas,
                onSelected: (_) => _cambiarVista(true),
              ),
            ],
          ),
        ),
        Expanded(child: lista),
      ],
    );
  }

  Widget _aviso(String texto) {
    return RefreshIndicator(
      onRefresh: _cargar,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(28),
        children: [
          const SizedBox(height: 40),
          Icon(Icons.local_shipping,
              size: 56, color: appState.colorCartera.withAlpha(150)),
          const SizedBox(height: 14),
          Text(texto, textAlign: TextAlign.center),
          const SizedBox(height: 14),
          Center(
            child: OutlinedButton.icon(
              onPressed: _cargar,
              icon: const Icon(Icons.refresh),
              label: const Text('Reintentar'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _avisoCache(String actualizado) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.orange.withAlpha(28),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.orange.withAlpha(90)),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              actualizado.isEmpty
                  ? 'Sin conexión: se muestra la última copia guardada.'
                  : 'Sin conexión: última copia del $actualizado.',
              style: const TextStyle(fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _ficha(Map<String, dynamic> fila, {required bool puedeConfirmar}) {
    final confirmada = (fila['fecha_confirmacion'] ?? '').toString();
    final factura = (fila['factura'] ?? '').toString();
    final trabajando = _confirmando == factura;
    return Card(
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: Color(0xFFE5E7EB)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final entrada in _campos.entries)
              _linea(entrada.value, (fila[entrada.key] ?? '').toString()),
            if (confirmada.isNotEmpty) _linea('Confirmada', confirmada),
            if (puedeConfirmar) ...[
              const SizedBox(height: 6),
              Align(
                alignment: Alignment.centerRight,
                child: OutlinedButton.icon(
                  onPressed: _confirmando == null ? () => _confirmar(factura) : null,
                  icon: trabajando
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.check_circle_outline, size: 18),
                  label: const Text('Confirmar'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: appState.colorCartera,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _linea(String etiqueta, String valor) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2.5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 108,
            child: Text(
              etiqueta,
              style: const TextStyle(
                fontSize: 10.5,
                fontWeight: FontWeight.w700,
                color: Colors.black54,
              ),
            ),
          ),
          Expanded(
            child: Text(
              valor.isEmpty ? '—' : valor,
              style: const TextStyle(fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmar(String factura) async {
    if (factura.isEmpty) return;
    final api = appState.api;
    if (api == null) return;
    final hoy = DateTime.now();
    var elegida = DateTime(hoy.year, hoy.month, hoy.day);
    final fecha = await showDialog<DateTime>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, cambiar) => AlertDialog(
          title: const Text('Confirmar entrega'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Factura $factura'),
              const SizedBox(height: 14),
              InkWell(
                onTap: () async {
                  final otra = await showDatePicker(
                    context: ctx,
                    initialDate: elegida,
                    firstDate: DateTime(2020),
                    lastDate: DateTime(hoy.year + 2, 12, 31),
                  );
                  if (otra != null) cambiar(() => elegida = otra);
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 12),
                  decoration: BoxDecoration(
                    border: Border.all(color: const Color(0xFFD1D5DB)),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.event, size: 20),
                      const SizedBox(width: 10),
                      Text(_fechaTexto(elegida),
                          style: const TextStyle(fontSize: 16)),
                      const Spacer(),
                      const Icon(Icons.edit_calendar,
                          size: 18, color: Colors.black45),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 6),
              const Text('Toca la fecha para cambiarla.',
                  style: TextStyle(fontSize: 11, color: Colors.black54)),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, elegida),
              child: const Text('Confirmar'),
            ),
          ],
        ),
      ),
    );
    if (fecha == null || !mounted) return;
    setState(() => _confirmando = factura);
    try {
      await api.post('/api/app/transportadoras/confirmar', {
        'factura': factura,
        'fecha': _fechaISO(fecha),
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Entrega confirmada')),
      );
      await _cargar();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('No se pudo confirmar: $e')),
      );
    } finally {
      if (mounted) setState(() => _confirmando = null);
    }
  }

  String _fechaTexto(DateTime d) {
    final dd = d.day.toString().padLeft(2, '0');
    final mm = d.month.toString().padLeft(2, '0');
    return '$dd/$mm/${d.year}';
  }

  String _fechaISO(DateTime d) {
    final mm = d.month.toString().padLeft(2, '0');
    final dd = d.day.toString().padLeft(2, '0');
    return '${d.year}-$mm-$dd';
  }
}
