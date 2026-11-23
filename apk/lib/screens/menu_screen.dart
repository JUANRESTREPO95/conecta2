import 'package:material_ui/material_ui.dart';

import '../state.dart';

/// Menú principal después del login: Pedidos o Cartera.
/// No consulta nada al panel: funciona sin internet.
class MenuScreen extends StatelessWidget {
  const MenuScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: appState,
      builder: (context, _) {
        final logo = appState.logoUrl;
        return Scaffold(
          body: SafeArea(
            child: Stack(
              children: [
                Center(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(24),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 460),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Center(
                            child: logo == null
                                ? _cajaLogo()
                                : SizedBox(
                                    height: 104,
                                    child: Image.network(
                                      logo,
                                      fit: BoxFit.contain,
                                      errorBuilder: (_, _, _) => _cajaLogo(),
                                    ),
                                  ),
                          ),
                          const SizedBox(height: 18),
                          Text(
                            appState.nombreEmpresa,
                            textAlign: TextAlign.center,
                            style: Theme.of(context)
                                .textTheme
                                .headlineSmall
                                ?.copyWith(fontWeight: FontWeight.w900),
                          ),
                          const SizedBox(height: 6),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                appState.online
                                    ? Icons.cloud_done
                                    : Icons.cloud_off,
                                size: 15,
                                color: appState.online
                                    ? const Color(0xFF15803D)
                                    : const Color(0xFFB45309),
                              ),
                              const SizedBox(width: 5),
                              Text(
                                appState.online
                                    ? 'Conectado'
                                    : 'Trabajando sin internet',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ],
                          ),
                          const SizedBox(height: 30),
                          _tarjeta(
                            titulo: 'Pedidos',
                            subtitulo: 'Catálogo, carrito y pedidos',
                            icono: Icons.receipt_long,
                            color: appState.colorPrimario,
                            onTap: appState.irAPedidos,
                          ),
                          const SizedBox(height: 14),
                          _tarjeta(
                            titulo: 'Cartera',
                            subtitulo: 'Saldos de tus clientes',
                            icono: Icons.account_balance_wallet,
                            color: appState.colorCartera,
                            onTap: appState.irACartera,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                // cerrar sesión: solo el ícono, sin barra
                Align(
                  alignment: Alignment.topRight,
                  child: Padding(
                    padding: const EdgeInsets.only(top: 4, right: 6),
                    child: IconButton(
                      tooltip: 'Cerrar sesión',
                      onPressed: () => appState.cerrarSesion(),
                      icon: Icon(Icons.logout, color: appState.colorPrimario),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _cajaLogo() {
    return Container(
      width: 96,
      height: 96,
      decoration: BoxDecoration(
        color: appState.colorPrimario,
        borderRadius: BorderRadius.circular(26),
      ),
      child: Icon(Icons.storefront, color: appState.colorLetra, size: 48),
    );
  }

  Widget _tarjeta({
    required String titulo,
    required String subtitulo,
    required IconData icono,
    required Color color,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: const Color(0xFFE5E7EB)),
          ),
          child: Row(
            children: [
              Container(
                width: 54,
                height: 54,
                decoration: BoxDecoration(
                  color: color.withAlpha(28),
                  borderRadius: BorderRadius.circular(15),
                ),
                child: Icon(icono, color: color, size: 29),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      titulo,
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitulo,
                      style: const TextStyle(
                          fontSize: 12, color: Color(0xFF6B7280)),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: color),
            ],
          ),
        ),
      ),
    );
  }
}
