import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// Una bodega (empresa) configurada en el teléfono: su panel y su token.
///
/// Cada bodega tiene su propia base de datos (`conecta2_<id>.db`), así que
/// el catálogo, los clientes y los pedidos de una nunca se mezclan con los
/// de otra y las cinco pueden trabajar sin internet al mismo tiempo.
class Bodega {
  Bodega({required this.id, required this.nombre, required this.url});

  final String id;
  String nombre;
  String url;

  String get archivoDb => 'conecta2_$id.db';

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'url': url,
      };

  factory Bodega.fromJson(Map<String, dynamic> m) => Bodega(
        id: (m['id'] ?? '').toString(),
        nombre: (m['nombre'] ?? '').toString(),
        url: (m['url'] ?? '').toString(),
      );
}

/// Lista de bodegas guardada en el teléfono (nombre y URL).
/// Los tokens y las sesiones se guardan aparte, por bodega.
class BodegasStore {
  static const _archivo = 'bodegas.json';

  Future<File> _file() async {
    final dir = await getApplicationDocumentsDirectory();
    return File(p.join(dir.path, _archivo));
  }

  Future<({List<Bodega> bodegas, String? activa})> leer() async {
    try {
      final f = await _file();
      if (!await f.exists()) {
        return (bodegas: <Bodega>[], activa: null);
      }
      final datos = jsonDecode(await f.readAsString());
      if (datos is Map) {
        final lista = (datos['bodegas'] as List?) ?? const [];
        return (
          bodegas: lista
              .whereType<Map>()
              .map((m) => Bodega.fromJson(m.cast<String, dynamic>()))
              .where((b) => b.id.isNotEmpty && b.url.isNotEmpty)
              .toList(),
          activa: datos['activa']?.toString(),
        );
      }
    } catch (_) {}
    return (bodegas: <Bodega>[], activa: null);
  }

  Future<void> guardar(List<Bodega> bodegas, {String? activa}) async {
    final f = await _file();
    await f.writeAsString(
      jsonEncode({
        'activa': activa,
        'bodegas': bodegas.map((b) => b.toJson()).toList(),
      }),
      flush: true,
    );
  }
}
