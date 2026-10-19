"""Validación del contrato explícito; no certifica exactitud documental."""
from datetime import date
from decimal import Decimal, InvalidOperation
import math

CAMPOS = ('razon_social', 'fecha_constitucion', 'numero_escritura', 'notario',
          'socios', 'representantes_legales', 'poderes', 'capital_social_actual')
ESTADOS = {'extraido', 'parcial', 'no_encontrado', 'no_aplicable', 'pendiente_revision', 'error'}


def validar(datos, control):
    if set(datos) != set(CAMPOS):
        raise ValueError('Se requieren exactamente los ocho campos')
    for c in ('razon_social', 'numero_escritura'):
        if datos[c] is not None and (not isinstance(datos[c], str) or not datos[c].strip()):
            raise ValueError('Texto inválido: ' + c)
    f = datos['fecha_constitucion']
    if f is not None and (not isinstance(f, str) or date.fromisoformat(f).isoformat() != f):
        raise ValueError('Fecha inválida')
    n = datos['notario']
    if n is not None:
        if not isinstance(n, dict) or set(n) != {'nombre', 'numero'}:
            raise ValueError('Objeto notario inválido')
        if n['nombre'] is not None and (not isinstance(n['nombre'], str) or not n['nombre'].strip()):
            raise ValueError('Nombre de notario inválido')
        if n['numero'] is not None and (type(n['numero']) is not int or n['numero'] < 1):
            raise ValueError('Número de notaría inválido')
    for c in ('socios', 'representantes_legales', 'poderes'):
        if not isinstance(datos[c], list) or any(not isinstance(v, str) or not v.strip() for v in datos[c]):
            raise ValueError('Lista inválida: ' + c)
    capital = datos['capital_social_actual']
    if capital is not None:
        if not isinstance(capital, dict) or set(capital) != {'valor', 'moneda'} or not isinstance(capital['moneda'], str):
            raise ValueError('Capital inválido')
        try:
            if isinstance(capital['valor'], bool):
                raise ValueError('Importe booleano')
            importe = Decimal(str(capital['valor']))
            if not importe.is_finite() or importe < 0:
                raise ValueError('Importe inválido')
        except InvalidOperation as e:
            raise ValueError('Importe inválido') from e
    if set(control['estados']) != set(CAMPOS):
        raise ValueError('Faltan estados')
    for c, registro in control['estados'].items():
        if registro['estado'] not in ESTADOS or registro.get('aprobado') is not False:
            raise ValueError('Estado automático inválido')
        if registro['estado'] in {'no_encontrado', 'no_aplicable'} and datos[c] not in (None, []):
            raise ValueError('Un estado sin valor contiene una respuesta')
        if registro['estado'] == 'no_aplicable' and not registro.get('justificacion'):
            raise ValueError('No aplicable requiere justificación explícita')
