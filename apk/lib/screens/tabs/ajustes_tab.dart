import 'package:material_ui/material_ui.dart';

import '../../state.dart';

class AjustesTab extends StatefulWidget {
  const AjustesTab({super.key});

  @override
  State<AjustesTab> createState() => _AjustesTabState();
}

class _AjustesTabState extends State<AjustesTab> {
  int _productos = 0;
  bool _trabajando = false;

  @override
  void initState() {
    super.initState();
    _contar();
  }

  Future<void> _contar() async {
    final n = await appState.db.contarProductos();
    if (mounted) setState(() => _productos = n);
  }

  Future<void> _sincronizar() async {
    setState(() => _trabajando = true);
    try {
      await appState.sincronizar();
      await appState.sincronizarHistorial();
      await appState.procesarCola();
      await _contar();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Datos actualizados')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No se pudo sincronizar: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _trabajando = false);
    }
  }

  Future<void> _borrarDatos() async {
    final seguro = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('¿Borrar los datos descargados?'),
        content: const Text(
            'Se borran el catálogo, los clientes y los pedidos guardados de '
            'esta bodega. La conexión se conserva: al sincronizar se vuelve '
            'a descargar todo.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Borrar datos'),
          ),
        ],
      ),
    );
    if (seguro == true) {
      await appState.borrarDatosLocales();
      await _contar();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Datos borrados')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ultima = appState.ultimaSyncOk;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: appState.colorPrimario,
            borderRadius: BorderRadius.circular(18),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                appState.nombreEmpresa,
                style: TextStyle(
                    color: appState.colorLetra,
                    fontSize: 22,
                    fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 4),
              Text(
                appState.online ? 'En línea' : 'Sin internet',
                style: TextStyle(color: appState.colorLetra),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFE5E7EB)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Bodega',
                  style: TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w800)),
              const SizedBox(height: 8),
              _dato('Nombre', appState.bodegaActiva?.nombre ?? '—'),
              _dato('Panel', appState.baseUrl ?? '—'),
              _dato('Token', appState.configurado ? 'guardado' : 'falta'),
              const SizedBox(height: 6),
              const Text(
                'Para agregar, cambiar o quitar bodegas, cierra sesión: '
                'todo eso se hace desde el login.',
                style: TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        _dato('Vendedor', appState.usuarioNombre ?? '—'),
        _dato('Código', appState.usuarioCodigo ?? '—'),
        _dato('Productos guardados', '$_productos'),
        _dato(
          'Última sincronización',
          ultima == null
              ? '—'
              : '${ultima.day.toString().padLeft(2, '0')}/'
                  '${ultima.month.toString().padLeft(2, '0')}/'
                  '${ultima.year} '
                  '${ultima.hour.toString().padLeft(2, '0')}:'
                  '${ultima.minute.toString().padLeft(2, '0')}',
        ),
        if (appState.mensajeInicio != null) ...[
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFFFF7ED),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(appState.mensajeInicio!,
                style: const TextStyle(color: Color(0xFF9A3412))),
          ),
        ],
        const SizedBox(height: 20),
        FilledButton.icon(
          onPressed: _trabajando ? null : _sincronizar,
          icon: _trabajando
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.sync),
          label: const Text('Sincronizar ahora'),
        ),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          onPressed: () => appState.cerrarSesion(),
          icon: const Icon(Icons.logout),
          label: const Text('Cerrar sesión'),
        ),
        const SizedBox(height: 10),
        TextButton.icon(
          onPressed: _borrarDatos,
          icon: const Icon(Icons.delete_forever, color: Color(0xFFB91C1C)),
          label: const Text('Borrar datos descargados',
              style: TextStyle(color: Color(0xFFB91C1C))),
        ),
        const SizedBox(height: 18),
        const Center(
          child: Text('Conecta2 1.1.0',
              style: TextStyle(fontSize: 12, color: Color(0xFF9CA3AF))),
        ),
      ],
    );
  }

  Widget _dato(String etiqueta, String valor) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150,
            child: Text(etiqueta,
                style: const TextStyle(
                    fontSize: 13, color: Color(0xFF6B7280))),
          ),
          Expanded(
            child: Text(valor,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    fontSize: 13, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}
