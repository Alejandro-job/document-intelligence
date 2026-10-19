"""Un comando reproducible: lectura, baseline, etiquetas y contexto; sin GT."""
import argparse
import json
from pathlib import Path
from document_revision import guardar
from pdf_reading import leer_pdf
from extraction_rules import ejecutar
from field_labels import extraer
from validate_output import validar


def procesar(pdf, salida, tessdata=None):
    salida = Path(salida)
    lectura = leer_pdf(pdf, salida / 'LECTURA', tessdata=tessdata)
    if lectura['paginas_no_leidas']:
        raise RuntimeError('Lectura incompleta; consultar LECTURA/LECTURA.json')
    datos_base, evidencia_base = ejecutar(lectura, salida / 'BASE_ANTERIOR')
    datos, registro, contexto = extraer(lectura, datos_base, evidencia_base['evidencias'])
    validar(datos, registro['control'])
    guardar(salida / 'EXTRACCION_OCHO_CAMPOS.json', datos)
    guardar(salida / 'EVIDENCIAS_Y_CONTROL.json', registro)
    guardar(salida / 'CONTEXTO_DOCUMENTAL.json', contexto)
    return datos


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--entrada', required=True, type=Path)
    p.add_argument('--salida', required=True, type=Path)
    p.add_argument('--tessdata')
    a = p.parse_args()
    documentos = [a.entrada] if a.entrada.is_file() else sorted(a.entrada.glob('*.pdf'))
    if not documentos:
        p.error('No se encontraron PDF')
    errores = []
    for pdf in documentos:
        try:
            d = procesar(pdf, a.salida / pdf.stem, a.tessdata)
            print(pdf.name, json.dumps(d, ensure_ascii=False), flush=True)
        except (ValueError, OSError, RuntimeError) as e:
            errores.append({'archivo': pdf.name, 'tipo': type(e).__name__, 'error': str(e)})
            guardar(a.salida / pdf.stem / 'ERROR.json', errores[-1])
            print('ERROR', pdf.name, type(e).__name__, str(e), flush=True)
    guardar(a.salida / 'ERRORES_LOTE.json', errores)
    if errores:
        raise SystemExit(1)
