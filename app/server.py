"""Servidor local del prototipo. No exponer directamente a Internet."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
from pathlib import Path
import re
import sys
import threading
from urllib.parse import parse_qs, unquote, urlsplit
import uuid
import zipfile

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
import pipeline
from storage import Store, ahora

MAX_FILE = 50 * 1024 * 1024
MAX_PAGES = 100
JOB_ID = r'[a-f0-9]{24}'


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def validar_revision(doc, draft):
    """Verifica identidad, tipos y citas. El nombre del revisor es declarado."""
    from validate_output import validar
    if (not isinstance(draft, dict) or draft.get('documento_id') != doc['id']
            or draft.get('snapshot') != doc['snapshot'] or draft.get('particion') != doc['partition']):
        raise ValueError('La revisión no corresponde a esta versión del documento')
    valores = dict(doc['values'])
    for campo, review in draft.get('fieldReviews', {}).items():
        if campo not in pipeline.CAMPOS or not isinstance(review, dict) or not str(review.get('reviewed_by', '')).strip():
            raise ValueError('Campo o revisor inválido')
        v = review.get('value')
        if v is None or v == []:
            raise ValueError('Un valor ausente no confirma ausencia global')
        valores[campo] = v
        e = review.get('evidence', {})
        if e.get('campo') != campo or type(e.get('pagina')) is not int or not 1 <= e['pagina'] <= len(doc['pages']):
            raise ValueError('La evidencia no corresponde al campo o página')
        p = doc['pages'][e['pagina'] - 1]
        if e.get('fuente_id') != p['source'] or e.get('sha256_texto_fuente') != p['textSha']:
            raise ValueError('Fuente de revisión incorrecta')
        rr = e.get('rangos', [])
        if not rr or any(not isinstance(r, list) or len(r) != 2 or type(r[0]) is not int or type(r[1]) is not int
                         or not 0 <= r[0] < r[1] <= len(p['text']) for r in rr):
            raise ValueError('Rangos de revisión incorrectos')
        if '\n'.join(p['text'][a:b] for a, b in rr) != e.get('texto_literal'):
            raise ValueError('La cita revisada no es literal')
    validar(valores, {'estados': {c: {'estado': 'pendiente_revision', 'aprobado': False} for c in pipeline.CAMPOS}})


class Application:
    def __init__(self, data, ui=None):
        self.store = Store(data)
        self.ui = Path(ui or pipeline.ROOT / 'ui').resolve()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='documento')
        self.submit_lock = threading.Lock()
        self.session = uuid.uuid4().hex
        self.fingerprint = pipeline.huella_pipeline()
        try:
            from pdf_reading import resolver_ocr
            self.ocr_fingerprint = resolver_ocr(instalar=False)
        except (FileNotFoundError, RuntimeError):
            self.ocr_fingerprint = None

    def submit(self, data, filename, engine='reglas', retry=False):
        if engine not in ('reglas', 'qwen'):
            raise Problem(400, 'Elige reglas o qwen')
        if engine == 'qwen' and not pipeline.capacidades()['qwen_bibliotecas']:
            raise Problem(409, 'Faltan dependencias Qwen. Prepara requirements-qwen.txt en el entorno antes de usar ese motor.')
        if len(data) > MAX_FILE:
            raise Problem(413, 'El PDF supera 50 MB')
        if b'%PDF-' not in data[:1024]:
            raise Problem(400, 'El archivo no tiene una cabecera PDF válida')
        # Preserva el original; el nombre no decide su identidad ni su tipo.
        filename = ''.join(c for c in filename.replace('\\', '/').split('/')[-1] if c.isprintable())[:180] or 'documento.pdf'
        digest = pipeline.sha(data)
        key = pipeline.sha(json.dumps([digest, self.fingerprint, self.ocr_fingerprint, engine,
                                      self.session if engine == 'qwen' else None], sort_keys=True).encode())[:24]
        with self.submit_lock:
            anterior = self.store.get(key)
            if anterior and not (retry and anterior['status'] == 'error'):
                return {**anterior, 'reused': True}
            if sum(j['status'] in ('queued', 'running') for j in self.store.list()) >= 3:
                raise Problem(429, 'Hay tres trabajos pendientes. Espera a que termine uno.')
            carpeta = self.store.root / key
            carpeta.mkdir(exist_ok=True)
            (carpeta / 'ORIGINAL.pdf').write_bytes(data)
            job = {'id': key, 'filename': filename, 'sha256_pdf': digest, 'engine': engine,
                   'status': 'queued', 'stage': 'En cola', 'created_at': ahora(), 'updated_at': ahora(),
                   'attempt': (anterior or {}).get('attempt', 0) + 1, 'error': None,
                   'pipeline_fingerprint': self.fingerprint, 'produccion_validada': False}
            self.store.put(job)
            self.pool.submit(self.run, key)
            return {**job, 'reused': False}

    def run(self, key):
        folder = self.store.root / key
        log = io.StringIO()
        try:
            self.store.update(key, status='running', stage='Inspeccionando PDF')
            import fitz
            with fitz.open(folder / 'ORIGINAL.pdf') as d:
                if d.needs_pass:
                    raise ValueError('PDF protegido: se necesita una copia accesible autorizada; no se hace OCR')
                if not 1 <= len(d) <= MAX_PAGES:
                    raise ValueError('Se admiten entre 1 y 100 páginas por trabajo')
                if any(p.rect.get_area() * (300/72)**2 > 30_000_000 for p in d):
                    raise ValueError('Una página excede el tamaño de renderizado del piloto')
            def etapa(texto):
                log.write(ahora() + ' ' + texto + '\n')
                self.store.update(key, stage=texto)
            doc = pipeline.procesar(folder / 'ORIGINAL.pdf', folder / 'RESULTADO', key,
                self.store.get(key)['engine'], etapa)
            doc['filename'] = self.store.get(key)['filename']
            doc['title'] = Path(doc['filename']).stem
            pipeline.guardar(folder / 'RESULTADO' / 'DOCUMENTO_WEB.json', doc)
            self.store.update(key, status='needs_review', stage='Listo para revisión humana',
                              document_url=f'api/jobs/{key}/document', json_url=f'api/jobs/{key}/extraction.json',
                              backup_url=f'api/jobs/{key}/backup.zip', seconds=doc['control']['segundos'])
        except Exception as e:
            self.store.update(key, status='error', stage='Requiere atención', error=f'{type(e).__name__}: {e}')
        finally:
            (folder / 'PROCESAMIENTO.log').write_text(log.getvalue(), encoding='utf-8')

    def close(self):
        self.pool.shutdown(wait=True)


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'DocumentPrototype/1.1'

        def log_message(self, *_):
            pass  # No se escriben PDF, nombres de personas ni texto documental en consola.

        def send_bytes(self, data, content_type, status=200, filename=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            self.send_header('Cache-Control', 'no-store' if self.path.startswith('/api/') else 'no-cache')
            if filename:
                safe = re.sub(r'[^A-Za-z0-9_.-]', '_', filename)
                self.send_header('Content-Disposition', f'attachment; filename="{safe}"')
            self.end_headers()
            self.wfile.write(data)

        def respond(self, obj, status=200):
            self.send_bytes(json.dumps(obj, ensure_ascii=False).encode(), 'application/json; charset=utf-8', status)

        def read_body(self, maximum):
            try:
                n = int(self.headers.get('Content-Length', '-1'))
            except ValueError:
                raise Problem(411, 'Se requiere Content-Length válido')
            if n < 0:
                raise Problem(411, 'Se requiere Content-Length')
            if n > maximum:
                raise Problem(413, 'El archivo supera el límite permitido')
            data = self.rfile.read(n)
            if len(data) != n:
                raise Problem(400, 'La carga del archivo quedó incompleta')
            return data

        def get_job(self, key):
            job = app.store.get(key)
            if not job:
                raise Problem(404, 'Trabajo no encontrado')
            return job

        def do_GET(self):
            try:
                path = unquote(urlsplit(self.path).path)
                if path == '/api/health':
                    return self.respond({'ok': True, **pipeline.capacidades(),
                        'persistencia': 'SQLite y archivos locales', 'autenticacion_app': 'no_implementada; solo entorno local/proxy autorizado'})
                if path == '/api/jobs':
                    return self.respond({'jobs': app.store.list()})
                m = re.fullmatch('/api/jobs/(' + JOB_ID + ')(?:/(.*))?', path)
                if m:
                    key, resource = m.groups()
                    job = self.get_job(key)
                    folder = app.store.root / key
                    if not resource:
                        return self.respond(job)
                    if resource == 'review':
                        return self.respond(app.store.review(key))
                    if resource == 'backup.zip':
                        if job['status'] in ('queued', 'running'):
                            raise Problem(409, 'El procesamiento todavía no termina')
                        memory = io.BytesIO()
                        with zipfile.ZipFile(memory, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                            for p in folder.rglob('*'):
                                if p.is_file() and p.suffix != '.tmp':
                                    z.write(p, p.relative_to(folder))
                            z.writestr('REVISION_SERVIDOR.json', json.dumps(app.store.review(key), ensure_ascii=False))
                            web_path = folder / 'RESULTADO/DOCUMENTO_WEB.json'
                            if web_path.is_file():
                                web = json.loads(web_path.read_text())
                                web['originalServerJob'] = web.pop('serverJob', None)
                                for p in web['pages']:
                                    image_name = f'PAGINAS/p{p["page"]:03}.jpg'
                                    z.write(folder / 'RESULTADO/PAGINAS' / f'{p["page"]}.jpg', image_name)
                                    p['image'] = image_name
                                z.writestr('DOCUMENTO_WEB.json', json.dumps(web, ensure_ascii=False))
                                review = app.store.review(key)
                                if review['draft']:
                                    z.writestr('REVISION_WEB.json', json.dumps(review['draft'], ensure_ascii=False))
                        return self.send_bytes(memory.getvalue(), 'application/zip', filename=f'DOCUMENTO_{key}.zip')
                    known = {'document': 'DOCUMENTO_WEB.json', 'extraction.json': 'EXTRACCION_OCHO_CAMPOS.json',
                             'evidence.json': 'EVIDENCIAS_Y_CONTROL.json', 'context.json': 'CONTEXTO_DOCUMENTAL.json'}
                    if resource in known:
                        p = folder / 'RESULTADO' / known[resource]
                        if not p.is_file():
                            raise Problem(409, 'El resultado todavía no está disponible')
                        return self.send_bytes(p.read_bytes(), 'application/json; charset=utf-8',
                            filename=known[resource] if resource.endswith('.json') else None)
                    page = re.fullmatch(r'pages/([1-9][0-9]{0,2})\.jpg', resource)
                    if page:
                        p = folder / 'RESULTADO' / 'PAGINAS' / (page[1] + '.jpg')
                        if not p.is_file():
                            raise Problem(404, 'Página no disponible')
                        return self.send_bytes(p.read_bytes(), 'image/jpeg')
                    raise Problem(404, 'Recurso no encontrado')
                if path.startswith('/api/'):
                    raise Problem(404, 'Ruta API no encontrada')
                p = (app.ui / (path.lstrip('/') or 'index.html')).resolve()
                if not p.is_relative_to(app.ui) or not p.is_file():
                    raise Problem(404, 'Archivo no encontrado')
                tipo = mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
                if p.suffix == '.mjs':
                    tipo = 'text/javascript'
                return self.send_bytes(p.read_bytes(), tipo)
            except Problem as e:
                self.respond({'error': e.message}, e.status)
            except (ValueError, KeyError, OSError) as e:
                self.respond({'error': str(e)}, 400)

        def do_POST(self):
            try:
                parsed = urlsplit(self.path)
                if parsed.path == '/api/jobs':
                    q = parse_qs(parsed.query)
                    job = app.submit(self.read_body(MAX_FILE), q.get('filename', ['documento.pdf'])[0],
                                     q.get('engine', ['reglas'])[0], q.get('retry', ['0'])[0] == '1')
                    return self.respond(job, 200 if job.get('reused') else 202)
                m = re.fullmatch('/api/jobs/(' + JOB_ID + ')/review', parsed.path)
                if m:
                    key = m[1]
                    job = self.get_job(key)
                    if job['status'] != 'needs_review':
                        raise Problem(409, 'El documento todavía no está listo para revisar')
                    req = json.loads(self.read_body(8 * 1024 * 1024))
                    document = json.loads((app.store.root / key / 'RESULTADO/DOCUMENTO_WEB.json').read_text())
                    validar_revision(document, req.get('draft'))
                    if type(req.get('base_revision')) is not int:
                        raise Problem(400, 'Se requiere base_revision entera')
                    try:
                        result = app.store.save_review(key, req['base_revision'], req['draft'])
                    except ValueError as e:
                        raise Problem(409, str(e))
                    return self.respond(result)
                raise Problem(404, 'Ruta API no encontrada')
            except Problem as e:
                self.respond({'error': e.message}, e.status)
            except (ValueError, KeyError, TypeError, OSError) as e:
                self.respond({'error': str(e)}, 400)

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--data', type=Path, default=pipeline.ROOT / 'runtime_data')
    a = p.parse_args()
    app = Application(a.data)
    server = ThreadingHTTPServer((a.host, a.port), handler_for(app))
    print(f'Proyecto documental: http://{a.host}:{a.port} | prototipo local con revisión humana', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == '__main__':
    main()
