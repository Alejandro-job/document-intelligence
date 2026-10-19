"""Motor documental: ocho campos, detonadores y referencias comprobables.

No recibe valores esperados. Los resultados automáticos son propuestas; las
fechas ambiguas y el capital sin evidencia expresa quedan en null.
"""
import argparse
import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path
from document_revision import CAMPOS, guardar, sha
from evidence_fragments import preparar, segmento
from date_candidates import numero_espanol

DETONADORES = {
    'razon_social': ['denominada', 'denominación', 'razón social', 'razón de la asociación'],
    'fecha_constitucion': ['constitución', 'constitutiva', 'otorgamiento', 'protocolización', 'asamblea'],
    'numero_escritura': ['instrumento', 'escritura', 'protocolo'],
    'notario': ['yo licenciado', 'yo, licenciada', 'notario', 'notaria', 'ante mí'],
    'socios': ['socios', 'accionistas', 'instituciones asociadas', 'asociados', 'suscriptores'],
    'representantes_legales': ['designan', 'designa', 'nombran', 'administrador único', 'apoderado'],
    'poderes': ['poder general', 'pleitos y cobranzas', 'actos de administración', 'actos de dominio', 'facultades'],
    'capital_social_actual': ['capital social', 'capital suscrito', 'capital pagado', 'patrimonio', 'aumento de capital'],
}

def compacto(s):
    return ' '.join(s.split())

def plano(s):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', compacto(s).casefold())
                   if unicodedata.category(c) != 'Mn')

def normalizar_lectura(x):
    """Admite LECTURA de paso16 y lectura multimotor; no une sus textos."""
    if not isinstance(x, dict) or not isinstance(x.get('paginas'), list):
        raise ValueError('Se esperaba un JSON con paginas y textos OCR')
    huella=x.get('sha256_pdf')
    if not isinstance(huella, str) or not re.fullmatch(r'[a-f0-9]{64}', huella):
        raise ValueError('Falta sha256_pdf válido; no se inventa identidad documental')
    pags=[]
    for original in x['paginas']:
        n=original.get('pagina')
        if not isinstance(n,int) or isinstance(n,bool) or n<1:
            raise ValueError('Número de página inválido')
        if original.get('sha256_pdf',huella)!=huella:
            raise ValueError('Páginas de distintos PDFs')
        fuentes=original.get('fuentes')
        if fuentes:
            # Una sola fuente por página: elegir por orden declarado, sin mezclar OCR.
            p=dict(fuentes[0],pagina=n)
        else:
            p=dict(original)
        if not isinstance(p.get('texto'),str):raise ValueError('Página sin texto válido')
        p.setdefault('fuente_id',f'doc_{huella[:24]}:p{n:03}:texto')
        p.setdefault('estado','completo')
        p['sha256_pdf']=huella
        pags.append(p)
    pags.sort(key=lambda p:p['pagina'])
    if [p['pagina'] for p in pags]!=list(range(1,len(pags)+1)):
        raise ValueError('Páginas ausentes o duplicadas')
    if x.get('paginas_totales',len(pags))!=len(pags):
        raise ValueError('El número total de páginas no coincide')
    if len({p['fuente_id'] for p in pags})!=len(pags):raise ValueError('Fuentes duplicadas')
    return {**x,'paginas':pags,'paginas_totales':len(pags)}

def leer_entrada(ruta):
    ruta=Path(ruta)
    if ruta.suffix.lower()=='.json':return normalizar_lectura(json.loads(ruta.read_bytes()))
    if ruta.suffix.lower()!='.zip':raise ValueError('Usa un PDF, LECTURA.json o ZIP de resultados')
    with zipfile.ZipFile(ruta) as z:
        opciones=[n for n in z.namelist() if Path(n).name in ('LECTURA.json','LECTURA_ORIGEN.json','lectura_para_extraccion.json')]
        if not opciones:raise ValueError('El ZIP no contiene lectura OCR; selecciona el ZIP de RESULTADOS')
        opciones.sort(key=lambda n:(n!='OCR/LECTURA.json',len(n),n))
        info=z.getinfo(opciones[0])
        if info.file_size>60_000_000:raise ValueError('Lectura demasiado grande')
        return normalizar_lectura(json.loads(z.read(info)))

def fragmentos(lectura, largo=1000, solape=160):
    if not 0<=solape<largo:raise ValueError('Solapamiento inválido')
    salida=[]
    for p in lectura['paginas']:
        a=0
        while a<len(p['texto']):
            b=min(len(p['texto']),a+largo)
            if b<len(p['texto']):
                salto=p['texto'].rfind('\n',a+largo//2,b)
                if salto>a:b=salto+1
            if p['texto'][a:b].strip():
                s=segmento(p,a,b,'fragmento_para_localizador')
                s['fragmento_id']=sha((p['fuente_id']+':'+str(a)+':'+str(b)).encode())[:24]
                s['detonadores']={c:[v for v in vv if plano(v) in plano(s['texto'])]
                                  for c,vv in DETONADORES.items()}
                salida.append(s)
            if b==len(p['texto']):break
            a=max(a+1,b-solape)
    return salida

def candidatos_directos(lectura):
    resultado={c:[] for c in CAMPOS}
    instrumento=re.compile(r'(?im)^[^\w\n]{0,16}(?:INSTRUMENTO|ESCRITURA)(?:\s+P[ÚU]BLICA)?\s*[:.-]?\s*(?:N[ÚU]MERO|N[Oº°][.]?)?\s*[:.-]?\s*(?P<valor>\d[\d,.]*\d|\d)\b')
    notario=re.compile(r'\bYO\s*,?\s*(?:(?:EL|LA)\s+)?(?:(?:LICENCIAD[OA]|LIC\.|DOCTOR[AA]?)\s+)?(?P<nombre>[^,;:.]{5,120}?)\s*,\s*NOTARI[OA]\b',re.I)
    designacion=re.compile(r'\b(?:designan|designa|nombran|nombra|designase|desígnase)\s+(?:como\s+)?(?P<rol>apoderad[oa]|administrador(?:a)?\s+[úu]nic[oa])\b[^.;]{0,200}?\b(?:señor[a]?|ciudadan[oa]|licenciad[oa])\s+(?P<nombre>[^,;.]{5,130}?)(?=,|\.|\s+quien\b)',re.I)
    for p in lectura['paginas']:
        texto=p['texto']
        for m in instrumento.finditer(texto):
            # Cabecera de apertura, no números de instrumentos citados más adelante.
            if p['pagina']>2 or m.start()>1500:continue
            a,b=m.span('valor')
            resultado['numero_escritura'].append({'valor':texto[a:b], 'segmento':segmento(p,max(0,m.start()-60),min(len(texto),m.end()+110),'cabecera_instrumento'), 'rango_valor':[a,b]})
        for m in notario.finditer(texto):
            a,b=m.span('nombre')
            tail=texto[m.end():m.end()+200]
            num=re.search(r'\bn[úu]mero\s+(?P<n>\d+|[A-ZÁÉÍÓÚÑ]+(?:\s+(?:Y|[A-ZÁÉÍÓÚÑ]+)){0,5})',tail,re.I)
            numero=None;lit=None;numero_span=None
            if num:
                palabras=num['n'].split()
                # El número termina antes de la primera palabra ajena a la gramática.
                for k in range(len(palabras),0,-1):
                    parcial=' '.join(palabras[:k])
                    try:numero=numero_espanol(parcial)
                    except ValueError:continue
                    if 1<=numero<=999:
                        inicio=m.end()+num.start('n')
                        palabras_originales=list(re.finditer(r'\S+',num['n']))
                        fin=inicio+palabras_originales[k-1].end()
                        lit=texto[inicio:fin];numero_span=[inicio,fin];break
                    numero=None
            resultado['notario'].append({'valor':{'nombre':compacto(texto[a:b]),'numero':numero},
                'numero_literal':lit,'rango_numero':numero_span,'rango_nombre':[a,b],
                'segmento':segmento(p,max(0,m.start()-100),min(len(texto),m.end()+260),'primera_persona_y_titulo_notarial')})
        for m in designacion.finditer(texto):
            a,b=m.span('nombre')
            resultado['representantes_legales'].append({'valor':{'nombre':compacto(texto[a:b]),'rol':compacto(m['rol'])},
                'rango_nombre':[a,b], 'segmento':segmento(p,max(0,m.start()-30),min(len(texto),m.end()+550),'designacion_explicita_personal')})
    return resultado

def evento_fecha(p, f):
    a,b=f['rango_valor_caracteres'];antes=p['texto'][max(0,a-360):a];despues=p['texto'][b:b+1000]
    s=plano(antes)
    if re.search(r'\b(?:nacio|nacido|nacimiento)\b',s):return 'personal'
    encabezados=list(re.finditer(r'\b(?:PREVENTIVA|DEFINITIVA|EXPEDICI[ÓO]N)\b',antes,re.I))
    if encabezados:
        return {'preventiva':'autorizacion_preventiva','definitiva':'autorizacion_definitiva','expedicion':'expedicion'}[plano(encabezados[-1].group())]
    if 'siendo las' in s and re.search(r'constituci[oó]n\s+de\s+una',despues,re.I):return 'asamblea_constitutiva'
    if p['pagina']<=2 and re.search(r'\byo\s*,?\s*(?:licenciad[oa]|el|la)',despues[:200],re.I):return 'otorgamiento_instrumento'
    if re.search(r'\b(?:permiso|s\.r\.e\.|fundamento|secretaria)\b',s):return 'antecedente_administrativo'
    if re.search(r'\bfecha\s*:?\s*$',s):return 'portada'
    return 'evento_no_resuelto'

def plantilla_etiquetado(lectura, fs):
    return [{'documento_id':lectura['sha256_pdf'],'fragmento_id':f['fragmento_id'],
        'pagina':f['pagina'],'fuente_id':f['fuente_id'],'rango_caracteres':f['rango_caracteres'],
        'sha256_texto_fuente':f['sha256_texto_fuente'],'texto':f['texto'],
        'etiquetas_sugeridas_por_reglas':[c for c,v in f['detonadores'].items() if v],
        'etiquetas':None,'verificado_humano':False,'revisado_por':None,'particion':'train'} for f in fs]

def validar_datos(datos):
    if set(datos)!=set(CAMPOS):raise ValueError('La salida debe tener exactamente ocho campos')
    for c in ('razon_social','numero_escritura'):
        if datos[c] is not None and not isinstance(datos[c],str):raise ValueError(c)
    if datos['fecha_constitucion'] is not None:
        if not isinstance(datos['fecha_constitucion'],str) or date.fromisoformat(datos['fecha_constitucion']).isoformat()!=datos['fecha_constitucion']:raise ValueError('fecha_constitucion')
    n=datos['notario']
    if n is not None and (not isinstance(n,dict) or set(n)!= {'nombre','numero'} or not isinstance(n['nombre'],str) or (n['numero'] is not None and (not isinstance(n['numero'],int) or isinstance(n['numero'],bool)))):raise ValueError('notario')
    for c in ('socios','representantes_legales','poderes'):
        if not isinstance(datos[c],list):raise ValueError(c)
    v=datos['capital_social_actual']
    if v is not None and (not isinstance(v,dict) or set(v)!= {'valor','moneda'} or not isinstance(v['valor'],(str,int,float)) or not isinstance(v['moneda'],str)):raise ValueError('capital_social_actual')

def ejecutar(lectura, salida, localizador=None):
    lectura=normalizar_lectura(lectura);salida=Path(salida);salida.mkdir(parents=True,exist_ok=True)
    paginas={p['fuente_id']:p for p in lectura['paginas']}
    preparado=preparar(lectura);directos=candidatos_directos(lectura)
    from clauses import extraer
    extras=extraer(lectura)
    for campo in ('numero_escritura','notario','representantes_legales'):
        directos[campo].extend(extras[campo])
    datos={c:([] if c in ('socios','representantes_legales','poderes') else None) for c in CAMPOS}
    evidencias={c:[] for c in CAMPOS};candidatos={c:[] for c in CAMPOS};refs={};contador=0
    def ref(s, campo, detalle=None):
        nonlocal contador
        p=paginas[s['fuente_id']];a,b=s['rango_caracteres']
        if p['texto'][a:b]!=s['texto'] or sha(p['texto'].encode())!=s['sha256_texto_fuente']:raise ValueError('Cita no literal')
        clave=(s['fuente_id'],a,b)
        if clave not in refs:
            contador+=1;refs[clave]={'referencia':f'E{contador:04}','pagina':s['pagina'],
                'fuente_id':s['fuente_id'],'rango_caracteres':[a,b],
                'sha256_texto_fuente':s['sha256_texto_fuente'],'cita_literal':s['texto']}
        v=dict(refs[clave]);v.update(detalle or {})
        if v not in evidencias[campo]:evidencias[campo].append(v)
        return v['referencia']
    for campo in ('numero_escritura','notario'):
        cs=directos[campo]
        unicos={re.sub(r'[,.]','',c['valor']) if campo=='numero_escritura'
                else json.dumps(c['valor'],ensure_ascii=False,sort_keys=True) for c in cs}
        if len(unicos)==1:datos[campo]=cs[0]['valor']
        for c in cs:
            e=ref(c['segmento'],campo,{'valor_propuesto':c['valor'],'metodo':c['segmento']['metodo']})
            candidatos[campo].append({**c,'referencia':e})
    nombres=preparado['detalles']['razon_social']
    cs=[c for t in preparado['tareas']+preparado['tareas_omitidas_por_presupuesto'] if t['campo']=='razon_social' for c in t['datos_por_codigo']['candidatos']]
    cs.extend(extras['razon_social'])
    if cs:
        prioridad=min(c['prioridad'] for c in cs);preferidos=[c for c in cs if c['prioridad']==prioridad]
        if len({plano(c['valor_literal_ocr']) for c in preferidos})==1:
            compuestos={c['valor_compuesto'] for c in preferidos if c.get('valor_compuesto')}
            datos['razon_social']=next(iter(compuestos)) if len(compuestos)==1 else compacto(preferidos[0]['valor_literal_ocr'])
        for c in cs:
            e=ref(c['segmento'],'razon_social',{'valor_propuesto':c.get('valor_compuesto',c['valor_literal_ocr']),'prioridad_regla':c['prioridad'],
                'rangos_componentes':c.get('rangos_valor',[c['rango_valor_caracteres']]),'composicion_explicita':bool(c.get('valor_compuesto'))})
            candidatos['razon_social'].append({**c,'referencia':e})
    # Se conservan los eventos; no se confunde fecha de acta con su protocolización.
    fechas=preparado['detalles']['fecha_constitucion']['fechas_detectadas']
    for f in fechas:
        p=paginas[f['fuente_id']];a,b=f['rango_valor_caracteres'];ev=evento_fecha(p,f)
        s=segmento(p,max(0,a-360),min(len(p['texto']),b+1000),'fecha_y_contexto_de_evento')
        e=ref(s,'fecha_constitucion',{'fecha_normalizada':f['fecha_iso'],'evento_por_regla':ev,'literal_fecha':f['valor_literal_ocr']})
        candidatos['fecha_constitucion'].append({**f,'evento_por_regla':ev,'referencia':e})
    constitutivas=[f for f in candidatos['fecha_constitucion'] if f['evento_por_regla']=='asamblea_constitutiva']
    # Política explícita: acta constitutiva original si es inequívoca; no usar autorización/testimonio.
    if len({f['fecha_iso'] for f in constitutivas})==1:datos['fecha_constitucion']=constitutivas[0]['fecha_iso']
    for grupo in preparado['detalles']['socios']['grupos']:
        er=[ref(s,'socios',{'tipo_lista':grupo['indicio_por_codigo'],'cierre_encontrado':grupo['cierre_encontrado']}) for s in grupo['segmentos']]
        if grupo['indicio_por_codigo']=='A' and grupo['cierre_encontrado']:
            for item in grupo['items']:
                es_rep=item['tipo_item_por_codigo']=='representantes_de_institucion'
                literal=item['texto_item_literal']
                # Separadores tipográficos posteriores al punto y descripción representativa
                # permanecen en texto_literal; no se corrigen caracteres de los nombres.
                nombre=re.split(r'\.(?=\s|$)',literal,maxsplit=1)[0]
                if re.match(r'Secretar[ií]a\b',nombre,re.I):nombre=nombre.split(',',1)[0]
                valor={'nombre':compacto(nombre),
                    'tipo':'representantes_institucionales' if es_rep else 'institucion_asociada',
                    'texto_literal':literal}
                if valor not in datos['socios']:datos['socios'].append(valor)
                candidatos['socios'].append({**item,'valor':valor,'referencias':er})
    prioridad_socios=min((c.get('prioridad',0) for c in extras['socios']),default=0)
    for c in extras['socios']:
        e=ref(c['segmento'],'socios',{'tipo_lista':'asociados_constituyentes_explicitos','valor_propuesto':c['valor']})
        if c.get('prioridad',0)==prioridad_socios and not any(plano(v['nombre'])==plano(c['valor']['nombre']) for v in datos['socios']):
            datos['socios'].append(c['valor'])
        candidatos['socios'].append({**c,'referencia':e})
    for c in directos['representantes_legales']:
        v=c['valor']
        if v not in datos['representantes_legales']:datos['representantes_legales'].append(v)
        e=ref(c['segmento'],'representantes_legales',{'valor_propuesto':v})
        candidatos['representantes_legales'].append({**c,'referencia':e})
    for t in preparado['tareas']+preparado['tareas_omitidas_por_presupuesto']:
        if t['campo']=='poderes':
            s=t['datos_por_codigo']['otorgamiento_literal']
            tipos=[]
            for patron,tipo in [(r'PLEITOS\s+Y\s+COBRANZAS','pleitos_y_cobranzas'),(r'ACTOS\s+DE\s+ADMINISTRACI[ÓO]N','administracion'),(r'ACTOS\s+DE\s+DOMINIO','dominio')]:
                if re.search(patron,s['texto'],re.I):tipos.append(tipo)
            e=ref(s,'poderes',{'tipos_identificados':tipos})
            datos['poderes'].append({'tipos':tipos,'texto_otorgamiento':s['texto'],
                'titulares_mencionados':[v['nombre'] for v in datos['representantes_legales'] if plano(v['nombre']) in plano(s['texto'])]})
            candidatos['poderes'].append({'referencia':e,'alcance_y_restricciones':'requieren_revision'})
    for grupo in extras['otorgamientos']:
        referencias=[];tipos=[]
        for s in grupo['segmentos']:
            referencias.append(ref(s,'poderes',{'tipo':'otorgamiento_personal_y_continuacion',
                'titular':grupo['persona'],'cierre_encontrado':grupo['cierre_encontrado']}))
            for patron,tipo in [(r'PLEITOS\s+Y\s+COBRANZAS','pleitos_y_cobranzas'),
                (r'ACTOS\s+DE\s+ADMINISTRACI[ÓO]N','administracion'),
                (r'ACTOS\s+DE\s+DOMINIO','dominio'),(r'MATERIA\s+LABORAL','laboral'),
                (r'T[IÍ]TULOS\s+Y\s+OPERACIONES\s+DE\s+CR[EÉ]DITO','titulos_de_credito'),
                (r'Delegar\s+sus\s+facultades','delegacion')]:
                if re.search(patron,s['texto'],re.I) and tipo not in tipos:tipos.append(tipo)
        datos['poderes'].append({'tipos':tipos,'titulares_mencionados':[grupo['persona']],
            'referencias':referencias,'alcance_y_restricciones':'requieren_revision',
            'continuacion_cerrada':grupo['cierre_encontrado']})
        candidatos['poderes'].append({'referencias':referencias,'alcance_y_restricciones':'requieren_revision'})
    for s in preparado['detalles']['poderes']['clausulas_relacionadas_para_revision']:
        ref(s,'poderes',{'tipo':'posible_restriccion; vinculacion_no_resuelta'})
    for sec in preparado['detalles']['capital_social_actual']['secciones']:
        for s in sec['segmentos']:ref(s,'capital_social_actual',{'tipo':'composicion_patrimonio; no_importe_de_capital_actual'})
    # Extraer importes no basta para afirmar el capital actual. Se conservan las menciones.
    for p in lectura['paginas']:
        for m in re.finditer(r'\bcapital\s+(?:social|suscrito|pagado)\b',p['texto'],re.I):
            s=segmento(p,max(0,m.start()-120),min(len(p['texto']),m.end()+550),'mencion_de_capital; vigencia_no_verificada')
            ref(s,'capital_social_actual',{'tipo':'mencion_documental; capital_actual_no_determinado'})
    fs=fragmentos(lectura)
    puntajes=None
    if localizador:
        from citi_entrenar import predecir
        puntajes=predecir(localizador,[f['texto'] for f in fs])
    rankings={}
    for campo in CAMPOS:
        filas=[]
        for i,f in enumerate(fs):
            det=f['detonadores'][campo];n=puntajes[i].get(campo) if puntajes else None
            if det or n is not None:
                filas.append({'fragmento_id':f['fragmento_id'],'pagina':f['pagina'],
                    'detonadores':det,'puntaje_red':n,'puntaje_reglas':len(det)})
        filas.sort(key=lambda r:(r['puntaje_red'] if r['puntaje_red'] is not None else -1,r['puntaje_reglas']),reverse=True)
        rankings[campo]=filas
    estados={}
    for c in CAMPOS:
        valor=datos[c]
        estados[c]={'estado':'propuesta_documental' if valor not in (None,[]) else 'no_determinado',
            'revision_humana':'pendiente','evidencia_disponible':bool(evidencias[c])}
    control={'sha256_pdf':lectura['sha256_pdf'],'archivo':lectura.get('archivo'),
        'estados':estados,'politica_fecha':'fecha de asamblea constitutiva explícita; otras fechas se conservan y no sustituyen el campo',
        'politica_capital':'no se afirma capital actual por una mención histórica o por el patrimonio',
        'ocr':'los errores de la fuente se conservan; revisar nombres y listas',
        'arrays_vacios':'no se determinaron elementos; no demuestran inexistencia',
        'vigencia_actual':'no_verificada','precision_extraccion':None,'recall_extraccion':None,'f1_extraccion':None,
        'entrenamiento_qwen':False,'modelo_localizador_usado':bool(localizador),
        'documento_en_train_localizador':lectura['sha256_pdf'] in localizador.get('documentos_train',[]) if localizador else False,
        'localizador':'ordena fragmentos para revisión; no sustituye las reglas de rol ni completa valores',
        'advertencia':'Caso de desarrollo. La revisión del OCR, las listas, los roles y las restricciones sigue pendiente.'}
    grupos_socios={}
    for c in extras['socios']:
        grupos_socios.setdefault(c['segmento']['fuente_id'],[]).append(c['valor']['nombre'])
    if len({tuple(sorted(plano(n) for n in nombres)) for nombres in grupos_socios.values()})>1:
        control['diferencias_listas_socios']={'estado':'nombres_literales_difieren; identidad_y_grafia_pendientes_de_revision',
            'grupos_por_fuente':grupos_socios,'politica':'se conserva la cláusula explícita; las otras apariciones se muestran sin crear personas adicionales'}
    validar_datos(datos)
    guardar(salida/'EXTRACCION_OCHO_CAMPOS.json',datos)
    guardar(salida/'EVIDENCIAS_Y_CONTROL.json',{'evidencias':evidencias,'control':control})
    guardar(salida/'CANDIDATOS_Y_EVENTOS.json',{'campos':candidatos,'fechas_sin_normalizar':preparado['detalles']['fecha_constitucion']['fechas_no_normalizadas']})
    guardar(salida/'RECUPERACION_DETONADORES.json',{'rankings':rankings,'fragmentos':fs,'recall_at_k':None,'mrr':None,'nota':'Sin relevancias completas verificadas; estos rankings no miden calidad.'})
    guardar(salida/'EJEMPLOS_PARA_CORREGIR.json',plantilla_etiquetado(lectura,fs))
    guardar(salida/'LECTURA.json',lectura)
    return datos,{'evidencias':evidencias,'control':control}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('entrada');p.add_argument('--salida',required=True);p.add_argument('--localizador')
    a=p.parse_args();m=json.loads(Path(a.localizador).read_bytes()) if a.localizador else None
    d,_=ejecutar(leer_entrada(a.entrada),a.salida,m)
    print(json.dumps(d,ensure_ascii=False,indent=2))
