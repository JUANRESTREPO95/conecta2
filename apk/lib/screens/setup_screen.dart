import 'package:material_ui/material_ui.dart';

import '../state.dart';

class SetupScreen extends StatefulWidget {
  const SetupScreen({super.key});

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  final _url = TextEditingController();
  final _token = TextEditingController();
  bool _cargando = false;
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _token.dispose();
    super.dispose();
  }

  Future<void> _conectar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      await appState.agregarBodega(_url.text, _token.text);
      if (mounted && Navigator.canPop(context)) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final aviso = _error ?? appState.mensajeInicio;
    final lleno = !appState.puedeAgregarBodega;
    return Scaffold(
      appBar: AppBar(title: const Text('Agregar bodega')),
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
                    child: Container(
                      width: 78,
                      height: 78,
                      decoration: BoxDecoration(
                        color: appState.colorPrimario,
                        borderRadius: BorderRadius.circular(24),
                      ),
                      child: const Icon(Icons.add_business,
                          color: Colors.white, size: 44),
                    ),
                  ),
                  const SizedBox(height: 22),
                  Text(
                    'Nueva bodega',
                    textAlign: TextAlign.center,
                    style: Theme.of(context)
                        .textTheme
                        .headlineMedium
                        ?.copyWith(fontWeight: FontWeight.w900),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Bodega ${appState.bodegas.length + 1} de '
                    '${AppState.maxBodegas}',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 28),
                  TextField(
                    controller: _url,
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                    decoration: const InputDecoration(
                      labelText: 'URL del panel',
                      hintText: 'https://pedidos.col.lt',
                      prefixIcon: Icon(Icons.link),
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _token,
                    obscureText: true,
                    autocorrect: false,
                    textCapitalization: TextCapitalization.none,
                    keyboardType: TextInputType.visiblePassword,
                    decoration: const InputDecoration(
                      labelText: 'Token de la app',
                      hintText: 'Pégalo desde Apps en el panel',
                      prefixIcon: Icon(Icons.key),
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'El token se genera en el panel, en Apps, y solo se '
                    'muestra una vez.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Necesitas internet para agregarla: se prueba el token y '
                    'se descargan sus datos. Después funcionará también sin '
                    'internet.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 22),
                  if (aviso != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF7ED),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(aviso,
                          style: const TextStyle(color: Color(0xFF9A3412))),
                    ),
                    const SizedBox(height: 16),
                  ],
                  FilledButton(
                    onPressed: (_cargando || lleno) ? null : _conectar,
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                    child: _cargando
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(lleno
                            ? 'Máximo ${AppState.maxBodegas} bodegas'
                            : 'Conectar y descargar datos'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
