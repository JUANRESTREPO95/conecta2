import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

class AppDb {
  AppDb({this.archivo = 'conecta2.db'});

  /// Archivo de esta bodega: `conecta2_<id>.db`.
  final String archivo;
  Database? _db;

  /// Cierra la conexión (antes de eliminar la bodega).
  Future<void> cerrar() async {
    final d = _db;
    _db = null;
    if (d != null) await d.close();
  }

  Future<Database> get db async {
    if (_db != null) return _db!;
    final carpeta = await getDatabasesPath();
    _db = await openDatabase(
      p.join(carpeta, archivo),
      version: 2,
      onCreate: (d, version) async {
        await d.execute('''
          CREATE TABLE productos (
            codigo TEXT PRIMARY KEY,
            descripcion TEXT,
            unidad TEXT,
            precio REAL,
            actualizado TEXT
          )
        ''');
        await d.execute('''
          CREATE TABLE existencias (
            codigo TEXT PRIMARY KEY,
            existencia REAL
          )
        ''');
        await d.execute('''
          CREATE TABLE clientes (
            codigo TEXT PRIMARY KEY,
            nombre TEXT,
            nit TEXT,
            rif TEXT
          )
        ''');
        await d.execute('''
          CREATE TABLE autorizados (
            codigo TEXT PRIMARY KEY,
            cliente_codigo TEXT,
            nombre TEXT,
            direccion TEXT,
            activo INTEGER
          )
        ''');
        await d.execute(
            'CREATE INDEX idx_aut_cliente ON autorizados(cliente_codigo)');
        await d.execute('''
          CREATE TABLE usuarios_locales (
            codigo TEXT PRIMARY KEY,
            nombre TEXT,
            rol TEXT,
            salt TEXT,
            hash TEXT
          )
        ''');
        await d.execute('''
          CREATE TABLE pedidos (
            uuid TEXT PRIMARY KEY,
            server_id INTEGER,
            vendedor_codigo TEXT,
            numero TEXT,
            estado TEXT NOT NULL,
            referencia TEXT,
            cliente_codigo TEXT,
            cliente_nombre TEXT,
            cliente_nit TEXT,
            autorizado_codigo TEXT,
            autorizado_nombre TEXT,
            autorizado_direccion TEXT,
            total REAL,
            creado TEXT,
            actualizado TEXT,
            intentos INTEGER DEFAULT 0,
            ultimo_error TEXT
          )
        ''');
        await d.execute('''
          CREATE TABLE pedido_lineas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL,
            codigo TEXT,
            descripcion TEXT,
            cantidad REAL,
            precio REAL
          )
        ''');
        await d.execute(
            'CREATE INDEX idx_lineas_uuid ON pedido_lineas(uuid)');
        await d.execute('''
          CREATE TABLE config (
            clave TEXT PRIMARY KEY,
            valor TEXT
          )
        ''');
      },
      onUpgrade: (d, anterior, nueva) async {
        if (anterior < 2) {
          try {
            await d.execute(
                'ALTER TABLE pedidos ADD COLUMN vendedor_codigo TEXT');
          } catch (_) {}
        }
      },
    );
    return _db!;
  }

  // ---------- configuración ----------

  Future<void> setConfig(String clave, String? valor) async {
    final d = await db;
    if (valor == null) {
      await d.delete('config', where: 'clave = ?', whereArgs: [clave]);
    } else {
      await d.insert('config', {'clave': clave, 'valor': valor},
          conflictAlgorithm: ConflictAlgorithm.replace);
    }
  }

  Future<String?> getConfig(String clave) async {
    final d = await db;
    final filas =
        await d.query('config', where: 'clave = ?', whereArgs: [clave]);
    return filas.isEmpty ? null : filas.first['valor'] as String?;
  }

  // ---------- datos de la sincronización ----------

  Future<void> guardarSync({
    required List<dynamic> productos,
    required Map<String, dynamic> existencias,
    required List<dynamic> clientes,
    required List<dynamic> autorizados,
    required List<dynamic> eliminados,
  }) async {
    final d = await db;
    await d.transaction((txn) async {
      var lote = txn.batch();
      var cuenta = 0;
      for (final p in productos) {
        if (p is! Map) continue;
        lote.insert(
          'productos',
          {
            'codigo': p['codigo']?.toString() ?? '',
            'descripcion': p['descripcion']?.toString() ?? '',
            'unidad': p['unidad']?.toString() ?? '',
            'precio': (p['precio'] as num?)?.toDouble() ?? 0,
            'actualizado': p['actualizado']?.toString(),
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
        cuenta++;
        if (cuenta >= 2000) {
          await lote.commit(noResult: true);
          lote = txn.batch();
          cuenta = 0;
        }
      }
      for (final codigo in eliminados) {
        lote.delete('productos', where: 'codigo = ?', whereArgs: [codigo]);
        lote.delete('existencias', where: 'codigo = ?', whereArgs: [codigo]);
      }
      await lote.commit(noResult: true);

      lote = txn.batch();
      cuenta = 0;
      for (final entrada in existencias.entries) {
        lote.insert(
          'existencias',
          {
            'codigo': entrada.key,
            'existencia': (entrada.value as num?)?.toDouble() ?? 0,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
        cuenta++;
        if (cuenta >= 2000) {
          await lote.commit(noResult: true);
          lote = txn.batch();
          cuenta = 0;
        }
      }
      await lote.commit(noResult: true);

      lote = txn.batch();
      for (final c in clientes) {
        if (c is! Map) continue;
        lote.insert(
          'clientes',
          {
            'codigo': c['codigo']?.toString() ?? '',
            'nombre': c['nombre']?.toString() ?? '',
            'nit': c['nit']?.toString() ?? '',
            'rif': c['rif']?.toString() ?? '',
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      for (final a in autorizados) {
        if (a is! Map) continue;
        lote.insert(
          'autorizados',
          {
            'codigo': a['codigo']?.toString() ?? '',
            'cliente_codigo': a['cliente_codigo']?.toString() ?? '',
            'nombre': a['nombre']?.toString() ?? '',
            'direccion': a['direccion']?.toString() ?? '',
            'activo': (a['activo'] == true) ? 1 : 0,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      await lote.commit(noResult: true);
    });
  }

  Future<int> contarProductos() async {
    final d = await db;
    final r = await d.rawQuery('SELECT COUNT(*) AS n FROM productos');
    return (r.first['n'] as num?)?.toInt() ?? 0;
  }

  Future<List<Map<String, dynamic>>> buscarProductos(
    String consulta, {
    int limite = 120,
    String filtro = 'todo',
    int minimo = 0,
  }) async {
    final d = await db;
    final donde = <String>[];
    final valores = <Object?>[];
    final q = consulta.trim().toUpperCase();
    if (q.isNotEmpty) {
      donde.add('(UPPER(p.descripcion) LIKE ? OR UPPER(p.codigo) LIKE ?)');
      valores.add('%$q%');
      valores.add('%$q%');
    }
    if (filtro == 'positivo') {
      donde.add('COALESCE(e.existencia, 0) > 0');
    } else if (filtro == 'personalizado') {
      donde.add('COALESCE(e.existencia, 0) >= ?');
      valores.add(minimo);
    }
    final sql = 'SELECT p.codigo, p.descripcion, p.unidad, p.precio, '
        'COALESCE(e.existencia, 0) AS existencia '
        'FROM productos p LEFT JOIN existencias e ON e.codigo = p.codigo '
        '${donde.isEmpty ? '' : 'WHERE ${donde.join(' AND ')} '}'
        'ORDER BY p.descripcion LIMIT ?';
    final filas = await d.rawQuery(sql, [...valores, limite]);
    return filas.map((f) => f.cast<String, dynamic>()).toList();
  }

  Future<Map<String, dynamic>?> producto(String codigo) async {
    final d = await db;
    final filas = await d.rawQuery(
      'SELECT p.codigo, p.descripcion, p.unidad, p.precio, '
      'COALESCE(e.existencia, 0) AS existencia '
      'FROM productos p LEFT JOIN existencias e ON e.codigo = p.codigo '
      'WHERE p.codigo = ?',
      [codigo],
    );
    return filas.isEmpty ? null : filas.first.cast<String, dynamic>();
  }

  Future<List<Map<String, dynamic>>> buscarClientes(String consulta,
      {int limite = 40}) async {
    final d = await db;
    final q = consulta.trim().toUpperCase();
    final filas = await d.rawQuery(
      'SELECT codigo, nombre, nit, rif FROM clientes '
      'WHERE UPPER(nombre) LIKE ? OR UPPER(codigo) LIKE ? OR nit LIKE ? '
      'ORDER BY nombre LIMIT ?',
      ['%$q%', '%$q%', '%$q%', limite],
    );
    return filas.map((f) => f.cast<String, dynamic>()).toList();
  }

  /// Guarda un cliente creado desde la app (para poder buscarlo enseguida).
  Future<void> guardarCliente(Map<String, dynamic> c) async {
    final d = await db;
    await d.insert(
      'clientes',
      {
        'codigo': c['codigo']?.toString() ?? '',
        'nombre': c['nombre']?.toString() ?? '',
        'nit': c['nit']?.toString() ?? '',
        'rif': c['rif']?.toString() ?? '',
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<List<Map<String, dynamic>>> autorizadosDe(String cliente) async {
    final d = await db;
    final filas = await d.rawQuery(
      'SELECT codigo, nombre, direccion FROM autorizados '
      'WHERE cliente_codigo = ? ORDER BY nombre, codigo',
      [cliente],
    );
    return filas.map((f) => f.cast<String, dynamic>()).toList();
  }

  // ---------- usuarios locales ----------

  Future<void> guardarUsuario({
    required String codigo,
    required String nombre,
    required String rol,
    required String salt,
    required String hash,
  }) async {
    final d = await db;
    await d.insert(
      'usuarios_locales',
      {
        'codigo': codigo,
        'nombre': nombre,
        'rol': rol,
        'salt': salt,
        'hash': hash,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<Map<String, dynamic>?> usuarioLocal(String codigo) async {
    final d = await db;
    final filas = await d.query('usuarios_locales',
        where: 'codigo = ?', whereArgs: [codigo]);
    return filas.isEmpty ? null : filas.first.cast<String, dynamic>();
  }

  // ---------- pedidos ----------

  static String ahora() =>
      DateTime.now().toIso8601String().replaceFirst('T', ' ').substring(0, 19);

  Future<void> crearPedidoLocal({
    required String uuid,
    required String vendedorCodigo,
    required String referencia,
    String? clienteCodigo,
    String? clienteNombre,
    String? clienteNit,
    String? autorizadoCodigo,
    String? autorizadoNombre,
    String? autorizadoDireccion,
    required double total,
    required List<Map<String, dynamic>> lineas,
  }) async {
    final d = await db;
    final momento = ahora();
    await d.transaction((txn) async {
      await txn.insert(
        'pedidos',
        {
          'uuid': uuid,
          'vendedor_codigo': vendedorCodigo,
          'estado': 'por_enviar',
          'referencia': referencia,
          'cliente_codigo': clienteCodigo,
          'cliente_nombre': clienteNombre,
          'cliente_nit': clienteNit,
          'autorizado_codigo': autorizadoCodigo,
          'autorizado_nombre': autorizadoNombre,
          'autorizado_direccion': autorizadoDireccion,
          'total': total,
          'creado': momento,
          'actualizado': momento,
        },
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
      for (final l in lineas) {
        await txn.insert('pedido_lineas', {'uuid': uuid, ...l});
      }
    });
  }

  Future<void> actualizarPedido(
    String uuid, {
    int? serverId,
    String? numero,
    String? estado,
    String? error,
    bool sumarIntento = false,
  }) async {
    final d = await db;
    final campos = <String, Object?>{'actualizado': ahora()};
    if (serverId != null) campos['server_id'] = serverId;
    if (numero != null) campos['numero'] = numero;
    if (estado != null) campos['estado'] = estado;
    if (error != null) {
      campos['ultimo_error'] = error;
    } else if (estado != null && estado != 'por_enviar') {
      campos['ultimo_error'] = null;
    }
    if (sumarIntento) {
      await d.rawUpdate(
        'UPDATE pedidos SET intentos = COALESCE(intentos, 0) + 1 '
        'WHERE uuid = ?',
        [uuid],
      );
    }
    await d.update('pedidos', campos, where: 'uuid = ?', whereArgs: [uuid]);
  }

  Future<List<Map<String, dynamic>>> pedidosPendientes(String vendedor) async {
    final d = await db;
    final filas = await d.query('pedidos',
        where: "estado = 'por_enviar' AND vendedor_codigo = ?",
        whereArgs: [vendedor],
        orderBy: 'creado');
    return filas.map((f) => f.cast<String, dynamic>()).toList();
  }

  Future<List<Map<String, dynamic>>> pedidos(String vendedor,
      {int limite = 200}) async {
    final d = await db;
    final filas = await d.query('pedidos',
        where: 'vendedor_codigo = ?',
        whereArgs: [vendedor],
        orderBy: 'creado DESC',
        limit: limite);
    return filas.map((f) => f.cast<String, dynamic>()).toList();
  }

  Future<List<Map<String, dynamic>>> lineasDe(String uuid) async {
    final d = await db;
    final filas = await d.query('pedido_lineas',
        where: 'uuid = ?', whereArgs: [uuid], orderBy: 'id');
    return filas.map((f) => f.cast<String, dynamic>()).toList();
  }

  Future<Map<String, dynamic>?> pedido(String uuid) async {
    final d = await db;
    final filas = await d.query('pedidos',
        where: 'uuid = ?', whereArgs: [uuid], limit: 1);
    return filas.isEmpty ? null : filas.first.cast<String, dynamic>();
  }

  Future<void> guardarHistorial(List<dynamic> servidor, String vendedor) async {
    final d = await db;
    await d.transaction((txn) async {
      for (final pedido in servidor) {
        if (pedido is! Map) continue;
        final serverId = (pedido['id'] as num?)?.toInt();
        if (serverId == null) continue;
        final uuidServidor = pedido['uuid']?.toString();
        String uuid;
        final porServidor = await txn.query('pedidos',
            columns: ['uuid'],
            where: 'server_id = ?',
            whereArgs: [serverId],
            limit: 1);
        if (porServidor.isNotEmpty) {
          uuid = porServidor.first['uuid'] as String;
        } else if (uuidServidor != null && uuidServidor.isNotEmpty) {
          final porUuid = await txn.query('pedidos',
              columns: ['uuid'],
              where: 'uuid = ?',
              whereArgs: [uuidServidor],
              limit: 1);
          uuid = porUuid.isNotEmpty ? uuidServidor : uuidServidor;
        } else {
          uuid = 'srv-$serverId';
        }
        await txn.insert(
          'pedidos',
          {
            'uuid': uuid,
            'server_id': serverId,
            'vendedor_codigo': vendedor,
            'numero': pedido['numero']?.toString(),
            'estado': pedido['estado']?.toString() ?? 'pendiente',
            'referencia': pedido['referencia']?.toString(),
            'cliente_codigo': pedido['cliente_codigo']?.toString(),
            'cliente_nombre': pedido['cliente_nombre']?.toString(),
            'cliente_nit': pedido['cliente_nit']?.toString(),
            'autorizado_codigo': pedido['autorizado_codigo']?.toString(),
            'autorizado_nombre': pedido['autorizado_nombre']?.toString(),
            'autorizado_direccion': pedido['autorizado_direccion']?.toString(),
            'total': (pedido['total'] as num?)?.toDouble() ?? 0,
            'creado': pedido['creado']?.toString(),
            'actualizado': ahora(),
            'intentos': (pedido['intentos'] as num?)?.toInt() ?? 0,
            'ultimo_error': pedido['error_a2']?.toString(),
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
        await txn.delete('pedido_lineas',
            where: 'uuid = ?', whereArgs: [uuid]);
        final lineas = pedido['lineas'];
        if (lineas is List) {
          for (final l in lineas) {
            if (l is! Map) continue;
            await txn.insert('pedido_lineas', {
              'uuid': uuid,
              'codigo': l['codigo']?.toString(),
              'descripcion': l['descripcion']?.toString(),
              'cantidad': (l['cantidad'] as num?)?.toDouble() ?? 0,
              'precio': (l['precio'] as num?)?.toDouble() ?? 0,
            });
          }
        }
      }
    });
  }

  Future<void> limpiarDatos() async {
    final d = await db;
    await d.transaction((txn) async {
      for (final tabla in [
        'pedido_lineas',
        'pedidos',
        'autorizados',
        'clientes',
        'existencias',
        'productos',
        'usuarios_locales',
      ]) {
        await txn.delete(tabla);
      }
    });
  }
}
