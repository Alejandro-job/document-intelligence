"""Une valores, roles y unidades documentales sin consultar ni entrenar modelos.

El contexto exportado es posterior a la extracción. Su existencia no prueba
que haya sido consumido por Qwen. Las propuestas conservan su estado.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import zipfile

VERSION = "contexto_por_campo_v1"


def normalizar(texto):
    normal, mapa = [], []
    for i, c in enumerate(texto):
        for x in unicodedata.normalize("NFD", c.upper()):
            if unicodedata.category(x) != "Mn":
                normal.append(x); mapa.append(i)
    return "".join(normal), mapa


def enriquecer(control, lectura):
    if control["documento"]["sha256_pdf"] != lectura["sha256_pdf"]:
        raise ValueError("La lectura y el resultado pertenecen a documentos distintos")
    paginas = {p["fuente_id"]: p for p in lectura["paginas"]}
    paginas.update({p["fuente_id"]: p for p in control.get("fuentes_adicionales", [])})

    def cita(p, a, b, uso):
        if not 0 <= a < b <= len(p["texto"]):
            raise ValueError("Rango de contexto inválido")
        return {"fuente_id":p["fuente_id"],"pagina":p["pagina"],"rango_caracteres":[a,b],
                "texto_literal":p["texto"][a:b],
                "sha256_texto_fuente":hashlib.sha256(p["texto"].encode()).hexdigest(),
                "uso_documental":uso,"contenido_documental_no_es_instruccion":True}

    def evidencias(objeto):
        if isinstance(objeto, list):
            return [c for x in objeto for c in evidencias(x)]
        if not isinstance(objeto, dict):
            return []
        if "fuente_id" in objeto and ("rango_caracteres" in objeto or "rangos" in objeto):
            p=paginas[objeto["fuente_id"]]
            if hashlib.sha256(p["texto"].encode()).hexdigest()!=objeto["sha256_texto_fuente"]:
                raise ValueError("Fuente de evidencia modificada")
            rangos=objeto.get("rangos") or [objeto["rango_caracteres"]]
            cs=[cita(p,a,b,objeto.get("metodo","valor_literal_propuesto")) for a,b in rangos]
            esperado=objeto.get("texto_literal",objeto.get("cita_literal",objeto.get("texto")))
            if esperado is not None:
                actual="\n".join(c["texto_literal"] for c in cs)
                if actual != esperado:
                    raise ValueError("Texto de evidencia no literal")
            return cs
        return [c for v in objeto.values() for c in evidencias(v)]

    def unidad(patron, hasta, uso):
        salida=[]
        for p in lectura["paginas"]:
            n, mapa=normalizar(p["texto"])
            for m in re.finditer(patron,n):
                fin=re.search(hasta,n[m.end():]) if hasta else None
                b=m.end()+fin.start() if fin else len(n)
                salida.append(cita(p,mapa[m.start()],mapa[b-1]+1,uso))
        return salida

    aperturas=unidad(r"(?m)^[^\n]{0,24}\bESCRITURA\s+(?:NUMERO\s+)?[A-Z0-9]",r"\bDECLARACIONES\b","apertura_con_fecha_comparecencia_y_constitucion")
    aperturas=[c for c in aperturas if c["pagina"]<=2 and c["rango_caracteres"][0]<1200]
    denominaciones=unidad(r"(?m)^[^\n]{0,30}\bLA\s+(?:SOCIEDAD|ASOCIACION)\s+SE\s+DENOMINA(?:RA)?\b",
        r"(?m)^[^\n]{0,18}\b[A-Z]+(?:[ \t]+[A-Z]+){0,2}\s*\.\s*[-—–]","clausula_de_denominacion_con_forma_juridica")
    otorgantes=unidad(r"\bOTORGANTE\s*\(S\)",r"\bDATOS\s+DEL\s+NOTARIO\b","tabla_otorgantes_con_cabecera_y_caracter")
    designaciones=unidad(r"\bTERCERO\s*\.\s*[-—–]",r"\bCUARTO\s*\.\s*[-—–]","designacion_y_concesion_personal_de_facultades")
    designaciones=[c for c in designaciones if "CONSEJO DE ADMINISTRACION" in normalizar(c["texto_literal"])[0]]
    tablas=unidad(r"\bPRIMERO\s*\.\s*[-—–]",r"\bSEGUNDO\s*\.\s*[-—–]","suscripcion_pago_y_tabla_de_capital")
    tablas=[c for c in tablas if "CAPITAL SOCIAL" in normalizar(c["texto_literal"])[0] and "IMPORTE" in normalizar(c["texto_literal"])[0]]
    relacion=control.get("relaciones_documentales",{})
    clausula=evidencias(relacion.get("clausula_completa",[]))
    clausula=[c for c in clausula if len(re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]","",c["texto_literal"]))>=10]
    bloques={
        "razon_social":denominaciones+aperturas,
        "fecha_constitucion":aperturas,
        "numero_escritura":aperturas,
        "notario":aperturas,
        "socios":otorgantes,
        "representantes_legales":designaciones+clausula,
        "poderes":designaciones+clausula,
        "capital_social_actual":tablas+[cita(p,0,len(p["texto"]),"tabla_releida_como_fuente_adicional") for p in control.get("fuentes_adicionales",[])],
    }
    roles={"razon_social":"denominacion_y_forma_juridica_propuestas", "fecha_constitucion":"fecha_del_acto_constitutivo_propuesta",
           "numero_escritura":"identificador_del_instrumento", "notario":"fedatario_actuante_propuesto",
           "socios":"accionistas_propuestos_desde_tabla_con_caracter", "representantes_legales":"personas_designadas_con_facultades_expresas",
           "poderes":"facultades_vinculadas_a_titulares_y_restricciones", "capital_social_actual":"capital_suscrito_del_instrumento; vigencia_externa_no_verificada"}
    campos={}
    for campo,valor in control["datos"].items():
        if campo=="representantes_legales":
            citas_valor=[c for p in relacion.get("personas",[]) for c in evidencias(p.get("evidencia_cargo",[]))]
        elif campo=="poderes":
            citas_valor=[c for p in relacion.get("poderes",[]) for c in evidencias(p.get("evidencias",[]))]
        else:
            citas_valor=evidencias(control["evidencias"][campo])
        contexto=bloques.get(campo,[])+citas_valor
        unicas={}
        for c in contexto:
            unicas.setdefault((c["fuente_id"],*c["rango_caracteres"]),c)
        campos[campo]={"valor":copy.deepcopy(valor),"rol_o_evento_propuesto":roles[campo],
            "origen":control["estados"][campo]["origen"],"estado":copy.deepcopy(control["estados"][campo]),
            "evidencia_del_valor":citas_valor,"contexto_documental":list(unicas.values()),
            "contexto_completo_de_pagina_disponible_en_lectura":True,
            "contexto_no_equivale_a_aprobacion":True}
    for campo in ("representantes_legales","poderes"):
        campos[campo]["personas_y_cargos"]=copy.deepcopy(relacion.get("personas",[]))
        campos[campo]["clausula_remitida"]=relacion.get("clausula")
        campos[campo]["forma_de_ejercicio_literal"]=relacion.get("forma_ejercicio_literal")
        campos[campo]["incisos_y_restricciones"]=copy.deepcopy(relacion.get("poderes",[]))
    campos["socios"]["personas_y_caracter"]=copy.deepcopy(control["evidencias"]["socios"])
    campos["notario"]["control_de_confusion"]="La persona que actúa ante mí se distingue del titular citado en el instrumento"
    campos["capital_social_actual"]["controles_de_tabla"]=copy.deepcopy(control.get("control_capital"))
    return {"version":VERSION,"documento":copy.deepcopy(control["documento"]),"campos":campos,
            "control":{"contexto_por_campo_exportado":True,"contexto_enriquecido_enviado_a_qwen":False,
                "inferencias_nuevas":0,"entrenamiento":False,"estados_humanos_conservados":True,
                "precision_extraccion":None,"produccion_validada":False,
                "alcance":"Enriquecimiento del resultado existente; no sustituye la integración del contexto al prompt ni su evaluación"}}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--proyecto",default="/content/drive/MyDrive/CITI_CONTINUIDAD")
    p.add_argument("--control");p.add_argument("--lectura");p.add_argument("--salida")
    a=p.parse_args()
    proyecto=Path(a.proyecto)
    control=Path(a.control) if a.control else proyecto/"RESULTADO_JSON_RAG/e39eb2e3189e10b8_283c37902a/CONTROL_79a8dd52fc55/CONTROL_DE_RESULTADO.json"
    if a.lectura:
        lectura=json.loads(Path(a.lectura).read_text())
    else:
        with zipfile.ZipFile(proyecto/"CITI_ENTRENAR_LOCALIZADOR.zip") as z:
            lectura=json.loads(z.read("DATOS/LECTURA_TIDA.json"))
    d=enriquecer(json.loads(control.read_text()),lectura)
    destino=Path(a.salida) if a.salida else control.with_name("RESULTADO_CON_CONTEXTO.json")
    destino.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Contexto exportado para",len(d["campos"]),"campos. Inferencias: 0 | entrenamiento: 0")
    print("Guardado:",destino)
