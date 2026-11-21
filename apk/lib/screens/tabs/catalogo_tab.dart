import 'dart:async';

import 'package:material_ui/material_ui.dart';

import '../../state.dart';
import 'fila_producto.dart';

class CatalogoTab extends StatefulWidget {
  final VoidCallback onIrAlPedido;

  const CatalogoTab({super.key, required this.onIrAlPedido});

  @override
  State<CatalogoTab> createState() => _CatalogoTabState();
}

class _CatalogoTabState extends State<CatalogoTab> {
  final _buscar = TextEditingController();
  Timer? _debounce;
  List<Map<String, dynamic>> _items = [];
  bool _cargando = true;
  String? _error;
  int _generacion = 0;

  DateTime? _ultimaSync;

  @override
  void initState() {
    super.initState();
    _ultimaSync = appState.ultimaSyncOk;
    appState.addListener(_alCambiarEstado);
    _cargar();
  }

  @override
  void dispose() {
    appState.removeListener(_alCambiarEstado);
    _debounce?.cancel();
    _buscar.dispose();
    super.dispose();
  }

  void _alCambiarEstado() {
    // si terminó una sincronización, refresca la lista con precios/existencias
    final sincronizado = appState.ultimaSyncOk;
    if (sincronizado != null && sincronizado != _ultimaSync) {
      _ultimaSync = sincronizado;
      _cargar();
    }
  }

  Future<void> _cargar() async {
    final generacion = ++_generacion;
    try {
      final items = await appState.db.buscarProductos(
        _buscar.text,
        limite: 150,
        filtro: appState.filtroExistencia,
        minimo: appState.existenciaMinima,
      );
      if (!mounted || generacion != _generacion) return;
      setState(() {
        _items = items;
        _cargando = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _cargando = false;
        _error = e.toString();
      });
    }
  }

  void _cambio() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 250), _cargar);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
          child: TextField(
            controller: _buscar,
            onChanged: (_) => _cambio(),
            decoration: InputDecoration(
              hintText: 'Buscar por código o descripción…',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _buscar.text.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () {
                        _buscar.clear();
                        _cargar();
                      },
                    ),
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide.none,
              ),
            ),
          ),
        ),
        Expanded(
          child: _cargando
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Center(child: Text(_error!))
                  : _items.isEmpty
                      ? const Center(child: Text('Sin productos'))
                      : RefreshIndicator(
                          onRefresh: _cargar,
                          child: ListView.separated(
                            padding: const EdgeInsets.fromLTRB(14, 4, 14, 90),
                            itemCount: _items.length,
                            separatorBuilder: (_, _) =>
                                const SizedBox(height: 8),
                            itemBuilder: (context, i) {
                              final p = _items[i];
                              final codigo = p['codigo']?.toString() ?? '';
                              final existencia =
                                  (p['existencia'] as num?)?.toDouble() ?? 0;
                              final enCarrito = appState.carrito[codigo] ?? 0;
                              return FilaProducto(
                                key: ValueKey(codigo),
                                producto: p,
                                existencia: existencia,
                                cantidad: enCarrito,
                                onFijar: (n) =>
                                    appState.fijarCantidad(codigo, n),
                                onAgregar: () => appState.agregar(codigo),
                                onQuitar: () => appState.quitar(codigo),
                              );
                            },
                          ),
                        ),
        ),
        if (appState.totalUnidades > 0)
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 4, 14, 10),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: widget.onIrAlPedido,
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 15),
                  ),
                  child: Text(
                      'Ver pedido (${appState.totalUnidades} unidades)'),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
