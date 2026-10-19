"""Compara salidas ya generadas con la referencia sintética original.

Este archivo nunca se importa desde extracción. No implica validación humana
ni una prueba independiente; el catálogo y la normalización quedan declarados.
"""
import argparse
import json
import re
import unicodedata
from collections import Counter
from decimal import Decimal
from pathlib import Path

from document_revision import CAMPOS, guardar


def texto(v):
    return ' '.join(unicodedata.normalize('NFC', v).split()).casefold()


def normal_poder(v):
    s = ''.join(c for c in unicodedata.normalize('NFD', v.upper()) if unicodedata.category(c) != 'Mn')
    catalogo = {'PLEITOS Y COBRANZAS': 'pleitos_y_cobranzas',
                'ACTOS DE ADMINISTRACION': 'administracion', 'ACTOS DE DOMINIO': 'dominio'}
    return catalogo.get(s, v)


def lista(campo, valores):
    salida = []
    for v in valores or []:
        if isinstance(v, dict):
            if campo == 'poderes':
                salida.extend(texto(t) for t in v.get('tipos', [])); continue
            v = v.get('nombre', json.dumps(v, ensure_ascii=False, sort_keys=True))
        salida.append(texto(normal_poder(v) if campo == 'poderes' else v))
    return set(salida)


def escalar(campo, v):
    if v is None:
        return None
    if campo == 'capital_social_actual':
        return (Decimal(str(v['valor'])), texto(v['moneda']))
    return texto(v)


def dividir(n, d):
    return round(n/d, 6) if d else None


def evaluar(referencias, resultados, base_anterior=False):
    contadores = {c: Counter() for c in CAMPOS}
    detalles = []
    for pdf in sorted(Path(resultados).iterdir()):
        if not pdf.is_dir():
            continue
        ref = next((r for r in referencias['documentos'] if Path(r['archivo']).stem == pdf.name), None)
        if ref is None:
            continue
        salida = pdf / ('SALIDA' if base_anterior else '')
        pred_path = salida / 'EXTRACCION_OCHO_CAMPOS.json'
        if not pred_path.is_file():
            continue
        pred = json.loads(pred_path.read_text())
        lectura = json.loads((pdf/'LECTURA'/'LECTURA.json').read_text())
        if lectura['sha256_pdf'] != ref['sha256']:
            raise ValueError('La referencia no corresponde a los bytes del PDF')
        por_campo = {}
        for campo in CAMPOS:
            c = contadores[campo]
            r, p = ref['campos_esperados'][campo], pred[campo]
            if campo == 'notario':
                # El dataset de origen aporta una notaría ficticia, no el
                # nombre personal del fedatario: no se inventa una referencia.
                numero = re.search(r'\d+', r or '')
                esperado = int(numero.group()) if numero else None
                c['numeros_evaluables'] += esperado is not None
                c['numeros_correctos'] += bool(p and p.get('numero') == esperado)
                c['nombres_sin_referencia_personal'] += 1
                c['salidas_con_nombre_personal'] += bool(p and p.get('nombre'))
                por_campo[campo] = {'numero_esperado': esperado,
                                   'numero_obtenido': p.get('numero') if p else None,
                                   'nombre_personal': 'no_evaluable: no figura en la referencia',
                                   'completo': False}
                continue
            c['campos_evaluables'] += 1
            c['campos_con_valor'] += p not in (None, [])
            if campo in ('socios', 'representantes_legales', 'poderes'):
                er, ep = lista(campo, r), lista(campo, p)
                c['tp'] += len(er & ep); c['fp'] += len(ep-er); c['fn'] += len(er-ep)
                exacto = er == ep
                por_campo[campo] = {'esperados': sorted(er), 'obtenidos': sorted(ep), 'exacto': exacto}
            else:
                exacto = escalar(campo, r) == escalar(campo, p)
                por_campo[campo] = {'esperado': r, 'obtenido': p, 'exacto': exacto}
            c['campos_exactos'] += exacto
        detalles.append({'archivo': ref['archivo'], 'sha256_pdf': ref['sha256'], 'campos': por_campo})
    metricas = {}
    for campo, c in contadores.items():
        d = dict(c)
        if campo == 'notario':
            d['coincidencia_numero_notaria'] = dividir(c['numeros_correctos'], c['numeros_evaluables'])
            d['precision_nombre_personal'] = None
        else:
            d['coincidencia_exacta_campo'] = dividir(c['campos_exactos'], c['campos_evaluables'])
            d['cobertura_con_valor'] = dividir(c['campos_con_valor'], c['campos_evaluables'])
        if campo in ('socios', 'representantes_legales', 'poderes'):
            d.update(precision=dividir(c['tp'], c['tp']+c['fp']), recall=dividir(c['tp'], c['tp']+c['fn']),
                     f1=dividir(2*c['tp'], 2*c['tp']+c['fp']+c['fn']))
        metricas[campo] = d
    return {'estado': 'comparacion_ejecutada', 'documentos': len(detalles), 'particion': 'desarrollo_sintetico',
            'baseline_anterior': base_anterior, 'por_campo': metricas, 'detalles': detalles,
            'normalizacion': ['Unicode NFC, espacios y mayúsculas; no se corrigen letras OCR ni acentos de nombres.',
                             'Capital por valor decimal y moneda; listas como conjuntos.',
                             'Poderes mediante catálogo explícito de tres categorías.',
                             'Notario: solo número evaluable; el dataset no aporta nombre personal.'],
            'limites': ['Tres casos sintéticos, usados durante desarrollo: no prueba ciega ni estimación productiva.',
                       'A y C corresponden a la misma sociedad ficticia; no son empresas independientes.',
                       'Se conserva sin cambios el ground truth sintético de origen; no se atribuye revisión humana.',
                       'La exactitud de citas, vigencia externa, alcance de poderes y privacidad requieren controles adicionales.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--referencias', required=True, type=Path)
    p.add_argument('--resultados', required=True, type=Path); p.add_argument('--salida', required=True, type=Path)
    p.add_argument('--base-anterior', action='store_true'); a = p.parse_args()
    r = evaluar(json.loads(a.referencias.read_text()), a.resultados, a.base_anterior)
    guardar(a.salida, r)
    for c, m in r['por_campo'].items(): print(c, json.dumps(m, ensure_ascii=False))
