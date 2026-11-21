import 'package:material_ui/material_ui.dart';

import '../../hoja_app.dart';
import '../../state.dart';
import '../../utils.dart';

class PedidosTab extends StatefulWidget {
  final VoidCallback onIrAlPedido;

  const PedidosTab({super.key, required this.onIrAlPedido});

  @override
  State<PedidosTab> createState() => _PedidosTabState();
}

class _PedidosTabState extends State<PedidosTab> {
  List<Map<String, dynamic>> _pedidos = [];
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    appState.addListener(_alCambiarEstado);
    _cargar();
    if (appState.online) {
      Future.microtask(() async {
        try {
          await appState.sincronizarHistorial();
        } catch (_) {}
        await _cargar();
      });
    }
  }

  @override
  void dispose() {
    appState.removeListener(_alCambiarEstado);
    super.dispose();
  }

  void _alCambiarEstado() {
    if (mounted) _cargar();
  }

  Future<void> _cargar() async {
    final lista = await appState.db.pedidos(appState.usuarioCodigo ?? '');
    if (!mounted) return;
    setState(() {
      _pedidos = lista;
      _cargando = false;
    });
  }

  Future<void> _refrescar() async {
    try {
      await appState.sincronizarHistorial();
      await appState.procesarCola();
    } catch (_) {}
    await _cargar();
  }

  ({String texto, Color color}) _estado(String estado) {
    switch (estado) {
      case 'por_enviar':
        return (texto: 'Por enviar', color: const Color(0xFFB45309));
      case 'montado':
        return (texto: 'Montado en A2', color: const Color(0xFF15803D));
      case 'error':
        return (texto: 'Error', color: const Color(0xFFB91C1C));
      default:
        return (texto: 'Enviado', color: const Color(0xFF1D4ED8));
    }
  }

  Future<void> _detalle(Map<String, dynamic> pedido) async {
    final lineas = await appState.db.lineasDe(pedido['uuid'] as String);
    if (!mounted) return;
    final estado = _estado(pedido['estado']?.toString() ?? '');
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => SizedBox(
        height: MediaQuery.of(context).size.height * 0.8,
        child: Column(
          children: [
            Container(
              width: 42,
              height: 4,
              margin: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFFD1D5DB),
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
                children: [
                  Text(
                    pedido['numero']?.toString() ?? 'Pedido por enviar',
                    style: const TextStyle(
                        fontSize: 22, fontWeight: FontWeight.w900),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 9, vertical: 4),
                        decoration: BoxDecoration(
                          color: estado.color.withAlpha(28),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(estado.texto,
                            style: TextStyle(
                                color: estado.color,
                                fontSize: 12,
                                fontWeight: FontWeight.w800)),
                      ),
                      const SizedBox(width: 10),
                      Text(fechaCorta(pedido['creado']?.toString()),
                          style: const TextStyle(
                              fontSize: 12, color: Color(0xFF6B7280))),
                    ],
                  ),
                  const SizedBox(height: 14),
                  if ((pedido['cliente_nombre'] ?? '') != '')
                    Text(
                        'Cliente: ${pedido['cliente_nombre']} '
                        '(${pedido['cliente_nit'] ?? '—'})'),
                  if ((pedido['autorizado_nombre'] ?? '') != '')
                    Text(
                        'Autorizado: ${pedido['autorizado_nombre']} — '
                        '${pedido['autorizado_direccion'] ?? ''}'),
                  if ((pedido['referencia'] ?? '') != '')
                    Text('Referencia: ${pedido['referencia']}'),
                  const SizedBox(height: 14),
                  ...lineas.map((l) => Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Row(
                          children: [
                            Expanded(
                                child: Text(
                                    '${l['cantidad']} × ${l['descripcion']}')),
                            Text('\$ ${dinero((l['precio'] as num?) ?? 0)}'),
                          ],
                        ),
                      )),
                  const Divider(),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Total sin IVA',
                          style: TextStyle(fontWeight: FontWeight.w700)),
                      Text('\$ ${dinero((pedido['total'] as num?) ?? 0)}',
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w900)),
                    ],
                  ),
                  if ((pedido['ultimo_error'] ?? '') != '' &&
                      pedido['estado'] != 'montado') ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFE4E6),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text('${pedido['ultimo_error']}',
                          style: const TextStyle(color: Color(0xFF9F1239))),
                    ),
                  ],
                  const SizedBox(height: 16),
                  if (pedido['estado'] == 'por_enviar')
                    FilledButton.icon(
                      onPressed: () async {
                        Navigator.pop(context);
                        await appState.procesarCola();
                        await _cargar();
                      },
                      icon: const Icon(Icons.upload),
                      label: const Text('Reintentar envío ahora'),
                    ),
                  if (pedido['estado'] != 'por_enviar') ...[
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: () async {
                        await appState.cargarCarrito(lineas);
                        if (mounted) Navigator.pop(context);
                        widget.onIrAlPedido();
                      },
                      icon: const Icon(Icons.replay),
                      label: const Text('Reenviar (cargar en el carrito)'),
                    ),
                  ],
                  if ((pedido['numero'] ?? '').toString().isNotEmpty) ...[
                    const SizedBox(height: 8),
                    FilledButton.icon(
                      onPressed: () async {
                        try {
                          await HojaApp.compartir(pedido);
                        } catch (e) {
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                  content: Text(
                                      'No se pudo generar la hoja: $e')),
                            );
                          }
                        }
                      },
                      icon: const Icon(Icons.picture_as_pdf),
                      label: const Text('Compartir hoja PDF (WhatsApp)'),
                    ),
                  ] else
                    const Padding(
                      padding: EdgeInsets.only(top: 10),
                      child: Text(
                        'La hoja se podrá compartir cuando el pedido tenga número.',
                        style: TextStyle(
                            fontSize: 12, color: Color(0xFF6B7280)),
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

  @override
  Widget build(BuildContext context) {
    if (_cargando) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: _refrescar,
      child: Column(
        children: [
          if (appState.sesionVencida)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              color: const Color(0xFFFFF7ED),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Tu sesión venció: los pedidos guardados no se han podido '
                    'enviar. Inicia sesión otra vez para enviarlos.',
                    style: TextStyle(color: Color(0xFF9A3412)),
                  ),
                  const SizedBox(height: 6),
                  TextButton(
                    onPressed: () => appState.cerrarSesion(),
                    child: const Text('Iniciar sesión'),
                  ),
                ],
              ),
            ),
          Expanded(
            child: _pedidos.isEmpty
                ? ListView(
                    children: const [
                      SizedBox(height: 120),
                      Center(child: Text('Todavía no hay pedidos')),
                    ],
                  )
                : ListView.separated(
                    padding: const EdgeInsets.all(14),
                    itemCount: _pedidos.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 8),
                    itemBuilder: (context, i) {
                      final p = _pedidos[i];
                      final estado =
                          _estado(p['estado']?.toString() ?? '');
                      return InkWell(
                        onTap: () => _detalle(p),
                        borderRadius: BorderRadius.circular(14),
                        child: Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(color: const Color(0xFFE5E7EB)),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      p['numero']?.toString() ?? 'Por enviar',
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w800),
                                    ),
                                  ),
                                  Text(
                                    '\$ ${dinero((p['total'] as num?) ?? 0)}',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w800,
                                        color: appState.colorPrimario),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Text(
                                [
                                  p['cliente_nombre'],
                                  p['referencia'],
                                  fechaCorta(p['creado']?.toString()),
                                ]
                                    .where((x) =>
                                        x != null && x.toString().isNotEmpty)
                                    .join(' · '),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontSize: 12, color: Color(0xFF6B7280)),
                              ),
                              const SizedBox(height: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 9, vertical: 3),
                                decoration: BoxDecoration(
                                  color: estado.color.withAlpha(28),
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: Text(estado.texto,
                                    style: TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w800,
                                        color: estado.color)),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
