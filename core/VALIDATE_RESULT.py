"""Controla respuestas guardadas sin cargar modelos, entrenar ni repetir OCR.

Colab: %run /content/drive/MyDrive/CITI_CONTINUIDAD/VALIDATE_RESULT.py
El resultado original no se modifica. Las reglas se identifican por separado.
"""
import argparse
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import zipfile

VERSION = "control_roles_fecha_y_relaciones_documentales_v2"
CARPETA_EJECUCION = "e39eb2e3189e10b8_283c37902a"
CAMPOS = ("razon_social", "fecha_constitucion", "numero_escritura", "notario",
          "socios", "representantes_legales", "poderes", "capital_social_actual")
DIAS = ("uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
        "diez", "once", "doce", "trece", "catorce", "quince", "dieciseis",
        "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidos",
        "veintitres", "veinticuatro", "veinticinco", "veintiseis", "veintisiete",
        "veintiocho", "veintinueve", "treinta", "treinta y uno")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")


def sha(datos):
    return hashlib.sha256(datos).hexdigest()


def normal(texto):
    # Se permiten caja y tildes; N y Ñ siguen siendo letras distintas.
    texto = texto.casefold().replace("ñ", "\ue000")
    texto = "".join(c for c in unicodedata.normalize("NFD", texto)
                    if unicodedata.category(c) != "Mn").replace("\ue000", "ñ")
    return " ".join(texto.split())


def guardar(ruta, valor):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(valor, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)


def validar_candidato(candidato, paginas):
    pagina = paginas[candidato["fuente_id"]]
    if candidato["pagina"] != pagina["pagina"]:
        raise ValueError("Página del candidato no coincide")
    if sha(pagina["texto"].encode()) != candidato["sha256_texto_fuente"]:
        raise ValueError("El texto fuente del candidato cambió")
    literales = []
    for a, b in candidato["rangos"]:
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(pagina["texto"]):
            raise ValueError("Rango inválido")
        literales.append(pagina["texto"][a:b])
    if not literales or "\n".join(literales) != candidato["texto_literal"]:
        raise ValueError("Literal del candidato no coincide con los rangos")


def soporte_socio(candidato, personas):
    """Exige una aparición en una fila de personas con carácter de accionista.

    Una palabra 'accionistas' en otra parte de la página no respalda al nombre.
    No se excluyen personas morales por su forma textual; las no soportadas por
    este adaptador quedan pendientes, no clasificadas como personas inexistentes.
    """
    for persona in personas:
        evidencia = persona["evidencia"]
        if persona["rol_documental_propuesto"] != "accionista_propuesto":
            continue
        if evidencia["fuente_id"] != candidato["fuente_id"]:
            continue
        a, b = evidencia["rango_caracteres"]
        if not all(a <= x < y <= b for x, y in candidato["rangos"]):
            continue
        if normal(candidato["texto_literal"]) != normal(evidencia["texto"]):
            continue
        return persona
    return None


def fecha_redundante(texto):
    """Acepta día numérico y en letras solo cuando ambos coinciden."""
    patron = r"(\d{1,2})\s+([a-z ]+?)\s+dias\s+del\s+mes\s+de\s+([a-z]+)\s+de\s+(\d{4})"
    m = re.fullmatch(patron, normal(texto))
    if not m:
        return None
    dia, letras, mes, anio = m.groups()
    if letras not in DIAS or DIAS.index(letras) + 1 != int(dia) or mes not in MESES:
        return None
    try:
        return date(int(anio), MESES.index(mes) + 1, int(dia)).isoformat()
    except ValueError:
        return None


def apertura_constitutiva(pagina, a, b):
    """Patrón conservador de un otorgamiento constitutivo, no una fecha fiscal."""
    if pagina["pagina"] > 2:
        return False
    antes = normal(pagina["texto"][max(0, a - 350):a])
    despues = normal(pagina["texto"][b:b + 750])
    if not re.search(r"\bescritura\b", antes):
        return False
    if re.search(r"\b(?:antecedentes|transcripcion|reproduccion|certificacion)\b", antes):
        return False
    return (bool(re.search(r"\bante mi\b", despues[:130]))
            and bool(re.search(r"\bcomparecen\b", despues))
            and "por medio del presente instrumento" in despues
            and bool(re.search(r"\bvienen a constituir una sociedad\b", despues)))


def reconciliar_fecha(resultado, paginas):
    """Revisa únicamente objetos completos ya rechazados por el parser anterior."""
    refs = {c["ref"]: c for c in resultado.get("prompt", {}).get("citas", [])}
    candidatos = []
    for rechazo in resultado.get("rechazos", []):
        x = rechazo.get("propuesta", {})
        if not isinstance(x, dict) or x.get("evento") != "constitucion":
            continue
        literal = x.get("texto")
        if not isinstance(literal, str) or not (valor := fecha_redundante(literal)):
            continue
        ref = refs.get(x.get("ref"))
        if not ref:
            continue
        pagina = paginas[ref["fuente_id"]]
        aa, bb = ref["rango_caracteres"]
        if (pagina["texto"][aa:bb] != ref["texto"]
                or sha(pagina["texto"].encode()) != ref["sha256_texto_fuente"]):
            raise ValueError("La cita de fecha no coincide con su fuente")
        hits = list(re.finditer(re.escape(literal), ref["texto"]))
        if len(hits) != 1:
            continue
        a, b = aa + hits[0].start(), aa + hits[0].end()
        if not apertura_constitutiva(pagina, a, b):
            continue
        candidatos.append({"campo": "fecha_constitucion", "valor": valor,
            "pagina": pagina["pagina"], "fuente_id": pagina["fuente_id"],
            "rangos": [[a, b]], "texto_literal": pagina["texto"][a:b],
            "sha256_texto_fuente": ref["sha256_texto_fuente"], "cita": ref,
            "referencia_modelo": x["ref"], "evento": "constitucion",
            "metodo_control": "dia_cifra_letras_concordantes_y_apertura_constitutiva",
            "origen": "propuesta_qwen_previa_reconciliada_por_reglas",
            "generacion_original_incompleta": bool(resultado.get("salida_incompleta")),
            "aprobado": False})
    unicos = {(x["fuente_id"], tuple(x["rangos"][0])): x for x in candidatos}
    return list(unicos.values())


def controlar_estado(estado, lectura):
    """No muta el estado original ni evalúa respuestas humanas inexistentes."""
    from DOCUMENT_CONTEXT import analizar
    from model_extract import consolidar
    if estado["protocolo"]["sha256_pdf"] != lectura["sha256_pdf"]:
        raise ValueError("La inferencia y la lectura pertenecen a documentos distintos")
    paginas = {p["fuente_id"]: p for p in lectura["paginas"]}
    contexto = analizar(lectura)
    resultados = copy.deepcopy(estado["campos"])
    nuevos_rechazos = []
    for campo, resultado in resultados.items():
        conservados = []
        for candidato in resultado.get("candidatos", []):
            validar_candidato(candidato, paginas)
            if campo == "socios" and not soporte_socio(candidato, contexto["personas_en_tablas"]):
                rechazo = {"campo": campo,
                    "motivo": "sin_aparicion_en_fila_de_persona_con_caracter_de_accionista",
                    "valor_rechazado": candidato["valor"], "candidato_original": candidato,
                    "ausencia_de_soporte_no_prueba_que_la_persona_no_sea_socia": True}
                resultado.setdefault("rechazos", []).append(rechazo)
                nuevos_rechazos.append(rechazo)
            else:
                conservados.append(candidato)
        resultado["candidatos"] = conservados
        if not conservados and resultado.get("estado") == "con_candidatos":
            resultado["estado"] = "rechazado_por_control_de_rol"
    fecha = resultados.get("fecha_constitucion", {})
    agregados = reconciliar_fecha(fecha, paginas)
    for candidato in agregados:
        validar_candidato(candidato, paginas)
        clave = (candidato["fuente_id"], candidato["rangos"])
        if not any((c["fuente_id"], c["rangos"]) == clave for c in fecha.get("candidatos", [])):
            fecha.setdefault("candidatos", []).append(candidato)
    if fecha.get("candidatos"):
        fecha["estado"] = "con_candidatos"
    salida = consolidar(resultados, lectura)
    salida["control_semantico"] = {"version": VERSION,
        "alcance": "rol de accionista en tablas soportadas y fecha con día redundante en apertura constitutiva",
        "rechazos_nuevos": nuevos_rechazos, "fechas_reconciliadas": agregados,
        "roles_o_vigencia_juridica_globales_validados": False}
    return salida, resultados, contexto


def plano(salida):
    datos = copy.deepcopy(salida["datos"])
    for campo in ("socios", "representantes_legales"):
        datos[campo] = [x["nombre"] if isinstance(x, dict) else x for x in datos[campo]]
    datos["poderes"] = [x["texto_literal"] if isinstance(x, dict) else x for x in datos["poderes"]]
    return datos


def integrar(salida_ia, datos_reglas, registro, lectura, contexto, fuente_tabla=None):
    """Mantiene el origen de cada campo; las reglas no son aciertos de Qwen."""
    from verify_citations import verificar
    from validate_output import validar
    verificar(lectura, [registro])
    datos_qwen = plano(salida_ia)
    datos = copy.deepcopy(datos_qwen)
    origenes = {c: "qwen_con_cita_literal; pendiente_revision" if datos[c] not in (None, []) else "pendiente" for c in CAMPOS}
    evidencias = {c: [m for m in salida_ia["propuestas"] if m["campo"] == c] for c in CAMPOS}
    reemplazos = []
    metodos = {"numero_escritura": "cabecera_instrumento_en_letras",
               "notario": "ante_mi_y_adscripcion_notarial"}
    for c, metodo in metodos.items():
        valor = datos_reglas.get(c)
        evs = [e for e in registro["evidencias"][c]
               if e.get("metodo") == metodo and e.get("valor_propuesto") == valor]
        if datos[c] in (None, []) and valor is not None and evs:
            datos[c], evidencias[c] = copy.deepcopy(valor), evs
            origenes[c] = "reglas_documentales; " + metodo
            reemplazos.append(c)
    personas = [p for p in contexto["personas_en_tablas"]
                if p["rol_documental_propuesto"] == "accionista_propuesto"]
    candidatos_tabla = {normal(p["nombre_propuesto"]): p for p in personas}
    socios = datos_reglas.get("socios", [])
    if not datos["socios"] and socios and all(normal(s) in candidatos_tabla for s in socios):
        datos["socios"] = list(socios)
        evidencias["socios"] = [candidatos_tabla[normal(s)] for s in socios]
        origenes["socios"] = "reglas_tabla_otorgantes_con_caracter_accionista_y_columnas_geometricas"
        reemplazos.append("socios")
    if salida_ia["control_semantico"]["fechas_reconciliadas"] and datos["fecha_constitucion"]:
        origenes["fecha_constitucion"] = "propuesta_qwen_previa; fecha_reconciliada_por_reglas_de_apertura"
    from DOCUMENT_RELATIONS import extraer_relaciones, capital_de_fuente
    relaciones = extraer_relaciones(lectura)
    capital = capital_de_fuente(lectura, fuente_tabla)
    conflictos = []
    if relaciones["estado"] == "propuesta_por_designacion_y_remision":
        nuevos = {"representantes_legales": [p["nombre"] for p in relaciones["personas"]],
                  "poderes": [p["texto_propuesto"] for p in relaciones["poderes"]]}
        for campo, valor in nuevos.items():
            if datos[campo] and datos[campo] != valor:
                conflictos.append({"campo": campo, "qwen": datos[campo], "reglas": valor})
                datos[campo] = []
                origenes[campo] = "conflicto_entre_propuestas; pendiente_revision"
            else:
                datos[campo] = valor
                origenes[campo] = "reglas_designacion_personal_y_remision_expresa; no_qwen"
                evidencias[campo] = relaciones["designacion_y_otorgamiento"]+relaciones["clausula_completa"]
                reemplazos.append(campo)
    if capital["estado"] == "propuesta_capital_suscrito_del_instrumento":
        if datos["capital_social_actual"] and datos["capital_social_actual"] != capital["valor"]:
            conflictos.append({"campo": "capital_social_actual", "qwen": datos["capital_social_actual"], "reglas": capital["valor"]})
            datos["capital_social_actual"] = None
            origenes["capital_social_actual"] = "conflicto_entre_propuestas; pendiente_revision"
        else:
            datos["capital_social_actual"] = capital["valor"]
            evidencias["capital_social_actual"] = capital["evidencias"]
            origenes["capital_social_actual"] = capital["origen"]
            reemplazos.append("capital_social_actual")
    estados = {c: {"estado": "pendiente_revision", "aprobado": False,
                  "revision_humana": "pendiente", "valor_propuesto": datos[c] not in (None, []),
                  "origen": origenes[c], "exhaustividad": "no_verificada"} for c in CAMPOS}
    validar(datos, {"estados": estados})
    lectura_citas = {**lectura, "paginas": list(lectura["paginas"])+([fuente_tabla] if fuente_tabla else [])}
    citas_verificadas = verificar(lectura_citas, [evidencias, relaciones, capital])
    return {"documento": {"archivo": lectura.get("archivo"), "sha256_pdf": lectura["sha256_pdf"],
                          "paginas": len(lectura["paginas"])},
            "datos": datos, "datos_qwen_filtrados": datos_qwen, "estados": estados,
            "evidencias": evidencias, "campos_completados_por_reglas": reemplazos,
            "relaciones_documentales": relaciones, "control_capital": capital,
            "conflictos_entre_metodos": conflictos,
            "citas_de_la_integracion_verificadas": citas_verificadas,
            "fuentes_adicionales": [fuente_tabla] if fuente_tabla else [],
            "control_semantico": salida_ia["control_semantico"],
            "propuestas_no_son_resultados_aprobados": True, "estructura_validada": True,
            "entrenamiento": False, "inferencias_nuevas": 0, "ocr_nuevo": 0,
            "ocr_nuevo_se_refiere_a_este_reprocesamiento": True,
            "precision_ocho_campos": None, "produccion_validada": False,
            "campos_sin_propuesta": [c for c in CAMPOS if datos[c] in (None, [])],
            "pendientes": ["Revisión humana de valores, cargos, restricciones y capital del instrumento",
                "Medición en documentos de empresas y expedientes no usados para ajustar estas reglas",
                "La vigencia jurídica y el capital actuales fuera de este expediente no se verificaron"]}


def cargar_codigo(proyecto):
    paquete = Path(proyecto) / "CITI_CONTEXTO_Y_EVALUACION_v1.zip"
    carpeta = Path(tempfile.mkdtemp(prefix="citi_control_resultado_"))
    with zipfile.ZipFile(paquete) as z:
        for nombre in z.namelist():
            if nombre.startswith(("CODIGO/", "MODELO_OPCIONAL/")) and nombre.endswith(".py"):
                (carpeta / Path(nombre).name).write_bytes(z.read(nombre))
        (carpeta / "ESQUEMA_SALIDA.json").write_bytes(z.read("CODIGO/ESQUEMA_SALIDA.json"))
    modulo_relaciones = Path(__file__).with_name("DOCUMENT_RELATIONS.py")
    if not modulo_relaciones.is_file():
        raise FileNotFoundError("Falta DOCUMENT_RELATIONS.py junto al validador")
    (carpeta / modulo_relaciones.name).write_bytes(modulo_relaciones.read_bytes())
    sys.path.insert(0, str(carpeta))
    return carpeta


def reprocesar(proyecto, resultado):
    proyecto, resultado = Path(proyecto), Path(resultado)
    cargar_codigo(proyecto)
    from DOCUMENT_CONTEXT import leer
    lectura = leer(proyecto / "CITI_ENTRENAR_LOCALIZADOR.zip")
    ruta_estado = resultado / "RAG/ESTADO_EXTRACTOR_IA.json"
    estado = json.loads(ruta_estado.read_text(encoding="utf-8"))
    datos_reglas = json.loads((resultado / "REGLAS/EXTRACCION_OCHO_CAMPOS.json").read_text())
    registro = json.loads((resultado / "REGLAS/EVIDENCIAS_Y_CONTROL.json").read_text())
    filtrada, resultados, contexto = controlar_estado(estado, lectura)
    ruta_fuente = proyecto / "CITI_FUENTE_TABLA_CAPITAL.json"
    fuente_tabla = json.loads(ruta_fuente.read_text()) if ruta_fuente.is_file() else None
    control = integrar(filtrada, datos_reglas, registro, lectura, contexto, fuente_tabla)
    control["ejecucion_original"] = str(resultado)
    control["sha256_estado_original"] = sha(ruta_estado.read_bytes())
    control["modelo_de_la_ejecucion_original"] = estado["protocolo"]["modelo"]
    control["resumen_por_campo"] = {c: {"candidatos_conservados": len(r.get("candidatos", [])),
        "rechazos": r.get("rechazos", []), "salida_incompleta": r.get("salida_incompleta", False)}
        for c, r in resultados.items()}
    revision = resultado / "COPIA_REVISIONES.json"
    if revision.is_file():
        control["revisiones_humanas_originales"] = json.loads(revision.read_text())
        control["sha256_revisiones_originales"] = sha(revision.read_bytes())
        control["relevancia_no_equivale_a_aprobacion_del_valor"] = True
    huella = Path(__file__).read_bytes()+Path(__file__).with_name("DOCUMENT_RELATIONS.py").read_bytes()
    if ruta_fuente.is_file():
        huella += ruta_fuente.read_bytes()
    destino = resultado / ("CONTROL_" + sha(huella)[:12])
    guardar(destino / "EXTRACCION_OCHO_CAMPOS_CONTROLADA.json", control["datos"])
    guardar(destino / "EXTRACCION_RAG_FILTRADA.json", control["datos_qwen_filtrados"])
    guardar(destino / "CONTROL_DE_RESULTADO.json", control)
    print("CONTROL TERMINADO. Inferencias nuevas: 0 | entrenamiento: 0")
    for campo, valor in control["datos"].items():
        if campo != "poderes":
            print(campo+":", json.dumps(valor, ensure_ascii=False))
    print("poderes:", len(control["datos"]["poderes"]), "incisos; texto completo y restricciones en el JSON")
    print("Campos sin propuesta:", ", ".join(control["campos_sin_propuesta"]) or "ninguno en este caso")
    print("Origen por reglas:", ", ".join(control["campos_completados_por_reglas"]))
    print("Fuentes OCR adicionales reutilizadas:", len(control["fuentes_adicionales"]))
    print("Todas son propuestas pendientes de revisión; no se midió precisión.")
    print("RESULTADOS CONTROLADOS:", destino)
    return destino


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proyecto", default="/content/drive/MyDrive/CITI_CONTINUIDAD")
    parser.add_argument("--resultado")
    args = parser.parse_args()
    proyecto = Path(args.proyecto)
    if not proyecto.is_dir():
        from google.colab import drive
        drive.mount("/content/drive")
    reprocesar(proyecto, args.resultado or proyecto / "RESULTADO_JSON_RAG" / CARPETA_EJECUCION)
