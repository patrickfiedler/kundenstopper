#!/usr/bin/env python3
"""
Apply pending database migrations.

Tracks applied migrations in the schema_migrations table.
Each migration is a Python file in migrations/ with a run() function.

On first run against an existing installation (upgrading from before
migration tracking was introduced), all current migrations are marked
as baseline without executing them, since init_db() already created
the current schema.
"""
import sqlite3
import os
import importlib.util
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'kundenstopper.db')
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), 'migrations')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def setup_tracking(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    ''')
    conn.commit()


def get_applied(conn):
    return {row['id'] for row in conn.execute('SELECT id FROM schema_migrations ORDER BY id')}


def mark_applied(conn, migration_id):
    conn.execute(
        'INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)',
        (migration_id, datetime.now().isoformat())
    )
    conn.commit()


def db_is_initialized(conn):
    """Return True if init_db() has already run (base tables exist)."""
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='displays'"
    ).fetchone() is not None


def list_migration_files():
    if not os.path.isdir(MIGRATIONS_DIR):
        return []
    return sorted(
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith('.py') and not f.startswith('_')
    )


def run_migration(path):
    spec = importlib.util.spec_from_file_location('migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, 'run'):
        module.run()


def main():
    if not os.path.exists(DB_PATH):
        print('Database not found — app has not started yet. Skipping migrations.')
        return

    conn = get_db()
    setup_tracking(conn)
    applied = get_applied(conn)
    files = list_migration_files()

    if not files:
        print('No migration files found.')
        conn.close()
        return

    # First run on an existing installation that predates migration tracking:
    # mark everything as baseline so we don't re-apply already-handled changes.
    if not applied and db_is_initialized(conn):
        print('Existing installation detected — recording migration baseline.')
        for fname in files:
            mid = fname[:-3]
            mark_applied(conn, mid)
            print(f'  baseline: {mid}')
        conn.close()
        print('Done. Future migrations will be tracked from here.')
        return

    pending = [f for f in files if f[:-3] not in applied]

    if not pending:
        print('Database is up to date.')
        conn.close()
        return

    print(f'{len(pending)} pending migration(s):')
    for fname in pending:
        mid = fname[:-3]
        path = os.path.join(MIGRATIONS_DIR, fname)
        print(f'  Applying {mid} ... ', end='', flush=True)
        try:
            run_migration(path)
            mark_applied(conn, mid)
            print('done')
        except Exception as e:
            print(f'FAILED: {e}')
            conn.close()
            raise SystemExit(f'Migration {mid} failed. Fix the issue and re-run.')

    conn.close()
    print(f'\n{len(pending)} migration(s) applied successfully.')


if __name__ == '__main__':
    main()
