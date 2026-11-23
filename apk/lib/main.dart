import 'package:material_ui/material_ui.dart';

import 'screens/cartera_screen.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/menu_screen.dart';
import 'state.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const Conecta2App());
  // al arrancar se leen las bodegas guardadas y se abre la última usada
  appState.init();
}

class Conecta2App extends StatelessWidget {
  const Conecta2App({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: appState,
      builder: (context, _) {
        return MaterialApp(
          title: 'Conecta2',
          debugShowCheckedModeBanner: false,
          theme: ThemeData(
            useMaterial3: true,
            // el primario exacto de la empresa, no un tono derivado:
            // así el botón del login y los acentos usan el mismo color
            colorScheme: ColorScheme.fromSeed(
              seedColor: appState.colorPrimario,
            ).copyWith(
              primary: appState.colorPrimario,
              onPrimary: appState.colorLetra,
              secondary: appState.colorPrimario,
            ),
            scaffoldBackgroundColor: const Color(0xFFF6F7FB),
          ),
          // este AnimatedBuilder es el que hace que la raíz cambie a Home
          // cuando el login cambia el estado (sin él se queda en Login)
          home: AnimatedBuilder(
            animation: appState,
            // sin const: debe crear una instancia nueva para que _Raiz
            // vuelva a ejecutar su build cuando cambie el estado
            builder: (context, _) => _Raiz(),
          ),
        );
      },
    );
  }
}

class _Raiz extends StatelessWidget {
  const _Raiz();

  /// Pantalla según la sección, sin pasar por el menú cuando solo hay una
  /// sección activa (se apagan desde el panel).
  Widget _pantalla() {
    final pedidos = appState.pedidosActivo;
    final cartera = appState.carteraActiva;
    if (appState.seccion == 'pedidos' && pedidos) return const HomeScreen();
    if (appState.seccion == 'cartera' && cartera) return const CarteraScreen();
    if (pedidos && !cartera) return const HomeScreen();
    if (cartera && !pedidos) return const CarteraScreen();
    return const MenuScreen();
  }

  @override
  Widget build(BuildContext context) {
    if (!appState.iniciado) return const CargandoPantalla();
    // sin bodegas, o con una bodega sin token: siempre al login
    if (appState.bodegas.isEmpty ||
        appState.bodegaActiva == null ||
        !appState.configurado) {
      return const LoginScreen();
    }
    if (appState.appRevocada) {
      return const BloqueoScreen(
        icono: Icons.block,
        titulo: 'App deshabilitada',
        texto: 'El administrador revocó el acceso de esta app.\n'
            'Pide un token nuevo en el panel, en Apps, y agrega la bodega '
            'de nuevo desde el login.',
      );
    }
    if (!appState.online && !appState.puedeOffline) {
      return const BloqueoScreen(
        icono: Icons.wifi_off,
        titulo: 'Necesitas internet',
        texto: 'Pasaron más de 3 días sin descargar datos nuevos.\n'
            'Conéctate a internet para seguir usando la app.',
      );
    }
    if (!appState.logueado) return const LoginScreen();
    return _pantalla();
  }
}

class CargandoPantalla extends StatelessWidget {
  const CargandoPantalla({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 74,
              height: 74,
              decoration: BoxDecoration(
                color: appState.colorPrimario,
                borderRadius: BorderRadius.circular(22),
              ),
              child: const Icon(Icons.shopping_bag,
                  color: Colors.white, size: 42),
            ),
            const SizedBox(height: 22),
            Text('Conecta2',
                style: Theme.of(context)
                    .textTheme
                    .headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 24),
            const CircularProgressIndicator(),
            const SizedBox(height: 14),
            Text(
              appState.paso,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class BloqueoScreen extends StatelessWidget {
  final IconData icono;
  final String titulo;
  final String texto;

  const BloqueoScreen({
    super.key,
    required this.icono,
    required this.titulo,
    required this.texto,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icono, size: 72, color: appState.colorPrimario),
              const SizedBox(height: 22),
              Text(titulo,
                  textAlign: TextAlign.center,
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 12),
              Text(texto,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge),
              const SizedBox(height: 28),
              FilledButton.icon(
                onPressed: () async {
                  await appState.reintentarInicio();
                },
                icon: const Icon(Icons.refresh),
                label: const Text('Reintentar'),
              ),
              if (appState.appRevocada && appState.bodegaActiva != null) ...[
                const SizedBox(height: 8),
                TextButton(
                  onPressed: () =>
                      appState.eliminarBodega(appState.bodegaActiva!.id),
                  child: const Text('Quitar esta bodega'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
