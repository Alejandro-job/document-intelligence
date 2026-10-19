import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('citi_launcher_under_test', ROOT / 'scripts/iniciar_colab.py')
launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def archive(self, path, entries):
        manifest = {'files': {k: hashlib.sha256(v).hexdigest() for k, v in entries.items()}}
        with zipfile.ZipFile(path, 'w') as z:
            for name, data in entries.items():
                z.writestr(name, data)
            z.writestr('MANIFEST.json', json.dumps(manifest))

    def test_paquete_integro_con_hash_fijado(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'a.zip'; self.archive(p, {'app/server.py': b'contenido fixture'})
            root, digest = launcher.preparar_paquete(p, Path(tmp) / 'destino', hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual((root / 'app/server.py').read_bytes(), b'contenido fixture')

    def test_hash_del_zip_modificado_se_rechaza(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'a.zip'; self.archive(p, {'a.txt': b'fixture'})
            with self.assertRaises(ValueError):
                launcher.preparar_paquete(p, Path(tmp) / 'out', '0'*64)

    def test_ruta_fuera_del_paquete_no_se_extrae(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'a.zip'; self.archive(p, {'../fuera.txt': b'fixture'})
            with self.assertRaises(ValueError):
                launcher.preparar_paquete(p, Path(tmp) / 'out')
            self.assertFalse((Path(tmp) / 'fuera.txt').exists())

    def test_archivo_sin_huella_en_manifiesto_no_se_ejecuta(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'a.zip'; self.archive(p, {'a.txt': b'fixture'})
            with zipfile.ZipFile(p, 'a') as z:
                z.writestr('app/server.py', b'no verificado')
            with self.assertRaises(ValueError):
                launcher.preparar_paquete(p, Path(tmp) / 'out')


if __name__ == '__main__':
    unittest.main()
