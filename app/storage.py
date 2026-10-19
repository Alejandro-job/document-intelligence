"""Persistencia local de trabajos y revisiones. No es un sistema multiusuario."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading


def ahora():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / 'jobs.sqlite3'
        self.lock = threading.Lock()
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(n INTEGER PRIMARY KEY, job_id TEXT NOT NULL, at TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL);
            ''')
            for row in db.execute('SELECT id,payload FROM jobs').fetchall():
                job = json.loads(row['payload'])
                if job['status'] in ('queued', 'running'):
                    job.update(status='error', stage='Ejecución interrumpida', updated_at=ahora(),
                               error='El servidor se cerró antes de terminar. Puedes reintentar explícitamente.')
                    db.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(job), job['id']))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM jobs ORDER BY rowid DESC LIMIT 30').fetchall()
        return [json.loads(r[0]) for r in rows]

    def put(self, job):
        with self.connect() as db:
            db.execute('INSERT INTO jobs(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (job['id'], json.dumps(job, ensure_ascii=False)))

    def update(self, job_id, **values):
        with self.lock:
            job = self.get(job_id)
            job.update(**values, updated_at=ahora())
            self.put(job)
        return job

    def review(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT revision,payload FROM reviews WHERE id=?', (job_id,)).fetchone()
        return {'revision': row[0], 'draft': json.loads(row[1])} if row else {'revision': 0, 'draft': None}

    def save_review(self, job_id, expected, draft):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT revision FROM reviews WHERE id=?', (job_id,)).fetchone()
            actual = row[0] if row else 0
            if actual != expected:
                raise ValueError('Otra revisión cambió el servidor. Recupera la versión más reciente.')
            nuevo = actual + 1
            payload = json.dumps(draft, ensure_ascii=False)
            db.execute('INSERT INTO reviews(id,revision,payload) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',
                       (job_id, nuevo, payload))
            db.execute('INSERT INTO events(job_id,at,action,payload) VALUES(?,?,?,?)',
                       (job_id, ahora(), 'revision_explicita', payload))
        return {'revision': nuevo, 'draft': draft}
