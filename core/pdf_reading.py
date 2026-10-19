"""Lectura por página: texto del PDF primero, OCR español como respaldo.

No exige carpetas de una sesión anterior. La inspección se guarda antes de
resolver dependencias OCR. No instala ni carga modelos de lenguaje.
"""
import argparse
import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from document_revision import guardar,sha,firma

DPI=300

def elegir_interprete(instalar=False):
    candidatos=[sys.executable,'/content/citi_ocr_env/bin/python']
    for exe in dict.fromkeys(candidatos):
        if not Path(exe).is_file():continue
        prueba=subprocess.run([exe,'-c','import fitz; from PIL import Image; assert hasattr(fitz,"open")'],capture_output=True,timeout=30)
        if prueba.returncode==0:return exe
    if not instalar:raise RuntimeError('Faltan PyMuPDF/Pillow en los intérpretes disponibles')
    print('Preparando lector PDF y visor: PyMuPDF/Pillow. Se conserva Qwen.',flush=True)
    subprocess.run([sys.executable,'-m','pip','install','-q','pymupdf>=1.24,<2','Pillow>=10,<13'],check=True,timeout=180)
    return sys.executable

def resolver_ocr(tessdata=None,instalar=False):
    def buscar():
        if not shutil.which('tesseract'):return None
        rutas=[]
        if tessdata:rutas.append(Path(tessdata))
        if os.environ.get('TESSDATA_PREFIX'):rutas.append(Path(os.environ['TESSDATA_PREFIX']))
        rutas.extend(Path(p) for p in (
            '/content/citi_prueba_externa/citi_verificacion_ocr/tessdata',
            '/usr/share/tesseract-ocr/5/tessdata','/usr/share/tesseract-ocr/4.00/tessdata',
            '/usr/share/tessdata','/usr/local/share/tessdata'))
        r=subprocess.run(['tesseract','--list-langs'],capture_output=True,text=True,timeout=20)
        for ruta in re.findall(r'"([^"\n]+)"',r.stdout+'\n'+r.stderr):rutas.append(Path(ruta))
        for ruta in dict.fromkeys(rutas):
            modelo=ruta/'spa.traineddata'
            if modelo.is_file() and modelo.stat().st_size>1000:
                prueba=subprocess.run(['tesseract','--tessdata-dir',str(ruta),'--list-langs'],capture_output=True,text=True,timeout=20)
                if 'spa' in (prueba.stdout+'\n'+prueba.stderr).splitlines():return ruta
        return None
    ruta=buscar()
    if ruta is None and instalar:
        if not shutil.which('apt-get'):raise RuntimeError('No se encontró Tesseract español ni apt-get; el PDF necesita OCR')
        print('Sólo las páginas sin texto requieren OCR. Preparando Tesseract y español…',flush=True)
        subprocess.run(['apt-get','update','-qq'],check=True,timeout=180)
        subprocess.run(['apt-get','install','-y','-qq','--no-install-recommends','tesseract-ocr','tesseract-ocr-spa'],check=True,timeout=180)
        ruta=buscar()
    if ruta is None:raise FileNotFoundError('Estas páginas necesitan OCR; no se encontró Tesseract con español. No se requiere OCR para páginas con texto utilizable.')
    return {'tessdata':str(ruta),'sha256_spa':sha((ruta/'spa.traineddata').read_bytes()),
            'version':subprocess.check_output(['tesseract','--version'],text=True).splitlines()[0]}

def construir_texto(grupos):
    texto=[];lineas=[];palabras=[];cursor=0
    for grupo in grupos:
        if not grupo:continue
        inicio=cursor;trozos=[];boxes=[]
        for t,box in grupo:
            if trozos:cursor+=1
            palabras.append({'a':cursor,'b':cursor+len(t),'t':t,'box':list(box)})
            cursor+=len(t);trozos.append(t);boxes.append(box)
        linea=' '.join(trozos)
        lineas.append({'texto':linea,'rango_caracteres':[inicio,cursor],
            'bbox_pixeles':[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]})
        texto.append(linea);cursor+=1
    return '\n'.join(texto),lineas,palabras

def texto_pdf(pagina):
    import fitz
    grupos={};escala=DPI/72
    for w in pagina.get_text('words',sort=True):
        t=w[4].strip()
        if not t:continue
        r=(fitz.Rect(w[:4])*pagina.rotation_matrix)&pagina.rect
        if r.is_empty:continue
        box=[r.x0*escala,r.y0*escala,r.x1*escala,r.y1*escala]
        grupos.setdefault((w[5],w[6]),[]).append((t,box))
    return construir_texto(grupos.values())

def decidir_pagina(pagina,texto,palabras):
    utiles=sum(c.isalnum() for c in texto);danados=texto.count('\ufffd')
    imagenes=pagina.get_image_info();area=pagina.rect.get_area() or 1
    grande=any(max(0,(min(i['bbox'][2],pagina.rect.width)-max(i['bbox'][0],0)))*max(0,(min(i['bbox'][3],pagina.rect.height)-max(i['bbox'][1],0)))/area>.60 for i in imagenes)
    if not palabras and not imagenes and not pagina.get_drawings() and not list(pagina.annots() or []):
        metodo='vacia'
    elif utiles>=40 and danados<=max(1,len(texto)*.02) and (not grande or utiles>=200):metodo='texto_pdf'
    else:metodo='tesseract_spa'
    return {'metodo':metodo,'requiere_ocr':metodo=='tesseract_spa','caracteres_texto_pdf':len(texto),
        'caracteres_alfanumericos':utiles,'imagen_grande':grande,
        'criterio':'heuristica_de_texto_utilizable; no mide exactitud ni completitud'}

def leer_tsv_palabras(tsv):
    lector=csv.DictReader(io.StringIO(tsv),delimiter='\t',quoting=csv.QUOTE_NONE)
    requeridas={'level','page_num','block_num','par_num','line_num','left','top','width','height','text'}
    if not lector.fieldnames or not requeridas<=set(lector.fieldnames):raise ValueError('Tesseract no devolvió TSV válido')
    grupos={}
    for f in lector:
        if f.get('level')!='5' or not f.get('text','').strip():continue
        x,y,w,h=[int(f[k]) for k in ('left','top','width','height')]
        key=tuple(f[k] for k in ('page_num','block_num','par_num','line_num'))
        grupos.setdefault(key,[]).append((f['text'].strip(),[x,y,x+w,y+h]))
    return construir_texto(grupos.values())

def ocr_pagina(pagina,config,imagen,tsv):
    import fitz
    from PIL import Image,ImageChops,ImageOps
    pix=pagina.get_pixmap(dpi=DPI,colorspace=fitz.csRGB,alpha=False)
    original=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
    r,g,b=original.split()
    ImageOps.autocontrast(ImageChops.lighter(ImageChops.lighter(r,g),b)).save(imagen)
    try:
        res=subprocess.run(['tesseract',str(imagen),'stdout','-l','spa','--tessdata-dir',config['tessdata'],
            '--psm','6','-c','tessedit_create_tsv=1','-c','tessedit_create_txt=0'],capture_output=True,text=True,encoding='utf-8',check=True,timeout=120)
        tsv.write_text(res.stdout,encoding='utf-8');t,ls,ws=leer_tsv_palabras(res.stdout)
        return {'texto':t,'lineas':ls,'palabras':ws,'ancho':pix.width,'alto':pix.height,'avisos_ocr':res.stderr.strip()}
    finally:imagen.unlink(missing_ok=True)

def leer_pdf(pdf,salida,tessdata=None,instalar=False):
    import fitz
    pdf=Path(pdf);salida=Path(salida);salida.mkdir(parents=True,exist_ok=True)
    huella=sha(pdf.read_bytes())
    try:doc=fitz.open(pdf)
    except (RuntimeError,ValueError) as err:
        guardar(salida/'INSPECCION_PDF.json',{'sha256_pdf':huella,'estado':'no_se_pudo_abrir','error':str(err)})
        raise ValueError('No se pudo abrir el PDF. Se guardó el diagnóstico de entrada.') from err
    with doc:
        if doc.needs_pass:
            guardar(salida/'INSPECCION_PDF.json',{'sha256_pdf':huella,'estado':'protegido_sin_clave'})
            raise ValueError('El PDF requiere contraseña; no se intenta OCR sobre contenido inaccesible')
        if not len(doc):raise ValueError('El PDF no contiene páginas')
        analisis=[];nativos=[]
        for n,p in enumerate(doc,1):
            t,ls,ws=texto_pdf(p);d=decidir_pagina(p,t,ws)
            analisis.append({'pagina':n,**d});nativos.append((t,ls,ws))
        cantidad=sum(a['requiere_ocr'] for a in analisis)
        clasificacion='mixto' if 0<cantidad<len(doc) else ('escaneado_o_texto_no_utilizable' if cantidad else 'texto_pdf_o_paginas_vacias')
        inspeccion={'archivo':pdf.name,'sha256_pdf':huella,'estado':'inspeccionado','clasificacion':clasificacion,
            'paginas_totales':len(doc),'paginas_con_ocr_necesario':cantidad,'pdf_reparado_por_pymupdf':bool(doc.is_repaired),'paginas':analisis}
        guardar(salida/'INSPECCION_PDF.json',inspeccion)
        print(f'INSPECCIÓN: {len(doc)} páginas | {len(doc)-cantidad} con texto/vacías | {cantidad} requieren OCR',flush=True)
        config=resolver_ocr(tessdata,instalar) if cantidad else None
        protocolo={'version':'citi_lectura_hibrida_v1','sha256_pdf':huella,'pymupdf':fitz.VersionBind,
            'dpi':DPI,'psm':6,'ocr':config,'codigo':sha(Path(__file__).read_bytes())}
        clave=firma(protocolo);paginas=[]
        for indice,p in enumerate(doc):
            n=indice+1;d=analisis[indice];metodo=d['metodo'];dest=salida/f'pagina_{n:03}.json'
            anterior=json.loads(dest.read_bytes()) if dest.is_file() else {}
            if anterior.get('firma_lectura')==clave and anterior.get('estado')=='completo':
                paginas.append(anterior);print(f'Página {n}/{len(doc)}: {metodo} reutilizado',flush=True);continue
            reg={'pagina':n,'fuente_id':f'doc_{huella[:24]}:p{n:03}:{metodo}','sha256_pdf':huella,
                'firma_lectura':clave,'metodo_lectura':metodo,'texto':'','lineas':[],'palabras':[],'dpi':DPI,
                'ancho':p.rect.width*DPI/72,'alto':p.rect.height*DPI/72}
            inicio=time.monotonic()
            try:
                if metodo=='tesseract_spa':reg.update(ocr_pagina(p,config,salida/f'pagina_{n:03}.png',salida/f'pagina_{n:03}.tsv'))
                elif metodo=='texto_pdf':
                    t,ls,ws=nativos[indice];reg.update(texto=t,lineas=ls,palabras=ws)
                reg.update(estado='completo',caracteres=len(reg['texto']))
            except (OSError,RuntimeError,ValueError,subprocess.SubprocessError) as err:reg.update(estado='error',error=f'{type(err).__name__}: {err}')
            reg['segundos']=round(time.monotonic()-inicio,3);guardar(dest,reg);paginas.append(reg)
            print(f"Página {n}/{len(doc)}: {metodo} | {reg['estado']} | {len(reg['texto'])} caracteres",flush=True)
        lectura={'archivo':pdf.name,'sha256_pdf':huella,'paginas':paginas,'paginas_totales':len(paginas),
            'protocolo_lectura':protocolo,'inspeccion_pdf':inspeccion,
            'paginas_no_leidas':[p['pagina'] for p in paginas if p['estado']!='completo'],
            'paginas_sin_texto':[p['pagina'] for p in paginas if not p['texto'].strip()]}
        guardar(salida/'LECTURA.json',lectura);return lectura

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--pdf',required=True);a.add_argument('--salida',required=True)
    a.add_argument('--tessdata');a.add_argument('--instalar-dependencias',action='store_true');v=a.parse_args()
    leer_pdf(v.pdf,v.salida,v.tessdata,v.instalar_dependencias)
