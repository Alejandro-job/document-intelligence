"""Lectura y extracción reutilizables. Nunca recibe el ground truth."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'core'
sys.path.insert(0, str(CORE))
from document_revision import CAMPOS, guardar
from pdf_reading import leer_pdf
from extraction_rules import ejecutar
from field_labels import extraer
from validate_output import validar
from verify_citations import verificar
from DOCUMENT_RELATIONS import extraer_relaciones

VERSION = 'citi_entrega_1.0.0'
_MODELO = {}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def huella_pipeline():
    archivos = list(CORE.glob('*.py')) + list(Path(__file__).parent.glob('*.py')) + list(CORE.glob('*.json'))
    return sha('\n'.join(f'{p.name}:{sha(p.read_bytes())}' for p in sorted(archivos)).encode())


def capacidades():
    import shutil
    import subprocess
    idiomas = []
    if shutil.which('tesseract'):
        try:
            r = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True, timeout=10)
            idiomas = r.stdout.splitlines()[1:]
        except subprocess.SubprocessError:
            pass
    return {'version': VERSION, 'lector': 'PyMuPDF', 'ocr_espanol': 'spa' in idiomas,
            'qwen_bibliotecas': all(importlib.util.find_spec(x) is not None for x in ('torch', 'transformers', 'lmformatenforcer')),
            'motor_predeterminado': 'reglas', 'modelo_qwen': 'Qwen/Qwen2.5-1.5B-Instruct',
            'entrenamiento_automatico': False, 'produccion_validada': False}


def citas_planas(objeto):
    if isinstance(objeto, list):
        return [e for v in objeto for e in citas_planas(v)]
    if not isinstance(objeto, dict):
        return []
    if {'fuente_id', 'pagina', 'sha256_texto_fuente'} <= objeto.keys():
        rangos = objeto.get('rangos') or objeto.get('rangos_componentes')
        if not rangos and 'rango_caracteres' in objeto:
            rangos = [objeto['rango_caracteres']]
        if rangos:
            return [{**objeto, 'rangos': rangos}]
    return [e for v in objeto.values() for e in citas_planas(v)]


def propuestas_visuales(lectura, evidencias):
    paginas = {p['fuente_id']: p for p in lectura['paginas']}
    salida, usadas = [], set()
    for campo in CAMPOS:
        for e in citas_planas(evidencias.get(campo, [])):
            if e['fuente_id'] not in paginas:
                raise ValueError('Una evidencia no pertenece a la lectura del documento')
            p = paginas[e['fuente_id']]
            rangos = e['rangos']
            for a, b in rangos:
                if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(p['texto']):
                    raise ValueError('Rango de evidencia inválido')
            if sha(p['texto'].encode()) != e['sha256_texto_fuente']:
                raise ValueError('Hash de evidencia inválido')
            literal = '\n'.join(p['texto'][a:b] for a, b in rangos)
            esperado = e.get('texto_literal', e.get('cita_literal', e.get('texto')))
            if esperado is not None and esperado != literal:
                raise ValueError('La evidencia cambió respecto a su fuente')
            clave = (campo, e['fuente_id'], tuple(tuple(r) for r in rangos))
            if clave in usadas:
                continue
            usadas.add(clave)
            salida.append({'id': 'ev_' + sha(repr(clave).encode())[:20], 'campo': campo,
                'pagina': p['pagina'], 'fuente_id': p['fuente_id'], 'rangos': rangos,
                'texto_literal': literal, 'sha256_texto_fuente': e['sha256_texto_fuente'],
                'estado': 'propuesta', 'contexto': len(literal) > 180,
                'es_contexto': len(literal) > 180, 'origen_visual': e.get('metodo', 'evidencia_del_motor'),
                'nota': 'Cita literal verificada por código. Valor, rol y alcance pendientes de revisión.'})
    return salida


def construir_documento(lectura, datos, evidencias, control, salida, job_id, contexto=None):
    """Renderizado visual en la misma rotación que las cajas del lector."""
    import fitz
    salida = Path(salida)
    propuestas = propuestas_visuales(lectura, evidencias)
    paginas = []
    for p in lectura['paginas']:
        ancho, alto = p['ancho'], p['alto']
        palabras = []
        for w in p.get('palabras', []):
            box = w['box']
            # El lector nuevo entrega píxeles; algunas lecturas importadas ya
            # son normalizadas. Cada fuente conserva su propio texto y rangos.
            if max(box) > 1:
                box = [box[0]/ancho, box[1]/alto, box[2]/ancho, box[3]/alto]
            box = [max(0.0, min(1.0, float(x))) for x in box]
            if box[0] < box[2] and box[1] < box[3]:
                palabras.append({**w, 'box': box})
        paginas.append({'page': p['pagina'], 'source': p['fuente_id'], 'text': p['texto'],
            'textSha': sha(p['texto'].encode()), 'words': palabras,
            'width': ancho, 'height': alto,
            'image': f'api/jobs/{job_id}/pages/{p["pagina"]}.jpg',
            'method': p.get('metodo_lectura', 'desconocido')})
    doc = {'id': lectura['sha256_pdf'], 'title': Path(lectura['archivo']).stem,
           'filename': lectura['archivo'], 'partition': 'sin_asignar', 'pages': paginas,
           'values': datos, 'proposals': propuestas, 'fragments': [], 'control': control,
           'annotations': {'version': 'citi_anotaciones_v1', 'particion': 'sin_asignar',
                           'documento_id': lectura['sha256_pdf'], 'anotaciones': []},
           'contextByField': {c: [copy.deepcopy(e) for e in propuestas if e['campo'] == c] for c in CAMPOS},
           'additionalSources': [],
           'serverJob': job_id, 'sourceFile': 'procesamiento_api', 'weights': None}
    doc['snapshot'] = sha(json.dumps([datos, [p['textSha'] for p in paginas], propuestas],
                                     ensure_ascii=False, sort_keys=True).encode())[:24]
    guardar(salida / 'DOCUMENTO_WEB.json', doc)
    return doc


def qwen(lectura, datos_reglas, salida, etapa):
    """Una pasada por campo. Las abstenciones no se rellenan con reglas."""
    from load_qwen import cargar
    from context_rag import construir
    import model_extract as ia
    from VALIDATE_RESULT import controlar_estado, plano
    import REPRESENTATIVE_CONTEXT as especial
    from FIELD_CONTEXT import enriquecer
    modelo, tokenizer, info = cargar(_MODELO)
    indice = construir(lectura)
    resultados, reconciliacion = {}, None
    for i, campo in enumerate(CAMPOS, 1):
        etapa(f'Qwen {i}/8: {campo}')
        try:
            rel = extraer_relaciones(lectura) if campo == 'representantes_legales' else {}
            if rel.get('estado') == 'propuesta_por_designacion_y_remision':
                control_previo = {'documento': {'archivo': lectura['archivo'], 'sha256_pdf': lectura['sha256_pdf'],
                    'paginas': len(lectura['paginas'])}, 'datos': datos_reglas,
                    'evidencias': {c: [] for c in CAMPOS}, 'estados': {c: {'origen': 'preparacion'} for c in CAMPOS},
                    'relaciones_documentales': rel}
                preparado = especial.preparar_contexto(control_previo, lectura, enriquecer, extraer_relaciones)
                mensajes = especial.mensajes(preparado['citas'])
                from context_rag import contar
                paquete = {'campo': campo, 'estado': 'listo', 'mensajes': mensajes, 'citas': preparado['citas'],
                           'tokens_entrada': contar(mensajes, tokenizer)[0], 'limite': 6144, 'max_valores': 4}
                original = ia.esquema_salida
                ia.esquema_salida = lambda c, refs: especial.esquema(refs) if c == campo else original(c, refs)
                try:
                    g = ia.generar(paquete, modelo, tokenizer, max_new_tokens=384, max_segundos=180)
                finally:
                    ia.esquema_salida = original
                guardar(salida / 'QWEN' / f'{campo}_GENERACION_ORIGINAL.json', g)
                reconciliacion = especial.reconciliar_referencias(g.get('respuesta_cruda'), preparado, lectura)
                cs = []
                for c in reconciliacion['candidatos_con_referencias_por_codigo']:
                    e = c['evidencias_nombre'][0]
                    cs.append({'campo': campo, 'valor': c['texto_propuesto_por_qwen'], 'rol': c['rol_propuesto_por_qwen'],
                        'pagina': e['pagina'], 'fuente_id': e['fuente_id'], 'rangos': [e['rango_caracteres']],
                        'texto_literal': e['texto'], 'sha256_texto_fuente': e['sha256_texto_fuente']})
                rs = reconciliacion['rechazos_reconciliacion']
                guardar(salida / 'QWEN' / 'RECONCILIACION_REFERENCIAS.json', reconciliacion)
            else:
                paquete = ia.preparar(campo, indice, tokenizer, max_tokens=6144)
                g = ia.generar(paquete, modelo, tokenizer, max_new_tokens=384, max_segundos=180)
                guardar(salida / 'QWEN' / f'{campo}_GENERACION_ORIGINAL.json', g)
                cs, rs = ia.interpretar(campo, g.get('respuesta_cruda'), paquete, indice,
                    bool(g.get('limite_tokens_alcanzado') or g.get('limite_tiempo_alcanzado')))
            resultados[campo] = {'estado': 'con_candidatos' if cs else 'rechazado' if rs else 'abstencion',
                'prompt': paquete, 'generacion': g, 'candidatos': cs, 'rechazos': rs,
                'salida_incompleta': bool(g.get('limite_tokens_alcanzado') or g.get('limite_tiempo_alcanzado'))}
        except Exception as e:
            resultados[campo] = {'estado': 'error', 'error': f'{type(e).__name__}: {e}', 'candidatos': [], 'rechazos': []}
        guardar(salida / 'QWEN' / 'ESTADO_EXTRACTOR_IA.json', {'protocolo': {'modelo': info,
            'sha256_pdf': lectura['sha256_pdf'], 'codigo': huella_pipeline()}, 'campos': resultados})
    salida_ia, filtrados, _ = controlar_estado({'protocolo': {'sha256_pdf': lectura['sha256_pdf']},
                                               'campos': resultados}, lectura)
    evidencias = {c: [x for x in filtrados[c].get('candidatos', [])] for c in CAMPOS}
    if reconciliacion:
        evidencias['representantes_legales'] += [e for c in reconciliacion['candidatos_con_referencias_por_codigo']
                                                for e in c['designacion_y_otorgamiento']]
        evidencias['representantes_legales'] += [e for c in reconciliacion['candidatos_con_referencias_por_codigo']
                                                for p in c['facultades_y_restricciones'] for e in p['evidencias']]
    datos = plano(salida_ia)
    estados = {c: {**s, 'estado_motor': s['estado'], 'aprobado': False,
        'estado': 'pendiente_revision' if datos[c] not in (None, []) else 'error' if s['estado'] == 'error' else 'no_encontrado',
        'origen': 'qwen_con_controles_por_codigo', 'revision_humana': 'pendiente'}
        for c, s in salida_ia['estados'].items()}
    control = {'estados': estados, 'motor': 'qwen', 'modelo': info,
               'origen': 'Qwen; referencias y controles por código; no se rellenan abstenciones con reglas',
               'control_semantico': salida_ia['control_semantico'], 'aprobado': False,
               'entrenamiento': False, 'precision_independiente': None}
    return datos, evidencias, control


def procesar(pdf, salida, job_id, motor='reglas', etapa=lambda x: None):
    import fitz
    inicio = time.monotonic()
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    etapa('Inspeccionando y leyendo páginas')
    lectura = leer_pdf(pdf, salida / 'LECTURA', instalar=False)
    if lectura['paginas_no_leidas']:
        raise RuntimeError('Lectura incompleta; se conserva el diagnóstico, sin afirmar ausencia de campos')
    etapa('Extrayendo propuestas por reglas y estructura')
    base, ev_base = ejecutar(lectura, salida / 'BASELINE')
    datos, registro, contexto = extraer(lectura, base, ev_base['evidencias'])
    verificar(lectura, [registro])
    guardar(salida / 'REGLAS' / 'EXTRACCION_OCHO_CAMPOS.json', datos)
    guardar(salida / 'REGLAS' / 'EVIDENCIAS_Y_CONTROL.json', registro)
    evidencias, control = registro['evidencias'], registro['control']
    control.update(motor='reglas', origen='reglas y etiquetas explícitas; sin inferencia Qwen')
    relaciones = extraer_relaciones(lectura)
    if relaciones.get('estado') == 'propuesta_por_designacion_y_remision':
        datos['representantes_legales'] = [p['nombre'] for p in relaciones['personas']]
        datos['poderes'] = [p['texto_propuesto'] for p in relaciones['poderes']]
        evidencias['representantes_legales'] = relaciones['designacion_y_otorgamiento'] + relaciones['clausula_completa']
        evidencias['poderes'] = relaciones['clausula_completa']
        for c in ('representantes_legales', 'poderes'):
            control['estados'][c] = {'estado': 'pendiente_revision', 'aprobado': False,
                'origen': 'reglas_designacion_y_remision', 'revision_humana': 'pendiente'}
    if motor == 'qwen':
        datos, evidencias, control = qwen(lectura, datos, salida, etapa)
    elif motor != 'reglas':
        raise ValueError('Motor desconocido')
    etapa('Validando contrato y evidencia; preparando el visor')
    validar(datos, control)
    marcas = propuestas_visuales(lectura, evidencias)
    control.update(aprobado=False, produccion_validada=False, precision_independiente=None,
                   version_pipeline=VERSION, sha256_codigo=huella_pipeline(),
                   segundos=round(time.monotonic()-inicio, 3), evidencia_literal_verificada=True,
                   vigencia_externa='no_verificada', extraccion_requiere_revision=True)
    guardar(salida / 'EXTRACCION_OCHO_CAMPOS.json', datos)
    guardar(salida / 'EVIDENCIAS_Y_CONTROL.json', {'control': control, 'evidencias': evidencias})
    guardar(salida / 'CONTEXTO_DOCUMENTAL.json', contexto)
    guardar(salida / 'PROPUESTAS_IA_VISOR.json', marcas)
    with fitz.open(pdf) as documento:
        imagenes = salida / 'PAGINAS'
        imagenes.mkdir(exist_ok=True)
        for n, p in enumerate(documento, 1):
            pix = p.get_pixmap(dpi=110, colorspace=fitz.csRGB, alpha=False)
            (imagenes / f'{n}.jpg').write_bytes(pix.tobytes('jpeg', jpg_quality=82))
    return construir_documento(lectura, datos, evidencias, control, salida, job_id, contexto)
