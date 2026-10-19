"""Variantes documentales con rangos literales. Propuestas, sin etiquetas humanas."""
import re
from document_revision import CAMPOS
from date_candidates import numero_espanol
from evidence_fragments import segmento

NOMBRE = r'(?-i:[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ \t\n]{5,130}?)'


def compacto(texto):
    return ' '.join(texto.split())


def numero_cabecera(texto):
    """Hasta 999999; cada componente debe ser un numeral español reconocido."""
    try:
        return numero_espanol(texto)
    except ValueError:
        partes = re.split(r'\bMIL\b', texto, flags=re.I)
        if len(partes) != 2:
            raise
        base = numero_espanol(partes[0]) if partes[0].strip() else 1
        resto = numero_espanol(partes[1]) if partes[1].strip() else 0
        if not 1 <= base <= 999 or not 0 <= resto <= 999:
            raise ValueError('Número de instrumento fuera de gramática')
        return base * 1000 + resto


def numero_prefijo(texto):
    palabras = list(re.finditer(r'\S+', texto))
    for k in range(len(palabras), 0, -1):
        fin = palabras[k-1].end()
        try:
            n = numero_espanol(texto[:fin])
        except ValueError:
            continue
        if 1 <= n <= 999:
            return n, fin
    return None, None


def nombres_separados(texto, a, b):
    """Separa una enumeración explícita conservando sus posiciones originales."""
    literal=texto[a:b]
    separadores=list(re.finditer(r'\s+Y\s+|,\s*',literal))
    inicio=0
    for fin,siguiente in [(s.start(),s.end()) for s in separadores]+[(len(literal),len(literal))]:
        x,y=a+inicio,a+fin
        while x<y and texto[x].isspace():x+=1
        while y>x and texto[y-1].isspace():y-=1
        if x<y:yield x,y
        inicio=siguiente


def extraer(lectura):
    r = {c: [] for c in CAMPOS}
    r['otorgamientos'] = []
    for indice, p in enumerate(lectura['paginas']):
        t = p['texto']
        # Una cláusula de denominación, también para nombres breves.
        patron = r'\b(?:La\s+)?(?:Asociación|Sociedad)\s+se\s+denominar[aá]\s+["“](?P<nombre>[^"”\n]{2,240})["”]'
        for m in re.finditer(patron, t, re.I):
            a,b = m.span('nombre')
            if not re.search(r'[A-Za-zÁÉÍÓÚÑáéíóúñ]', t[a:b]) or '_' in t[a:b]:
                continue
            candidato={'valor_literal_ocr': t[a:b], 'rango_valor_caracteres':[a,b],
                'prioridad':0, 'segmento':segmento(p,m.start(),min(len(t),m.end()+200),'clausula_se_denominara')}
            forma=re.match(r'[,\s]*(?:seguida|seguido)\s+de\s+(?:las\s+)?palabras\s+["“](?P<forma>[^"”\n]{2,100})["”]',t[m.end():],re.I)
            if forma:
                x,y=m.end()+forma.start('forma'),m.end()+forma.end('forma')
                candidato.update(forma_juridica_literal=t[x:y],rango_forma_juridica=[x,y],
                    rangos_valor=[[a,b],[x,y]],valor_compuesto=compacto(t[a:b])+', '+compacto(t[x:y]))
                alias=re.match(r'[,\s]*o\s+de\s+sus\s+abreviaturas\s+["“](?P<alias>[^"”\n]{2,35})["”]',t[m.end()+forma.end():],re.I)
                if alias:
                    x,y=m.end()+forma.end()+alias.start('alias'),m.end()+forma.end()+alias.end('alias')
                    candidato.update(abreviatura_literal=t[x:y],rango_abreviatura=[x,y])
            r['razon_social'].append(candidato)

        if p['pagina'] <= 2:
            # Los números en letras se leen de la cabecera, no de antecedentes.
            pat = r'\b(?:INSTRUMENTO|ESCRITURA)\s+(?P<n>[A-ZÁÉÍÓÚÑ]+(?:[ \t]+[A-ZÁÉÍÓÚÑ]+){0,13})'
            for m in re.finditer(pat,t):
                if m.start() > 1500:
                    continue
                literal = m['n'].strip()
                try:
                    n = numero_cabecera(literal)
                except ValueError:
                    continue
                a,b = m.span('n')
                r['numero_escritura'].append({'valor':str(n),'literal_numero':literal,
                    'rango_valor':[a,b], 'segmento':segmento(p,max(0,m.start()-40),min(len(t),m.end()+100),'cabecera_instrumento_en_letras')})

            # El sujeto de "hago constar" se identifica en la apertura.
            pat = (r'(?P<nombre>'+NOMBRE+r'),\s*plenamente\s+identificad[oa]\b'
                   r'[^.;]{0,160}?\b(?:Titular|Interin[oa])\s+de\s+la\s+Notar[ií]a\s+'
                   r'(?P<n>[^,;.]{1,65}?)\s+del?\s+[^.;]{0,80}?\bhago\s+constar')
            for m in re.finditer(pat,t,re.I):
                if m.start() > 1600:
                    continue
                n,fin = numero_prefijo(m['n'])
                a,b = m.span('nombre'); na = m.start('n')
                r['notario'].append({'valor':{'nombre':compacto(t[a:b]),'numero':n},
                    'rango_nombre':[a,b], 'rango_numero':[na,na+fin] if fin else None,
                    'numero_literal':t[na:na+fin] if fin else None,
                    'segmento':segmento(p,max(0,m.start()-100),m.end(),'sujeto_identificado_y_hago_constar')})

            # "Ante mí" corresponde al actuante; no al titular citado después.
            pat = (r'\bante\s+m[ií]\s*,?\s*(?:LICENCIAD[OA]\s+|LIC\.\s*)?'
                   r'(?P<nombre>'+NOMBRE+r'),[\s|]*(?:Adscrit[oa]\s+a\s+la\s+)?'
                   r'Notar[ií][oa](?:\s+P[úu]blic[oa])?\s+(?:N[úu]mero\s+)?(?P<n>[^,;.\n]{1,65})')
            for m in re.finditer(pat,t,re.I):
                if m.start() > 1600:
                    continue
                n,fin = numero_prefijo(m['n']);a,b = m.span('nombre');na=m.start('n')
                r['notario'].append({'valor':{'nombre':compacto(t[a:b]),'numero':n},
                    'rango_nombre':[a,b], 'rango_numero':[na,na+fin] if fin else None,
                    'numero_literal':t[na:na+fin] if fin else None,
                    'segmento':segmento(p,max(0,m.start()-100),min(len(t),m.end()+240),'ante_mi_y_adscripcion_notarial')})

        # Comparecer en un permiso no basta: se requiere el rol constituyente.
        patrones=[
            (r'\b(?:Las\s+señoras|Los\s+señores)\s+(?P<nombres>'+NOMBRE+r');\s*'
             r'comparecen\s+como\s+asociad[oa]s\s+para\s+la\s+constituci[oó]n',0,'asociados_constituyentes_explicitos'),
            (r'\bCONTRATO\s+DE\s+ASOCIACI[ÓO]N\s+CIVIL\s*,?\s+que\s+otorgan\s+'
             r'(?:las\s+señoras|los\s+señores)\s+(?P<nombres>'+NOMBRE+r')\s*[;.]',1,'otorgantes_contrato_constitutivo')]
        for pat,prioridad,metodo in patrones:
            for m in re.finditer(pat,t,re.I):
                a,b=m.span('nombres')
                s=segmento(p,m.start(),min(len(t),m.end()+80),metodo)
                for x,y in nombres_separados(t,a,b):
                    valor={'nombre':compacto(t[x:y]),'tipo':'asociado_constituyente','texto_literal':t[x:y]}
                    r['socios'].append({'valor':valor,'segmento':s,'rango_caracteres':[x,y],
                        'prioridad':prioridad,'nota':'Otorgante del contrato constitutivo' if prioridad else 'Cláusula explícita de asociados constituyentes'})

        pat = (r'\bSer[aá]\s+(?P<rol>apoderad[oa])\b[^.;]{0,180}?\bseñor[a]?\s+'
               r'(?P<nombre>'+NOMBRE+r')\s+gozar[aá]\s+de\s+las\s+siguientes\s+facultades')
        for m in re.finditer(pat,t,re.I):
            a,b=m.span('nombre');persona=compacto(t[a:b])
            s=segmento(p,m.start(),min(len(t),m.end()+600),'designacion_sera_apoderado_y_facultades')
            r['representantes_legales'].append({'valor':{'nombre':persona,'rol':m['rol']},
                'rango_nombre':[a,b],'segmento':s})
            segs=[];cerrado=False
            cierre=re.compile(r'^[^\w\n]{0,40}G[ \t]*E[ \t]*N[ \t]*E[ \t]*R[ \t]*A[ \t]*L[ \t]*E[ \t]*S[^\w\n]*(?:\n|$)|\bYO\s*,?\s*EL\s+NOTARIO\s+CERTIFICO|\b(?:TERCERA|CUARTA)\s*[.]',re.I|re.M)
            for j in range(indice,min(len(lectura['paginas']),indice+6)):
                pp=lectura['paginas'][j];inicio=m.start() if j==indice else 0
                fin_cierre=cierre.search(pp['texto'],m.end() if j==indice else 0)
                fin=fin_cierre.start() if fin_cierre else len(pp['texto'])
                if fin>inicio:segs.append(segmento(pp,inicio,fin,'otorgamiento_y_continuacion_documental'))
                if fin_cierre:cerrado=True;break
            r['otorgamientos'].append({'persona':persona,'segmentos':segs,'cierre_encontrado':cerrado})
    return r
