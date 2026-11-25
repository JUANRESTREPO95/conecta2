import 'dart:convert';

import 'package:material_ui/material_ui.dart';

import '../../state.dart';

/// Transportadoras registradas (solo lectura).
/// El panel entrega únicamente las filas registradas del vendedor.
class TransportadorasTab extends StatefulWidget {
  const TransportadorasTab({super.key});

  @override
  State<TransportadorasTab> createState() => _TransportadorasTabState();
}

class _TransportadorasTabState extends State<TransportadorasTab> {
  Map<String, dynamic>? _datos;
  bool _cargando = true;
  bool _desdeCache = false;
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

  @override
  void initState() {
    super.initState();
    Future.microtask(_cargar);
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
    try {
      final datos = await api.get(
        '/api/app/transportadoras',
        timeout: const Duration(seconds: 90),
      );
      try {
        await appState.db.setConfig('transporte_cache', jsonEncode(datos));
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _datos = datos;
        _desdeCache = false;
        _cargando = false;
      });
    } catch (e) {
      String? guardado;
      try {
        guardado = await appState.db.getConfig('transporte_cache');
      } catch (_) {}
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
          '${filas.length} registrada${filas.length == 1 ? '' : 's'}'
          '${actualizado.isNotEmpty ? ' · $actualizado' : ''}',
          style: const TextStyle(fontSize: 12, color: Colors.black54),
        ),
      ),
      if (filas.isEmpty)
        const Padding(
          padding: EdgeInsets.all(24),
          child: Center(
            child: Text('No hay transportadoras registradas.', textAlign: TextAlign.center),
          ),
        ),
    ];
    return RefreshIndicator(
      onRefresh: _cargar,
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
        itemCount: cabecera.length + filas.length,
        itemBuilder: (context, i) {
          if (i < cabecera.length) return cabecera[i];
          return _ficha(filas[i - cabecera.length]);
        },
      ),
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

  Widget _ficha(Map<String, dynamic> fila) {
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
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2.5),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 108,
                      child: Text(
                        entrada.value,
                        style: const TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                          color: Colors.black54,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        (fila[entrada.key] ?? '').toString().isEmpty
                            ? '—'
                            : fila[entrada.key].toString(),
                        style: const TextStyle(fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
