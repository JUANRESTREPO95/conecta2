import 'package:material_ui/material_ui.dart';

import '../state.dart';
import 'tabs/ajustes_tab.dart';
import 'tabs/catalogo_tab.dart';
import 'tabs/pedido_tab.dart';
import 'tabs/pedidos_tab.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 4, vsync: this);
    if (appState.online) {
      Future.microtask(() async {
        try {
          await appState.sincronizarHistorial();
          await appState.procesarCola();
        } catch (_) {}
      });
    }
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

  /// Vuelve al login (allí se cambia de bodega).
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
        return Scaffold(
          appBar: AppBar(
            backgroundColor: primario,
            foregroundColor: letra,
            title: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  appState.nombreEmpresa,
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
                Tab(text: 'Catálogo'),
                Tab(text: 'Pedido'),
                Tab(text: 'Pedidos'),
                Tab(text: 'Ajustes'),
              ],
            ),
          ),
          body: TabBarView(
            controller: _tab,
            children: [
              CatalogoTab(onIrAlPedido: () => _tab.animateTo(1)),
              PedidoTab(
                onIrAlCatalogo: () => _tab.animateTo(0),
                onIrAPedidos: () => _tab.animateTo(2),
              ),
              PedidosTab(onIrAlPedido: () => _tab.animateTo(1)),
              const AjustesTab(),
            ],
          ),
        );
      },
    );
  }
}
