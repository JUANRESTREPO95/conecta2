import 'dart:io';

import 'package:conecta2/hoja_app.dart';
import 'package:conecta2/state.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('genera la hoja PDF del pedido', () async {
    appState.empresa = {
      'nombre': 'MEGAFANTASY',
      'color_primario': '#c01c28',
      'color_letra': '#ffffff',
      'usar_clientes': 1,
      'usar_autorizados': 1,
      'logo': null,
    };
    appState.baseUrl = 'http://192.168.0.199:8050';
    appState.usuarioCodigo = '17';
    appState.usuarioNombre = 'ROBERTO PUERTA';

    final bytes = await HojaApp.generar({
      'numero': '17-20260001',
      'creado': '2026-11-18 14:00:00',
      'cliente_nombre': 'GONZÁLEZ GÓMEZ SEBASTIÁN',
      'cliente_nit': '1038411339',
      'autorizado_nombre': 'ZULUAGA GIRALDO DUVER ESTEBAN',
      'autorizado_direccion': 'CR 100 96 50 APARTADO',
      'referencia': 'PRUEBA PDF APP',
      'total': 2469134,
    });

    final archivo = File('build/hoja_prueba.pdf');
    await archivo.parent.create(recursive: true);
    await archivo.writeAsBytes(bytes);
    expect(bytes.length, greaterThan(1000));
  });
}
