"""Revisar propuestas YA generadas. No contiene valores esperados ni llama modelos."""
import hashlib
import json
import re
from pathlib import Path

CAMPOS = ('razon_social', 'fecha_constitucion', 'numero_escritura', 'notario',
          'socios', 'representantes_legales', 'poderes', 'capital_social_actual')

def sha(datos):
    return hashlib.sha256(datos).hexdigest()

def firma(objeto):
    return sha(json.dumps(objeto, sort_keys=True, ensure_ascii=False).encode())

def guardar(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')

def pares_unicos(pares):
    d = {}
    for k, v in pares:
        if k in d:
            raise ValueError('Clave JSON duplicada: ' + k)
        d[k] = v
    return d

def constante_invalida(x):
    raise ValueError('Constante no JSON: ' + x)

DEC = json.JSONDecoder(object_pairs_hook=pares_unicos, parse_constant=constante_invalida)

def leer_propuestas(crudo, generacion_incompleta=False):
    """Admite un ] sobrante, o un prefijo de objetos completos de una lista truncada.

    Nunca cierra un objeto incompleto ni examina llaves sueltas dentro del texto.
    Las posiciones conservadas permiten comprobar que los valores no cambiaron.
    """
    inicio = len(crudo) - len(crudo.lstrip())
    s = crudo[inicio:]
    error = None
    try:
        obj, fin = DEC.raw_decode(s)
    except (json.JSONDecodeError, ValueError) as e:
        error = str(e)
    else:
        sufijo = s[fin:]
        if sufijo.strip() not in ('', ']'):
            raise ValueError('Contenido posterior no admitido; se conserva sin interpretar')
        if not isinstance(obj, dict) or not isinstance(obj.get('valores'), list):
            raise ValueError('Falta objeto con lista valores')
        return obj['valores'], {'modo': 'json_completo' if not sufijo.strip() else 'cierre_sobrante_omitido',
            'sufijo_original': sufijo, 'valores_modificados': False,
            'generacion_original_incompleta': generacion_incompleta,
            'rango_json_original': [inicio, inicio + fin]}
    if not generacion_incompleta:
        raise ValueError(error)
    cabecera = re.match(r'\{\s*"valores"\s*:\s*\[', s)
    if not cabecera:
        raise ValueError('La salida truncada no comienza con la lista prevista')
    pos, objetos, rangos = cabecera.end(), [], []
    while True:
        while pos < len(s) and s[pos].isspace():
            pos += 1
        if pos >= len(s):
            break
        comienzo = pos
        try:
            valor, fin = DEC.raw_decode(s, pos)
        except (json.JSONDecodeError, ValueError):
            break
        if not isinstance(valor, dict):
            break
        objetos.append(valor)
        rangos.append([inicio + pos, inicio + fin])
        pos = fin
        while pos < len(s) and s[pos].isspace():
            pos += 1
        if pos < len(s) and s[pos] == ',':
            pos += 1
            continue
        break
    return objetos, {'modo': 'prefijo_de_objetos_completos', 'valores_modificados': False,
        'generacion_original_incompleta': True, 'rangos_objetos_originales': rangos,
        'cola_sin_interpretar': s[pos:],
        'advertencia': 'La respuesta original sigue incompleta; recuperar objetos no completa el campo.'}

def coincidencias(valor, fuente):
    partes = valor.strip().split()
    if not partes:
        return []
    patron = r'\s+'.join(re.escape(x) for x in partes)
    if valor.strip()[0].isalnum():
        patron = r'(?<!\w)' + patron
    if valor.strip()[-1].isalnum():
        patron += r'(?!\w)'
    return list(re.finditer(patron, fuente, re.IGNORECASE))

def control_campo(campo, texto, a, b):
    """Reglas conservadoras, no equivalentes a una validación semántica general."""
    antes, despues = texto[max(0, a-260):a], texto[b:b+170]
    valor = texto[a:b]
    if campo == 'numero_escritura':
        linea = antes.rsplit('\n', 1)[-1]
        if re.fullmatch(r'[\d,.]+', valor) and re.search(
                r'\b(?:INSTRUMENTO|ESCRITURA)(?:\s+P[ÚU]BLICA)?\s*(?:N[ÚU]MERO|N[Oº°.]*)?\s*$', linea, re.I):
            return {'indicio': 'numero_tras_cabecera_instrumento_o_escritura',
                    'rango_contexto': [a-len(linea), min(len(texto), b+100)]}
        return None
    if campo == 'notario':
        # Una firma junto al nombre de un notario no convierte a otra persona en fedatario.
        primera = re.search(r'\bYO\s+(?:EL\s+|LA\s+)?(?:LICENCIAD[OA]\s*)?$', antes[-100:], re.I)
        titulo = re.search(r'^\s*,?\s*NOTARI[OA]\b', despues, re.I)
        if primera and titulo:
            return {'indicio': 'primera_persona_y_titulo_notarial_contiguos',
                    'rango_contexto': [max(0, a-110), min(len(texto), b+170)]}
        return None
    if campo == 'representantes_legales':
        # Exige una designación que anteceda al valor; no basta una facultad cerca de un nombre.
        patron = (r'\b(?:designan|designa|nombran|nombra)\s+(?:como\s+)?apoderad[oa]\b'
                  r'[^.;:]{0,220}\b(?:señor[a]?|ciudadan[oa]|licenciad[oa])\s*$')
        ancla = re.search(patron, antes, re.I | re.S)
        if ancla:
            return {'indicio': 'designacion_explicita_como_apoderado',
                    'rango_contexto': [max(0, a-260)+ancla.start(), min(len(texto), b+170)]}
        return None
    # Se evita admitir campos sin una regla de rol probada en este paso.
    return None

def revisar_campo(campo, registro):
    objetos, formato = leer_propuestas(registro.get('respuesta_cruda', ''),
                                      registro.get('estado') == 'generacion_incompleta')
    aceptados, rechazados = [], []
    fuentes = registro['fuentes_recibidas']
    indice = {f'F{i}': f for i, f in enumerate(fuentes, 1)}
    vistos = {}
    for i, p in enumerate(objetos):
        motivo = None
        if not isinstance(p, dict):
            motivo = 'propuesta_no_es_objeto'
        elif not isinstance(p.get('texto'), str) or not p['texto'].strip():
            motivo = 'valor_vacio_o_no_textual'
        elif not isinstance(p.get('fuente'), str) or p['fuente'] not in indice:
            motivo = 'fuente_no_recibida_por_el_modelo'
        elif p['texto'].strip().casefold() in {campo.casefold(), campo.replace('_', ' ').casefold()}:
            motivo = 'nombre_del_campo_usado_como_valor'
        if motivo:
            rechazados.append({'indice_propuesta': i, 'motivo': motivo, 'propuesta_original': p})
            continue
        f = indice[p['fuente']]
        matches = coincidencias(p['texto'], f['texto'])
        if not matches:
            rechazados.append({'indice_propuesta': i, 'motivo': 'valor_no_literal_en_fuente_declarada',
                               'propuesta_original': p})
            continue
        compatibles = [(m, control_campo(campo, f['texto'], m.start(), m.end())) for m in matches]
        compatibles = [(m, c) for m, c in compatibles if c]
        if len(compatibles) != 1:
            motivo = ('control_de_rol_no_implementado_para_este_campo' if campo not in
                      ('numero_escritura', 'notario', 'representantes_legales') else
                      ('rol_no_respaldado_por_regla_acotada' if not compatibles else
                       'mas_de_un_contexto_compatible'))
            rechazados.append({'indice_propuesta': i, 'motivo': motivo, 'propuesta_original': p})
            continue
        m, control = compatibles[0]
        a, b = m.span()
        ca, cb = control['rango_contexto']
        desplazamiento = f['rango_caracteres'][0]
        clave = (campo, f['fuente_id'], desplazamiento+a, desplazamiento+b)
        if clave in vistos:
            aceptados[vistos[clave]]['propuestas_originales'].append(p)
            aceptados[vistos[clave]]['indices_propuestas_originales'].append(i)
            continue
        visto = len(aceptados)
        vistos[clave] = visto
        aceptados.append({'campo': campo, 'valor_literal_ocr': f['texto'][a:b],
            'pagina': f['pagina'], 'fuente_id': f['fuente_id'], 'fragmento_id': f['fragmento_id'],
            'sha256_texto_fuente': f['sha256_texto_fuente'],
            'rango_valor_caracteres_fuente': [desplazamiento+a, desplazamiento+b],
            'rango_cita_caracteres_fuente': [desplazamiento+ca, desplazamiento+cb],
            'cita_literal_ocr_por_codigo': f['texto'][ca:cb], 'control': control['indicio'],
            'propuestas_originales': [p], 'indices_propuestas_originales': [i],
            'cita_del_modelo_modificada': False,
            'origen_cita_adicional': 'contexto_copiado_por_codigo_de_la_fuente_ya_recibida',
            'estado': 'candidato_reconciliado_para_revision', 'aprobado': False,
            'validacion_semantica_humana': 'pendiente', 'vigencia_actual': 'no_verificada'})
    return {'estado_original': registro['estado'], 'control_formato': formato,
            'objetos_completos_revisados': len(objetos), 'candidatos': aceptados,
            'rechazos': rechazados, 'campo_completado': False,
            'nota': 'No se proponen valores que el modelo no haya escrito. Las reglas son acotadas; el resto sigue pendiente.'}

ANCLAS = {
    'razon_social': [(r'\braz[oó]n\s+de\s+la\s+asociaci[oó]n\s+civil\s+es\b', 'declaracion_denominacion')],
    'fecha_constitucion': [(r'\bSiendo\s+las\b', 'apertura_acta_transcrita'),
        (r'\bA\s+LOS\b.{0,140}\bDEL\s+MES\s+DE\b', 'fecha_en_palabras; revisar_evento')],
    'numero_escritura': [(r'\b(?:INSTRUMENTO|ESCRITURA)\s+\d[\d,.]*', 'cabecera_instrumento')],
    'notario': [(r'\bYo\s+Licenciad[oa]\b', 'primera_persona_del_fedatario')],
    'socios': [(r'\bcomo\s+instituciones\s+asociadas\s+las\s+siguientes', 'inicio_lista_instituciones_asociadas')],
    'representantes_legales': [(r'\bdesignan\s+como\s+apoderad[oa]\b', 'designacion_apoderado')],
    'poderes': [(r'\bPODER\s+GENERAL\s+PARA\s+PLEITOS\s+Y\s+COBRANZAS', 'otorgamiento_o_mencion; revisar_contexto')],
    'capital_social_actual': [(r'\bpatrimonio\s+de\s+la\s+asociaci[oó]n\s+estar[aá]\s+integrado', 'patrimonio; no_equivale_a_capital_vigente')],
}

def diagnosticar_anclas(lectura, fragmentos, registros, rankings):
    """Cobertura de señales textuales: no usa ni fabrica relevancias humanas."""
    resultados = {}
    for campo, patrones in ANCLAS.items():
        filas = []
        recibidos = {f['fragmento_id'] for f in registros[campo]['fuentes_recibidas']}
        puestos = {f['fragmento_id']: f['rango'] for f in rankings[campo]['ranking']}
        for p in lectura['paginas']:
            for patron, tipo in patrones:
                for m in re.finditer(patron, p['texto'], re.I | re.S):
                    contiene = [f for f in fragmentos if f['pagina'] == p['pagina']
                        and f['rango_caracteres'][0] <= m.start() < m.end() <= f['rango_caracteres'][1]]
                    filas.append({'tipo_ancla': tipo, 'pagina': p['pagina'],
                        'rango_caracteres': list(m.span()), 'texto_ancla_literal': m.group(),
                        'contexto_literal': p['texto'][max(0, m.start()-120):min(len(p['texto']),m.end()+360)],
                        'fragmentos_que_contienen_ancla': [{'fragmento_id': f['fragmento_id'],
                            'rango_bm25': puestos.get(f['fragmento_id']),
                            'recibido_por_qwen': f['fragmento_id'] in recibidos} for f in contiene],
                        'ancla_entregada_a_qwen': any(f['fragmento_id'] in recibidos for f in contiene)})
        resultados[campo] = filas
    return {'tipo': 'diagnostico_de_cobertura_de_anclas_no_gold', 'campos': resultados,
            'recall': None, 'mrr': None, 'referencias_humanas_verificadas': False,
            'advertencia': 'Las anclas son reglas diagnósticas. No constituyen una lista completa de evidencia relevante ni respuestas correctas.'}
