import 'dart:async';

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../../state.dart';
import '../../utils.dart';

class PedidoTab extends StatefulWidget {
  final VoidCallback onIrAlCatalogo;
  final VoidCallback onIrAPedidos;

  const PedidoTab({
    super.key,
    required this.onIrAlCatalogo,
    required this.onIrAPedidos,
  });

  @override
  State<PedidoTab> createState() => _PedidoTabState();
}

class _PedidoTabState extends State<PedidoTab> {
  final _referencia = TextEditingController();
  List<Map<String, dynamic>> _lineas = [];
  List<Map<String, dynamic>> _autorizados = [];
  bool _cargando = true;
  bool _enviando = false;
  String? _error;
  String? _clienteCargado;

  @override
  void initState() {
    super.initState();
    appState.addListener(_alCambiarEstado);
    _cargar();
  }

  @override
  void dispose() {
    appState.removeListener(_alCambiarEstado);
    _referencia.dispose();
    super.dispose();
  }

  void _alCambiarEstado() {
    if (mounted) _cargar();
  }

  Future<void> _cargar() async {
    final salida = <Map<String, dynamic>>[];
    for (final entrada in appState.carrito.entries) {
      final p = await appState.db.producto(entrada.key);
      if (p != null) {
        salida.add({...p, 'cantidad': entrada.value});
      }
    }
    final cliente = appState.clienteSeleccionado;
    final codigoCliente = cliente?['codigo']?.toString();
    List<Map<String, dynamic>> autorizados = _autorizados;
    if (codigoCliente != _clienteCargado) {
      _clienteCargado = codigoCliente;
      autorizados = cliente == null
          ? []
          : await appState.db.autorizadosDe(codigoCliente ?? '');
    }
    if (!mounted) return;
    setState(() {
      _lineas = salida;
      _autorizados = autorizados;
      _cargando = false;
    });
  }

  double get _total =>
      _lineas.fold(0, (suma, l) => suma + (l['precio'] as num) * (l['cantidad'] as num));

  Future<void> _elegirCliente() async {
    final elegido = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _SelectorCliente(),
    );
    if (elegido != null) {
      appState.elegirCliente(elegido);
      _clienteCargado = null;
      await _cargar();
    }
  }

  Future<void> _nuevoCliente() async {
    final resultado = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _ClienteNuevo(),
    );
    if (resultado == null || !mounted) return;
    _clienteCargado = null;
    await _cargar();
    if (!mounted) return;
    final aviso = (resultado['aviso'] ?? '').toString();
    if (aviso.isNotEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(aviso)));
    }
  }

  Future<void> _enviar() async {
    if (_enviando) return;
    setState(() {
      _enviando = true;
      _error = null;
    });
    try {
      final cliente = appState.clienteSeleccionado;
      final autorizado = appState.autorizadoSeleccionado;
      final id = await appState.enviarPedido(
        referencia: _referencia.text,
        clienteCodigo: cliente?['codigo']?.toString(),
        clienteNombre: cliente?['nombre']?.toString(),
        clienteNit: cliente?['nit']?.toString(),
        autorizadoCodigo: autorizado?['codigo']?.toString(),
        autorizadoNombre: autorizado?['nombre']?.toString(),
        autorizadoDireccion: autorizado?['direccion']?.toString(),
      );
      final guardado = await appState.db.pedido(id);
      if (!mounted) return;
      _referencia.clear();
      final numero = guardado?['numero'];
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(numero == null
              ? 'Pedido guardado. Se enviará cuando haya internet.'
              : 'Pedido $numero enviado.'),
        ),
      );
      widget.onIrAPedidos();
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_lineas.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.shopping_cart_outlined,
                size: 64, color: appState.colorPrimario.withAlpha(130)),
            const SizedBox(height: 14),
            const Text('El pedido está vacío'),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: widget.onIrAlCatalogo,
              child: const Text('Ir al catálogo'),
            ),
          ],
        ),
      );
    }
    final cliente = appState.clienteSeleccionado;
    final autorizado = appState.autorizadoSeleccionado;
    final codigoAutorizado = autorizado?['codigo']?.toString();
    final autorizadoEnLista = codigoAutorizado != null &&
        _autorizados.any(
            (a) => a['codigo']?.toString() == codigoAutorizado);
    final faltaCliente = appState.usarClientes && cliente == null;
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(14, 14, 14, 10),
            children: [
              ..._lineas.map((l) {
                final codigo = l['codigo']?.toString() ?? '';
                final cantidad = (l['cantidad'] as num).toInt();
                final precio = (l['precio'] as num).toDouble();
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFFE5E7EB)),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(l['descripcion']?.toString() ?? '',
                                style: const TextStyle(fontWeight: FontWeight.w700)),
                            Text(codigo,
                                style: const TextStyle(
                                    fontSize: 11, color: Color(0xFF6B7280))),
                            Text('\$ ${dinero(precio)}',
                                style: TextStyle(
                                    fontSize: 12,
                                    color: appState.colorPrimario)),
                          ],
                        ),
                      ),
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            visualDensity: VisualDensity.compact,
                            onPressed: () => appState.quitar(codigo),
                            icon: const Icon(Icons.remove_circle_outline),
                          ),
                          Text('$cantidad',
                              style:
                                  const TextStyle(fontWeight: FontWeight.w800)),
                          IconButton(
                            visualDensity: VisualDensity.compact,
                            onPressed: cantidad >=
                                    ((l['existencia'] as num?)
                                                ?.toDouble() ??
                                            0)
                                        .floor()
                                ? null
                                : () => appState.agregar(codigo),
                            icon: const Icon(Icons.add_circle_outline),
                          ),
                          IconButton(
                            visualDensity: VisualDensity.compact,
                            onPressed: () => appState.borrarDelCarrito(codigo),
                            icon: const Icon(Icons.delete_outline,
                                color: Color(0xFFB91C1C)),
                          ),
                        ],
                      ),
                    ],
                  ),
                );
              }),
              const SizedBox(height: 6),
              if (appState.usarClientes) ...[
                Container(
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFFE5E7EB)),
                  ),
                  child: ListTile(
                    leading: Icon(Icons.person, color: appState.colorPrimario),
                    title: Text(
                      cliente?['nombre']?.toString() ?? 'Elegir cliente',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    subtitle: Text(
                      cliente == null
                          ? 'Obligatorio para enviar'
                          : 'NIT ${cliente['nit'] ?? '—'} · ${cliente['codigo']}',
                    ),
                    trailing: TextButton(
                      onPressed: _elegirCliente,
                      child: Text(cliente == null ? 'Elegir' : 'Cambiar'),
                    ),
                  ),
                ),
                if (appState.usarClientesNuevos)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: _nuevoCliente,
                      icon: const Icon(Icons.person_add_alt_1, size: 20),
                      label: const Text('Cliente nuevo'),
                    ),
                  ),
                const SizedBox(height: 10),
                if (appState.usarAutorizados && cliente != null) ...[
                  if (_autorizados.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 4, vertical: 6),
                      child: Text('Este cliente no tiene autorizados en A2.',
                          style: TextStyle(fontSize: 12, color: Color(0xFF6B7280))),
                    )
                  else
                    DropdownButtonFormField<String>(
                      initialValue:
                          autorizadoEnLista ? codigoAutorizado : null,
                      isExpanded: true,
                      itemHeight: 68,
                      decoration: const InputDecoration(
                        labelText: 'Autorizado (opcional)',
                        border: OutlineInputBorder(),
                        filled: true,
                        fillColor: Colors.white,
                      ),
                      items: _autorizados
                          .map((a) => DropdownMenuItem(
                                value: a['codigo']?.toString(),
                                child: SizedBox(
                                  width: double.infinity,
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Text(
                                        a['nombre']?.toString() ?? '',
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w600),
                                      ),
                                      if ((a['direccion'] ?? '')
                                          .toString()
                                          .isNotEmpty)
                                        Text(
                                          a['direccion'].toString(),
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                          style: const TextStyle(
                                              fontSize: 11,
                                              color: Color(0xFF6B7280)),
                                        ),
                                    ],
                                  ),
                                ),
                              ))
                          .toList(),
                      selectedItemBuilder: (context) => _autorizados
                          .map((a) => Align(
                                alignment: Alignment.centerLeft,
                                child: Text(
                                  a['nombre']?.toString() ?? '',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(fontSize: 13),
                                ),
                              ))
                          .toList(),
                      onChanged: (valor) {
                        if (valor == null) {
                          appState.elegirAutorizado(null);
                        } else {
                          appState.elegirAutorizado(_autorizados.firstWhere(
                              (a) => a['codigo']?.toString() == valor));
                        }
                      },
                    ),
                  if (autorizado != null) ...[
                    const SizedBox(height: 8),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: const Color(0xFFE5E7EB)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Autorizado seleccionado',
                            style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                color: Color(0xFF6B7280)),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            autorizado['nombre']?.toString() ?? '',
                            style: const TextStyle(
                                fontWeight: FontWeight.w700),
                          ),
                          if ((autorizado['direccion'] ?? '')
                              .toString()
                              .isNotEmpty) ...[
                            const SizedBox(height: 2),
                            Text(
                              autorizado['direccion'].toString(),
                              style: const TextStyle(fontSize: 13),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: 10),
                ],
              ],
              TextField(
                controller: _referencia,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Referencia (notas del cliente)',
                  border: OutlineInputBorder(),
                  filled: true,
                  fillColor: Colors.white,
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFE4E6),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(_error!,
                      style: const TextStyle(color: Color(0xFF9F1239))),
                ),
              ],
            ],
          ),
        ),
        SafeArea(
          top: false,
          child: Container(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
            decoration: const BoxDecoration(
              color: Colors.white,
              border: Border(top: BorderSide(color: Color(0xFFE5E7EB))),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('Total sin IVA',
                        style: TextStyle(fontWeight: FontWeight.w600)),
                    Text('\$ ${dinero(_total)}',
                        style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w900,
                            color: appState.colorPrimario)),
                  ],
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: (_enviando || faltaCliente) ? null : _enviar,
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 15),
                    ),
                    child: _enviando
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(faltaCliente
                            ? 'Elige el cliente para continuar'
                            : appState.online
                                ? 'Enviar pedido'
                                : 'Guardar para enviar'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _SelectorCliente extends StatefulWidget {
  const _SelectorCliente();

  @override
  State<_SelectorCliente> createState() => _SelectorClienteState();
}

class _SelectorClienteState extends State<_SelectorCliente> {
  final _buscar = TextEditingController();
  Timer? _debounce;
  List<Map<String, dynamic>> _items = [];
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _buscar.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    final items = await appState.db.buscarClientes(_buscar.text);
    if (!mounted) return;
    setState(() {
      _items = items;
      _cargando = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: MediaQuery.of(context).size.height * 0.82,
      child: Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
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
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: TextField(
                controller: _buscar,
                autofocus: true,
                onChanged: (_) {
                  _debounce?.cancel();
                  _debounce =
                      Timer(const Duration(milliseconds: 200), _cargar);
                },
                decoration: const InputDecoration(
                  hintText: 'Buscar por nombre, NIT o código…',
                  prefixIcon: Icon(Icons.search),
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            Expanded(
              child: _cargando
                  ? const Center(child: CircularProgressIndicator())
                  : _items.isEmpty
                      ? const Center(child: Text('Sin clientes'))
                      : ListView.separated(
                          itemCount: _items.length,
                          separatorBuilder: (_, _) =>
                              const Divider(height: 1),
                          itemBuilder: (context, i) {
                            final c = _items[i];
                            return ListTile(
                              title: Text(c['nombre']?.toString() ?? '',
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w600)),
                              subtitle: Text(
                                  'NIT ${c['nit'] ?? '—'} · ${c['codigo']}'),
                              onTap: () => Navigator.pop(context, c),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ClienteNuevo extends StatefulWidget {
  const _ClienteNuevo();

  @override
  State<_ClienteNuevo> createState() => _ClienteNuevoState();
}

class _ClienteNuevoState extends State<_ClienteNuevo> {
  final _nit = TextEditingController();
  final _nombre = TextEditingController();
  final _direccion = TextEditingController();
  final _telefono = TextEditingController();
  bool _guardando = false;
  String? _error;

  @override
  void dispose() {
    _nit.dispose();
    _nombre.dispose();
    _direccion.dispose();
    _telefono.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    final nit = _nit.text.trim();
    final nombre = _nombre.text.trim();
    final direccion = _direccion.text.trim();
    final telefono = _telefono.text.trim();
    if (!RegExp(r'^\d{1,10}$').hasMatch(nit)) {
      setState(() => _error = 'El NIT debe ser solo números (máximo 10).');
      return;
    }
    if (nombre.isEmpty || direccion.isEmpty || telefono.isEmpty) {
      setState(() => _error = 'Nombre, dirección y teléfono son obligatorios.');
      return;
    }
    setState(() {
      _guardando = true;
      _error = null;
    });
    try {
      final r = await appState.crearCliente(
        nit: nit,
        nombre: nombre,
        direccion: direccion,
        telefono: telefono,
      );
      if (!mounted) return;
      Navigator.pop(context, {'aviso': r['aviso']});
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _guardando = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding:
          EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Cliente nuevo',
                  style:
                      TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              const Text('Se guarda en A2 en el próximo ciclo del agente.',
                  style: TextStyle(fontSize: 12, color: Color(0xFF6B7280))),
              const SizedBox(height: 12),
              TextField(
                controller: _nit,
                keyboardType: TextInputType.number,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(10),
                ],
                decoration: const InputDecoration(
                  labelText: 'NIT / Cédula (solo números, máximo 10)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _nombre,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: 'Nombre',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _direccion,
                decoration: const InputDecoration(
                  labelText: 'Dirección',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _telefono,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'Teléfono',
                  border: OutlineInputBorder(),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(_error!,
                    style: const TextStyle(
                        color: Color(0xFFB91C1C),
                        fontWeight: FontWeight.w600)),
              ],
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: TextButton(
                      onPressed:
                          _guardando ? null : () => Navigator.pop(context),
                      child: const Text('Cancelar'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: FilledButton(
                      onPressed: _guardando ? null : _guardar,
                      child: Text(_guardando ? 'Guardando…' : 'Guardar cliente'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
