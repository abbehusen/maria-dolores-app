"""Restauração preparada na interface e aplicada antes de abrir o banco."""
import sqlite3
from contextlib import closing
import tempfile
import os
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from .db import Database

MAX_BACKUP_BYTES = 100 * 1024 * 1024


def validate_backup(path):
    """Valida uma cópia, inclusive migrações, sem alterar o arquivo recebido."""
    with tempfile.TemporaryDirectory() as folder:
        candidate = Path(folder) / 'candidate.sqlite3'
        candidate.write_bytes(Path(path).read_bytes())
        if candidate.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError('O backup deve ter até 100 MB.')
        with closing(sqlite3.connect(candidate)) as conn:
            if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('O arquivo está corrompido.')
            version = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if not version or version[0] not in {'1', '2', '3', '4', '5', '6', '7', '8'}:
                raise ValueError('Versão de backup incompatível.')
            if conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchone():
                raise ValueError('O backup contém uma estrutura não reconhecida.')
        db = Database(candidate)
        reference = Database(Path(folder) / 'reference.sqlite3')
        with db.connect() as conn, reference.connect() as expected:
            def structure(c):
                return {(r[0], r[1]): r[2] for r in c.execute(
                    "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('table','view')")}
            if structure(conn) != structure(expected):
                raise ValueError('Este arquivo não tem a estrutura de um backup do Fe Abbehusen Flow.')
            if conn.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('O backup contém vínculos inválidos.')
        return candidate.read_bytes()


def stage_restore(db, raw):
    if len(raw) > MAX_BACKUP_BYTES:
        raise ValueError('O backup deve ter até 100 MB.')
    pending = db.path.with_suffix('.restore-pending')
    with tempfile.NamedTemporaryFile(dir=db.path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(raw)
    try:
        validated = validate_backup(temp)
        temp.write_bytes(validated)
        os.replace(temp, pending)
    finally:
        temp.unlink(missing_ok=True)


def apply_pending_restore(path):
    path = Path(path)
    pending = path.with_suffix('.restore-pending')
    if not pending.exists():
        return None
    validated = validate_backup(pending)
    saved = None
    if path.exists():
        saved = path.parent / 'backups' / f'antes-restauracao-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.sqlite3'
        saved.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(saved)) as target:
            source.backup(target)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(validated)
    try:
        with closing(sqlite3.connect(temp)) as source, closing(sqlite3.connect(path)) as target:
            source.backup(target)
        pending.unlink()
    finally:
        temp.unlink(missing_ok=True)
    return saved
