"""Detectar y normalizar fechas españolas conservando sus caracteres originales.

No interpreta el evento jurídico. Formatos fuera de la gramática quedan sin
detectar; no encontrar un patrón no prueba ausencia de fecha.
"""

import hashlib
import re
import unicodedata
from datetime import date


MESES = dict(zip(('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre').split(), range(1, 13)))
MESES['setiembre'] = 9
UNIDADES = ('cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro veinticinco veintiseis veintisiete veintiocho veintinueve').split()
DECENAS = {30:'treinta', 40:'cuarenta', 50:'cincuenta', 60:'sesenta', 70:'setenta', 80:'ochenta', 90:'noventa'}
CENTENAS = {100:'cien', 200:'doscientos', 300:'trescientos', 400:'cuatrocientos', 500:'quinientos', 600:'seiscientos', 700:'setecientos', 800:'ochocientos', 900:'novecientos'}


def palabras(n):
    if n < 30:
        return UNIDADES[n]
    if n < 100:
        decena, unidad = divmod(n, 10)
        return DECENAS[decena * 10] + (' y ' + UNIDADES[unidad] if unidad else '')
    centena, resto = divmod(n, 100)
    return ('ciento' if centena == 1 and resto else CENTENAS[centena * 100]) + (' ' + palabras(resto) if resto else '')


def simple(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto.casefold())
                   if unicodedata.category(c) != 'Mn')


NUMEROS = {simple(palabras(n)).replace(' ', ''): n for n in range(1, 1000)}
NUMEROS.update(un=1, primero=1, primer=1)


def numero_espanol(texto):
    t = re.sub(r'\s+', '', simple(texto))
    if t.isdigit():
        return int(t)
    if t in NUMEROS:
        return NUMEROS[t]
    if t.count('mil') == 1:
        antes, despues = t.split('mil')
        base = 1 if not antes else NUMEROS.get(antes)
        resto = 0 if not despues else NUMEROS.get(despues)
        if base is not None and 1 <= base <= 9 and resto is not None:
            return base * 1000 + resto
    raise ValueError('Número español no reconocido sin corregir letras o cifras')


def flexible(palabra):
    return r'\s*'.join(map(re.escape, palabra.split()))


SUFIJO = '(?:' + '|'.join(flexible(palabras(n)) for n in sorted(range(1, 1000), key=lambda n: len(palabras(n)), reverse=True)) + ')'
MIL = '(?:(?:' + '|'.join(UNIDADES[2:10]) + r')\s*mil|mil)'
ANIO = r'(?:[0-9]{4}|' + MIL + r'(?:\s*' + SUFIJO + r')?)'
DIA = r'(?:[0-9]{1,2}|' + '|'.join(flexible(palabras(n)) for n in range(31, 0, -1)) + r'|primero|primer|un)'
MES = '(?:' + '|'.join(MESES) + ')'
VERBAL = re.compile(
    r'(?<![a-z0-9])(?P<dia>' + DIA + r')(?:\s*\((?P<dia_alias>' + DIA + r')\))?'
    r'\s*de\s*(?P<mes>' + MES + r')\s*(?:del|de)\s*(?:ano\s*)?'
    r'(?P<anio>' + ANIO + r')(?:\s*\((?P<anio_alias>' + ANIO + r')\))?(?![a-z0-9])'
)
NUMERICA = re.compile(r'(?<![0-9])(?:[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}|[0-9]{1,2}[/.\-][0-9]{1,2}[/.\-][0-9]{4})(?![0-9])')


def fecha_numerica(texto):
    t = texto.strip()
    if re.fullmatch(r'[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}', t):
        anio, mes, dia = map(int, t.split('-'))
    elif re.fullmatch(r'[0-9]{1,2}[/.\-][0-9]{1,2}[/.\-][0-9]{4}', t):
        dia, mes, anio = map(int, re.split(r'[/.\-]', t))
    else:
        raise ValueError('Formato numérico no reconocido; no se convierte con suposiciones')
    return date(anio, mes, dia).isoformat()


def _mapa(texto):
    salida, mapa = [], []
    for i, c in enumerate(texto):
        for x in simple(c):
            salida.append(x)
            mapa.append(i)
    return ''.join(salida), mapa


def detectar_fechas(texto, fuente_id, pagina):
    normalizado, mapa = _mapa(texto)
    hallazgos = []
    for patron in (VERBAL, NUMERICA):
        for m in patron.finditer(normalizado):
            try:
                if patron is NUMERICA:
                    iso = fecha_numerica(m.group())
                else:
                    dia, anio = numero_espanol(m['dia']), numero_espanol(m['anio'])
                    if not m['anio'].isdigit() and re.match(r'\s*[a-z0-9]', normalizado[m.end():]):
                        # No convertir un prefijo válido de un año escrito corrupto.
                        # La variante verbal requiere cierre por puntuación o fin de texto.
                        continue
                    if m['dia_alias'] and numero_espanol(m['dia_alias']) != dia:
                        continue
                    if m['anio_alias'] and numero_espanol(m['anio_alias']) != anio:
                        continue
                    iso = date(anio, MESES[m['mes']], dia).isoformat()
            except ValueError:
                continue
            a, b = mapa[m.start()], mapa[m.end() - 1] + 1
            if any(x['rango_valor_caracteres'] == [a, b] for x in hallazgos):
                continue
            c, d = max(0, a - 150), min(len(texto), b + 150)
            hallazgos.append({'fecha_iso': iso, 'valor_literal_ocr': texto[a:b],
                'rango_valor_caracteres': [a, b], 'cita': texto[c:d],
                'rango_caracteres': [c, d], 'fuente_id': fuente_id, 'pagina': pagina,
                'sha256_texto_fuente': hashlib.sha256(texto.encode()).hexdigest(),
                'metodo': 'gramatica_fechas_es_y_normalizacion_determinista',
                'evento': 'pendiente_de_revision', 'aprobado': False})
    return sorted(hallazgos, key=lambda x: x['rango_valor_caracteres'][0])


def alinear_fecha_propuesta(valor, fechas):
    try:
        iso = fecha_numerica(valor)
    except (ValueError, TypeError):
        return [], 'formato_propuesto_no_admitido'
    coincidencias = [f for f in fechas if f['fecha_iso'] == iso]
    if not coincidencias:
        return [], 'fecha_sin_coincidencia_entre_formatos_reconocidos_de_esta_fuente'
    if len(coincidencias) != 1:
        return [], 'fecha_ambigua_en_esta_fuente'
    return coincidencias, None
