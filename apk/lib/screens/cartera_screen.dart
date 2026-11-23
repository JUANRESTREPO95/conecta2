import 'dart:convert';

import 'package:material_ui/material_ui.dart';

import '../state.dart';
import 'tabs/ajustes_tab.dart';

/// Cartera de la empresa: la misma información que el panel.
/// Muestra total, búsqueda, filtros y los registros del vendedor.
/// Sin internet enseña la última copia guardada.
class CarteraScreen extends StatefulWidget {
  const CarteraScreen({super.key});

  @override
  State<CarteraScreen> createState() => _CarteraScreenState();
}

class _CarteraScreenState extends State<CarteraScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tab;
  final TextEditingController _buscar = TextEditingController();
  final Map<int, String> _filtros = {};

  Map<String, dynamic>? _datos;
  bool _cargando = true;
  bool _desdeCache = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
    Future.microtask(_cargar);
  }

  @override
  void dispose() {
    _tab.dispose();
    _buscar.dispose();
    super.dispose();
  }

  // ---------- datos ----------

  Future<void> _cargar() async {
    final api = appState.api;
    if (api == null) {
      if (mounted) {
        setState(() {
          _cargando = false;
          _error = 'Falta configurar la app.';
        });
      }
      return;
    }
    if (mounted) {
      setState(() {
        _cargando = true;
        _error = null;
      });
    }
    try {
      final datos = await api.get(
        '/api/app/cartera',
        timeout: const Duration(seconds: 90),
      );
      try {
        await appState.db.setConfig('cartera_cache', jsonEncode(datos));
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _datos = datos;
        _desdeCache = false;
        _cargando = false;
        _filtros.clear();
      });
    } catch (e) {
      String? guardado;
      try {
        guardado = await appState.db.getConfig('cartera_cache');
      } catch (_) {}
      if (guardado != null && guardado.isNotEmpty) {
        try {
          final cache = jsonDecode(guardado);
          if (cache is Map<String, dynamic> && mounted) {
            setState(() {
              _datos = cache;
              _desdeCache = true;
              _cargando = false;
              _error = e.toString();
              _filtros.clear();
            });
            return;
          }
        } catch (_) {}
      }
      if (!mounted) return;
      setState(() {
        _cargando = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _sincronizar() async {
    try {
      await appState.sincronizar();
      await appState.sincronizarHistorial();
      await appState.procesarCola();
    } catch (_) {}
    await _cargar();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_desdeCache
              ? 'Sin conexión: se muestra la última copia'
              : 'Datos actualizados'),
        ),
      );
    }
  }

  Future<void> _salir() async {
    await appState.cerrarSesion();
  }

  // ---------- pantalla ----------

  @override
  Widget build(BuildContext context) {
    // Cartera tiene su propio color de panel; la letra es la misma
    final primario = appState.colorCartera;
    final letra = appState.colorLetra;
    // todo lo que se dibuja dentro de Cartera (botones, campos, acentos)
    // usa el color de cartera, no el de Pedidos
    final tema = Theme.of(context).copyWith(
      colorScheme: Theme.of(context).colorScheme.copyWith(
        primary: primario,
        onPrimary: letra,
      ),
    );
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
                  onPressed: (appState.sincronizando || _cargando)
                      ? null
                      : _sincronizar,
                  icon: (appState.sincronizando || _cargando)
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
            body: Theme(
              data: tema,
              child: TabBarView(
                controller: _tab,
                children: [
                  _cartera(),
                  const AjustesTab(),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _cartera() {
    if (_cargando && _datos == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final datos = _datos;
    if (datos == null) {
      return _aviso();
    }
    final columnas = _lista(datos['columnas']);
    if (columnas.isEmpty) {
      return _aviso(
        mensaje: datos['hay_enlace'] == true
            ? 'La cartera todavía no tiene columnas configuradas.\n'
                'El administrador la configura en el panel.'
            : 'La cartera todavía no está configurada.\n'
                'El administrador la activa en el panel.',
      );
    }

    final todas = (datos['filas'] as List? ?? const []);
    final filtros = (datos['filtros'] as List? ?? const [])
        .whereType<Map>()
        .map((f) => f.cast<String, dynamic>())
        .toList();

    // prepara cada registro una sola vez
    final registros = <Map<String, dynamic>>[];
    for (final cruda in todas) {
      if (cruda is! Map) continue;
      final fila = cruda.cast<String, dynamic>();
      registros.add({
        'celdas': _lista(fila['celdas']),
        'valores': _lista(fila['filtros']),
        'saldo': fila['saldo'],
      });
    }
    final q = _normal(_buscar.text);

    // filtros en cascada: cada desplegable solo ofrece los valores que
    // existen con los otros filtros y la búsqueda aplicados
    bool pasa(Map<String, dynamic> reg, int sinIndice) {
      final celdas = reg['celdas'] as List<String>;
      if (q.isNotEmpty && !_normal(celdas.join(' ')).contains(q)) return false;
      final valores = reg['valores'] as List<String>;
      for (var i = 0; i < filtros.length; i++) {
        if (i == sinIndice) continue;
        final elegido = _filtros[i] ?? '';
        if (elegido.isEmpty) continue;
        if (i >= valores.length || valores[i] != elegido) return false;
      }
      return true;
    }

    var opciones = <int, List<String>>{};
    for (var vuelta = 0; vuelta < 2; vuelta++) {
      opciones = {};
      for (var i = 0; i < filtros.length; i++) {
        final hay = <String>{};
        for (final reg in registros) {
          if (!pasa(reg, i)) continue;
          final valores = reg['valores'] as List<String>;
          if (i < valores.length && valores[i].isNotEmpty) {
            hay.add(valores[i]);
          }
        }
        // conserva el orden que trae la hoja
        final base = _lista(filtros[i]['opciones']);
        opciones[i] = base.where(hay.contains).toList();
      }
      // lo elegido que ya no existe con los demás filtros se suelta
      for (var i = 0; i < filtros.length; i++) {
        final actual = _filtros[i] ?? '';
        if (actual.isNotEmpty && !(opciones[i] ?? const []).contains(actual)) {
          _filtros[i] = '';
        }
      }
    }

    final visibles = <Map<String, dynamic>>[];
    for (final reg in registros) {
      if (pasa(reg, -1)) visibles.add(reg);
    }

    var total = 0.0;
    for (final f in visibles) {
      final saldo = f['saldo'];
      if (saldo is num) total += saldo.toDouble();
    }
    final mostrarTotal =
        datos['hay_saldo'] == true && datos['mostrar_total'] == true;
    final actualizado = (datos['actualizado'] ?? '').toString();

    final cabecera = <Widget>[
      if (mostrarTotal) _total(total),
      Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: TextField(
          controller: _buscar,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(
            hintText: 'Buscar en la cartera…',
            prefixIcon: Icon(Icons.search),
            border: OutlineInputBorder(),
            isDense: true,
          ),
        ),
      ),
      if (filtros.isNotEmpty) _filtrosWidget(filtros, opciones),
      if (_desdeCache) _avisoCache(actualizado),
      if (actualizado.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Text(
            'Actualizado: $actualizado',
            style: const TextStyle(fontSize: 11, color: Colors.black45),
          ),
        ),
      Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
          '${visibles.length} de ${todas.length} registros',
          style: const TextStyle(fontSize: 12, color: Colors.black54),
        ),
      ),
      if (visibles.isEmpty)
        const Padding(
          padding: EdgeInsets.all(24),
          child: Center(child: Text('No hay registros con ese filtro.')),
        ),
    ];

    return RefreshIndicator(
      onRefresh: _cargar,
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
        itemCount: cabecera.length + visibles.length,
        itemBuilder: (context, i) {
          if (i < cabecera.length) return cabecera[i];
          return _ficha(columnas, visibles[i - cabecera.length]);
        },
      ),
    );
  }

  // ---------- piezas ----------

  List<String> _lista(dynamic valor) {
    if (valor is List) return valor.map((e) => e.toString()).toList();
    return const [];
  }

  Widget _aviso({String? mensaje}) {
    final texto = mensaje ?? 'No se pudo cargar la cartera.\n${_error ?? ''}';
    return RefreshIndicator(
      onRefresh: _cargar,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(28),
        children: [
          const SizedBox(height: 40),
          Icon(Icons.account_balance_wallet,
              size: 56, color: appState.colorCartera.withAlpha(150)),
          const SizedBox(height: 14),
          Text(texto, textAlign: TextAlign.center),
          const SizedBox(height: 14),
          Center(
            child: OutlinedButton.icon(
              onPressed: _cargar,
              icon: const Icon(Icons.refresh),
              label: const Text('Reintentar'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _avisoCache(String actualizado) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.orange.withAlpha(28),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.orange.withAlpha(90)),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              actualizado.isEmpty
                  ? 'Sin conexión: se muestra la última copia guardada.'
                  : 'Sin conexión: última copia del $actualizado.',
              style: const TextStyle(fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _total(double total) {
    final primario = appState.colorCartera;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: primario.withAlpha(18),
        border: Border.all(color: primario, width: 2),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            'SALDO TOTAL',
            style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.8),
          ),
          Text(
            _num(total),
            style: TextStyle(
                fontSize: 24, fontWeight: FontWeight.w900, color: primario),
          ),
        ],
      ),
    );
  }

  Widget _filtrosWidget(
      List<Map<String, dynamic>> filtros, Map<int, List<String>> opciones) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (var i = 0; i < filtros.length; i++)
            _unFiltro(filtros[i], i, opciones[i] ?? const []),
        ],
      ),
    );
  }

  Widget _unFiltro(
      Map<String, dynamic> filtro, int indice, List<String> opciones) {
    final actual = _filtros[indice] ?? '';
    return SizedBox(
      width: 160,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            (filtro['nombre'] ?? '').toString(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 3),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              border: Border.all(color: Colors.black26),
              borderRadius: BorderRadius.circular(8),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                value: actual.isEmpty ? '' : actual,
                isDense: true,
                isExpanded: true,
                items: [
                  const DropdownMenuItem(value: '', child: Text('Todos')),
                  for (final op in opciones)
                    DropdownMenuItem(
                      value: op,
                      child: Text(op, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: (valor) {
                  setState(() {
                    _filtros[indice] = valor ?? '';
                  });
                },
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _ficha(List<String> columnas, Map<String, dynamic> fila) {
    final celdas = _lista(fila['celdas']);
    return Card(
      // blanco fijo: sin el tinte del tema (que salía rosado)
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: Color(0xFFE5E7EB)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var i = 0; i < columnas.length; i++)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2.5),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 108,
                      child: Text(
                        columnas[i],
                        style: const TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                          color: Colors.black54,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        i < celdas.length ? celdas[i] : '',
                        style: const TextStyle(fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// Número con separador de miles (1.234.567), como en el panel.
  String _num(num valor) {
    final entero = valor.round();
    final texto = entero.abs().toString();
    final conPuntos = texto.replaceAllMapped(
      RegExp(r'(\d)(?=(\d{3})+$)'),
      (m) => '${m[1]}.',
    );
    return entero < 0 ? '-$conPuntos' : conPuntos;
  }

  /// Mayúsculas y sin tildes, para que "Perez" encuentre "Pérez".
  String _normal(String texto) {
    const acentos = 'áéíóúàèìòùäëïöüñçÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÑÇ';
    const planos = 'aeiouaeiouaeiouncAEIOUAEIOUAEIOUNC';
    var salida = texto;
    for (var i = 0; i < acentos.length; i++) {
      salida = salida.replaceAll(acentos[i], planos[i]);
    }
    return salida.toUpperCase();
  }
}
