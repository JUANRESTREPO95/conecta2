import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../../state.dart';
import '../../utils.dart';

/// Fila del catálogo: cantidad editable, − y +, sin pasar del stock.
class FilaProducto extends StatefulWidget {
  final Map<String, dynamic> producto;
  final double existencia;
  final int cantidad;
  final ValueChanged<int> onFijar;
  final VoidCallback onAgregar;
  final VoidCallback onQuitar;

  const FilaProducto({
    super.key,
    required this.producto,
    required this.existencia,
    required this.cantidad,
    required this.onFijar,
    required this.onAgregar,
    required this.onQuitar,
  });

  @override
  State<FilaProducto> createState() => _FilaProductoState();
}

class _FilaProductoState extends State<FilaProducto> {
  late final TextEditingController _control;
  final FocusNode _foco = FocusNode();

  int get _maximo => widget.existencia.floor();

  @override
  void initState() {
    super.initState();
    _control = TextEditingController(
        text: widget.cantidad > 0 ? '${widget.cantidad}' : '');
    _foco.addListener(_alCambiarFoco);
  }

  void _alCambiarFoco() {
    if (!_foco.hasFocus) _confirmar();
  }

  @override
  void didUpdateWidget(covariant FilaProducto oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!_foco.hasFocus && widget.cantidad != oldWidget.cantidad) {
      _control.text = widget.cantidad > 0 ? '${widget.cantidad}' : '';
    }
  }

  @override
  void dispose() {
    _foco.removeListener(_alCambiarFoco);
    _foco.dispose();
    _control.dispose();
    super.dispose();
  }

  void _confirmar() {
    final n = int.tryParse(_control.text.trim()) ?? 0;
    final valor = n.clamp(0, _maximo);
    if (n > _maximo && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_maximo <= 0
              ? 'No hay existencia de este producto.'
              : 'Solo hay $_maximo en existencia.'),
        ),
      );
    }
    _control.text = valor > 0 ? '$valor' : '';
    if (valor != widget.cantidad) widget.onFijar(valor);
  }

  void _sumar() {
    _foco.unfocus();
    if (widget.cantidad < _maximo) widget.onAgregar();
  }

  void _restar() {
    _foco.unfocus();
    if (widget.cantidad > 0) widget.onQuitar();
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.producto;
    final precio = (p['precio'] as num?)?.toDouble() ?? 0;
    final primario = appState.colorPrimario;
    final agotado = _maximo <= 0;
    final enTope = widget.cantidad >= _maximo;
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      p['descripcion']?.toString() ?? '',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${p['codigo']} · '
                      '${agotado ? 'Agotado' : 'Stock ${widget.existencia.toStringAsFixed(0)}'}',
                      style: TextStyle(
                        fontSize: 12,
                        color: agotado
                            ? const Color(0xFFB91C1C)
                            : const Color(0xFF4B5563),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Text(
                '\$ ${dinero(precio)}',
                style: TextStyle(
                    fontWeight: FontWeight.w800, color: primario),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: 'Quitar uno',
                onPressed: widget.cantidad > 0 ? _restar : null,
                icon: const Icon(Icons.remove_circle_outline),
              ),
              SizedBox(
                width: 68,
                child: TextField(
                  controller: _control,
                  focusNode: _foco,
                  enabled: !agotado,
                  textAlign: TextAlign.center,
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.done,
                  inputFormatters: [
                    FilteringTextInputFormatter.digitsOnly
                  ],
                  onSubmitted: (_) {
                    _confirmar();
                    _foco.unfocus();
                  },
                  onTapOutside: (_) => _foco.unfocus(),
                  style: const TextStyle(fontWeight: FontWeight.w800),
                  decoration: const InputDecoration(
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(vertical: 8),
                    hintText: '0',
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: 'Agregar uno',
                onPressed: (!agotado && !enTope) ? _sumar : null,
                icon: Icon(
                  Icons.add_circle,
                  color: (!agotado && !enTope)
                      ? primario
                      : const Color(0xFF9CA3AF),
                ),
              ),
              const Spacer(),
              if (widget.cantidad > 0)
                Text(
                  'En pedido: ${widget.cantidad}',
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: primario),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
