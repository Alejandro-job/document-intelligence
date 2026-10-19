"""Inicia el prototipo de revisión y procesamiento dentro de Colab.

Ejecutar con %run -i para reutilizar un Qwen compatible que ya esté en memoria.
El modelo no se carga al iniciar la interfaz ni se entrena automáticamente.
"""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import threading
import time
import zipfile

PAQUETE_ESPERADO = None  # La copia de inicio en Drive fija el hash del ZIP entregado.


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verificar_manifiesto(root):
    root = Path(root)
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    for name, digest in manifest['files'].items():
        p = (root / name).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file() or sha(p.read_bytes()) != digest:
            raise ValueError('El archivo del paquete no coincide con su manifiesto: ' + name)
    return manifest


def preparar_paquete(archivo, destino, esperado=None):
    archivo, destino = Path(archivo), Path(destino)
    huella = sha(archivo.read_bytes())
    if esperado and huella != esperado:
        raise ValueError('El ZIP cambió respecto al paquete de entrega. Se conserva sin ejecutarlo.')
    root = destino / ('citi_app_' + huella[:16])
    with zipfile.ZipFile(archivo) as z:
        if len(z.infolist()) > 5000 or sum(i.file_size for i in z.infolist()) > 150 * 1024 * 1024:
            raise ValueError('El ZIP supera el tamaño previsto para este paquete')
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        if len(set(names)) != len(names):
            raise ValueError('El ZIP contiene nombres duplicados')
        manifest = json.loads(z.read('MANIFEST.json'))
        if set(names) != set(manifest['files']) | {'MANIFEST.json'}:
            raise ValueError('El ZIP tiene archivos sin verificar por el manifiesto')
        for i in z.infolist():
            p = PurePosixPath(i.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in i.filename or (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('El ZIP contiene una ruta no permitida')
        z.extractall(root)
    verificar_manifiesto(root)
    return root, huella


def dependencias_lectura():
    faltan = {'fitz': 'pymupdf>=1.26,<2', 'PIL': 'Pillow>=10,<13'}
    paquetes = [p for m, p in faltan.items() if importlib.util.find_spec(m) is None]
    if paquetes:
        print('Preparando lector PDF e imágenes…', flush=True)
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', *paquetes], check=True)
    # No se instala torch/transformers al abrir la web.
    if not __import__('shutil').which('tesseract'):
        idiomas = ''
    else:
        idiomas = subprocess.run(['tesseract', '--list-langs'], text=True, capture_output=True, timeout=20).stdout
    if 'spa' not in idiomas.splitlines():
        print('Preparando Tesseract español para los PDFs escaneados…', flush=True)
        subprocess.run(['apt-get', 'update', '-qq'], check=True, timeout=180)
        subprocess.run(['apt-get', 'install', '-y', '-qq', '--no-install-recommends',
                        'tesseract-ocr', 'tesseract-ocr-spa'], check=True, timeout=180)


def iniciar(espacio):
    from google.colab import output
    ruta_script = Path(__file__).resolve()
    proyecto = ruta_script.parents[1]
    if (proyecto / 'app/server.py').is_file() and (proyecto / 'MANIFEST.json').is_file():
        root = proyecto
        verificar_manifiesto(root)
        huella = sha((root / 'MANIFEST.json').read_bytes())
    else:
        archivo = ruta_script.with_name('DOCUMENTOS_ENTREGA.zip')
        if not archivo.is_file():
            archivo = Path('/content/drive/MyDrive/CITI_CONTINUIDAD/DOCUMENTOS_ENTREGA.zip')
        if not archivo.is_file():
            raise FileNotFoundError('Falta DOCUMENTOS_ENTREGA.zip junto al script de inicio. Conserva ambos en la misma carpeta.')
        root, huella = preparar_paquete(archivo, '/content', PAQUETE_ESPERADO)
    anterior = espacio.get('_CITI_APP_STATE')
    if anterior and anterior['thread'].is_alive() and anterior['huella'] == huella:
        print('Aplicación ya iniciada; se reutiliza el servidor y no se procesan documentos.', flush=True)
        output.serve_kernel_port_as_iframe(anterior['port'], height=1000)
        return anterior
    if anterior and anterior['thread'].is_alive():
        if any(j['status'] in ('running', 'queued') for j in anterior['app'].store.list()):
            raise RuntimeError('Hay un trabajo activo. Termina ese trabajo antes de cambiar la versión de la aplicación.')
        anterior['server'].shutdown(); anterior['server'].server_close(); anterior['app'].close()
    dependencias_lectura()
    # Se cargan los módulos del paquete entregado. Se conservan los objetos de
    # modelos y las revisiones del usuario; no se reinicia el kernel.
    nombres = {p.stem for p in (root / 'core').glob('*.py')} | {'pipeline', 'storage', 'server'}
    for n in nombres:
        sys.modules.pop(n, None)
    sys.path.insert(0, str(root / 'app'))
    importlib.invalidate_caches()
    import server as servidor
    for n in ['modelo_qwen', 'tokenizer_qwen', 'tokenizador_qwen', 'modelo_ia', 'tokenizer_ia']:
        if espacio.get(n) is not None:
            servidor.pipeline._MODELO[n] = espacio[n]
    # Un kernel cerrado pierde /content. Exportar el ZIP de revisión conserva
    # datos y evidencias; el script no copia documentos a servicios de terceros.
    app = servidor.Application('/content/citi_app_runtime')
    from http.server import ThreadingHTTPServer
    http = ThreadingHTTPServer(('127.0.0.1', 0), servidor.handler_for(app))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    estado = {'app': app, 'server': http, 'thread': thread, 'port': http.server_port,
              'huella': huella, 'root': str(root)}
    espacio['_CITI_APP_STATE'] = estado
    print('APLICACIÓN LISTA · lectura, contexto, ocho campos y revisión', flush=True)
    print('Motor inicial: reglas. Qwen es opcional y sólo se consulta si lo seleccionas.', flush=True)
    print('Los resultados automáticos conservan su estado de propuestas.', flush=True)
    print('No hay OCR, inferencia ni entrenamiento nuevos por abrir esta interfaz.', flush=True)
    output.serve_kernel_port_as_iframe(http.server_port, height=1000)
    return estado


if __name__ == '__main__':
    iniciar(globals())
