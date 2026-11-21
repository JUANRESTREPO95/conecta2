import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../bodega.dart';
import '../state.dart';
import 'setup_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _codigo = TextEditingController();
  final _clave = TextEditingController();
  bool _cargando = false;
  bool _verClave = false;
  String? _error;

  @override
  void dispose() {
    _codigo.dispose();
    _clave.dispose();
    super.dispose();
  }

  Future<void> _entrar() async {
    FocusScope.of(context).unfocus();
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      if (!appState.configurado) {
        throw 'Esta bodega no tiene token. Elimínala y agrégala otra vez.';
      }
      if (!appState.online) {
        // sin conexión: primero los datos locales (respuesta inmediata)
        try {
          await appState.loginOffline(_codigo.text, _clave.text);
          return;
        } catch (_) {
          // no hay usuario local: intenta en línea por si la red volvió
        }
      }
      try {
        await appState.login(
          _codigo.text,
          _clave.text,
          timeout: appState.online
              ? const Duration(seconds: 90)
              : const Duration(seconds: 6),
        );
        if (!appState.logueado) {
          throw 'El panel respondió, pero no devolvió el usuario.';
        }
        return;
      } on ApiException catch (e) {
        if (e.status == 401) rethrow;
        // panel inalcanzable o sin los endpoints: probar con lo guardado
        try {
          await appState.loginOffline(_codigo.text, _clave.text);
          return;
        } catch (_) {
          throw e;
        }
      } catch (_) {
        await appState.loginOffline(_codigo.text, _clave.text);
        return;
      }
    } catch (e) {
      if (mounted) {
        final texto = e.toString();
        setState(() => _error = texto);
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(texto)));
      }
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  // ---------- bodegas ----------

  Future<void> _elegir(Bodega b) async {
    if (appState.bodegaActiva?.id == b.id) return;
    _codigo.clear();
    _clave.clear();
    setState(() {
      _error = null;
      _verClave = false;
    });
    await appState.seleccionarBodega(b.id);
  }

  Future<void> _agregar() async {
    if (!appState.puedeAgregarBodega) {
      _aviso('Máximo ${AppState.maxBodegas} bodegas');
      return;
    }
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const SetupScreen()),
    );
    if (mounted) {
      _codigo.clear();
      _clave.clear();
      setState(() => _error = null);
    }
  }

  Future<void> _menuBodega(Bodega b) async {
    final accion = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.storefront),
              title: Text(b.nombre),
              subtitle: Text(
                b.url,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              dense: true,
            ),
            const Divider(height: 1),
            ListTile(
              leading: const Icon(Icons.edit),
              title: const Text('Renombrar'),
              onTap: () => Navigator.pop(ctx, 'renombrar'),
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline,
                  color: Color(0xFFB91C1C)),
              title: const Text('Eliminar bodega',
                  style: TextStyle(color: Color(0xFFB91C1C))),
              onTap: () => Navigator.pop(ctx, 'eliminar'),
            ),
            ListTile(
              leading: const Icon(Icons.close),
              title: const Text('Cancelar'),
              onTap: () => Navigator.pop(ctx),
            ),
          ],
        ),
      ),
    );
    if (!mounted || accion == null) return;
    if (accion == 'renombrar') await _renombrar(b);
    if (accion == 'eliminar') await _eliminar(b);
  }

  Future<void> _renombrar(Bodega b) async {
    final ctrl = TextEditingController(text: b.nombre);
    final nombre = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Renombrar bodega'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(
            labelText: 'Nombre de la bodega',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, ctrl.text),
            child: const Text('Guardar'),
          ),
        ],
      ),
    );
    ctrl.dispose();
    if (nombre != null && nombre.trim().isNotEmpty) {
      await appState.renombrarBodega(b.id, nombre);
    }
  }

  Future<void> _eliminar(Bodega b) async {
    final seguro = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Eliminar bodega'),
        content: Text(
          'Se borrarán del teléfono el catálogo, los clientes y los pedidos '
          'guardados de "${b.nombre}". Los pedidos que ya se enviaron al '
          'panel no se tocan.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Eliminar'),
          ),
        ],
      ),
    );
    if (seguro == true) {
      await appState.eliminarBodega(b.id);
      if (mounted) {
        _codigo.clear();
        _clave.clear();
        setState(() => _error = null);
      }
    }
  }

  void _aviso(String texto) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(texto)));
  }

  // ---------- interfaz ----------

  @override
  Widget build(BuildContext context) {
    // escucha el estado: al cambiar de bodega o terminar la sincronización
    // llegan el logo y los colores y la pantalla se vuelve a pintar
    return AnimatedBuilder(
      animation: appState,
      builder: (context, _) {
        final vacio = appState.bodegas.isEmpty;
        return Scaffold(
          body: SafeArea(
            child: Column(
              children: [
                const SizedBox(height: 8),
                _filaBodegas(),
                Expanded(child: vacio ? _sinBodegas() : _formulario()),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _filaBodegas() {
    if (appState.bodegas.isEmpty) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
        child: SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: _agregar,
            icon: const Icon(Icons.add_business),
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
            label: const Text('Agregar bodega'),
          ),
        ),
      );
    }
    return SizedBox(
      height: 46,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        children: [
          for (final b in appState.bodegas)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: _chipBodega(b),
            ),
          if (appState.puedeAgregarBodega) _chipAgregar(),
        ],
      ),
    );
  }

  Widget _chipBodega(Bodega b) {
    final activa = appState.bodegaActiva?.id == b.id;
    return GestureDetector(
      onTap: () => _elegir(b),
      onLongPress: () => _menuBodega(b),
      child: Container(
        alignment: Alignment.center,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          color: activa ? appState.colorPrimario : Colors.white,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
            color: activa
                ? appState.colorPrimario
                : const Color(0xFFD1D5DB),
            width: 1.5,
          ),
        ),
        child: Text(
          b.nombre,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: activa ? appState.colorLetra : const Color(0xFF374151),
            fontWeight: FontWeight.w700,
            fontSize: 13,
          ),
        ),
      ),
    );
  }

  Widget _chipAgregar() {
    return GestureDetector(
      onTap: _agregar,
      child: Container(
        width: 46,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: const Color(0xFFD1D5DB), width: 1.5),
        ),
        child: const Icon(Icons.add, size: 20, color: Color(0xFF374151)),
      ),
    );
  }

  Widget _sinBodegas() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.store_mall_directory,
                size: 64, color: appState.colorPrimario.withAlpha(180)),
            const SizedBox(height: 16),
            Text(
              'Configura tu primera bodega',
              textAlign: TextAlign.center,
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Text(
              'Necesitas internet y el token de la app que se genera en el '
              'panel (Apps). Después de descargar sus datos, esta bodega '
              'funciona también sin internet.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }

  Widget _formulario() {
    final logo = appState.logoUrl;
    Widget cajaLogo() => Container(
          width: 78,
          height: 78,
          decoration: BoxDecoration(
            color: appState.colorPrimario,
            borderRadius: BorderRadius.circular(24),
          ),
          child: Icon(Icons.storefront, color: appState.colorLetra, size: 42),
        );
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: logo == null
                    ? cajaLogo()
                    : SizedBox(
                        height: 96,
                        child: Image.network(
                          logo,
                          fit: BoxFit.contain,
                          errorBuilder: (_, _, _) => cajaLogo(),
                        ),
                      ),
              ),
              const SizedBox(height: 20),
              Text(
                appState.nombreEmpresa,
                textAlign: TextAlign.center,
                style: Theme.of(context)
                    .textTheme
                    .headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w900),
              ),
              if ((appState.baseUrl ?? '').isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  appState.baseUrl!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      fontSize: 11, color: Color(0xFF6B7280)),
                ),
              ],
              const SizedBox(height: 4),
              Text(
                appState.online
                    ? 'Ingresa con tu código de vendedor'
                    : 'Sin internet: ingresa con tus datos guardados',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    appState.online ? Icons.cloud_done : Icons.cloud_off,
                    size: 16,
                    color: appState.online
                        ? const Color(0xFF15803D)
                        : const Color(0xFFB45309),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    appState.online
                        ? 'Conectado'
                        : 'Trabajando sin internet',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
              if (appState.sesionVencida) ...[
                const SizedBox(height: 16),
                _avisoCaja(
                  'Tu sesión venció. Conéctate e ingresa para poder enviar '
                  'los pedidos pendientes.',
                ),
              ],
              const SizedBox(height: 24),
              TextField(
                controller: _codigo,
                autocorrect: false,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'Código de vendedor',
                  prefixIcon: Icon(Icons.person),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _clave,
                obscureText: !_verClave,
                onSubmitted: (_) => _cargando ? null : _entrar(),
                decoration: InputDecoration(
                  labelText: 'Clave',
                  prefixIcon: const Icon(Icons.lock),
                  suffixIcon: IconButton(
                    onPressed: () => setState(() => _verClave = !_verClave),
                    icon: Icon(
                      _verClave ? Icons.visibility_off : Icons.visibility,
                    ),
                  ),
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 22),
              if (_error != null) ...[
                _avisoCaja(_error!, rojo: true),
                const SizedBox(height: 16),
              ],
              FilledButton(
                onPressed: _cargando ? null : _entrar,
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                child: _cargando
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Entrar'),
              ),
              if (!appState.online) ...[
                const SizedBox(height: 12),
                TextButton.icon(
                  onPressed: () async {
                    setState(() => _error = null);
                    await appState.reintentarInicio();
                  },
                  icon: const Icon(Icons.refresh),
                  label: const Text('Buscar conexión'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _avisoCaja(String texto, {bool rojo = false}) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: rojo ? const Color(0xFFFFE4E6) : const Color(0xFFFFF7ED),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        texto,
        style: TextStyle(
          color: rojo ? const Color(0xFF9F1239) : const Color(0xFF9A3412),
        ),
      ),
    );
  }
}
