"""Adaptador determinista de etiquetas explícitas, sin respuestas esperadas.

No resuelve lenguaje legal general ni acredita vigencia fuera del expediente.
Solo incorpora valores con citas; el motor anterior permanece como baseline.
"""
import json
import re
from decimal import Decimal
from pathlib import Path

from document_revision import CAMPOS, guardar
from date_candidates import detectar_fechas
from DOCUMENT_CONTEXT import analizar, cita, normalizar, coincidencias

VERSION = 'etiquetas_explicitas_y_tablas_v1'
PODERES = {
    'pleitos_y_cobranzas': r'\bPLEITOS\s+Y\s+COBRANZAS\b',
    'administracion': r'\bACTOS\s+DE\s+ADMINISTRACION\b',
    'dominio': r'\bACTOS\s+DE\s+DOMINIO\b',
}


def compacto(texto):
    return ' '.join(texto.split()).strip(' ;.\n')


def extraer(lectura, datos_base, evidencia_base):
    """Añade contexto a una salida existente sin consultar el ground truth."""
    datos = dict(datos_base)
    for campo in ('socios', 'representantes_legales'):
        datos[campo] = [v['nombre'] if isinstance(v, dict) else v for v in datos[campo]]
    datos['poderes'] = sorted({t for v in datos['poderes'] for t in
                               (v.get('tipos', []) if isinstance(v, dict) else [v])})
    contexto = analizar(lectura)
    evidencias = {c: list(evidencia_base.get(c, [])) for c in CAMPOS}
    eventos = []
    candidatos = {c: [] for c in CAMPOS}
    revocados = []

    def proponer(campo, valor, p, a, b, metodo, **extra):
        s = cita(p, a, b, metodo)
        registro = {'valor': valor, 'evidencia': s, **extra}
        candidatos[campo].append(registro)
        return registro

    def etiqueta(p, patron, fin=r'\n|$'):
        # El valor termina ante un cambio de etiqueta o párrafo; no se pide al
        # modelo adivinar límites. La expresión debe declarar el grupo valor.
        texto = p['texto']
        n, mapa = normalizar(texto)
        for m in re.finditer(patron, n, re.M):
            a, b = m.span('valor')
            if a < b:
                yield mapa[a], mapa[b-1]+1, m

    for p in lectura['paginas']:
        texto = p['texto']
        for a, b, _ in etiqueta(p, r'\b(?:RAZON\s+SOCIAL|DENOMINACION\s+SOCIAL)\s*:\s*(?P<valor>[^\n]+)'):
            # No se elimina puntuación societaria: S.A. de C.V. se conserva.
            proponer('razon_social', texto[a:b].strip(), p, a, b, 'etiqueta_razon_social')
        for a, b, _ in etiqueta(p, r'\b(?:FECHA|ANTECEDENTE)\s+DE\s+CONSTITUCION\s*:\s*(?P<valor>[^\n]+)'):
            fechas = detectar_fechas(texto[a:b], p['fuente_id'], p['pagina'])
            unicas = {f['fecha_iso'] for f in fechas}
            if len(unicas) == 1:
                proponer('fecha_constitucion', next(iter(unicas)), p, a, b,
                         'fecha_tras_etiqueta_constitutiva; excluye_modificacion_y_registro')
        for a, b, _ in etiqueta(p, r'\bSOCIOS(?:\s+FUNDADORES)?\s*:\s*(?P<valor>[^.]+)'):
            nombres = [compacto(v) for v in re.split(r'\s+[yY]\s+|;', texto[a:b]) if v.strip()]
            if nombres:
                proponer('socios', nombres, p, a, b, 'lista_tras_etiqueta_socios')
        for a, b, _ in etiqueta(p, r'(?m)^REPRESENTANTE\s+LEGAL\s*:\s*(?P<valor>[^.\n]+)'):
            proponer('representantes_legales', [compacto(texto[a:b])], p, a, b,
                     'etiqueta_representante_legal')
        for a, b, _ in etiqueta(p, r'\bSE\s+DESIGNA\s+A\s+(?P<valor>[^.;]{3,110}?)\s+COMO\s+REPRESENTANTE\s+LEGAL\b'):
            r = proponer('representantes_legales', [compacto(texto[a:b])], p, a, b,
                         'designacion_explicita_de_representante', evento='designacion')
            eventos.append({'tipo': 'designacion', **r})
        for a, b, _ in etiqueta(p, r'\bSE\s+REVOCAN\s+LOS\s+PODERES\s+DE\s+(?P<valor>[^.;]{3,110}?)\s+COMO\s+REPRESENTANTE\s+LEGAL\b'):
            r = {'tipo': 'revocacion', 'nombre': compacto(texto[a:b]),
                 'evidencia': cita(p, a, b, 'revocacion_personal_explicita')}
            revocados.append(r); eventos.append(r)
        # Un notario ficticio o una notaría no identifica el nombre de persona.
        n = normalizar(texto)[0]
        for a, b, _ in etiqueta(p, r'\bNOTARI[OA]\s+(?:FICTICI[OA]|SIMULAD[OA])\s+(?:NUMERO\s+)?(?P<valor>\d+)\b'):
            proponer('notario', {'nombre': None, 'numero': int(texto[a:b])}, p,
                     max(0, a-35), b, 'numero_de_notaria; nombre_personal_no_documentado')
        for a, b, _ in etiqueta(p, r'\bPODERES\s+CONFERIDOS\s*:\s*(?P<valor>[^.]+)'):
            tipos = [tipo for tipo, patron in PODERES.items()
                     if re.search(patron, normalizar(texto[a:b])[0])]
            if tipos:
                proponer('poderes', tipos, p, a, b, 'facultades_tras_etiqueta_explicita')
        # La referencia «la nueva representante» se vincula después, solo si
        # existe una única designación explícita en este mismo instrumento.
        for a, b, _ in etiqueta(p, r'\bA\s+LA\s+NUEVA\s+REPRESENTANTE\s+SE\s+OTORGAN\s+PODERES\s+PARA\s+(?P<valor>[^.]+)'):
            tipos = [tipo for tipo, patron in PODERES.items()
                     if re.search(patron, normalizar(texto[a:b])[0])]
            if tipos:
                proponer('poderes', tipos, p, a, b, 'poderes_a_nueva_representante',
                         requiere_designacion_unica=True)
        for a, b, m in etiqueta(p, r'\bCAPITAL\s+SOCIAL(?:\s+ORIGINAL)?\s*:\s*\$\s*(?P<valor>\d[\d,]*(?:\.\d{2})?)\s+MXN\b'):
            proponer('capital_social_actual', {'valor': str(Decimal(texto[a:b].replace(',', ''))), 'moneda': 'MXN'},
                     p, max(0, a-35), min(len(texto), b+5), 'capital_expreso_en_instrumento', evento='original')
        for a, b, _ in etiqueta(p, r'\bSE\s+AUMENTA\s+EL\s+CAPITAL\s+SOCIAL\s+A\s*\$\s*(?P<valor>\d[\d,]*(?:\.\d{2})?)\s+MXN\b'):
            r = proponer('capital_social_actual', {'valor': str(Decimal(texto[a:b].replace(',', ''))), 'moneda': 'MXN'},
                         p, max(0, a-45), min(len(texto), b+100), 'aumento_explicito', evento='aumento')
            eventos.append({'tipo': 'aumento_capital', **r})

    def elegir_unico(campo, seleccion=None):
        cs = candidatos[campo] if seleccion is None else seleccion
        distintos = {json.dumps(c['valor'], ensure_ascii=False, sort_keys=True) for c in cs}
        if len(distintos) == 1:
            datos[campo] = cs[0]['valor']
            evidencias[campo] = [c['evidencia'] for c in cs]
        elif len(distintos) > 1:
            datos[campo] = [] if campo in ('socios', 'representantes_legales', 'poderes') else None
            evidencias[campo] = [c['evidencia'] for c in cs]

    for campo in ('razon_social', 'fecha_constitucion', 'socios'):
        if campo == 'razon_social' and datos[campo] is not None:
            # La cláusula de denominación del motor existente tiene precedencia
            # sobre una etiqueta en permisos o anexos administrativos.
            continue
        elegir_unico(campo)
    # Una tabla se incorpora solo cuando el carácter ACCIONISTA está presente;
    # OTORGANTE, por sí solo, puede ser vendedor, apoderado u otro interviniente.
    tablas = [v for v in contexto['personas_en_tablas'] if v['rol_documental_propuesto'] == 'accionista_propuesto']
    grupos = {}
    for v in tablas:
        grupos.setdefault(v['evidencia']['fuente_id'], []).append(v)
    firmas = {tuple(v['nombre_propuesto'] for v in grupo) for grupo in grupos.values()}
    if not candidatos['socios'] and len(firmas) == 1:
        grupo = next(iter(grupos.values()))
        datos['socios'] = [v['nombre_propuesto'] for v in grupo]
        evidencias['socios'] = [v['evidencia'] for v in grupo]

    if datos['notario'] is None:
        elegir_unico('notario')
    designaciones = [v for v in candidatos['representantes_legales'] if v.get('evento') == 'designacion']
    # No se infiere cronología entre varias actas ni entre varios nombramientos.
    elegir_unico('representantes_legales', designaciones or None)
    if len(designaciones) > 1:
        datos['representantes_legales'] = []
    bajas = {normalizar(v['nombre'])[0] for v in revocados}
    datos['representantes_legales'] = [v for v in datos['representantes_legales'] if normalizar(v)[0] not in bajas]
    if revocados:
        evidencias['representantes_legales'].extend(v['evidencia'] for v in revocados)
    poderes = [v for v in candidatos['poderes'] if not v.get('requiere_designacion_unica') or len(designaciones) == 1]
    elegir_unico('poderes', poderes)
    aumentos = [v for v in candidatos['capital_social_actual'] if v.get('evento') == 'aumento']
    # El adapter solo resuelve un único aumento en un único instrumento. Varios
    # eventos o reducciones fuera de esta gramática requieren conciliación.
    elegir_unico('capital_social_actual', aumentos or None)
    if len(aumentos) > 1:
        datos['capital_social_actual'] = None

    estados = {}
    for campo in CAMPOS:
        valor = datos[campo]
        estado = 'extraido' if valor not in (None, []) else 'no_encontrado'
        if (candidatos[campo] or evidencias[campo]) and valor in (None, []):
            estado = 'pendiente_revision'
        if campo == 'notario' and valor and valor['nombre'] is None:
            estado = 'parcial'
        estados[campo] = {'estado': estado, 'aprobado': False,
                         'revision_humana': 'pendiente', 'evidencia_disponible': bool(evidencias[campo])}
    etiquetas_na = {'razon_social': 'RAZON SOCIAL', 'fecha_constitucion': 'FECHA DE CONSTITUCION',
                    'numero_escritura': '(?:NUMERO DE )?ESCRITURA', 'notario': 'NOTARIO',
                    'socios': 'SOCIOS', 'representantes_legales': 'REPRESENTANTES? LEGALES?',
                    'poderes': 'PODERES', 'capital_social_actual': 'CAPITAL SOCIAL'}
    for campo, etiqueta_na in etiquetas_na.items():
        for p in lectura['paginas']:
            for a, b in coincidencias(p['texto'], fr'(?m)^{etiqueta_na}\s*:\s*NO\s+APLICA\b'):
                e = cita(p, a, b, 'no_aplicabilidad_declarada_en_documento')
                evidencias[campo].append(e)
                if datos[campo] in (None, []):
                    estados[campo].update(estado='no_aplicable', evidencia_disponible=True,
                                         justificacion='Declaración literal NO APLICA; revisión humana pendiente')
                else:
                    estados[campo]['estado'] = 'pendiente_revision'
    # El estado no_aplicable existe en el contrato, pero ninguna ausencia lo
    # activa automáticamente: requiere una decisión documentada del revisor.
    if lectura.get('paginas_no_leidas'):
        for v in estados.values():
            v['cobertura_documental'] = 'incompleta'
    control = {'version': VERSION, 'estados': estados, 'eventos': eventos,
               'alcance_capital': 'último estado explícito del instrumento; vigencia externa no verificada',
               'orden_eventos': 'solo una designación y un aumento explícitos; múltiples eventos requieren revisión',
               'entrenamiento': False, 'inferencia_nueva': False, 'aprobado': False}
    return datos, {'control': control, 'evidencias': evidencias, 'candidatos': candidatos}, contexto
