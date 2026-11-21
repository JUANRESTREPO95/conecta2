import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  final int status;
  final String message;

  ApiException(this.status, this.message);

  bool get tokenInvalido => status == 401;
  bool get sesionVencida => status == 401;

  @override
  String toString() => message;
}

class Api {
  final String baseUrl;
  final String appToken;
  String? sesion;

  Api({required this.baseUrl, required this.appToken, this.sesion});

  Uri _uri(String path, [Map<String, String>? query]) {
    final base = baseUrl.replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.parse('$base$path');
    return query == null ? uri : uri.replace(queryParameters: query);
  }

  Map<String, String> _headers({bool conSesion = true}) {
    final headers = <String, String>{
      'Authorization': 'Bearer $appToken',
      'Accept': 'application/json',
    };
    if (conSesion && sesion != null && sesion!.isNotEmpty) {
      headers['X-Sesion'] = sesion!;
    }
    return headers;
  }

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String>? query,
    bool conSesion = true,
    Duration timeout = const Duration(seconds: 60),
  }) async {
    final respuesta = await http
        .get(_uri(path, query), headers: _headers(conSesion: conSesion))
        .timeout(timeout);
    return _json(respuesta);
  }

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, {
    bool conSesion = true,
    Duration timeout = const Duration(seconds: 90),
  }) async {
    final respuesta = await http
        .post(
          _uri(path),
          headers: {
            ..._headers(conSesion: conSesion),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(body),
        )
        .timeout(timeout);
    return _json(respuesta);
  }

  Map<String, dynamic> _json(http.Response respuesta) {
    Map<String, dynamic> datos = {};
    try {
      final decodificado = jsonDecode(utf8.decode(respuesta.bodyBytes));
      if (decodificado is Map<String, dynamic>) datos = decodificado;
    } catch (_) {
      // respuesta sin JSON
    }
    if (respuesta.statusCode < 200 || respuesta.statusCode >= 300) {
      throw ApiException(
        respuesta.statusCode,
        (datos['error'] ?? 'Error ${respuesta.statusCode}').toString(),
      );
    }
    return datos;
  }
}
