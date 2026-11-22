import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:cryptography/cryptography.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

import 'api.dart';
import 'db.dart';

final appState = AppState();

class AppState extends ChangeNotifier {
  final AppDb db = AppDb();
  final FlutterSecureStorage secure = const FlutterSecureStorage();
  final Uuid uuid = const Uuid();

  Api? api;
  String? baseUrl;
  String? appToken;
  String? sesion;
  Map<String, dynamic>? empresa;

  String? usuarioCodigo;
  String? usuarioNombre;
  String? usuarioRol;

  DateTime? ultimaSyncOk;
  String? ultimoSyncServidor;

  bool iniciado = false;
  bool sincronizando = false;
  bool online = false;
  bool appRevocada = false;
  bool sesionVencida = false;
  bool modoConfig = false;
  /// Sección visible después del login: 'menu', 'pedidos' o 'cartera'.
  String seccion = 'menu';
  String? mensajeInicio;
  String paso = 'Iniciando…';
  int _generacion = 0;

  final Map<String, int> carrito = {};
  Map<String, dynamic>? clienteSeleccionado;
  Map<String, dynamic>? autorizadoSeleccionado;
  StreamSubscription<List<ConnectivityResult>>? _conexion;

  bool get configurado => baseUrl != null && appToken != null;
  bool get logueado => usuarioCodigo != null;
  String get nombreEmpresa => (empresa?['nombre'] ?? 'Conecta2').toString();

  /// URL completa del logo de la empresa (viene como /logos/... del panel).
  String? get logoUrl {
    final ruta = (empresa?['logo'] ?? '').toString().trim();
    if (ruta.isEmpty) return null;
    if (ruta.startsWith('http')) return ruta;
    if (ruta.startsWith('/') && baseUrl != null) {
      return '${baseUrl!.replaceAll(RegExp(r'/+$'), '')}$ruta';
    }
    return null;
  }

  bool get usarClientes => empresa?['usar_clientes'] == 1;
  bool get usarAutorizados => usarClientes && empresa?['usar_autorizados'] == 1;
  bool get usarClientesNuevos =>
      usarClientes && empresa?['usar_clientes_nuevos'] == 1;
  String get filtroExistencia =>
      (empresa?['filtro_existencia'] ?? 'todo').toString();
  int get existenciaMinima =>
      int.tryParse('${empresa?['existencia_minima'] ?? 0}') ?? 0;

  Color get colorPrimario {
    final hex = (empresa?['color_primario'] ?? '#1e40af')
        .toString()
        .replaceFirst('#', '');
    final valor = int.tryParse(hex.length == 6 ? 'FF$hex' : hex, radix: 16);
    return Color(valor ?? 0xFF1E40AF);
  }

  Color get colorLetra {
    final hex = (empresa?['color_letra'] ?? '#ffffff').toString().replaceFirst(
      '#',
      '',
    );
    final valor = int.tryParse(hex.length == 6 ? 'FF$hex' : hex, radix: 16);
    return Color(valor ?? 0xFFFFFFFF);
  }

  bool get puedeOffline {
    final ultima = ultimaSyncOk;
    if (ultima == null) return false;
    return DateTime.now().difference(ultima).inHours < 72;
  }

  // ---------- navegación principal ----------

  void irAlMenu() {
    seccion = 'menu';
    notifyListeners();
  }

  void irAPedidos() {
    seccion = 'pedidos';
    notifyListeners();
  }

  void irACartera() {
    seccion = 'cartera';
    notifyListeners();
  }

  Future<void> init() async {
    final gen = ++_generacion;
    try {
      _paso('Abriendo la base de datos…');
      final urlGuardada = await _config('url');
      if (gen != _generacion) return;
      baseUrl ??= urlGuardada;
      if (baseUrl != null) {
        _paso('Leyendo la configuración…');
        if (appToken == null) {
          final v = await _seguro('app_token');
          if (gen != _generacion) return;
          appToken ??= v;
        }
        if (sesion == null) {
          final v = await _seguro('sesion');
          if (gen != _generacion) return;
          sesion ??= v;
        }
        if (empresa == null) {
          final empresaJson = await _config('empresa');
          if (gen != _generacion) return;
          if (empresa == null && empresaJson != null) {
            try {
              empresa = jsonDecode(empresaJson) as Map<String, dynamic>;
            } catch (_) {}
          }
        }
        // no pisar lo que el login/configuración ya hayan cargado
        if (usuarioCodigo == null) {
          final c = await _config('usuario_codigo');
          final n = await _config('usuario_nombre');
          final r = await _config('usuario_rol');
          if (gen != _generacion) return;
          usuarioCodigo ??= c;
          usuarioNombre ??= n;
          usuarioRol ??= r;
        }
        if (ultimaSyncOk == null) {
          final ok = await _config('ultima_sync_ok');
          if (gen != _generacion) return;
          if (ok != null) ultimaSyncOk ??= DateTime.tryParse(ok);
        }
        if (ultimoSyncServidor == null) {
          final v = await _config('ultimo_sync');
          if (gen != _generacion) return;
          ultimoSyncServidor ??= v;
        }
        if (carrito.isEmpty) {
          final carritoJson = await _config('carrito');
          if (gen != _generacion) return;
          if (carritoJson != null) {
            try {
              final mapa = jsonDecode(carritoJson) as Map<String, dynamic>;
              mapa.forEach((k, v) => carrito[k] = (v as num).toInt());
            } catch (_) {}
          }
        }
      }
      if (gen != _generacion) return;
      if (configurado) {
        api = Api(baseUrl: baseUrl!, appToken: appToken!, sesion: sesion);
        _paso('Comprobando conexión…');
        online = await _hayInternet();
        if (online) {
          _paso('Sincronizando datos…');
          try {
            await sincronizar();
            await procesarCola();
          } catch (e) {
            mensajeInicio = e.toString();
          }
        }
        _escucharConexion();
      }
    } catch (e) {
      mensajeInicio = e.toString();
    } finally {
      paso = 'Listo';
      iniciado = true;
      notifyListeners();
    }
  }

  Future<String?> _config(String clave) async {
    try {
      return await db.getConfig(clave).timeout(const Duration(seconds: 6));
    } catch (e) {
      debugPrint('Conecta2 config $clave: $e');
      return null;
    }
  }

  Future<String?> _seguro(String clave) async {
    // el respaldo en la base es inmediato y siempre se escribe al guardar
    final respaldo = await _config('seg_$clave');
    if (respaldo != null && respaldo.isNotEmpty) return respaldo;
    try {
      return await secure.read(key: clave).timeout(const Duration(seconds: 4));
    } catch (e) {
      debugPrint('Conecta2 secure $clave: $e');
      return null;
    }
  }

  Future<void> _guardarSeguro(String clave, String? valor) async {
    try {
      if (valor == null) {
        await secure.delete(key: clave).timeout(const Duration(seconds: 8));
      } else {
        await secure
            .write(key: clave, value: valor)
            .timeout(const Duration(seconds: 8));
      }
    } catch (e) {
      debugPrint('Conecta2 secure guardar $clave: $e');
    }
    // copia de respaldo: si al leer el almacenamiento seguro falla, se usa esta
    await _setConfig('seg_$clave', valor);
  }

  Future<void> _setConfig(String clave, String? valor) async {
    try {
      await db.setConfig(clave, valor).timeout(const Duration(seconds: 8));
    } catch (e) {
      debugPrint('Conecta2 config guardar $clave: $e');
    }
  }

  void _paso(String texto) {
    paso = texto;
    debugPrint('Conecta2: $texto');
    notifyListeners();
  }

  void forzarInicio([String? error]) {
    if (iniciado) return;
    if (error != null) mensajeInicio = error;
    paso = 'Listo';
    iniciado = true;
    notifyListeners();
  }

  /// Acceso de configuración: entra sin panel para poner URL y token en Ajustes.
  void entrarConfiguracion() {
    _generacion++;
    modoConfig = true;
    mensajeInicio = null;
    notifyListeners();
  }

  Future<bool> _hayInternet() async {
    final estados = await Connectivity().checkConnectivity().timeout(
      const Duration(seconds: 3),
      onTimeout: () => <ConnectivityResult>[ConnectivityResult.none],
    );
    if (estados.contains(ConnectivityResult.none) || estados.isEmpty) {
      return false;
    }
    try {
      await api?.get(
        '/api/app/saludo',
        conSesion: false,
        timeout: const Duration(seconds: 6),
      );
      return true;
    } on ApiException catch (e) {
      // 401 = llegó al panel, pero el token ya no sirve
      return e.status == 401;
    } catch (_) {
      return false;
    }
  }

  void _escucharConexion() {
    _conexion?.cancel();
    _conexion = Connectivity().onConnectivityChanged.listen((estados) async {
      if (estados.contains(ConnectivityResult.none)) {
        online = false;
        notifyListeners();
        return;
      }
      final hay = await _hayInternet();
      online = hay;
      notifyListeners();
      if (hay && configurado) {
        try {
          await sincronizar();
          await procesarCola();
        } catch (_) {}
      }
    });
  }

  String _normalizaUrl(String url) {
    var u = url.trim();
    if (u.isEmpty) throw 'Escribe la URL del panel';
    if (!u.startsWith('http://') && !u.startsWith('https://')) {
      u = 'https://$u';
    }
    return u.replaceAll(RegExp(r'/+$'), '');
  }

  Future<void> configurar(String url, String token) async {
    _generacion++;
    final limpia = _normalizaUrl(url);
    final tok = token.trim();
    if (tok.isEmpty) throw 'Escribe el token de la app';
    final prueba = Api(baseUrl: limpia, appToken: tok);
    await prueba.get(
      '/api/app/saludo',
      conSesion: false,
      timeout: const Duration(seconds: 30),
    );
    baseUrl = limpia;
    appToken = tok;
    api = Api(baseUrl: limpia, appToken: tok, sesion: sesion);
    await _setConfig('url', limpia);
    await _guardarSeguro('app_token', tok);
    online = true;
    notifyListeners();
    try {
      await sincronizar(completo: true);
    } catch (e) {
      // si la primera descarga falla, se vuelve a pedir la configuración
      baseUrl = null;
      appToken = null;
      api = null;
      online = false;
      await _setConfig('url', null);
      await _guardarSeguro('app_token', null);
      notifyListeners();
      rethrow;
    }
  }

  Future<void> reintentarInicio() async {
    online = await _hayInternet();
    if (online) {
      try {
        await sincronizar();
        await procesarCola();
      } catch (e) {
        mensajeInicio = e.toString();
      }
    }
    notifyListeners();
  }

  void elegirCliente(Map<String, dynamic>? cliente) {
    clienteSeleccionado = cliente;
    autorizadoSeleccionado = null;
    notifyListeners();
  }

  void elegirAutorizado(Map<String, dynamic>? autorizado) {
    autorizadoSeleccionado = autorizado;
    notifyListeners();
  }

  /// Crea un cliente desde la app. Queda seleccionado para el pedido y se
  /// guarda en A2 con el agente. Devuelve {nuevo, aviso}.
  Future<Map<String, dynamic>> crearCliente({
    required String nit,
    required String nombre,
    required String direccion,
    required String telefono,
  }) async {
    if (api == null) throw 'Falta configurar la app';
    final datos = await api!.post('/api/app/cliente-nuevo', {
      'nit': nit,
      'nombre': nombre,
      'direccion': direccion,
      'telefono': telefono,
    });
    if (datos['ok'] != true) {
      throw (datos['error'] ?? 'No se pudo crear el cliente').toString();
    }
    final cliente = (datos['cliente'] as Map?)?.cast<String, dynamic>() ?? {};
    await db.guardarCliente(cliente);
    elegirCliente(cliente);
    return {
      'nuevo': datos['nuevo'] == true,
      'aviso': (datos['aviso'] ?? '').toString(),
    };
  }

  Future<void> sincronizar({bool completo = false}) async {
    if (!configurado || api == null) throw 'Falta configurar la app';
    if (sincronizando) return;
    sincronizando = true;
    notifyListeners();
    try {
      final desde = completo ? '' : (ultimoSyncServidor ?? '');
      final datos = await api!.get(
        '/api/app/datos',
        query: {'desde': desde},
        timeout: const Duration(minutes: 5),
      );
      await db
          .guardarSync(
            productos: (datos['productos'] as List?) ?? const [],
            existencias:
                (datos['existencias'] as Map?)?.cast<String, dynamic>() ??
                const {},
            clientes: (datos['clientes'] as List?) ?? const [],
            autorizados: (datos['autorizados'] as List?) ?? const [],
            eliminados: (datos['eliminados'] as List?) ?? const [],
          )
          .timeout(const Duration(minutes: 3));
      final emp = datos['empresa'];
      if (emp is Map) {
        empresa = emp.cast<String, dynamic>();
        await db.setConfig('empresa', jsonEncode(empresa));
      }
      ultimoSyncServidor = datos['servidor']?.toString();
      await db.setConfig('ultimo_sync', ultimoSyncServidor);
      ultimaSyncOk = DateTime.now();
      await db.setConfig('ultima_sync_ok', ultimaSyncOk!.toIso8601String());
      appRevocada = false;
      online = true;
      mensajeInicio = null;
    } on ApiException catch (e) {
      if (e.status == 401) appRevocada = true;
      rethrow;
    } finally {
      sincronizando = false;
      notifyListeners();
    }
  }

  Future<void> login(
    String codigo,
    String clave, {
    Duration timeout = const Duration(seconds: 90),
  }) async {
    _generacion++;
    if (api == null) throw 'Falta configurar la app';
    final codigoLimpio = codigo.trim().toUpperCase();
    final r = await api!.post(
      '/api/app/login',
      {'codigo': codigoLimpio, 'clave': clave},
      conSesion: false,
      timeout: timeout,
    );
    debugPrint(
      'Conecta2 login: usuario=${r['usuario']} '
      '| sesion=${r['sesion'] != null}',
    );
    sesion = r['sesion']?.toString();
    if (sesion == null || sesion!.isEmpty) {
      throw 'El panel no devolvió la sesión. Revisa que el panel esté actualizado.';
    }
    api!.sesion = sesion;
    await _guardarSeguro('sesion', sesion ?? '');
    final u = (r['usuario'] as Map?)?.cast<String, dynamic>() ?? {};
    usuarioCodigo = u['codigo']?.toString() ?? codigoLimpio;
    usuarioNombre = u['nombre']?.toString() ?? usuarioCodigo;
    usuarioRol = u['rol']?.toString() ?? 'vendedor';
    await db.setConfig('usuario_codigo', usuarioCodigo);
    await db.setConfig('usuario_nombre', usuarioNombre);
    await db.setConfig('usuario_rol', usuarioRol);
    await _guardarHashLocal(
      codigoLimpio,
      clave,
      usuarioNombre ?? usuarioCodigo ?? '',
      usuarioRol ?? 'vendedor',
    );
    sesionVencida = false;
    online = true;
    modoConfig = false;
    seccion = 'menu';
    notifyListeners();
    await procesarCola();
  }

  Future<void> _guardarHashLocal(
    String codigo,
    String clave,
    String nombre,
    String rol,
  ) async {
    final azar = Random.secure();
    final sal = List<int>.generate(16, (_) => azar.nextInt(256));
    final pbkdf2 = Pbkdf2(
      macAlgorithm: Hmac.sha256(),
      iterations: 100000,
      bits: 256,
    );
    final llave = await pbkdf2.deriveKeyFromPassword(
      password: clave,
      nonce: sal,
    );
    final bytes = await llave.extractBytes();
    await db.guardarUsuario(
      codigo: codigo,
      nombre: nombre,
      rol: rol,
      salt: _hex(sal),
      hash: _hex(bytes),
    );
  }

  Future<void> loginOffline(String codigo, String clave) async {
    _generacion++;
    final codigoLimpio = codigo.trim().toUpperCase();
    final u = await db.usuarioLocal(codigoLimpio);
    if (u == null) {
      throw 'Sin internet: este usuario no ha entrado nunca en este teléfono.';
    }
    final sal = _deHex(u['salt'] as String? ?? '');
    final pbkdf2 = Pbkdf2(
      macAlgorithm: Hmac.sha256(),
      iterations: 100000,
      bits: 256,
    );
    final llave = await pbkdf2.deriveKeyFromPassword(
      password: clave,
      nonce: sal,
    );
    final bytes = await llave.extractBytes();
    if (_hex(bytes) != (u['hash'] as String? ?? '')) {
      throw 'Clave incorrecta';
    }
    usuarioCodigo = (u['codigo'] as String?) ?? codigoLimpio;
    usuarioNombre = (u['nombre'] as String?) ?? usuarioCodigo;
    usuarioRol = (u['rol'] as String?) ?? 'vendedor';
    await db.setConfig('usuario_codigo', usuarioCodigo);
    await db.setConfig('usuario_nombre', usuarioNombre);
    await db.setConfig('usuario_rol', usuarioRol);
    // conserva la sesión que ya se cargó; si falta, usa el respaldo local
    sesion ??= await _seguro('sesion');
    api?.sesion = sesion;
    online = false;
    seccion = 'menu';
    notifyListeners();
  }

  Future<void> cerrarSesion() async {
    _generacion++;
    modoConfig = false;
    seccion = 'menu';
    usuarioCodigo = null;
    usuarioNombre = null;
    usuarioRol = null;
    sesion = null;
    api?.sesion = null;
    carrito.clear();
    clienteSeleccionado = null;
    autorizadoSeleccionado = null;
    await _guardarCarrito();
    await _guardarSeguro('sesion', null);
    await db.setConfig('usuario_codigo', null);
    await db.setConfig('usuario_nombre', null);
    await db.setConfig('usuario_rol', null);
    notifyListeners();
  }

  Future<void> procesarCola() async {
    if (!configurado || api == null) return;
    if (usuarioCodigo == null) return;
    if (!await _hayInternet()) return;
    if (sesion == null || sesion!.isEmpty) {
      sesionVencida = true;
      notifyListeners();
      return;
    }
    final pendientes = await db.pedidosPendientes(usuarioCodigo!);
    for (final pedido in pendientes) {
      final lineas = await db.lineasDe(pedido['uuid'] as String);
      final cuerpo = {
        'uuid': pedido['uuid'],
        'referencia': pedido['referencia'] ?? '',
        'cliente_codigo': pedido['cliente_codigo'] ?? '',
        'cliente_nombre': pedido['cliente_nombre'] ?? '',
        'cliente_nit': pedido['cliente_nit'] ?? '',
        'autorizado_codigo': pedido['autorizado_codigo'] ?? '',
        'lineas': lineas
            .map((l) => {'codigo': l['codigo'], 'cantidad': l['cantidad']})
            .toList(),
      };
      try {
        final r = await api!.post(
          '/api/app/pedido',
          cuerpo,
          timeout: const Duration(seconds: 60),
        );
        await db.actualizarPedido(
          pedido['uuid'] as String,
          serverId: (r['id'] as num?)?.toInt(),
          numero: r['numero']?.toString(),
          estado: r['estado']?.toString() ?? 'pendiente',
        );
        sesionVencida = false;
      } on ApiException catch (e) {
        if (e.status == 401) {
          sesionVencida = true;
          await db.actualizarPedido(
            pedido['uuid'] as String,
            error: 'Inicia sesión para enviar',
          );
          notifyListeners();
          return;
        }
        if (e.status == 400) {
          await db.actualizarPedido(
            pedido['uuid'] as String,
            estado: 'error',
            error: e.message,
          );
          continue;
        }
        await db.actualizarPedido(
          pedido['uuid'] as String,
          error: e.message,
          sumarIntento: true,
        );
        continue;
      } catch (_) {
        await db.actualizarPedido(
          pedido['uuid'] as String,
          error: 'Sin conexión: se reintentará',
          sumarIntento: true,
        );
        notifyListeners();
        return;
      }
    }
    notifyListeners();
  }

  Future<void> sincronizarHistorial() async {
    if (!configurado || api == null || sesion == null) return;
    final r = await api!.get(
      '/api/app/mis-pedidos',
      timeout: const Duration(seconds: 60),
    );
    await db.guardarHistorial(
      (r['pedidos'] as List?) ?? const [],
      usuarioCodigo ?? '',
    );
    notifyListeners();
  }

  Future<String> enviarPedido({
    required String referencia,
    String? clienteCodigo,
    String? clienteNombre,
    String? clienteNit,
    String? autorizadoCodigo,
    String? autorizadoNombre,
    String? autorizadoDireccion,
  }) async {
    if (usuarioCodigo == null) {
      throw 'Inicia sesión como vendedor para enviar pedidos';
    }
    if (carrito.isEmpty) throw 'El pedido está vacío';
    if (usarClientes && (clienteCodigo == null || clienteCodigo.isEmpty)) {
      throw 'Elige el cliente';
    }
    final lineas = <Map<String, dynamic>>[];
    var total = 0.0;
    for (final entrada in carrito.entries) {
      final p = await db.producto(entrada.key);
      if (p == null) continue;
      final cantidad = entrada.value;
      final existencia = (p['existencia'] as num?)?.toDouble() ?? 0;
      if (cantidad > existencia) {
        throw 'No hay existencia suficiente de ${p['descripcion']} '
            '(hay ${existencia.toStringAsFixed(0)})';
      }
      final precio = (p['precio'] as num?)?.toDouble() ?? 0;
      total += precio * cantidad;
      lineas.add({
        'codigo': entrada.key,
        'descripcion': p['descripcion'],
        'cantidad': cantidad,
        'precio': precio,
      });
    }
    if (lineas.isEmpty) throw 'El pedido está vacío';
    final id = uuid.v4();
    await db.crearPedidoLocal(
      uuid: id,
      vendedorCodigo: usuarioCodigo ?? '',
      referencia: referencia,
      clienteCodigo: usarClientes ? clienteCodigo : null,
      clienteNombre: usarClientes ? clienteNombre : null,
      clienteNit: usarClientes ? clienteNit : null,
      autorizadoCodigo: usarAutorizados ? autorizadoCodigo : null,
      autorizadoNombre: usarAutorizados ? autorizadoNombre : null,
      autorizadoDireccion: usarAutorizados ? autorizadoDireccion : null,
      total: total,
      lineas: lineas,
    );
    carrito.clear();
    clienteSeleccionado = null;
    autorizadoSeleccionado = null;
    await _guardarCarrito();
    notifyListeners();
    if (online) await procesarCola();
    return id;
  }

  Future<void> reintentarPedido(String id) async {
    await db.actualizarPedido(id, estado: 'por_enviar');
    await procesarCola();
  }

  // ---------- carrito ----------

  /// Carga las líneas de un pedido anterior en el carrito (Reenviar).
  Future<void> cargarCarrito(List<Map<String, dynamic>> lineas) async {
    carrito.clear();
    for (final l in lineas) {
      final codigo = l['codigo']?.toString() ?? '';
      final cantidad = (l['cantidad'] as num?)?.toInt() ?? 0;
      if (codigo.isNotEmpty && cantidad > 0) {
        carrito[codigo] = cantidad;
      }
    }
    clienteSeleccionado = null;
    autorizadoSeleccionado = null;
    await _guardarCarrito();
    notifyListeners();
  }

  /// Fija la cantidad de un producto en el carrito (0 lo quita).
  void fijarCantidad(String codigo, int cantidad) {
    if (cantidad <= 0) {
      carrito.remove(codigo);
    } else {
      carrito[codigo] = cantidad;
    }
    _guardarCarrito();
    notifyListeners();
  }

  void agregar(String codigo, [int cantidad = 1]) {
    carrito[codigo] = (carrito[codigo] ?? 0) + cantidad;
    _guardarCarrito();
    notifyListeners();
  }

  void quitar(String codigo, [int cantidad = 1]) {
    final actual = carrito[codigo] ?? 0;
    final nuevo = actual - cantidad;
    if (nuevo <= 0) {
      carrito.remove(codigo);
    } else {
      carrito[codigo] = nuevo;
    }
    _guardarCarrito();
    notifyListeners();
  }

  void borrarDelCarrito(String codigo) {
    carrito.remove(codigo);
    _guardarCarrito();
    notifyListeners();
  }

  int get totalUnidades => carrito.values.fold(0, (a, b) => a + b);

  Future<void> _guardarCarrito() =>
      db.setConfig('carrito', jsonEncode(carrito));

  // ---------- utilidades ----------

  static String _hex(List<int> bytes) =>
      bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

  static List<int> _deHex(String texto) {
    final salida = <int>[];
    for (var i = 0; i + 1 < texto.length; i += 2) {
      salida.add(int.parse(texto.substring(i, i + 2), radix: 16));
    }
    return salida;
  }

  Future<void> borrarTodo() async {
    _generacion++;
    await db.limpiarDatos();
    try {
      await secure.deleteAll().timeout(const Duration(seconds: 8));
    } catch (_) {}
    await _setConfig('seg_app_token', null);
    await _setConfig('seg_sesion', null);
    baseUrl = null;
    appToken = null;
    sesion = null;
    api = null;
    empresa = null;
    usuarioCodigo = null;
    usuarioNombre = null;
    usuarioRol = null;
    modoConfig = false;
    carrito.clear();
    ultimaSyncOk = null;
    ultimoSyncServidor = null;
    await _setConfig('url', null);
    await db.setConfig('empresa', null);
    await db.setConfig('ultimo_sync', null);
    await db.setConfig('ultima_sync_ok', null);
    await db.setConfig('usuario_codigo', null);
    await db.setConfig('usuario_nombre', null);
    await db.setConfig('usuario_rol', null);
    await db.setConfig('carrito', null);
    notifyListeners();
  }

  @override
  void dispose() {
    _conexion?.cancel();
    super.dispose();
  }
}
