"""Encrypted, expiring server-side sessions and owner-bound transfer batches."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from cryptography.fernet import Fernet

class Store:
    def __init__(self, path, key):
        self.path, self.cipher = str(path), Fernet(key)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, expires REAL, data BLOB);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT, expires REAL, state TEXT, data BLOB);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA secure_delete=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(sid):
        return hashlib.sha256(sid.encode()).hexdigest()

    def encrypt(self, data):
        return self.cipher.encrypt(json.dumps(data).encode())

    def decrypt(self, data):
        return json.loads(self.cipher.decrypt(data))

    def create_session(self, data, seconds):
        sid = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (self.digest(sid), time.time()+seconds, self.encrypt(data)))
        return sid

    def session(self, sid):
        if not sid:
            return None
        with self.connect() as db:
            row = db.execute('SELECT * FROM sessions WHERE id=? AND expires>?', (self.digest(sid), time.time())).fetchone()
        return self.decrypt(row['data']) if row else None

    def logout(self, sid):
        with self.connect() as db:
            db.execute('DELETE FROM jobs WHERE owner=?', (self.digest(sid),))
            db.execute('DELETE FROM sessions WHERE id=?', (self.digest(sid),))

    def create_job(self, sid):
        job = secrets.token_hex(12)
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)', (job, self.digest(sid), time.time()+3600, 'generating', self.encrypt({'items': []})))
        return job

    def save_job(self, job, data, state):
        with self.connect() as db:
            db.execute('UPDATE jobs SET data=?, state=? WHERE id=?', (self.encrypt(data), state, job))

    def job(self, job, sid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=? AND expires>?', (job, self.digest(sid), time.time())).fetchone()
        return ({'state': row['state'], **self.decrypt(row['data'])} if row else None)

    def claim(self, job, sid):
        with self.connect() as db:
            return db.execute("UPDATE jobs SET state='sharing' WHERE id=? AND owner=? AND state='ready' AND expires>?",
                              (job, self.digest(sid), time.time())).rowcount == 1

    def purge(self):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
            db.execute('DELETE FROM jobs WHERE expires<=? OR owner NOT IN (SELECT id FROM sessions)', (time.time(),))
