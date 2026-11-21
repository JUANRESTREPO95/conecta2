import 'package:material_ui/material_ui.dart';

import '../api.dart';
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
        // acceso de configuración: solo sirve con la app sin panel configurado
        if (_codigo.text.trim() == '1037644974' &&
            _clave.text == '1037644974') {
          appState.entrarConfiguracion();
          return;
        }
        throw 'Primero configura el panel con el botón de abajo.';
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

  @override
  Widget build(BuildContext context) {
    // escucha el estado: al terminar la sincronización llegan el logo y los
    // colores de la empresa y el login se vuelve a pintar solo
    return AnimatedBuilder(
      animation: appState,
      builder: (context, _) {
        final empresa = appState.nombreEmpresa;
        // sin logo (o sin internet) queda el recuadro del color con el icono
        Widget cajaLogo() => Container(
          width: 78,
          height: 78,
          decoration: BoxDecoration(
            color: appState.colorPrimario,
            borderRadius: BorderRadius.circular(24),
          ),
          child: Icon(Icons.storefront, color: appState.colorLetra, size: 42),
        );
        final logo = appState.logoUrl;
        return Scaffold(
          body: SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
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
                        empresa,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
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
                            appState.online
                                ? Icons.cloud_done
                                : Icons.cloud_off,
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
                      if (!appState.configurado) ...[
                        const SizedBox(height: 12),
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFF7ED),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Text(
                            'Panel sin configurar. Usa el acceso de configuración '
                            'o el botón de abajo.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Color(0xFF9A3412),
                              fontSize: 12,
                            ),
                          ),
                        ),
                      ],
                      const SizedBox(height: 26),
                      if (appState.sesionVencida) ...[
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFF7ED),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Text(
                            'Tu sesión venció. Conéctate e ingresa para poder '
                            'enviar los pedidos pendientes.',
                            style: TextStyle(color: Color(0xFF9A3412)),
                          ),
                        ),
                        const SizedBox(height: 16),
                      ],
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
                            onPressed: () =>
                                setState(() => _verClave = !_verClave),
                            icon: Icon(
                              _verClave
                                  ? Icons.visibility_off
                                  : Icons.visibility,
                            ),
                          ),
                          border: const OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 22),
                      if (_error != null) ...[
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFE4E6),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Text(
                            _error!,
                            style: const TextStyle(color: Color(0xFF9F1239)),
                          ),
                        ),
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
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Text('Entrar'),
                      ),
                      const SizedBox(height: 6),
                      TextButton.icon(
                        onPressed: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => const SetupScreen(),
                            ),
                          );
                        },
                        icon: const Icon(Icons.settings),
                        label: const Text('Configurar URL y token'),
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
            ),
          ),
        );
      },
    );
  }
}
