import 'package:material_ui/material_ui.dart';

import '../state.dart';
import 'tabs/ajustes_tab.dart';

/// Cartera de la empresa. Por ahora el apartado queda listo (vacío) con
/// Ajustes en la misma posición que en Pedidos; los datos se conectarán
/// al panel más adelante. Funciona sin internet.
class CarteraScreen extends StatefulWidget {
  const CarteraScreen({super.key});

  @override
  State<CarteraScreen> createState() => _CarteraScreenState();
}

class _CarteraScreenState extends State<CarteraScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  Future<void> _sincronizar() async {
    try {
      await appState.sincronizar();
      await appState.sincronizarHistorial();
      await appState.procesarCola();
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
    }
  }

  Future<void> _salir() async {
    await appState.cerrarSesion();
  }

  @override
  Widget build(BuildContext context) {
    final primario = appState.colorPrimario;
    final letra = appState.colorLetra;
    return AnimatedBuilder(
      animation: appState,
      builder: (context, _) {
        return PopScope(
          canPop: false,
          onPopInvokedWithResult: (didPop, _) {
            if (!didPop) appState.irAlMenu();
          },
          child: Scaffold(
            appBar: AppBar(
              backgroundColor: primario,
              foregroundColor: letra,
              leading: IconButton(
                tooltip: 'Menú',
                onPressed: appState.irAlMenu,
                icon: const Icon(Icons.arrow_back),
              ),
              title: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${appState.nombreEmpresa} Cartera',
                    style: const TextStyle(
                        fontSize: 18, fontWeight: FontWeight.w800),
                  ),
                  Row(
                    children: [
                      Icon(
                        appState.online ? Icons.cloud_done : Icons.cloud_off,
                        size: 13,
                        color: letra,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        appState.online ? 'En línea' : 'Sin internet',
                        style: TextStyle(fontSize: 11, color: letra),
                      ),
                    ],
                  ),
                ],
              ),
              actions: [
                IconButton(
                  tooltip: 'Sincronizar',
                  onPressed: appState.sincronizando ? null : _sincronizar,
                  icon: appState.sincronizando
                      ? SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: letra),
                        )
                      : const Icon(Icons.sync),
                ),
                IconButton(
                  tooltip: 'Cerrar sesión',
                  onPressed: _salir,
                  icon: const Icon(Icons.logout),
                ),
              ],
              bottom: TabBar(
                controller: _tab,
                labelColor: letra,
                unselectedLabelColor: letra.withAlpha(170),
                indicatorColor: letra,
                tabs: const [
                  Tab(text: 'Cartera'),
                  Tab(text: 'Ajustes'),
                ],
              ),
            ),
            body: TabBarView(
              controller: _tab,
              children: [
                _carteraVacia(),
                const AjustesTab(),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _carteraVacia() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.account_balance_wallet,
                size: 64, color: appState.colorPrimario.withAlpha(150)),
            const SizedBox(height: 16),
            Text(
              'Cartera',
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Text(
              'Aquí verás los saldos de tus clientes. Se conectará con el '
              'panel cuando esté listo.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }
}
