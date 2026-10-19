"""Pruebas funcionales del servicio. Referencias sintéticas; sin inferencia Qwen."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from server import Application, handler_for, validar_revision
from http.server import ThreadingHTTPServer
from storage import Store
import pipeline


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app = Application(cls.tmp.name)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(cls.app))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.app.close(); cls.tmp.cleanup()

    def request(self, path, data=None, method=None, headers=None):
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def submit(self, name='01_acta_constitucion_A.pdf'):
        pdf = (ROOT / 'material_prueba' / name).read_bytes()
        status, body, _ = self.request('/api/jobs?filename=' + name, pdf, 'POST', {'Content-Type': 'application/pdf'})
        self.assertIn(status, [200, 202])
        job = json.loads(body)
        for _ in range(200):
            job = self.app.store.get(job['id'])
            if job['status'] in ('needs_review', 'error'):
                return job
            time.sleep(.025)
        self.fail('El trabajo de prueba no terminó')

    def document(self, job):
        status, body, _ = self.request('/api/jobs/' + job['id'] + '/document')
        self.assertEqual(status, 200)
        return json.loads(body)

    def test_health_no_afirma_produccion(self):
        status, data, _ = self.request('/api/health')
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(data)['produccion_validada'])

    def test_pdf_nativo_json_y_cache_sin_reextraer(self):
        job = self.submit()
        self.assertEqual(job['status'], 'needs_review', job['error'])
        doc = self.document(job)
        self.assertEqual(len(doc['values']), 8)
        self.assertEqual(doc['values']['numero_escritura'], '1201')
        self.assertTrue(all(not s['aprobado'] for s in doc['control']['estados'].values()))
        self.assertEqual(self.submit()['attempt'], 1)
        status, body, _ = self.request('/api/jobs/' + job['id'] + '/extraction.json')
        self.assertEqual(status, 200)
        self.assertEqual(set(json.loads(body)), set(pipeline.CAMPOS))

    def test_modificacion_mantiene_fecha_original_y_cambia_designacion_y_capital(self):
        job = self.submit('03_acta_modificacion_C.pdf')
        self.assertEqual(job['status'], 'needs_review', job['error'])
        doc = self.document(job)
        self.assertEqual(doc['values']['fecha_constitucion'], '2022-03-14')
        self.assertEqual(doc['values']['representantes_legales'], ['MARIANA ORTEGA EJEMPLO'])
        self.assertEqual(doc['values']['capital_social_actual']['valor'], '500000.00')
        self.assertEqual(len(doc['pages']), 2)

    def test_respaldo_autocontenido_con_pdf_imagenes_y_fuentes(self):
        job = self.submit()
        status, body, _ = self.request('/api/jobs/' + job['id'] + '/backup.zip')
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            self.assertIn('ORIGINAL.pdf', z.namelist())
            doc = json.loads(z.read('DOCUMENTO_WEB.json'))
            self.assertTrue(all(p['image'] in z.namelist() for p in doc['pages']))
            self.assertNotIn('serverJob', doc)

    def test_carga_que_no_es_pdf_se_rechaza(self):
        status, body, _ = self.request('/api/jobs', b'no es PDF', 'POST')
        self.assertEqual(status, 400)
        self.assertIn('PDF', json.loads(body)['error'])

    def test_pdf_corrupto_no_se_presenta_como_campos_vacios_validos(self):
        status, body, _ = self.request('/api/jobs', b'%PDF-1.7\ncontenido roto', 'POST')
        self.assertEqual(status, 202)
        job = json.loads(body)
        for _ in range(100):
            job = self.app.store.get(job['id'])
            if job['status'] == 'error':
                break
            time.sleep(.02)
        self.assertEqual(job['status'], 'error')
        self.assertEqual(self.request('/api/jobs/' + job['id'] + '/extraction.json')[0], 409)

    def test_pdf_protegido_no_intenta_ocr(self):
        import fitz
        with fitz.open(ROOT / 'material_prueba/01_acta_constitucion_A.pdf') as d:
            data = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='propietario', user_pw='clave_prueba')
        status, body, _ = self.request('/api/jobs', data, 'POST')
        self.assertEqual(status, 202)
        job = json.loads(body)
        for _ in range(100):
            job = self.app.store.get(job['id'])
            if job['status'] == 'error':
                break
            time.sleep(.02)
        self.assertEqual(job['status'], 'error')
        self.assertIn('protegido', job['error'])

    def test_clasificador_por_pagina_distingue_texto_y_scan(self):
        import fitz
        from pdf_reading import texto_pdf, decidir_pagina
        for name, expected in [('01_acta_constitucion_A.pdf', 'texto_pdf'), ('02_acta_escaneada_B.pdf', 'tesseract_spa')]:
            with fitz.open(ROOT / 'material_prueba' / name) as d:
                t, _, w = texto_pdf(d[0])
                self.assertEqual(decidir_pagina(d[0], t, w)['metodo'], expected)

    def test_scan_sin_modelo_espanol_devuelve_error_de_dependencia(self):
        if pipeline.capacidades()['ocr_espanol']:
            self.skipTest('El entorno dispone de OCR español; esta prueba es de dependencia ausente')
        job = self.submit('02_acta_escaneada_B.pdf')
        self.assertEqual(job['status'], 'error')
        self.assertIn('español', job['error'])

    def test_rutas_fuera_de_ui_y_api_desconocida_no_exponen_archivos(self):
        self.assertEqual(self.request('/%2e%2e/README.md')[0], 404)
        self.assertEqual(self.request('/api/jobs/no_es_id/document')[0], 404)

    def test_revision_versionada_y_original_inalterado(self):
        job = self.submit()
        doc = self.document(job)
        evidencia = next(e for e in doc['proposals'] if e['campo'] == 'razon_social')
        draft = {'version': 'citi_revision_web_v1', 'documento_id': doc['id'], 'snapshot': doc['snapshot'],
            'particion': doc['partition'], 'fieldReviews': {'razon_social': {'value': doc['values']['razon_social'],
                'evidence': evidencia, 'reviewed_by': 'revisor_prueba', 'note': 'fixture de prueba'}},
            'annotations': doc['annotations'], 'history': [], 'labels': {'version': 'citi_etiquetas_parciales_v1',
                'documento_id': doc['id'], 'particion': doc['partition'], 'revision': 0, 'decisiones': {}, 'historial': []}}
        req = json.dumps({'base_revision': 0, 'draft': draft}).encode()
        ruta = '/api/jobs/' + job['id'] + '/review'
        before = self.request('/api/jobs/' + job['id'] + '/extraction.json')[1]
        first, body, _ = self.request(ruta, req, 'POST', {'Content-Type': 'application/json'})
        if first == 409:  # El test puede ejecutarse otra vez sobre la misma instancia de clase.
            version = self.app.store.review(job['id'])['revision']
            req = json.dumps({'base_revision': version, 'draft': draft}).encode()
            first, body, _ = self.request(ruta, req, 'POST', {'Content-Type': 'application/json'})
        self.assertEqual(first, 200)
        self.assertEqual(self.request(ruta, req, 'POST', {'Content-Type': 'application/json'})[0], 409)
        self.assertEqual(before, self.request('/api/jobs/' + job['id'] + '/extraction.json')[1])
        bad = copy.deepcopy(draft)
        bad['fieldReviews']['razon_social']['evidence']['sha256_texto_fuente'] = '0' * 64
        with self.assertRaises(ValueError):
            validar_revision(doc, bad)

    def test_reinicio_conserva_trabajo_interrumpido_como_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            store.put({'id': 'a' * 24, 'status': 'running'})
            reopened = Store(tmp)
            self.assertEqual(reopened.get('a' * 24)['status'], 'error')


if __name__ == '__main__':
    unittest.main(verbosity=2)
