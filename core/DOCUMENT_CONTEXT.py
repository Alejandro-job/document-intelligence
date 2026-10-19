"""Contexto por página, encabezados y tablas de personas; sin entrenar modelos.

Lee una lectura existente. Las reglas proponen candidatos, no aprobaciones.
Conserva texto, rangos, fuente y huellas. No necesita Qwen ni OCR nuevo.
"""
import argparse
import hashlib
import json
import re
import statistics
import unicodedata
import zipfile
from pathlib import Path

CAMPOS=('razon_social','fecha_constitucion','numero_escritura','notario','socios',
        'representantes_legales','poderes','capital_social_actual')
PATRONES={
 'razon_social':[r'\bDENOMINACION\b',r'\bRAZON\s+SOCIAL\b',r'\bSE\s+DENOMINA(?:RA)?\b'],
 'fecha_constitucion':[r'\bCONSTITUCION\b',r'\bCONSTITUIR\b',r'\bFECHA\s+DE\s+FIRMA\b'],
 'numero_escritura':[r'\bESCRITURA\s+(?:NUMERO\b|[A-Z]|\d)',r'\bINSTRUMENTO\b'],
 'notario':[r'\bDATOS\s+DEL\s+NOTARIO\b',r'\bANTE\s+MI\b',r'\bEN\s+FUNCIONES\s+DE\s+NOTARIO\b',r'\bDE\s+NOTARIA\b'],
 'socios':[r'\bOTORGANTE\s*\(?S?\)?',r'\bACCIONI?STAS?\b',r'\bSOCIOS\b',r'\bSUSCRITO\s+Y\s+PAGADO\b'],
 'representantes_legales':[r'\bDESIGNANDO\b',r'\bDESIGNAN\b',r'\bNOMBRAMIENTO\b',r'\bCONFIEREN\b',r'\bAPODERAD[OA]\b'],
 'poderes':[r'\bPODER\s+GENERAL\b',r'\bFACULTADES\b',r'\bPLEITOS\s+Y\s+COBRANZAS\b'],
 'capital_social_actual':[r'\bCAPITAL\s+SOCIAL\b',r'\bCAPITAL\s+MINIMO\b',r'\bSUSCRITO\s+Y\s+PAGADO\b',r'\bACCIONISTA\b',r'\bIMPORTE\b'],
}
TIPOS={
 'identificacion_anexa':[r'CREDENCIAL\s+PARA\s+VOTAR',r'INSTITUTO\s+FEDERAL\s+ELECTOR'],
 'constancia_fiscal':[r'CONSTANCIA\s+DE\s+REGISTRO\s+EN\s+EL\s+RFC',r'INSCRIPCION\s+EN\s+EL\s+R\.?F\.?C'],
 'boleta_registral':[r'BOLETA\s+DE\s+INSCRIPCION',r'FOLIO\s+MERCANTIL'],
 'declaracion_notarial_fiscal':[r'DATOS\s+DEL\s+NOTARIO',r'OTORGANTE\s*\(S\)'],
 'autorizacion_denominacion':[r'CLAVE\s+UNICA\s+DEL\s+DOCUMENTO',r'AUTORIZACION\s+PARA\s+EL\s+USO'],
 'transitorios_y_designaciones':[r'T\s*R\s*A\s*N\s*S\s*I\s*T\s*O\s*R\s*I\s*O\s*S',r'DESIGNANDO\s+EN\s+ESTE\s+MOMENTO'],
 'apertura_del_instrumento':[r'ANTE\s+MI',r'VIENEN\s+A\s+CONSTITUIR'],
}
EXTRAS={
 'rfc':[r'\bREGISTRO\s+FEDERAL\s+DE\s+CONTRIBUYENTES\b',r'\bR\.?\s*F\.?\s*C\.?\b'],
 'fecha_inscripcion':[r'\bFECHA\s*DE\s*INSCRIPCION\b'],
 'inicio_operaciones':[r'\bINICIO\s*/?\s*DE\b',r'\bOPERACIONES\b'],
 'folio_mercantil':[r'\bFOLIO\s+MERCANTIL\s+ELECTRONICO\b'],
 'prelacion_registral':[r'\bFECHA\s+DE\s+PRELACION\b'],
 'registro':[r'\bREGISTRO\b',r'\bBOLETA\s+DE\s+INSCRIPCION\b'],
}
UNIDADES=r'(?:PRIMER[OA]|SEGUND[OA]|TERCER[OA]|CUART[OA]|QUINT[OA]|SEXT[OA]|SEPTIM[OA]|OCTAV[OA]|NOVEN[OA])'
DECENAS=r'(?:DECIM[OA]|VIGESIM[OA]|TRIGESIM[OA]|CUADRAGESIM[OA]|QUINCUAGESIM[OA]|SEXAGESIM[OA]|SEPTUAGESIM[OA]|OCTOGESIM[OA]|NONAGESIM[OA])'
ORDINAL=fr'(?:{DECENAS}(?:\s+{UNIDADES})?|{UNIDADES})'

def resolver_remisiones(paginas):
    cabeceras=[]
    for i,p in enumerate(paginas):
        for a,b in coincidencias(p['texto'],fr'(?m)^[^\n]{{0,12}}?--+\s*{ORDINAL}\s*\.-'):
            s=normalizar(p['texto'][a:b])[0]
            titulo=re.search(ORDINAL,s).group()
            cabeceras.append({'indice':i,'inicio':a,'clausula':titulo})
    cabeceras.sort(key=lambda x:(x['indice'],x['inicio']))
    salida=[]
    for p in paginas:
        for a,b in coincidencias(p['texto'],fr'\bCLAUSULA\s+{ORDINAL}\b'):
            titulo=re.sub(r'^CLAUSULA\s+','',normalizar(p['texto'][a:b])[0])
            destinos=[(j,h) for j,h in enumerate(cabeceras) if h['clausula']==titulo]
            if len(destinos)!=1:
                salida.append({'pagina_designacion':p['pagina'],'clausula':titulo,'segmentos':[],
                    'estado':'no_resuelta' if not destinos else 'ambigua','aprobado':False})
                continue
            j,h=destinos[0];siguiente=cabeceras[j+1] if j+1<len(cabeceras) else None
            segmentos=[]
            for i in range(h['indice'],len(paginas)):
                if siguiente and i>siguiente['indice']:break
                pp=paginas[i];aa=h['inicio'] if i==h['indice'] else 0
                bb=siguiente['inicio'] if siguiente and i==siguiente['indice'] else len(pp['texto'])
                if bb>aa:segmentos.append(cita(pp,aa,bb,'clausula_remitida_con_continuacion'))
                if siguiente and i==siguiente['indice']:break
            salida.append({'pagina_designacion':p['pagina'],'clausula':titulo,'segmentos':segmentos,
                'cita_remision':cita(p,a,b,'remision_literal'),'estado':'resuelta_por_encabezado_unico','aprobado':False})
    return salida

def normalizar(texto):
    salida=[];mapa=[]
    for i,c in enumerate(texto):
        for v in unicodedata.normalize('NFD',c.upper()):
            if unicodedata.category(v)!='Mn':salida.append(v);mapa.append(i)
    return ''.join(salida),mapa

def coincidencias(texto,patron):
    t,mapa=normalizar(texto)
    return [(mapa[m.start()],mapa[m.end()-1]+1) for m in re.finditer(patron,t) if m.end()>m.start()]

def cita(p,a,b,metodo):
    assert 0<=a<b<=len(p['texto'])
    return {'pagina':p['pagina'],'fuente_id':p['fuente_id'],'rango_caracteres':[a,b],
        'texto':p['texto'][a:b],'sha256_texto_fuente':hashlib.sha256(p['texto'].encode()).hexdigest(),
        'metodo':metodo,'aprobado':False}

def leer(ruta):
    p=Path(ruta)
    if p.suffix.lower()=='.json':return json.loads(p.read_bytes())
    with zipfile.ZipFile(p) as z:
        n=next((v for v in ['DATOS/LECTURA_TIDA.json','LECTURA.json','OCR/LECTURA.json'] if v in z.namelist()),None)
        if n is None:raise ValueError('El ZIP no contiene una lectura existente.')
        d=json.loads(z.read(n))
        if 'PAGINAS_RENDERIZADAS.json' in z.namelist():
            render=json.loads(z.read('PAGINAS_RENDERIZADAS.json'))
            rr={x['pagina']:x for x in render['paginas']}
            for page in d['paginas']:
                r=rr[page['pagina']]
                if r['texto']!=page['texto']:raise ValueError('Texto y geometría no coinciden.')
                page['palabras']=r['palabras']
        return d

def extraer_tabla_personas(p,inicio,fin,rol):
    """Asocia por columnas; no presupone un número fijo de palabras por nombre."""
    palabras=[w for w in p.get('palabras',[]) if inicio<=w['a']<fin and 'box' in w]
    if palabras and max(max(w['box']) for w in palabras)>1:
        ancho,alto=p.get('ancho'),p.get('alto')
        if not ancho or not alto:
            return []  # Sin unidades conocidas no se inventa una geometría.
        palabras=[{**w,'box':[w['box'][0]/ancho,w['box'][1]/alto,
                              w['box'][2]/ancho,w['box'][3]/alto]} for w in palabras]
    def col(nombre):return next((w for w in palabras if normalizar(w.get('t',''))[0]==nombre),None)
    paterno,materno,nombre=col('PATERNO'),col('MATERNO'),col('NOMBRE')
    if not all([paterno,materno,nombre]):return []
    centros=[(w['box'][0]+w['box'][2])/2 for w in [paterno,materno,nombre]]
    limites=[max(0,paterno['box'][0]-.12),(centros[0]+centros[1])/2,(centros[1]+centros[2])/2,
             min(1,centros[2]+(centros[2]-centros[1])*.8)]
    cabecera_fin=p['texto'].find('\n',nombre['b'])
    if cabecera_fin<0:return []
    datos=[w for w in palabras if w['a']>cabecera_fin and re.search(r'[A-ZÁÉÍÓÚÑ]{2}',w.get('t',''))
           and limites[0]<(w['box'][0]+w['box'][2])/2<limites[3]]
    if not datos:return []
    tolerancia=statistics.median(w['box'][3]-w['box'][1] for w in datos)*.55
    filas=[]
    for w in sorted(datos,key=lambda w:(w['box'][1]+w['box'][3])/2):
        cy=(w['box'][1]+w['box'][3])/2
        f=next((f for f in filas if abs(f['cy']-cy)<=tolerancia),None)
        if f is None:f={'cy':cy,'celdas':[[],[],[]]};filas.append(f)
        x=(w['box'][0]+w['box'][2])/2;j=0 if x<limites[1] else 1 if x<limites[2] else 2
        f['celdas'][j].append(w)
    candidatos=[]
    for f in filas:
        celdas=[sorted(v,key=lambda w:w['box'][0]) for v in f['celdas']]
        if not all(celdas):continue
        valores=[' '.join(w['t'] for w in celda) for celda in celdas]
        seleccion=[w for celda in celdas for w in celda]
        # Evitar interpretar etiquetas de otras secciones como una persona.
        if any(normalizar(v)[0] in ('REGISTRO','NOTARIO','DISTRITO','FIRMA') for v in valores):continue
        candidatos.append({'nombre_propuesto':' '.join([valores[2],valores[0],valores[1]]),
            'componentes':dict(zip(['apellido_paterno','apellido_materno','nombres'],valores)),
            'rol_documental_propuesto':rol,'rangos_nombre':[[w['a'],w['b']] for w in seleccion],
            'evidencia':cita(p,min(w['a'] for w in seleccion),max(w['b'] for w in seleccion),'tabla_con_columnas_geometricas'),
            'transformacion':'reordenar columnas nombre/apellidos; sin corregir letras OCR','aprobado':False})
    return candidatos

def analizar(lectura):
    paginas=lectura['paginas'];por_pagina=[];personas=[];alertas=[];unidades=[]
    for p in paginas:
        texto=p['texto'];n=normalizar(texto)[0]
        tipos=[tipo for tipo,patrones in TIPOS.items() if any(re.search(x,n) for x in patrones)]
        if not tipos:tipos=['texto_documental_sin_clasificar']
        detonadores={c:[cita(p,a,b,'detonador_literal_con_variante_de_OCR') for pat in pp for a,b in coincidencias(texto,pat)] for c,pp in PATRONES.items()}
        extras={c:[cita(p,a,b,'encabezado_de_metadato; no_sustituye_campo_constitutivo') for pat in pp for a,b in coincidencias(texto,pat)] for c,pp in EXTRAS.items()}
        registro={'pagina':p['pagina'],'tipos_propuestos':tipos,'detonadores':detonadores,'metadatos_contextuales':extras,
                  'fuente_id':p['fuente_id'],'texto_completo':texto,
                  'advertencia':'La clasificación describe el contenido de esta página; no sustituye el rol del instrumento completo.'}
        por_pagina.append(registro)
        # Bloques de tablas de partes y de notario con límites explícitos.
        otorgantes=coincidencias(texto,r'\bOTORGANTE\s*\(S\)')
        notario=coincidencias(texto,r'\bDATOS\s+DEL\s+NOTARIO\b')
        for a,b in otorgantes:
            fin=next((x for x,y in notario if x>b),len(texto))
            bloque=cita(p,a,fin,'bloque_otorgantes_hasta_siguiente_encabezado')
            bloque.update(campo='socios',tipo='tabla_otorgantes',prioridad=100)
            unidades.append(bloque)
            rol='accionista_propuesto' if re.search(r'\bACCIONI?STAS?\b',normalizar(texto[a:fin])[0]) else 'otorgante; caracter_pendiente'
            personas.extend(extraer_tabla_personas(p,b,fin,rol))
        for a,b in notario:
            finales=coincidencias(texto[b:],r'\b(?:OPERACION\s+EXENTA|PRECEPTO\s+LEGAL)\b')
            fin=b+finales[0][0] if finales else len(texto)
            bloque=cita(p,a,fin,'bloque_notario_con_nombre_notaria_y_RFC_propio')
            bloque.update(campo='notario',tipo='datos_del_notario',prioridad=100);unidades.append(bloque)
            corte=coincidencias(texto[b:fin],r'\bREGISTRO\s+FEDERAL\b')
            fin_nombre=b+corte[0][0] if corte else fin
            personas.extend(extraer_tabla_personas(p,b,fin_nombre,'notario_declarado; corroborar_actuante_en_apertura'))
        if re.search(r'\bACCIONISTA\s+SERIE\s+IMPORTE\b',n):
            a=coincidencias(texto,r'\bACCIONISTA\s+SERIE\s+IMPORTE\b')[0][0]
            corte=re.search(r'\bSEGUNDO\b',normalizar(texto[a:])[0])
            bloque=texto[a:a+corte.start()] if corte else texto[a:]
            if not re.search(r'\$\s*\d|\d[,.]\d{3}',bloque):
                alertas.append({'pagina':p['pagina'],'tipo':'tabla_de_accionistas_sin_filas_en_OCR',
                   'accion':'releer la región de tabla; conservar OCR nuevo como otra fuente',
                   'evidencia':cita(p,a,a+len(bloque),'cabecera_con_tabla_ausente_en_lectura')})
        for c,dd in detonadores.items():
            if dd:
                # La página completa queda disponible; no se cortan líneas arbitrariamente.
                score=len(dd)+(12 if c=='notario' and 'apertura_del_instrumento' in tipos else 0)
                score+=30 if c=='fecha_constitucion' and 'apertura_del_instrumento' in tipos else 0
                score+=15 if c in ('representantes_legales','poderes','capital_social_actual') and 'transitorios_y_designaciones' in tipos else 0
                if c=='fecha_constitucion' and any(t in tipos for t in ['boleta_registral','constancia_fiscal']):score-=20
                if 'identificacion_anexa' in tipos and c in ('socios','representantes_legales'):score-=30
                u=cita(p,0,len(texto),'contexto_completo_de_pagina');u.update(campo=c,tipo='pagina',prioridad=score,tipos=tipos);unidades.append(u)
    remisiones=resolver_remisiones(paginas)
    ranking={c:sorted([u for u in unidades if u['campo']==c],key=lambda u:(-u['prioridad'],u['pagina'])) for c in CAMPOS}
    return {'version':'contexto_encabezados_y_roles_v1','sha256_pdf':lectura['sha256_pdf'],
        'paginas':por_pagina,'personas_en_tablas':personas,'remisiones':remisiones,
        'recuperacion_por_campo':ranking,'alertas_calidad':alertas,
        'entrenamiento':False,'inferencia_nueva':False,'ocr_nuevo':False,
        'evaluacion':'diagnostico de desarrollo; no precision ni recall de extraccion',
        'aprobado':False}

def ejecutar(ruta=None,salida=None):
    ruta=Path(ruta or '/content/drive/MyDrive/CITI_CONTINUIDAD/CITI_ENTRENAR_LOCALIZADOR.zip')
    salida=Path(salida or '/content/drive/MyDrive/CITI_CONTINUIDAD/CONTEXTO_DOCUMENTAL_CORREGIDO')
    d=analizar(leer(ruta));salida.mkdir(parents=True,exist_ok=True)
    archivo=salida/'CONTEXTO_DOCUMENTAL.json';archivo.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    for p in d['paginas']:
        print('Página',p['pagina'],'|',', '.join(p['tipos_propuestos']),'| campos:',', '.join(c for c,v in p['detonadores'].items() if v),'| metadatos:',', '.join(c for c,v in p['metadatos_contextuales'].items() if v))
    for p in d['personas_en_tablas']:print('TABLA:',p['nombre_propuesto'],'|',p['rol_documental_propuesto'],'| página',p['evidencia']['pagina'])
    for r in d['remisiones']:print('REMISIÓN:',r['pagina_designacion'],'→',r['clausula'],'| páginas',[s['pagina'] for s in r['segmentos']])
    for a in d['alertas_calidad']:print('RELECTURA NECESARIA: página',a['pagina'],'|',a['tipo'])
    print('Guardado:',archivo,'| entrenamiento: 0 | inferencia nueva: 0 | OCR nuevo: 0')
    return d

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('lectura');p.add_argument('--salida',required=True);a=p.parse_args();ejecutar(a.lectura,a.salida)
