"""Copy an existing Flow SQLite database into Supabase/PostgreSQL.

Usage (PowerShell):
  $env:DATABASE_URL='postgresql://...'
  python scripts/migrate_sqlite_to_postgres.py data/flow.sqlite3

The destination must be empty. Use --force only when you deliberately want to
wipe the Flow tables in the destination before importing.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow.postgres import PostgresDatabase, TABLES, ID_TABLES


def columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]


def main():
    parser = argparse.ArgumentParser(description='Migra Flow SQLite v8 para PostgreSQL/Supabase')
    parser.add_argument('sqlite_path', type=Path)
    parser.add_argument('--force', action='store_true', help='APAGA as tabelas Flow do destino antes de importar')
    args = parser.parse_args()

    url = os.environ.get('DATABASE_URL')
    if not url:
        raise SystemExit('Defina DATABASE_URL com a conexão PostgreSQL do Supabase.')
    source_path = args.sqlite_path.resolve()
    if not source_path.exists():
        raise SystemExit(f'Arquivo não encontrado: {source_path}')

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    version = source.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
    if not version or version[0] != '8':
        raise SystemExit(f'O SQLite precisa estar no schema 8; encontrado: {version[0] if version else "sem metadata"}')

    db = PostgresDatabase(url, local_path=source_path)
    with db.connect() as dest:
        counts = {t: dest.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABLES if t != 'metadata'}
        bootstrap_locations = dest.execute("SELECT id,name FROM locations ORDER BY id").fetchall()
        bootstrap_only = (sum(v for k,v in counts.items() if k != 'locations') == 0
                          and [(r['id'], r['name']) for r in bootstrap_locations] == [(1,'Local a definir'),(2,'Com Nanda')])
        occupied = sum(counts.values())
        if occupied and not bootstrap_only and not args.force:
            raise SystemExit(f'O PostgreSQL já contém {occupied} registros. Abortei. Use --force somente se quiser substituir tudo.')
        if args.force:
            # CASCADE handles views/FKs; metadata is recreated below.
            dest.execute('TRUNCATE TABLE ' + ','.join(TABLES) + ' RESTART IDENTITY CASCADE')
            dest.execute("INSERT INTO metadata(key,value) VALUES('schema_version','8') ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value")
            dest.commit()
        elif bootstrap_only:
            dest.execute('DELETE FROM locations')
            dest.commit()

    # Dependency-safe order is TABLES.
    with db.transaction() as dest:
        for table in TABLES:
            if table == 'metadata':
                continue
            cols = columns(source, table)
            rows = source.execute(f'SELECT * FROM {table}').fetchall()
            if not rows:
                print(f'{table}: 0')
                continue
            placeholders = ','.join('?' for _ in cols)
            sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
            for row in rows:
                dest.execute(sql, tuple(row[c] for c in cols))
            print(f'{table}: {len(rows)}')

    db.reset_sequences()

    mismatches = []
    with db.connect() as dest:
        for table in TABLES:
            src = source.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            dst = dest.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            if src != dst:
                mismatches.append((table, src, dst))
    source.close()
    if mismatches:
        raise SystemExit('Contagens divergentes: ' + repr(mismatches))
    print('Migração concluída e contagens validadas.')


if __name__ == '__main__':
    main()
