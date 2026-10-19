"""Genera integridad para una copia revisada de este repositorio o un ZIP."""
import hashlib
import json
from pathlib import Path
from verificar_publicacion import ROOT, project_files, validate_files


def main():
    files = [p for p in project_files() if p.name != 'MANIFEST.json']
    errors = validate_files(files)
    if errors:
        raise ValueError('\n'.join(errors))
    manifest = {'schema_version': 'documental_repositorio_1.0.0',
                'produccion_validada': False,
                'files': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in files}}
    (ROOT / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    print('Manifiesto generado:', len(files), 'archivos revisados para distribución.')


if __name__ == '__main__':
    main()
