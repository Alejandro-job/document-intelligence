"""Verifica citas de resultados contra la lectura usada, sin evaluar su rol."""
import argparse
import hashlib
import json
from pathlib import Path


def verificar(lectura, artefactos):
    fuentes = {p['fuente_id']: p for p in lectura['paginas']}
    cuenta = 0

    def visitar(x):
        nonlocal cuenta
        if isinstance(x, dict):
            if {'fuente_id', 'rango_caracteres', 'sha256_texto_fuente'} <= x.keys() and ('texto' in x or 'cita_literal' in x):
                p = fuentes[x['fuente_id']]
                a, b = x['rango_caracteres']
                literal = x.get('texto', x.get('cita_literal'))
                if not 0 <= a < b <= len(p['texto']) or p['texto'][a:b] != literal:
                    raise ValueError('La cita no corresponde a su fuente/rango')
                if hashlib.sha256(p['texto'].encode()).hexdigest() != x['sha256_texto_fuente']:
                    raise ValueError('La huella de la fuente cambió')
                cuenta += 1
            for v in x.values(): visitar(v)
        elif isinstance(x, list):
            for v in x: visitar(v)
    for a in artefactos: visitar(a)
    return cuenta


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--lectura', required=True, type=Path)
    p.add_argument('artefactos', nargs='+', type=Path); a = p.parse_args()
    n = verificar(json.loads(a.lectura.read_text()), [json.loads(f.read_text()) for f in a.artefactos])
    print(n, 'referencias literales verificadas; no mide exactitud semántica')
