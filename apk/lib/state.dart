import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:material_ui/material_ui.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

import 'api.dart';
import 'bodega.dart';
import 'db.dart';

final appState = AppState();

class AppState extends ChangeNotifier {
  /// La primera bodega más cuatro más.
  static const int maxBodegas = 5;

  /// Base de la bodega activa. Se reemplaza al cambiar de bodega.
  AppDb db = AppDb(archivo: 'conecta2.db');
  final FlutterSecureStorage secure = const FlutterSecureStorage();
  final Uuid uuid = const Uuid();
  final BodegasStore _store = BodegasStore();

  List<Bodega> bodegas = [];
  Bodega? bodegaActiva;

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
  bool get puedeAgregarBodega => bodegas.length < maxBodegas;
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

  /// Color de la sección Cartera (el panel lo configura aparte de Pedidos).
  Color get colorCartera {
    final hex = (empresa?['color_cartera'] ?? '')
        .toString()
        .replaceFirst('#', '')
        .trim();
    if (hex.length != 6 && hex.length != 8) return colorPrimario;
    final valor = int.tryParse(hex.length == 6 ? 'FF$hex' : hex, radix: 16);
    return valor == null ? colorPrimario : Color(valor);
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

  /// El super usuario activa o apaga cada sección desde el panel.
  /// Si la app todavía no trae el dato, se toman como activas.
  bool get pedidosActivo {
    final valor = empresa?['pedidos_activo'];
    return valor == null ? true : valor == 1;
  }

  bool get carteraActiva {
    final valor = empresa?['cartera_activa'];
    return valor == null ? true : valor == 1;
  }

  /// Con una sola sección activa no tiene sentido mostrar el menú.
  bool get unaSolaSeccion => pedidosActivo != carteraActiva;

  /// Si solo hay una sección activa, entra directo a ella sin pasar por el menú.
  void ajustarSeccion() {
    if (seccion != 'menu') return;
    if (pedidosActivo && !carteraActiva) {
      seccion = 'pedidos';
    } else if (carteraActiva && !pedidosActivo) {
      seccion = 'cartera';
    }
  }

  // ---------- navegación principal ----------

  void irAlMenu() {
    seccion = 'menu';
    notifyListeners();
  }

  void irAPedidos() {
    if (!pedidosActivo) return;
    seccion = 'pedidos';
    notifyListeners();
  }

  void irACartera() {
    if (!carteraActiva) return;
    seccion = 'cartera';
    notifyListeners();
  }

  // ---------- arranque ----------

  Future<void> init() async {
    final gen = ++_generacion;
    try {
      _paso('Leyendo bodegas…');
      final guardado = await _store.leer();
      if (gen != _generacion) return;

      var lista = guardado.bodegas;
      var activaId = guardado.activa;

      // la primera vez después de actualizar: la bodega que ya estaba
      // configurada pasa a ser la bodega 1 sin perder sus datos
      if (lista.isEmpty) {
        final migrada = await _migrarBodegaUnica();
        if (gen != _generacion) return;
        if (migrada != null) {
          lista = [migrada];
          activaId = migrada.id;
          await _store.guardar(lista, activa: activaId);
        }
      }

      bodegas = lista;
      if (bodegas.isEmpty) {
        bodegaActiva = null;
        return;
      }
      bodegaActiva = _porId(activaId) ?? bodegas.first;
      await _cargarActiva(gen);
    } catch (e) {
      mensajeInicio = e.toString();
    } finally {
      paso = 'Listo';
      iniciado = true;
      ajustarSeccion();
      notifyListeners();
    }
  }

  /// Convierte la base única de la versión anterior en la bodega 1.
  Future<Bodega?> _migrarBodegaUnica() async {
    try {
      final carpeta = await getDatabasesPath();
      final legado = File(p.join(carpeta, 'conecta2.db'));
      if (!await legado.exists()) return null;

      final temporal = AppDb(archivo: 'conecta2.db');
      final url = (await temporal.getConfig('url') ?? '').trim();
      final empresaJson = await temporal.getConfig('empresa');
      await temporal.cerrar();
      if (url.isEmpty) return null;

      final id = uuid.v4().replaceAll('-', '').substring(0, 12);
      final nombre = (_json(empresaJson)?['nombre'] ?? 'Bodega 1').toString();
      for (final sufijo in ['', '-wal', '-shm']) {
        final archivo = File(p.join(carpeta, 'conecta2.db$sufijo'));
        if (await archivo.exists()) {
          await archivo.rename(p.join(carpeta, 'conecta2_$id.db$sufijo'));
        }
      }
      return Bodega(id: id, nombre: nombre, url: url);
    } catch (e) {
      debugPrint('Conecta2 migración: $e');
      return null;
    }
  }

  Future<void> _cargarActiva(int gen) async {
    final b = bodegaActiva;
    if (b == null) return;
    db = AppDb(archivo: b.archivoDb);
    _paso('Abriendo ${b.nombre}…');

    baseUrl = b.url;
    appToken = await _seguro('app_token');
    if (gen != _generacion) return;
    sesion = await _seguro('sesion');
    if (gen != _generacion) return;

    empresa = _json(await _config('empresa'));
    usuarioCodigo = await _config('usuario_codigo');
    usuarioNombre = await _config('usuario_nombre');
    usuarioRol = await _config('usuario_rol');
    ultimaSyncOk = DateTime.tryParse(await _config('ultima_sync_ok') ?? '');
    ultimoSyncServidor = await _config('ultimo_sync');
    _leerCarrito(await _config('carrito'));

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
  }

  // ---------- bodegas ----------

  Bodega? _porId(String? id) {
    if (id == null || id.isEmpty) return null;
    for (final b in bodegas) {
      if (b.id == id) return b;
    }
    return null;
  }

  /// Cambia de bodega. Con `forzarLogin` (desde el login) se vuelve a pedir
  /// el usuario; el token y la sesión de esa bodega quedan guardados.
  Future<void> seleccionarBodega(String id, {bool forzarLogin = true}) async {
    final b = _porId(id);
    if (b == null) return;
    _generacion++;
    bodegaActiva = b;
    await _store.guardar(bodegas, activa: b.id);

    _limpiarMemoria();
    seccion = 'menu';
    db = AppDb(archivo: b.archivoDb);
    baseUrl = b.url;
    appToken = await _seguro('app_token');
    sesion = await _seguro('sesion');
    empresa = _json(await _config('empresa'));
    if (!forzarLogin) {
      usuarioCodigo = await _config('usuario_codigo');
      usuarioNombre = await _config('usuario_nombre');
      usuarioRol = await _config('usuario_rol');
    }
    ultimaSyncOk = DateTime.tryParse(await _config('ultima_sync_ok') ?? '');
    ultimoSyncServidor = await _config('ultimo_sync');
    _leerCarrito(await _config('carrito'));
    api = configurado
        ? Api(baseUrl: baseUrl!, appToken: appToken!, sesion: sesion)
        : null;
    ajustarSeccion();
    notifyListeners();
    unawaited(_refrescarEnLinea());
  }

  Future<void> _refrescarEnLinea() async {
    if (!configurado) return;
    online = await _hayInternet();
    notifyListeners();
    if (online) {
      try {
        await sincronizar();
      } catch (_) {}
      if (logueado) {
        try {
          await procesarCola();
        } catch (_) {}
      }
    }
    _escucharConexion();
  }

  /// Agrega una bodega nueva. Exige internet: el token se prueba contra el
  /// panel y se descargan sus datos antes de dejarla lista.
  Future<void> agregarBodega(String url, String token) async {
    if (bodegas.length >= maxBodegas) {
      throw 'Máximo $maxBodegas bodegas';
    }
    final limpia = _normalizaUrl(url);
    final tok = token.trim();
    if (tok.isEmpty) throw 'Escribe el token de la app';

    final prueba = Api(baseUrl: limpia, appToken: tok);
    final saludo = await prueba.get(
      '/api/app/saludo',
      conSesion: false,
      timeout: const Duration(seconds: 30),
    );
    final emp = (saludo['empresa'] as Map?)?.cast<String, dynamic>() ?? {};
    final nombre = (emp['nombre'] ?? '').toString().trim();

    final id = uuid.v4().replaceAll('-', '').substring(0, 12);
    final b = Bodega(
      id: id,
      nombre: nombre.isEmpty ? 'Bodega ${bodegas.length + 1}' : nombre,
      url: limpia,
    );

    _generacion++;
    bodegaActiva = b;
    _limpiarMemoria();
    seccion = 'menu';
    db = AppDb(archivo: b.archivoDb);
    await db.setConfig('url', limpia);
    await db.setConfig('bodega_id', b.id);
    await db.setConfig('bodega_nombre', b.nombre);
    await _guardarSeguro('app_token', tok);

    bodegas = [...bodegas, b];
    baseUrl = limpia;
    appToken = tok;
    empresa = emp.isEmpty ? null : emp;
    api = Api(baseUrl: limpia, appToken: tok);
    online = true;
    await _store.guardar(bodegas, activa: b.id);
    notifyListeners();

    try {
      await sincronizar(completo: true);
    } catch (e) {
      // sin datos no sirve offline: se deshace la bodega a medias
      bodegas = bodegas.where((x) => x.id != b.id).toList();
      bodegaActiva = bodegas.isEmpty ? null : bodegas.first;
      await _store.guardar(bodegas, activa: bodegaActiva?.id);
      try {
        await db.cerrar();
      } catch (_) {}
      try {
        await deleteDatabase(p.join(await getDatabasesPath(), b.archivoDb));
      } catch (_) {}
      await _borrarSecretosBodega(b.id);
      if (bodegaActiva != null) {
        await seleccionarBodega(bodegaActiva!.id);
      } else {
        _limpiarEstado();
        notifyListeners();
      }
      rethrow;
    }
  }

  Future<void> renombrarBodega(String id, String nombre) async {
    final b = _porId(id);
    final limpio = nombre.trim();
    if (b == null || limpio.isEmpty) return;
    b.nombre = limpio;
    if (bodegaActiva?.id == id) await _setConfig('bodega_nombre', limpio);
    await _store.guardar(bodegas, activa: bodegaActiva?.id);
    notifyListeners();
  }

  /// Elimina la bodega y todos sus datos del teléfono.
  Future<void> eliminarBodega(String id) async {
    final b = _porId(id);
    if (b == null) return;
    final eraActiva = bodegaActiva?.id == id;
    bodegas = bodegas.where((x) => x.id != id).toList();
    if (eraActiva) bodegaActiva = null;
    await _store.guardar(bodegas, activa: bodegaActiva?.id);
    if (eraActiva) {
      try {
        await db.cerrar();
      } catch (_) {}
    }
    try {
      await deleteDatabase(p.join(await getDatabasesPath(), b.archivoDb));
    } catch (_) {}
    await _borrarSecretosBodega(id);
    if (eraActiva) {
      if (bodegas.isNotEmpty) {
        await seleccionarBodega(bodegas.first.id);
      } else {
        _generacion++;
        _limpiarEstado();
        notifyListeners();
      }
    } else {
      notifyListeners();
    }
  }

  Future<void> _borrarSecretosBodega(String id) async {
    try {
      await secure.delete(key: 'app_token_$id');
      await secure.delete(key: 'sesion_$id');
    } catch (e) {
      debugPrint('Conecta2 secure borrar $id: $e');
    }
  }

  // ---------- configuración local por bodega ----------

  Future<String?> _config(String clave) async {
    try {
      return await db.getConfig(clave).timeout(const Duration(seconds: 6));
    } catch (e) {
      debugPrint('Conecta2 config $clave: $e');
      return null;
    }
  }

  Future<String?> _seguro(String clave) async {
    // el respaldo en la base de esta bodega es inmediato
    final respaldo = await _config('seg_$clave');
    if (respaldo != null && respaldo.isNotEmpty) return respaldo;
    final id = bodegaActiva?.id;
    if (id == null) return null;
    try {
      return await secure
          .read(key: '${clave}_$id')
          .timeout(const Duration(seconds: 4));
    } catch (e) {
      debugPrint('Conecta2 secure $clave: $e');
      return null;
    }
  }

  Future<void> _guardarSeguro(String clave, String? valor) async {
    final id = bodegaActiva?.id;
    if (id != null) {
      try {
        if (valor == null) {
          await secure.delete(key: '${clave}_$id').timeout(
                const Duration(seconds: 8),
              );
        } else {
          await secure
              .write(key: '${clave}_$id', value: valor)
              .timeout(const Duration(seconds: 8));
        }
      } catch (e) {
        debugPrint('Conecta2 secure guardar $clave: $e');
      }
    }
    // copia de respaldo dentro de la base de esta bodega
    await _setConfig('seg_$clave', valor);
  }

  Future<void> _setConfig(String clave, String? valor) async {
    try {
      await db.setConfig(clave, valor).timeout(const Duration(seconds: 8));
    } catch (e) {
      debugPrint('Conecta2 config guardar $clave: $e');
    }
  }

  void _leerCarrito(String? carritoJson) {
    carrito.clear();
    if (carritoJson == null) return;
    try {
      final mapa = jsonDecode(carritoJson) as Map<String, dynamic>;
      mapa.forEach((k, v) => carrito[k] = (v as num).toInt());
    } catch (_) {}
  }

  Map<String, dynamic>? _json(String? texto) {
    if (texto == null || texto.isEmpty) return null;
    try {
      final datos = jsonDecode(texto);
      return datos is Map ? datos.cast<String, dynamic>() : null;
    } catch (_) {
      return null;
    }
  }

  void _limpiarMemoria() {
    carrito.clear();
    clienteSeleccionado = null;
    autorizadoSeleccionado = null;
    // una sincronización en curso de la bodega anterior ya no escribe
    // (se comprueba la bodega antes de guardar); se libera para la nueva
    sincronizando = false;
    sesionVencida = false;
    appRevocada = false;
    mensajeInicio = null;
    usuarioCodigo = null;
    usuarioNombre = null;
    usuarioRol = null;
    empresa = null;
    ultimaSyncOk = null;
    ultimoSyncServidor = null;
    appToken = null;
    sesion = null;
  }

  void _limpiarEstado() {
    _limpiarMemoria();
    baseUrl = null;
    api = null;
    bodegaActiva = null;
    online = false;
    sincronizando = false;
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
    ajustarSeccion();
    notifyListeners();
  }

  // ---------- red ----------

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

  // ---------- sesión ----------

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
    seccion = 'menu';
    ajustarSeccion();
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
    ajustarSeccion();
    notifyListeners();
  }

  Future<void> cerrarSesion() async {
    _generacion++;
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
    seccion = 'menu';
    notifyListeners();
  }

  // ---------- sincronización ----------

  Future<void> sincronizar({bool completo = false}) async {
    if (!configurado || api == null) throw 'Falta configurar la app';
    if (sincronizando) return;
    final bodegaId = bodegaActiva?.id;
    final base = db;
    sincronizando = true;
    notifyListeners();
    try {
      final desde = completo ? '' : (ultimoSyncServidor ?? '');
      final datos = await api!.get(
        '/api/app/datos',
        query: {'desde': desde},
        timeout: const Duration(minutes: 5),
      );
      if (bodegaActiva?.id != bodegaId) return;
      await base
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
      if (bodegaActiva?.id != bodegaId) return;
      final emp = datos['empresa'];
      if (emp is Map) {
        empresa = emp.cast<String, dynamic>();
        await base.setConfig('empresa', jsonEncode(empresa));
        ajustarSeccion();
      }
      ultimoSyncServidor = datos['servidor']?.toString();
      await base.setConfig('ultimo_sync', ultimoSyncServidor);
      ultimaSyncOk = DateTime.now();
      await base.setConfig('ultima_sync_ok', ultimaSyncOk!.toIso8601String());
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

  Future<void> procesarCola() async {
    if (!configurado || api == null) return;
    if (usuarioCodigo == null) return;
    if (!await _hayInternet()) return;
    if (sesion == null || sesion!.isEmpty) {
      sesionVencida = true;
      notifyListeners();
      return;
    }
    final bodegaId = bodegaActiva?.id;
    final base = db;
    final pendientes = await base.pedidosPendientes(usuarioCodigo!);
    for (final pedido in pendientes) {
      if (bodegaActiva?.id != bodegaId) return;
      final lineas = await base.lineasDe(pedido['uuid'] as String);
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
        if (bodegaActiva?.id != bodegaId) return;
        final total = (r['total'] as num?)?.toDouble();
        final finales = (r['lineas'] as List?)
                ?.whereType<Map>()
                .map((l) => l.cast<String, dynamic>())
                .toList() ??
            const <Map<String, dynamic>>[];
        if (finales.isNotEmpty && total != null) {
          await base.reemplazarLineasPedido(
              pedido['uuid'] as String, finales, total);
        } else if (total != null) {
          await base.actualizarPedido(pedido['uuid'] as String, total: total);
        }
        await base.actualizarPedido(
          pedido['uuid'] as String,
          serverId: (r['id'] as num?)?.toInt(),
          numero: r['numero']?.toString(),
          estado: r['estado']?.toString() ?? 'pendiente',
        );
        sesionVencida = false;
      } on ApiException catch (e) {
        if (bodegaActiva?.id != bodegaId) return;
        if (e.status == 401) {
          sesionVencida = true;
          await base.actualizarPedido(
            pedido['uuid'] as String,
            error: 'Inicia sesión para enviar',
          );
          notifyListeners();
          return;
        }
        if (e.status == 400) {
          final problemas = (e.datos['problemas'] as List?) ?? const [];
          await base.actualizarPedido(
            pedido['uuid'] as String,
            estado: 'error',
            error: e.message,
            problemas: problemas.isEmpty ? null : jsonEncode(problemas),
          );
          continue;
        }
        await base.actualizarPedido(
          pedido['uuid'] as String,
          error: e.message,
          sumarIntento: true,
        );
        continue;
      } catch (_) {
        if (bodegaActiva?.id != bodegaId) return;
        await base.actualizarPedido(
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
    final bodegaId = bodegaActiva?.id;
    final base = db;
    final r = await api!.get(
      '/api/app/mis-pedidos',
      timeout: const Duration(seconds: 60),
    );
    if (bodegaActiva?.id != bodegaId) return;
    await base.guardarHistorial(
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

  /// Reenvía un pedido rechazado pidiendo al panel que lo ajuste a la
  /// existencia actual (baja cantidades y quita productos no disponibles).
  Future<List<Map<String, dynamic>>> reenviarAjustado(String uuid) async {
    if (!configurado || api == null) throw 'Falta configurar la app';
    if (sesion == null || sesion!.isEmpty) {
      sesionVencida = true;
      notifyListeners();
      throw 'Inicia sesión para enviar';
    }
    final base = db;
    final pedido = await base.pedido(uuid);
    if (pedido == null) throw 'No se encontró el pedido';
    final lineas = await base.lineasDe(uuid);
    final cuerpo = {
      'uuid': uuid,
      'referencia': pedido['referencia'] ?? '',
      'cliente_codigo': pedido['cliente_codigo'] ?? '',
      'cliente_nombre': pedido['cliente_nombre'] ?? '',
      'cliente_nit': pedido['cliente_nit'] ?? '',
      'autorizado_codigo': pedido['autorizado_codigo'] ?? '',
      'lineas': lineas
          .map((l) => {'codigo': l['codigo'], 'cantidad': l['cantidad']})
          .toList(),
      'ajustar': true,
    };
    try {
      final r = await api!.post('/api/app/pedido', cuerpo,
          timeout: const Duration(seconds: 60));
      final total = (r['total'] as num?)?.toDouble() ?? 0;
      final finales = (r['lineas'] as List?)
              ?.whereType<Map>()
              .map((l) => l.cast<String, dynamic>())
              .toList() ??
          const <Map<String, dynamic>>[];
      if (finales.isNotEmpty) {
        await base.reemplazarLineasPedido(uuid, finales, total);
      } else if (total > 0) {
        await base.actualizarPedido(uuid, total: total);
      }
      await base.actualizarPedido(
        uuid,
        serverId: (r['id'] as num?)?.toInt(),
        numero: r['numero']?.toString(),
        estado: r['estado']?.toString() ?? 'pendiente',
      );
      sesionVencida = false;
      notifyListeners();
      return (r['ajustes'] as List?)
              ?.whereType<Map>()
              .map((a) => a.cast<String, dynamic>())
              .toList() ??
          const <Map<String, dynamic>>[];
    } on ApiException catch (e) {
      final problemas = (e.datos['problemas'] as List?) ?? const [];
      if (e.status == 401) {
        sesionVencida = true;
      }
      await base.actualizarPedido(
        uuid,
        estado: e.status == 401 ? null : 'error',
        error: e.message,
        problemas: problemas.isEmpty ? null : jsonEncode(problemas),
      );
      notifyListeners();
      rethrow;
    } catch (_) {
      await base.actualizarPedido(
        uuid,
        error: 'Sin conexión: se reintentará',
        sumarIntento: true,
      );
      notifyListeners();
      rethrow;
    }
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

  /// Vuelve a dejar el cliente/autorizado de un pedido para reenviarlo.
  void restaurarDatosPedido(Map<String, dynamic> pedido) {
    final codigo = (pedido['cliente_codigo'] ?? '').toString();
    if (codigo.isNotEmpty) {
      clienteSeleccionado = {
        'codigo': codigo,
        'nombre': (pedido['cliente_nombre'] ?? '').toString(),
        'nit': (pedido['cliente_nit'] ?? '').toString(),
      };
    }
    final aut = (pedido['autorizado_codigo'] ?? '').toString();
    if (aut.isNotEmpty) {
      autorizadoSeleccionado = {
        'codigo': aut,
        'nombre': (pedido['autorizado_nombre'] ?? '').toString(),
        'direccion': (pedido['autorizado_direccion'] ?? '').toString(),
      };
    }
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

  /// Borra el catálogo, los clientes y los pedidos guardados de esta bodega.
  /// La conexión (URL y token) se conserva.
  Future<void> borrarDatosLocales() async {
    await db.limpiarDatos();
    carrito.clear();
    clienteSeleccionado = null;
    autorizadoSeleccionado = null;
    ultimaSyncOk = null;
    ultimoSyncServidor = null;
    await _setConfig('carrito', null);
    await _setConfig('ultimo_sync', null);
    await _setConfig('ultima_sync_ok', null);
    notifyListeners();
  }

  @override
  void dispose() {
    _conexion?.cancel();
    super.dispose();
  }
}
