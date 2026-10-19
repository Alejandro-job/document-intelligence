"""Reglas de designación, remisión a facultades y tabla de capital con evidencia.

No entrena modelos ni interpreta vigencia externa. Una facultad estatutaria sin
una designación personal y una remisión expresa no se atribuye a personas.
"""
from decimal import Decimal
import hashlib
import re
import unicodedata

VERSION = "designacion_remision_e_inciso_con_limitaciones_v1"
UNIDAD = r"(?:PRIMER[OA]|SEGUND[OA]|TERCER[OA]|CUART[OA]|QUINT[OA]|SEXT[OA]|SEPTIM[OA]|OCTAV[OA]|NOVEN[OA])"
DECENA = r"(?:DECIM[OA]|VIGESIM[OA]|TRIGESIM[OA]|CUADRAGESIM[OA]|QUINCUAGESIM[OA]|SEXAGESIM[OA]|SEPTUAGESIM[OA]|OCTOGESIM[OA]|NONAGESIM[OA])"
ORDINAL = fr"(?:{DECENA}(?:\s+{UNIDAD})?|{UNIDAD})"


def normal(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.upper())
                   if unicodedata.category(c) != "Mn")


def vista(pagina):
    """Suprime márgenes de OCR y cabecera repetida; conserva el mapa original."""
    texto = pagina["texto"]
    cabecera = re.search(r"PROTOCOLO\s+ABIERTO\s+ORDINARIO[^\n]*\n", texto[:400], re.I)
    inicio = cabecera.end() if cabecera else 0
    letras, mapa = [], []
    for linea in re.finditer(r"[^\n]+(?:\n|$)", texto[inicio:]):
        bruto = linea.group()
        prefijo = re.match(r"\s*(?:(?:[|!,]\s*)|(?:[lI4]\s+(?=[A-ZÁÉÍÓÚÑ])))+", bruto)
        desde = prefijo.end() if prefijo else 0
        for j in range(desde, len(bruto)):
            c = bruto[j]
            if c == "|":
                c = " "
            if c.isspace():
                if letras and letras[-1] != " ":
                    letras.append(" "); mapa.append((pagina, inicio + linea.start() + j))
            else:
                letras.append(c); mapa.append((pagina, inicio + linea.start() + j))
    return "".join(letras), mapa


def citar_mapa(mapa, a, b, metodo):
    partes = []
    for p, i in mapa[a:b]:
        if not partes or partes[-1][0]["fuente_id"] != p["fuente_id"]:
            partes.append([p, i, i + 1])
        else:
            partes[-1][2] = i + 1
    return [{"pagina": p["pagina"], "fuente_id": p["fuente_id"],
             "rango_caracteres": [aa, bb], "texto": p["texto"][aa:bb],
             "sha256_texto_fuente": hashlib.sha256(p["texto"].encode()).hexdigest(),
             "metodo": metodo, "aprobado": False} for p, aa, bb in partes]


def extraer_relaciones(lectura):
    partes, mapa = [], []
    for p in lectura["paginas"]:
        texto, posiciones = vista(p)
        if not texto:
            continue
        if partes:
            partes.append(" "); mapa.append(posiciones[0])
        partes.append(texto); mapa.extend(posiciones)
    texto = "".join(partes)
    n = normal(texto)
    # La normalización descompone tildes españolas sin alterar la longitud.
    if len(n) != len(texto):
        raise ValueError("La normalización de la vista requiere un mapa adicional")
    cabeceras = list(re.finditer(fr"\b(?P<ordinal>{ORDINAL})\s*\.\s*[-—–]", n))
    cadenas = []
    for inicio in re.finditer(r"\bDESIGNANDO EN ESTE MOMENTO\b", n):
        antes = n[max(0, inicio.start()-180):inicio.start()]
        if not re.search(r"CONSEJO DE\s+ADMINISTRACION", antes):
            continue
        fin = re.search(r"\bLES CONFIEREN\b", n[inicio.end():inicio.end()+650])
        if not fin:
            continue
        a_fin = inicio.end()+fin.start()
        nombramientos = []
        patron = r"\bAL SENOR\s+(?P<nombre>[A-Z ]{5,110}?)\s+COMO\s+(?P<cargo>PRESIDENTE|SECRETARIO)\b"
        for m in re.finditer(patron, n[inicio.end():a_fin]):
            a, b = inicio.end()+m.start("nombre"), inicio.end()+m.end("nombre")
            nombramientos.append({"nombre": texto[a:b].strip(), "cargo": m["cargo"].lower(),
                "evidencias": citar_mapa(mapa, a, b, "nombre_en_designacion_de_consejo"),
                "evidencia_cargo": citar_mapa(mapa, inicio.end()+m.start(), inicio.end()+m.end(), "designacion_persona_y_cargo"),
                "aprobado": False})
        # Esta gramática exige una lista cerrada de presidente y secretario.
        if len(nombramientos) != 2 or {m["cargo"] for m in nombramientos} != {"presidente", "secretario"}:
            continue
        pat_remision = (r"LES CONFIEREN AL CONSEJO DE ADMINISTRACION EN LO INDIVIDUAL A CADA UNO DE SUS "
                        r"MIEMBROS.{0,140}?CONJUNTA O SEPARADAMENTE.{0,140}?CLAUSULA (?P<ordinal>"+ORDINAL+r")")
        remision = re.match(pat_remision, n[a_fin:a_fin+650])
        if not remision:
            continue
        destinos = [(j, h) for j, h in enumerate(cabeceras) if h["ordinal"] == remision["ordinal"]]
        if len(destinos) != 1:
            continue
        j, h = destinos[0]
        if j+1 >= len(cabeceras):
            continue  # No se declara completa una cláusula sin límite posterior.
        fin_clausula = cabeceras[j+1].start()
        cuerpo_n = n[h.end():fin_clausula]
        if not re.match(r"\s*EL ADMINISTRADOR UNICO O EL CONSEJO DE ADMINISTRACION", cuerpo_n):
            continue
        incisos = list(re.finditer(r"\b(?P<inciso>[A-Z])\)\s*[.\-]*\s*PODER\s+(?:GENERAL|ESPECIAL)\b", cuerpo_n))
        if not incisos or [m["inciso"] for m in incisos] != [chr(65+k) for k in range(len(incisos))]:
            continue
        poderes = []
        for k, m in enumerate(incisos):
            a = h.end()+m.start()
            b = h.end()+incisos[k+1].start() if k+1 < len(incisos) else fin_clausula
            if k+1 == len(incisos):
                cierre = re.search(r"\bTODAS LAS FACULTADES ENUNCIADAS EN LOS INCISOS", n[a:b])
                if cierre:
                    b = a+cierre.start()
            limitacion = re.search(r"\bLIMITACION\s*:", n[a:b])
            restricciones = []
            if limitacion:
                la = a+limitacion.start()
                restricciones = citar_mapa(mapa, la, b, "limitacion_del_inciso_no_se_omite")
            poderes.append({"inciso": m["inciso"], "texto_propuesto": texto[a:b].strip(),
                "evidencias": citar_mapa(mapa, a, b, "inciso_completo_con_continuacion_de_pagina"),
                "titulares": [v["nombre"] for v in nombramientos],
                "restricciones": restricciones, "aprobado": False})
        cadenas.append({"personas": nombramientos, "poderes": poderes,
            "clausula": remision["ordinal"],
            "designacion_y_otorgamiento": citar_mapa(mapa, inicio.start(), a_fin+remision.end(), "designacion_y_remision_expresa"),
            "clausula_completa": citar_mapa(mapa, h.start(), fin_clausula, "clausula_hasta_siguiente_encabezado_incluye_limitaciones"),
            "forma_ejercicio_literal": "conjunta o separadamente",
            "limite_posterior": cabeceras[j+1]["ordinal"], "aprobado": False})
    if len(cadenas) != 1:
        return {"estado": "pendiente_sin_cadena_unica", "cadenas": cadenas, "aprobado": False}
    # No se resuelve por esta gramática una revocación explícita posterior.
    if re.search(r"\b(?:SE|QUEDAN)\s+REVOCAD[OA]S?\b", n):
        return {"estado": "pendiente_por_revocacion", "cadenas": cadenas, "aprobado": False}
    return {"estado": "propuesta_por_designacion_y_remision", **cadenas[0],
            "transformacion_valores": "retirar márgenes de OCR, cabeceras repetidas y compactar espacios; sin corregir letras",
            "vigencia_externa": "no_verificada", "origen": "reglas_de_relaciones; no_qwen", "version": VERSION}


def capital_de_fuente(lectura, fuente):
    """El mínimo estatutario corrobora; el total procede de la tabla suscrita."""
    if not fuente or fuente.get("sha256_pdf") != lectura["sha256_pdf"]:
        return {"estado": "pendiente_fuente_adicional"}
    if hashlib.sha256(fuente["texto"].encode()).hexdigest() != fuente["sha256_texto_fuente"]:
        raise ValueError("Fuente adicional de capital modificada")
    ws = fuente["palabras"]
    for w in ws:
        a, b = w["a"], w["b"]
        if not 0 <= a < b <= len(fuente["texto"]) or fuente["texto"][a:b] != w["t"]:
            raise ValueError("Palabra adicional no literal")
        x1, y1, x2, y2 = w["box"]
        if not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1:
            raise ValueError("Geometría adicional inválida")
    totales = [w for w in ws if normal(w["t"]).strip("|: ") == "TOTAL"]
    cabeceras = [w for w in ws if normal(w["t"]) == "IMPORTE"]
    if len(totales) != 1 or len(cabeceras) != 1:
        return {"estado": "pendiente_cabecera_o_total_ambiguos"}
    total, cabecera = totales[0], cabeceras[0]
    monedas = [w for w in ws if re.fullmatch(r"\$\d{1,3}(?:,\d{3})*\.\d{2}", w["t"])
               and w["box"][0] >= cabecera["box"][0]-.025]
    yc = lambda w: (w["box"][1]+w["box"][3])/2
    altura = max(.004, total["box"][3]-total["box"][1])
    t = [w for w in monedas if abs(yc(w)-yc(total)) <= altura]
    filas = [w for w in monedas if yc(cabecera) < yc(w) < yc(total)-altura]
    if len(t) != 1 or not filas:
        return {"estado": "pendiente_asociacion_geometrica"}
    importe = lambda w: Decimal(w["t"].replace("$", "").replace(",", ""))
    if sum((importe(w) for w in filas), Decimal(0)) != importe(t[0]):
        return {"estado": "pendiente_sumas_no_coincidentes"}
    page = next(p for p in lectura["paginas"] if p["pagina"] == fuente["pagina"])
    original, posiciones = vista(page)
    n = normal(original)
    if not re.search(r"CAPITAL SOCIAL HA QUEDADO INTEGRAMENTE SUSCRITO Y PAGADO", n):
        return {"estado": "pendiente_alcance_de_la_tabla"}
    respaldo = []
    for p in lectura["paginas"]:
        v, mp = vista(p)
        m = re.search(r"CAPITAL MINIMO FIJO.{0,160}?\$(?P<importe>\d[\d,]*\.\d{2}).{0,80}?PESOS.{0,40}?MONEDA NACIONAL", normal(v))
        if m and Decimal(m["importe"].replace(",", "")) == importe(t[0]):
            respaldo.extend(citar_mapa(mp, m.start(), m.end(), "capital_minimo_y_moneda; no_sustituye_total_suscrito"))
    if not respaldo:
        return {"estado": "pendiente_corrobora_moneda_y_capital"}
    def citar(w):
        a, b = w["a"], w["b"]
        return {"pagina": fuente["pagina"], "fuente_id": fuente["fuente_id"],
                "rango_caracteres": [a, b], "texto": fuente["texto"][a:b],
                "sha256_texto_fuente": fuente["sha256_texto_fuente"], "box": w["box"],
                "metodo": "importe_columna_y_fila_total_en_ocr_adicional", "aprobado": False}
    return {"estado": "propuesta_capital_suscrito_del_instrumento", "aprobado": False,
            "valor": {"valor": format(importe(t[0]), ".2f"), "moneda": "MXN"},
            "evidencias": [citar(t[0]), citar(total)]+[citar(w) for w in filas]+respaldo,
            "suma_filas": format(sum((importe(w) for w in filas), Decimal(0)), ".2f"),
            "filas_con_importe": len(filas), "nombres_de_la_tabla_adicional_no_se_corrigen": True,
            "normalizacion_moneda": "pesos moneda nacional en instrumento mexicano; MXN",
            "alcance": "capital suscrito y pagado de este instrumento; vigencia externa no verificada",
            "origen": "ocr_adicional_y_reglas_geometricas; no_qwen"}
