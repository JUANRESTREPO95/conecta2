import 'package:intl/intl.dart';

final NumberFormat _dinero = NumberFormat.decimalPattern('es');

String dinero(num valor) => _dinero.format(valor);

String fechaCorta(String? texto) {
  if (texto == null || texto.isEmpty) return '';
  return texto.length >= 16 ? texto.substring(0, 16) : texto;
}
