import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError
from tests.helpers import fixture_xml

@pytest.fixture
def setup(tmp_path):
    b=Business(Database(tmp_path/'loc.sqlite3'))
    p=b.create_product({'sku':'A','name':'Anel','selling_price':'500'},quantity=5,unit_cost='200',when='2026-01-01')
    loc=b.save_location('SU MISURA')
    return b,p,loc

def qty(b,p,loc,lot=0):
    return sum(r['quantity'] for r in b.location_stock(loc) if r['product_id']==p and r['lot_id']==lot)

def transfer(b,p,source,target,q=2,key='t',when='2026-01-02',lot=0):
    b.transfer_stock([dict(product_id=p,lot_id=lot,quantity=q)],source,target,when=when,reason='Teste',key=key)

def sale(b,p,loc,when='2026-01-03',lot=0):
    return b.create_sale([dict(product_id=p,lot_id=lot,quantity=1,unit_price='500')],dict(location_id=loc,sale_date=when,method='Pix'),key='sale')

def test_distribution_transfer_preserves_cost_and_idempotency(setup):
    b,p,loc=setup
    before=b.product(p)
    assert qty(b,p,1)==5
    transfer(b,p,1,loc)
    transfer(b,p,1,loc)
    assert qty(b,p,loc)==2 and qty(b,p,1)==3
    assert b.product(p)==before
    transfer(b,p,loc,2,1,key='return')
    assert qty(b,p,loc)==1 and qty(b,p,2)==1
    assert not b.db.rows('SELECT * FROM sales')
    assert not b.db.rows('SELECT * FROM expenses')

def test_sale_cancel_and_correct_track_locations(setup):
    b,p,loc=setup
    transfer(b,p,1,loc)
    sid=sale(b,p,loc)
    assert qty(b,p,loc)==1 and qty(b,p,1)==3
    b.cancel_sale(sid,'Devolvido',when='2026-01-04')
    assert qty(b,p,loc)==2
    b.correct_sale(sid,reason='Remover teste')
    assert qty(b,p,loc)==2 and b.product(p)['stock']==5

def test_no_negative_and_atomic_batch(setup):
    b,p,loc=setup
    with pytest.raises(RuleError): sale(b,p,loc)
    assert not b.db.rows('SELECT * FROM sales')
    with pytest.raises(RuleError):
        b.transfer_stock([dict(product_id=p,quantity=3),dict(product_id=p,quantity=3)],1,loc,when='2026-01-02',reason='Lote',key='bad')
    assert qty(b,p,1)==5 and not b.location_history()
    transfer(b,p,1,loc,5)
    with pytest.raises(RuleError): sale(b,p,1)
    with pytest.raises(RuleError): b.save_location('SU MISURA',loc,False)
    with pytest.raises(RuleError): b.adjust_stock(p,0,'Incorreto',when='2026-01-05')
    assert b.product(p)['stock']==5

def test_backdated_sale_cannot_precede_transfer(setup):
    b,p,loc=setup
    transfer(b,p,1,loc,when='2026-01-10')
    with pytest.raises(RuleError): sale(b,p,loc,when='2026-01-05')
    assert b.product(p)['stock']==5

def test_consigned_stock_stays_separate(setup):
    b,p,loc=setup
    b.import_invoice(fixture_xml(),{'1':'estoque','2':'ignorar'},ownership='consigned',location_id=loc)
    lot=b.consignment_lots()[0];pid=lot['product_id']
    assert qty(b,pid,loc,lot['id'])==2
    sid=sale(b,pid,loc,lot=lot['id'])
    assert qty(b,pid,loc,lot['id'])==1
    b.cancel_sale(sid,'Voltou',when='2026-01-04')
    assert qty(b,pid,loc,lot['id'])==2
    transfer(b,pid,loc,1,2,key='return-matriz',lot=lot['id'],when='2026-01-04')
    b.return_consignment(lot['id'],2,'Retorno',when='2026-01-05')
    assert qty(b,pid,loc,lot['id'])==0 and qty(b,pid,1,lot['id'])==0

def test_initial_receipt_and_personal_withdrawal(setup):
    b,p,loc=setup
    pid=b.create_product(dict(sku='B',name='Brinco',location_id=loc),quantity=2,unit_cost='100',when='2026-01-01')
    assert qty(b,pid,loc)==2
    b.create_sale([dict(product_id=pid,quantity=1,unit_price='0')],dict(operation='personal',location_id=loc,customer='Nanda',sale_date='2026-01-03'),key='personal')
    assert qty(b,pid,loc)==1
    assert b.db.rows('SELECT revenue_cents FROM sales')[0]['revenue_cents']==0


def test_local_count_changes_only_selected_location(setup):
    from flow.money import today
    b,p,loc=setup
    transfer(b,p,1,loc)
    b.count_location(p,loc,1,'Faltou uma peça',key='count')
    assert qty(b,p,loc)==1 and qty(b,p,1)==3 and b.product(p)['stock']==4
    b.count_location(p,loc,1,'Reenvio',key='count')
    b.count_location(p,loc,2,'Peça encontrada',unit_cost='200',key='found')
    assert qty(b,p,loc)==2 and b.product(p)['stock']==5


def test_restore_preserves_locations_and_transfers(setup,tmp_path):
    from flow.backup_restore import stage_restore,apply_pending_restore
    b,p,loc=setup
    transfer(b,p,1,loc)
    snapshot=b.db.backup(tmp_path/'saved.sqlite3')
    dest=Database(tmp_path/'dest.sqlite3')
    stage_restore(dest,snapshot.read_bytes());apply_pending_restore(dest.path)
    restored=Business(Database(dest.path))
    assert qty(restored,p,loc)==2 and qty(restored,p,1)==3


def test_migrate_actual_v5_archive_with_existing_sale(tmp_path):
    import zipfile,types
    from pathlib import Path
    archive=Path(__file__).resolve().parents[3]/'Fe_Abbehusen_Flow_Python_v0.5.3.zip'
    if not archive.exists(): pytest.skip('Original v5 distribution unavailable')
    with zipfile.ZipFile(archive) as z: source=z.read('fe_flow/flow/db.py').decode()
    module=types.ModuleType('flow.old_db');module.__package__='flow'
    exec(compile(source,'old_db.py','exec'),module.__dict__)
    path=tmp_path/'legacy.sqlite3';old=module.Database(path)
    with old.transaction() as c:
        c.execute("INSERT INTO products(id,supplier,sku,name,selling_cents) VALUES(1,'Manual','OLD','Peça antiga',50000)")
        c.execute("INSERT INTO movements(product_id,occurred_on,quantity,cost_cents,kind,source,reason) VALUES(1,'2026-01-01',2,40000,'OPENING','old','Inicial')")
        c.execute("INSERT INTO sales(request_key,sale_date,method,subtotal_cents,discount_cents,revenue_cents,cost_cents,fee_cents,tax_cents,seller_cents,store_cents,net_cents) VALUES('old','2026-01-02','Pix',50000,0,50000,20000,0,0,0,0,30000)")
    b=Business(Database(path))
    assert qty(b,1,1)==2
    assert b.db.rows('SELECT location_id FROM sales')[0]['location_id']==1
    assert b.db.migration_backup.exists()


def test_same_product_sale_from_multiple_locations_correct_cancel(setup):
    b,p,loc=setup
    transfer(b,p,1,loc,2)
    transfer(b,p,1,2,2,key='nanda')
    items=[dict(product_id=p,quantity=1,unit_price='500',location_id=loc),dict(product_id=p,quantity=2,unit_price='500',location_id=2)]
    data=dict(sale_date='2026-01-03',method='Pix')
    sid=b.create_sale(items,data,key='multi')
    assert qty(b,p,loc)==1 and qty(b,p,2)==0 and qty(b,p,1)==1
    row=b.db.rows('SELECT * FROM sales')[0]
    assert row['revenue_cents']==150000 and row['cost_cents']==60000
    assert len(b.sale_snapshot(sid)['sale_locations'])==2
    items[1]['quantity']=1
    b.correct_sale(sid,items=items,data=data,reason='Uma peça a menos')
    assert qty(b,p,loc)==1 and qty(b,p,2)==1
    b.cancel_sale(sid,'Voltou',when='2026-01-04')
    assert qty(b,p,loc)==2 and qty(b,p,2)==2


def test_v6_single_location_sale_migrates_without_changing_balance(setup):
    import sqlite3
    b,p,loc=setup
    transfer(b,p,1,loc,2)
    sid=sale(b,p,loc)
    before=b.location_stock()
    # v7 adds only sale_locations. Remove it to recover the real v6 shape.
    with sqlite3.connect(b.db.path) as c:
        c.execute('DROP VIEW active_consignment_moves')
        c.execute('DROP TABLE stock_losses')
        c.execute('CREATE VIEW active_consignment_moves AS SELECT m.* FROM consignment_moves m WHERE NOT EXISTS (SELECT 1 FROM consignment_return_cancellations x WHERE x.movement_id=m.id)')
        c.execute('DROP TABLE sale_locations')
        c.execute("UPDATE metadata SET value='6' WHERE key='schema_version'")
    upgraded=Business(Database(b.db.path))
    assert upgraded.location_stock()==before
    a=upgraded.sale_snapshot(sid)['sale_locations']
    assert len(a)==1 and a[0]['location_id']==loc and a[0]['quantity']==1
