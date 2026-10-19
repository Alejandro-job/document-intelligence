"""Aplica la corrección a una lectura existente, sin dependencias de OCR/LLM."""
import argparse
import json
from pathlib import Path
from DOCUMENT_CONTEXT import leer
from extraction_rules import ejecutar
from field_labels import extraer
from document_revision import guardar
from validate_output import validar
from verify_citations import verificar


def aplicar(entrada, salida):
    lectura = leer(entrada)
    salida = Path(salida)
    datos_base, registro_base = ejecutar(lectura, salida / 'BASE_ANTERIOR')
    datos, registro, contexto = extraer(lectura, datos_base, registro_base['evidencias'])
    validar(datos, registro['control'])
    cantidad = verificar(lectura, [contexto, registro])
    for name, value in [('EXTRACCION_OCHO_CAMPOS.json', datos),
                        ('EVIDENCIAS_Y_CONTROL.json', registro),
                        ('CONTEXTO_DOCUMENTAL.json', contexto)]:
        guardar(salida / name, value)
    for p in contexto['paginas']:
        campos = ', '.join(c for c, hits in p['detonadores'].items() if hits)
        print('Página', p['pagina'], '|', ', '.join(p['tipos_propuestos']), '| campos:', campos)
    print('\nPROPUESTAS AUTOMÁTICAS:')
    print(json.dumps(datos, ensure_ascii=False, indent=2))
    for a in contexto['alertas_calidad']:
        print('REVISAR OCR: página', a['pagina'], a['tipo'])
    for c, e in registro['control']['estados'].items():
        if e['estado'] != 'extraido': print('PENDIENTE:', c, '|', e['estado'])
    print('Citas verificadas:', cantidad, '| OCR nuevo: 0 | inferencia nueva: 0 | entrenamiento: 0')
    print('Resultado en:', salida)
    print('Ningún campo se aprueba automáticamente.')
    return datos


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--entrada', required=True); p.add_argument('--salida', required=True)
    a = p.parse_args(); aplicar(a.entrada, a.salida)
