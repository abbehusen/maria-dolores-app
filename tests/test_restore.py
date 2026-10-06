import sqlite3
from pathlib import Path
import pytest
from flow.db import Database
from flow.backup_restore import stage_restore, apply_pending_restore
from flow.runtime import default_data_dir


def test_restore_preserves_previous_database(tmp_path):
    old = Database(tmp_path / 'active.sqlite3')
    incoming = Database(tmp_path / 'incoming.sqlite3')
    with old.transaction() as c:
        c.execute("INSERT INTO audit(action,entity,entity_id,detail) VALUES('old','test','1','old')")
    with incoming.transaction() as c:
        c.execute("INSERT INTO audit(action,entity,entity_id,detail) VALUES('new','test','1','new')")
    exported = incoming.backup(tmp_path / 'export.sqlite3')
    stage_restore(old, exported.read_bytes())
    assert old.rows('SELECT action FROM audit')[0]['action'] == 'old'
    saved = apply_pending_restore(old.path)
    assert old.rows('SELECT action FROM audit')[0]['action'] == 'new'
    with sqlite3.connect(saved) as c:
        assert c.execute('SELECT action FROM audit').fetchone()[0] == 'old'
    assert apply_pending_restore(old.path) is None


@pytest.mark.parametrize('raw', [b'not a database', b''])
def test_invalid_backup_keeps_current(tmp_path, raw):
    db = Database(tmp_path / 'active.sqlite3')
    with pytest.raises(Exception):
        stage_restore(db, raw)
    assert not db.path.with_suffix('.restore-pending').exists()
    assert db.rows("SELECT value FROM metadata WHERE key='schema_version'")[0]['value'] == '8'


def test_foreign_database_rejected(tmp_path):
    path = tmp_path / 'foreign.sqlite3'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE unrelated (id INTEGER)')
    db = Database(tmp_path / 'active.sqlite3')
    with pytest.raises(Exception):
        stage_restore(db, path.read_bytes())


def test_packaged_data_is_outside_bundle(monkeypatch, tmp_path):
    import sys
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert default_data_dir() == tmp_path / 'FeAbbehusenFlow' / 'data'


def test_restore_dialog_upload_and_confirmation(tmp_path, monkeypatch):
    import asyncio
    from nicegui import ui, app
    from nicegui.testing import user_simulation
    from nicegui.elements.upload_files import SmallFileUpload
    from flow.ui import register_pages
    from flow.service import Business
    shutdowns = []
    monkeypatch.setattr(app, 'shutdown', lambda: shutdowns.append(True))
    db = Database(tmp_path / 'active.sqlite3')
    incoming = Database(tmp_path / 'incoming.sqlite3')
    raw = incoming.backup(tmp_path / 'export.sqlite3').read_bytes()
    async def scenario():
        async with user_simulation() as user:
            register_pages(Business(db))
            await user.open('/relatorios')
            user.find(kind=ui.button, content='Restaurar backup').click()
            await user.should_see('Restaurar backup completo')
            user.find(kind=ui.button, content='Confirmar restauração e encerrar').click()
            assert not shutdowns
            upload = next(iter(user.find(kind=ui.upload).elements))
            with upload.client:
                await upload.handle_uploads([SmallFileUpload('backup.sqlite3', 'application/octet-stream', raw)])
            await user.should_see('Selecionado: backup.sqlite3')
            user.find(kind=ui.input, content='Digite RESTAURAR para confirmar').type('RESTAURAR')
            user.find(kind=ui.button, content='Confirmar restauração e encerrar').click()
            assert shutdowns == [True]
            assert db.path.with_suffix('.restore-pending').exists()
    asyncio.run(scenario())
