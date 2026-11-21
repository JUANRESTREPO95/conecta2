import 'dart:io';

import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:share_plus/share_plus.dart';

import 'state.dart';
import 'utils.dart';

/// Hoja del pedido en PDF, generada en el teléfono y compartida (WhatsApp).
class HojaApp {
  static Future<List<int>> generar(Map<String, dynamic> pedido) async {
    final documento = await _construir(pedido);
    return documento.save();
  }

  static Future<void> compartir(Map<String, dynamic> pedido) async {
    final bytes = await generar(pedido);
    final carpeta = await getTemporaryDirectory();
    final numero = (pedido['numero'] ?? 'pedido')
        .toString()
        .replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
    final archivo = File('${carpeta.path}/pedido-$numero.pdf');
    await archivo.writeAsBytes(bytes, flush: true);
    final total = (pedido['total'] as num?) ?? 0;
    await SharePlus.instance.share(ShareParams(
      files: [XFile(archivo.path, mimeType: 'application/pdf')],
      title: 'Pedido $numero',
      text: 'Pedido $numero — ${dinero(total)} sin IVA',
    ));
  }

  static Future<pw.Document> _construir(Map<String, dynamic> pedido) async {
    final primario = _pdfColor(
        (appState.empresa?['color_primario'] ?? '#1e40af').toString());
    final logo = await _logo();
    final fuente = pw.Font.ttf(
        await rootBundle.load('assets/fonts/NotoSans-Regular.ttf'));
    final fuenteNegrita = pw.Font.ttf(
        await rootBundle.load('assets/fonts/NotoSans-Bold.ttf'));
    final numero = (pedido['numero'] ?? '').toString();
    final creado = (pedido['creado'] ?? '').toString();
    final fecha = creado.length >= 10 ? creado.substring(0, 10) : creado;
    final clienteNombre = (pedido['cliente_nombre'] ?? '').toString().trim();
    final clienteNit = (pedido['cliente_nit'] ?? '').toString().trim();
    final autNombre = (pedido['autorizado_nombre'] ?? '').toString().trim();
    final autDir = (pedido['autorizado_direccion'] ?? '').toString().trim();
    final referencia = (pedido['referencia'] ?? '').toString().trim();
    final total = (pedido['total'] as num?) ?? 0;
    final vendedor = [
      (appState.usuarioCodigo ?? '').toString(),
      (appState.usuarioNombre ?? '').toString(),
    ].where((s) => s.isNotEmpty).join(' - ');

    final filas = <List<String>>[
      ['PEDIDO', numero],
      ['FECHA', fecha],
      ['VENDEDOR', vendedor],
    ];
    if (appState.usarClientes) {
      final cliente = clienteNombre.isEmpty ? 'CONSUMIDOR FINAL' : clienteNombre;
      filas.add([
        'CLIENTE',
        clienteNit.isEmpty ? cliente : '$cliente - NIT $clienteNit',
      ]);
    }
    if (appState.usarAutorizados) {
      final autorizado =
          [autNombre, autDir].where((s) => s.isNotEmpty).join(' - ');
      filas.add(['AUTORIZADO', autorizado]);
    }
    filas.add(['REFERENCIA', referencia.isEmpty ? '-' : referencia]);
    filas.add(['MONTO', dinero(total)]);

    final documento = pw.Document();
    documento.addPage(pw.Page(
      pageFormat: PdfPageFormat.a4.landscape,
      margin: const pw.EdgeInsets.all(24),
      theme: pw.ThemeData.withFont(base: fuente, bold: fuenteNegrita),
      build: (context) => pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.start,
        children: [
          pw.Row(
            crossAxisAlignment: pw.CrossAxisAlignment.center,
            children: [
              if (logo != null)
                pw.Container(
                  width: 58,
                  height: 58,
                  margin: const pw.EdgeInsets.only(right: 12),
                  child: pw.Image(logo, fit: pw.BoxFit.contain),
                ),
              pw.Column(
                crossAxisAlignment: pw.CrossAxisAlignment.start,
                children: [
                  pw.Text(
                    appState.nombreEmpresa,
                    style: pw.TextStyle(
                      fontSize: 22,
                      fontWeight: pw.FontWeight.bold,
                      color: primario,
                    ),
                  ),
                  pw.Text(
                    'Hoja de pedido',
                    style: const pw.TextStyle(
                      fontSize: 11,
                      color: PdfColors.grey700,
                    ),
                  ),
                ],
              ),
            ],
          ),
          pw.SizedBox(height: 18),
          pw.Table(
            border: pw.TableBorder.all(color: PdfColors.grey600, width: 0.6),
            columnWidths: const {
              0: pw.FixedColumnWidth(130),
              1: pw.FlexColumnWidth(),
            },
            children: filas
                .map((fila) => pw.TableRow(children: [
                      pw.Container(
                        padding: const pw.EdgeInsets.all(7),
                        child: pw.Text(
                          fila[0],
                          style: pw.TextStyle(
                            fontSize: 9,
                            fontWeight: pw.FontWeight.bold,
                            color: PdfColors.grey800,
                          ),
                        ),
                      ),
                      pw.Container(
                        padding: const pw.EdgeInsets.all(7),
                        child: pw.Text(
                          fila[1].isEmpty ? ' ' : fila[1],
                          style: const pw.TextStyle(fontSize: 12),
                        ),
                      ),
                    ]))
                .toList(),
          ),
        ],
      ),
    ));
    return documento;
  }

  static PdfColor _pdfColor(String hex) {
    var h = hex.replaceFirst('#', '');
    if (h.length == 3) {
      h = h.split('').map((c) => '$c$c').join();
    }
    final valor = int.tryParse('FF$h', radix: 16) ?? 0xFF1E40AF;
    return PdfColor.fromInt(valor);
  }

  static Future<pw.ImageProvider?> _logo() async {
    final ruta = (appState.empresa?['logo'] ?? '').toString();
    if (ruta.isEmpty) return null;
    var url = ruta;
    if (url.startsWith('/')) url = '${appState.baseUrl}$url';
    if (!url.startsWith('http')) return null;
    try {
      final respuesta = await http
          .get(Uri.parse(url))
          .timeout(const Duration(seconds: 10));
      if (respuesta.statusCode == 200 && respuesta.bodyBytes.length > 10) {
        return pw.MemoryImage(respuesta.bodyBytes);
      }
    } catch (_) {}
    return null;
  }
}
