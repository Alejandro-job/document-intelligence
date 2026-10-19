"""Comprueba el material distribuido; no certifica anonimización de textos nuevos."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OMIT = {'.git', '__pycache__', '.venv', 'venv', 'runtime_data', 'MI_EJECUCION',
        'build', 'dist', 'node_modules', '.ipynb_checkpoints'}


def project_files(root=ROOT):
    return sorted(p for p in root.rglob('*') if p.is_file()
                  and not any(part in OMIT for part in p.relative_to(root).parts)
                  and p.suffix not in {'.pyc', '.zip', '.log', '.gz'})


def validate_files(files, root=ROOT):
    reference = json.loads((root / 'material_prueba/etiquetas_y_reglas_esperadas.json').read_text())
    distribution = json.loads((root / 'material_prueba/DISTRIBUCION.json').read_text())
    original = {d['archivo']: d['sha256'] for d in reference['documentos']}
    allowed = {'material_prueba/' + d['archivo']: d['sha256'] for d in distribution['documentos_distribuidos']}
    if len(allowed) != 3 or any(original.get(d['archivo']) != d['sha256'] for d in distribution['documentos_distribuidos']):
        return ['La distribución no coincide con las tres referencias sintéticas originales.']
    errors = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            errors.append(rel + ': enlace no permitido')
            continue
        if p.name.startswith('.env') or p.suffix.lower() in {'.key', '.pem', '.pt', '.pth', '.bin', '.safetensors', '.sqlite', '.sqlite3', '.db', '.pkl', '.joblib'}:
            errors.append(rel + ': archivo privado o pesos no distribuidos en esta edición')
        if any(part in {'uploads', 'datasets_externos', 'exports', 'resultados_reales'} for part in p.relative_to(root).parts):
            errors.append(rel + ': carpeta fuera del material distribuido')
        if p.suffix.lower() == '.pdf':
            if rel not in allowed or hashlib.sha256(p.read_bytes()).hexdigest() != allowed[rel]:
                errors.append(rel + ': PDF fuera de los sintéticos esperados')
        if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'} and not (rel.startswith('ui/data/demo_') and p.name.startswith('p')):
            errors.append(rel + ': imagen fuera de los ejemplos sintéticos')
    for rel, digest in allowed.items():
        p = root / rel
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            errors.append(rel + ': falta o no coincide con la referencia')
    return errors


def main():
    files = project_files()
    # En Git revisa también los archivos versionados que las exclusiones de
    # ejecución podrían haber ocultado al recorrer la carpeta local.
    try:
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT,
                                capture_output=True, check=True)
        files = sorted(set(files) | {ROOT / n for n in result.stdout.decode().split('\0') if n})
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    errors = validate_files(files)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Contenido comprobado: tres PDFs sintéticos; sin pesos ni archivos privados conocidos.')
    print('Los textos nuevos requieren revisión humana antes de publicarse.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
