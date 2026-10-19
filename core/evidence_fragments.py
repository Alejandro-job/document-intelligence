"""Recuperación por estructura y candidatos literales; sin valores esperados."""
import json
import re
import zipfile
from datetime import date
from pathlib import Path
from document_revision import firma, guardar, sha
from date_candidates import (detectar_fechas, _mapa, DIA, MES, ANIO,
                                numero_espanol, MESES)

MAX_TAREAS = 16
MAX_TOKENS = 1536
FECHAS_EVENTOS = {
    'A': 'asamblea constitutiva transcrita', 'B': 'otorgamiento o protocolización del instrumento',
    'C': 'autorización preventiva', 'D': 'autorización definitiva',
    'E': 'permiso o antecedente administrativo', 'F': 'expedición de testimonio',
    'G': 'inscripción registral', 'H': 'otra fecha: personal, legal o no constitutiva',
    'X': 'el contexto no permite determinar el evento'}

ARTICULO = re.compile(r'\bArt[íi]culo\s+[A-Z0-9IVXLCDMT!()]+\b', re.I)
MES_INTERCALADO = re.compile(
    r'\b(?:a\s+los|los)\s+(?P<dia>'+DIA+r')(?P<separador>.{0,70}?)'
    r'\bdel\s+mes\s+de[\W_]*(?P<mes>'+MES+r')\s*(?:del|de)\s*(?:ano\s*)?'
    r'(?P<anio>'+ANIO+r')(?![a-z0-9])', re.S)

def segmento(p, a, b, metodo):
    if not 0 <= a < b <= len(p['texto']):
        raise ValueError('Rango documental inválido')
    return {'fuente_id': p['fuente_id'], 'pagina': p['pagina'],
            'rango_caracteres': [a,b], 'texto': p['texto'][a:b],
            'sha256_texto_fuente': sha(p['texto'].encode()), 'metodo': metodo}

def verificar_segmento(s, paginas):
    p = paginas[s['fuente_id']]
    a,b = s['rango_caracteres']
    if (s['pagina'] != p['pagina'] or not 0 <= a < b <= len(p['texto']) or
            p['texto'][a:b] != s['texto'] or sha(p['texto'].encode()) != s['sha256_texto_fuente']):
        raise ValueError('El segmento no corresponde literalmente a la lectura')

def hasta_articulo(lectura, indice, inicio, metodo, max_paginas=3):
    """Conserva cada página por separado; registra si no se encontró un cierre."""
    segmentos = []
    cerrado = False
    for i in range(indice, min(len(lectura['paginas']), indice+max_paginas)):
        p = lectura['paginas'][i]
        a = inicio if i == indice else 0
        siguiente = ARTICULO.search(p['texto'], a)
        b = siguiente.start() if siguiente else len(p['texto'])
        if b > a and p['texto'][a:b].strip():
            segmentos.append(segmento(p,a,b,metodo))
        if siguiente:
            cerrado = True
            break
    return segmentos, cerrado

def tarea(campo, objetivo, segmentos, opciones, datos, indicio=None):
    t = {'campo': campo, 'objetivo': objetivo, 'segmentos': segmentos,
         'opciones': opciones, 'datos_por_codigo': datos,
         'indicio_por_codigo': indicio, 'aprobado': False}
    t['tarea_id'] = campo+'_'+firma(t)[:16]
    return t

def denominaciones(lectura):
    patron = re.compile(r'(?:\bdenominad[ao]\s+|\braz[oó]n\s+de\s+la\s+asociaci[oó]n\s+civil\s+es\s+)'
                       r'["“](?P<nombre>[^"”]{10,240})["”]', re.I)
    por_clave = {}
    for p in lectura['paginas']:
        for m in patron.finditer(p['texto']):
            a,b = m.span('nombre')
            literal = p['texto'][a:b]
            clave = ' '.join(literal.casefold().split())
            s = segmento(p,max(0,m.start()-80),min(len(p['texto']),m.end()+160),'declaracion_con_denominacion_entre_comillas')
            prioridad = 0 if re.search(r'raz[oó]n\s+de',m.group(),re.I) else 1
            nuevo={'valor_literal_ocr': literal, 'rango_valor_caracteres': [a,b],
                   'segmento': s, 'prioridad': prioridad}
            if clave not in por_clave or prioridad<por_clave[clave]['prioridad']:
                por_clave[clave]=nuevo
    candidatos=list(por_clave.values())
    candidatos.sort(key=lambda c:(c['prioridad'],c['segmento']['pagina'],c['rango_valor_caracteres'][0]))
    elegidos = candidatos[:4]
    if not elegidos:
        return [], {'estado':'sin_patron_documental; no_demuestra_ausencia'}
    opciones = {chr(65+i): c['valor_literal_ocr'] for i,c in enumerate(elegidos)}
    opciones['X'] = 'ninguna opción identifica con claridad a la entidad constituida'
    t = tarea('razon_social',
        'Selecciona la denominación de la entidad que se constituye. Usa la opción mejor respaldada '
        'por una declaración de denominación. No selecciones personas físicas. Las opciones son '
        'textos OCR, con posibles errores; no los corrijas.',
        [c['segmento'] for c in elegidos], opciones, {'candidatos': elegidos})
    return [t], {'detectadas':len(candidatos),'incluidas':len(elegidos),
                 'omitidas_por_limite': candidatos[4:]}

def contexto_fecha(p, a, b):
    texto = p['texto']
    antes = texto[max(0,a-300):a]
    if re.search(r'\bSiendo\s+las\b', antes, re.I):
        m = list(re.finditer(r'\bSiendo\s+las\b', texto[:a], re.I))[-1]
        ca, cb = max(0,m.start()-25), min(len(texto),b+1150)
        cierre = re.search(r'\bESTATUTOS\b\s*\n|\bCAP[ÍI]TULO\b',texto[b:cb],re.I)
        if cierre: cb = b+cierre.start()
    else:
        ca,cb = max(0,a-260),min(len(texto),b+430)
        cierres = list(re.finditer(r'\b(?:DEFINITIVA|EXPEDICI[ÓO]N|PROTOCOLIZACI[ÓO]N\s+DE\s+ACTA)\b',texto[b:cb],re.I))
        if cierres and cierres[0].start()>20: cb=b+cierres[0].start()
    return segmento(p,ca,cb,'ventana_del_evento_de_fecha_sin_mezclar_paginas')

def fechas(lectura):
    tareas, inventario, excluidas = [], [], []
    for p in lectura['paginas']:
        encontrados = detectar_fechas(p['texto'],p['fuente_id'],p['pagina'])
        normalizado,mapa = _mapa(p['texto'])
        for m in MES_INTERCALADO.finditer(normalizado):
            try:
                anio = numero_espanol(m['anio'])
                if not m['anio'].isdigit() and re.match(r'\s*[a-z0-9]',normalizado[m.end():]):
                    continue
                iso = date(anio,MESES[m['mes']],numero_espanol(m['dia'])).isoformat()
            except ValueError:
                continue
            a,b = mapa[m.start()],mapa[m.end()-1]+1
            if any(a<=f['rango_valor_caracteres'][0] and f['rango_valor_caracteres'][1]<=b for f in encontrados):
                continue
            comp = {}
            for clave in ('dia','mes','anio'):
                x,y = mapa[m.start(clave)],mapa[m.end(clave)-1]+1
                comp[clave]={'literal':p['texto'][x:y],'rango_caracteres':[x,y]}
            encontrados.append({'fecha_iso':iso, 'valor_literal_ocr':p['texto'][a:b],
                'rango_valor_caracteres':[a,b], 'componentes_literales':comp,
                'metodo':'componentes_en_formula_DEL_MES_DE; sin_sustituir_caracteres',
                'alertas':['separador_intermedio_con_ruido_OCR; revisar']
                    if not re.fullmatch(r'[\W_]*(?:dias?)?[\W_]*',m['separador']) else []})
        for f in sorted(encontrados,key=lambda f:f['rango_valor_caracteres'][0]):
            a,b=f['rango_valor_caracteres']
            s=contexto_fecha(p,a,b)
            f.update(pagina=p['pagina'],fuente_id=p['fuente_id'],aprobado=False)
            # La fecha de nacimiento no se presenta como candidata a constitución.
            if re.search(r'\b(?:nacid[oa]|naci[oó]|nacimiento)\b',p['texto'][max(0,a-300):a],re.I):
                excluidas.append(dict(f,motivo='indicio_de_fecha_personal; revisar'))
                continue
            inventario.append(f)
            tareas.append(tarea('fecha_constitucion',
                'Clasifica ÚNICAMENTE el evento de la fecha indicada, no otras fechas del fragmento. '
                'Conserva separados la asamblea transcrita, la protocolización y las autorizaciones. '
                'Esta consulta no elige una fecha final de constitución. FECHA INDICADA: '+f['valor_literal_ocr'],
                [s], FECHAS_EVENTOS, {'fecha':f}))
    # Conserva aperturas de expedición aunque la fecha no entre en la gramática.
    no_normalizadas=[]
    for p in lectura['paginas']:
        for m in re.finditer(r'\bSE\s+EXPIDE\s+A\s*LOS\b',p['texto'],re.I):
            s=segmento(p,max(0,m.start()-80),min(len(p['texto']),m.end()+430),'expedicion_con_fecha_no_normalizada')
            no_normalizadas.append({'segmento':s,'fecha_iso':None,
                'estado':'revisar_dia_y_anio_literal; no_se_completa_fecha_desde_el_modelo'})
    return tareas,{'fechas_detectadas':inventario,'fechas_personales_excluidas':excluidas,
                    'fechas_no_normalizadas':no_normalizadas,
                    'fecha_final_constitucion':None,'estado':'eventos_y_conflictos_pendientes_de_revision'}

def items_enumerados(segmentos):
    items=[]
    patron=re.compile(r'(?im)^[ \t]*[^\w\n]{0,18}(?P<marca>[a-z0-9€]{0,2})[ \t]*\)[ \t]*(?P<valor>[^\n]+)')
    for s in segmentos:
        matches=list(patron.finditer(s['texto']))
        for i,m in enumerate(matches):
            a=m.start('valor')
            b=matches[i+1].start() if i+1<len(matches) else len(s['texto'])
            # Un pie de página no se convierte en parte del último elemento.
            pie=re.search(r'(?m)^\s*(?:ESC\.|VOL\.|RG[Il/])',s['texto'][a:b])
            if pie:b=a+pie.start()
            while b>a and s['texto'][b-1].isspace():b-=1
            if b>a:
                items.append({'texto_item_literal':s['texto'][a:b],'pagina':s['pagina'],
                    'fuente_id':s['fuente_id'],'rango_caracteres':[s['rango_caracteres'][0]+a,s['rango_caracteres'][0]+b],
                    'sha256_texto_fuente':s['sha256_texto_fuente'],
                    'marca_ocr_literal':m['marca'],
                    'tipo_item_por_codigo':'representantes_de_institucion' if re.match(r'\d+\s+representantes\b',s['texto'][a:b],re.I)
                         else 'elemento_de_lista; revisar_nombre_y_OCR', 'aprobado':False})
    return items

def listas_asociados(lectura):
    tareas,grupos=[],[]
    patrones=[(r'\bcomo\s+instituciones\s+asociadas\s+las\s+siguientes\s*:', 'A'),
              (r'\bLos\s+observadores\s+ser[aá]n\s+los\s+siguientes\s*:', 'B')]
    for i,p in enumerate(lectura['paginas']):
        for patron,indicio in patrones:
            for m in re.finditer(patron,p['texto'],re.I):
                segs,cerrado=hasta_articulo(lectura,i,m.end(),'lista_hasta_siguiente_articulo; conserva_continuacion')
                # Incluye su cabecera y la definición inmediatamente anterior.
                contexto=[segmento(p,max(0,m.start()-380),m.end(),'cabecera_y_definicion_de_lista')]+segs
                datos={'items':items_enumerados(segs),'cierre_encontrado':cerrado,
                       'tipo_de_estructura':'lista_documental; no_tabla_accionaria',
                       'advertencia':'Puede contener instituciones o representantes institucionales; no se infiere propiedad ni acciones.'}
                grupos.append({'segmentos':contexto,**datos,'indicio_por_codigo':indicio})
                tareas.append(tarea('socios',
                    'Clasifica el rol de ESTA enumeración. Distingue instituciones asociadas, '
                    'observadores con voz sin voto y accionistas. No conviertas asistentes o '
                    'representantes institucionales en propietarios. Lee la cabecera y su lista.',
                    contexto,{'A':'lista de asociados o instituciones asociadas',
                              'B':'lista de observadores', 'C':'lista de accionistas con acciones',
                              'X':'rol indeterminado'},datos,indicio))
    return tareas,{'grupos':grupos,'exhaustividad_documental':'no_verificada'}

def poderes(lectura):
    tareas,relacionadas=[],[]
    for p in lectura['paginas']:
        for m in re.finditer(r'\bdesignan\s+como\s+apoderad[oa]\b',p['texto'],re.I):
            a=max(0,m.start()-70)
            siguientes=re.search(r'\bLas\s+personas\s+anteriormente\s+nombradas\b|\bTercero\b',p['texto'][m.end():],re.I)
            b=m.end()+siguientes.start() if siguientes else min(len(p['texto']),m.end()+1400)
            s=segmento(p,a,b,'clausula_de_designacion_y_otorgamiento')
            datos={'otorgamiento_literal':s,'alcance_global':'pendiente_de_revision',
                   'limitaciones_y_remisiones':'no_se_afirman_resueltas'}
            tareas.append(tarea('poderes',
                '¿El fragmento realiza una designación u otorgamiento a una persona, enumera '
                'facultades generales de un órgano o transcribe una norma? Clasifica el acto '
                'documental. La clasificación no decide vigencia ni todas sus restricciones.',
                [s],{'A':'designación de apoderado u otorgamiento expreso a persona',
                     'B':'facultades estatutarias de órgano sin designación personal',
                     'C':'transcripción de norma legal', 'X':'no se puede determinar'},datos,'A'))
        for m in re.finditer(r'\b(?:limitaci[oó]n|autorizaci[oó]n\s+expresa|l[ií]mites\s+de\s+sus\s+propias\s+facultades)\b',p['texto'],re.I):
            s=segmento(p,max(0,m.start()-260),min(len(p['texto']),m.end()+550),'posible_restriccion; vinculacion_juridica_pendiente')
            relacionadas.append(s)
    return tareas,{'clausulas_relacionadas_para_revision':relacionadas,
                    'alcance':'La clasificación recibe sólo la cláusula de designación. Las restricciones relacionadas no quedan aplicadas ni descartadas automáticamente.'}

def patrimonio(lectura):
    tareas,secciones=[],[]
    patron=r'\bpatrimonio\s+de\s+la\s+asociaci[oó]n\s+estar[aá]\s+integrado\s*:'
    for i,p in enumerate(lectura['paginas']):
        for m in re.finditer(patron,p['texto'],re.I):
            segs,cerrado=hasta_articulo(lectura,i,m.start(),'patrimonio_hasta_siguiente_articulo')
            datos={'segmentos':segs,'cierre_encontrado':cerrado,
                   'capital_social_actual':None,'importe_vigente':None,
                   'alcance':'únicamente los fragmentos recibidos; no certifica ausencia ni capital vigente'}
            secciones.append(datos)
            indicio='B' if not re.search(r'\bcapital\s+social\b','\n'.join(s['texto'] for s in segs),re.I) else None
            tareas.append(tarea('capital_social_actual',
                '¿Qué acredita este fragmento? Distingue fuentes del patrimonio de una asociación '
                'de una cantidad expresa de capital social. No calcules importes ni infieras '
                'capital actual. Tu respuesta describe únicamente este pasaje.',segs,
                {'A':'cantidad expresa de capital social',
                 'B':'fuentes o composición del patrimonio sin importe expreso de capital social',
                 'C':'importe inicial o mínimo, sin acreditar vigencia actual',
                 'X':'no se puede determinar'},datos,indicio))
    return tareas,{'secciones':secciones,'capital_social_actual':None,
                   'nota':'No encontrar esta fórmula no demuestra ausencia de capital o patrimonio.'}

def preparar(lectura):
    tareas,detalles=[],{}
    for nombre,funcion in [('razon_social',denominaciones),('fecha_constitucion',fechas),
            ('socios',listas_asociados),('poderes',poderes),('capital_social_actual',patrimonio)]:
        ts,d=funcion(lectura)
        tareas.extend(ts);detalles[nombre]=d
    paginas={p['fuente_id']:p for p in lectura['paginas']}
    for t in tareas:
        for s in t['segmentos']:verificar_segmento(s,paginas)
        if 'X' not in t['opciones']:raise ValueError('Toda consulta debe permitir abstención')
    ids=[t['tarea_id'] for t in tareas]
    if len(set(ids))!=len(ids):raise ValueError('Tareas duplicadas')
    return {'tareas':tareas[:MAX_TAREAS],'tareas_omitidas_por_presupuesto':tareas[MAX_TAREAS:],
            'detalles':detalles,'metodo':'recuperacion_estructural_y_clasificacion; variante_de_desarrollo',
            'respuestas_esperadas_recibidas':False,'referencias_humanas_verificadas':False,
            'precision':None,'recall_recuperacion':None,
            'advertencia':'La nueva recuperación se desarrolla sobre este caso. Falta evaluar su generalización y cobertura.'}
