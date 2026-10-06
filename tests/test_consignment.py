import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError
from flow import reports
from .helpers import fixture_xml


@pytest.fixture
def biz(tmp_path):
    return Business(Database(tmp_path / 'flow.sqlite3'))


def receive(biz, number=1, ownership='consigned'):
    biz.import_invoice(fixture_xml(number=number), {'1': 'estoque', '2': 'ignorar'}, ownership=ownership)
    return biz.products()[0]['id']


def sell(biz, pid, lot=1, qty=1, key='sale', **data):
    return biz.create_sale([{'product_id': pid, 'lot_id': lot, 'quantity': qty, 'unit_price': '210'}],
                           {'sale_date': '2025-02-01', 'method': 'Pix', **data}, key=key)


def test_consignment_receipt_does_not_create_owned_stock_or_payable(biz):
    pid = receive(biz)
    assert biz.product(pid)['stock'] == 0
    assert not biz.db.rows('SELECT * FROM expenses')
    lot = biz.consignment_lots()[0]
    assert lot['stock'] == 2 and lot['unit_cost_cents'] == 9500
    values = reports.summary(biz.db, '2025-01-01', '2025-12-31')
    assert values['stock_cents'] == 0 and values['consigned_stock_cents'] == 19000
    assert values['payable_cents'] == values['cash_out_cents'] == values['net_cents'] == 0
    assert biz.db.rows('SELECT xml FROM invoices')[0]['xml'] == fixture_xml(number=1)
    with pytest.raises(RuleError):
        receive(biz)


def test_discount_does_not_reduce_repasse_and_payment_does_not_double_cost(biz):
    pid = receive(biz)
    sid = sell(biz, pid, paid_on='2025-02-01', discount='10', fee='5')
    exp = biz.db.rows('SELECT * FROM expenses')[0]
    assert exp['amount_cents'] == 9500 and exp['affects_result'] == 0 and exp['sale_id'] == sid
    feb = reports.summary(biz.db, '2025-02-01', '2025-02-28')
    assert feb['revenue_cents'] == 20000 and feb['net_cents'] == 10000
    assert feb['cash_net_cents'] == 19500 and feb['consignment_payable_cents'] == 9500
    biz.pay_expenses([exp['id']], '2025-03-01')
    march = reports.summary(biz.db, '2025-03-01', '2025-03-31')
    assert march['net_cents'] == 0 and march['cash_net_cents'] == -9500
    assert march['consignment_paid_cents'] == 9500 and march['consignment_payable_cents'] == 0
    assert reports.summary(biz.db, '2025-02-01', '2025-02-28')['consignment_payable_cents'] == 9500


def test_mixed_sale_same_product_owned_and_two_lots(biz):
    pid = receive(biz)
    receive(biz, number=2, ownership='own')
    receive(biz, number=3)
    items = [{'product_id': pid, 'lot_id': lot, 'quantity': 1, 'unit_price': '200'} for lot in [None, 1, 2]]
    sid = biz.create_sale(items, {'sale_date': '2025-02-01', 'method': 'Pix'}, key='mixed')
    assert biz.product(pid)['stock'] == 1
    assert [l['stock'] for l in biz.consignment_lots()] == [1,1]
    row = biz.db.rows('SELECT * FROM sales WHERE id=?', (sid,))[0]
    assert row['cost_cents'] == 28500 and row['net_cents'] == 31500
    receive(biz, number=4, ownership='own')
    assert biz.db.rows('SELECT cost_cents FROM sales WHERE id=?', (sid,))[0]['cost_cents'] == 28500


def test_cancel_unpaid_repasse_restores_lot_and_voids_payable(biz):
    pid = receive(biz)
    sid = sell(biz, pid)
    biz.cancel_sale(sid, 'Cliente desistiu', when='2025-02-02')
    assert biz.consignment_lots()[0]['stock'] == 2
    assert biz.db.rows('SELECT cancelled_on FROM expenses')[0]['cancelled_on'] == '2025-02-02'
    assert reports.summary(biz.db, '2025-02-01', '2025-02-28')['net_cents'] == 0
    biz.delete_cancelled_test_sale(sid, confirmation=f'EXCLUIR TESTE #{sid}', reason='Teste')
    assert not biz.db.rows('SELECT * FROM consignment_sale_items')
    assert not biz.db.rows('SELECT * FROM consignment_moves')
    assert biz.consignment_lots()[0]['stock'] == 2


def test_paid_repasse_blocks_cancellation_without_partial_changes(biz):
    pid = receive(biz)
    sid = sell(biz, pid)
    biz.pay_expense(biz.db.rows('SELECT id FROM expenses')[0]['id'], '2025-02-02')
    with pytest.raises(RuleError, match='repasse'):
        biz.cancel_sale(sid, 'Desistência', when='2025-02-03')
    assert not biz.db.rows('SELECT cancelled_on FROM sales')[0]['cancelled_on']
    assert biz.consignment_lots()[0]['stock'] == 1


def test_return_and_backdated_sale_cannot_overdraw_lot(biz):
    pid = receive(biz)
    biz.return_consignment(1, 1, 'Fim da remessa', when='2025-03-01', key='return')
    biz.return_consignment(1, 1, 'Fim da remessa', when='2025-03-01', key='return')
    assert biz.consignment_lots()[0]['returned'] == 1
    with pytest.raises(RuleError):
        sell(biz, pid, qty=2, historical=True)
    assert not biz.db.rows('SELECT * FROM sales') and not biz.db.rows('SELECT * FROM expenses')
    sell(biz, pid)
    assert biz.consignment_lots()[0]['stock'] == 0
    assert biz.consignment_lots()[0]['sold'] == 1
    with pytest.raises(RuleError):
        biz.return_consignment(1,1,'Extra',when='2025-03-01')
    assert reports.summary(biz.db, '2025-03-01', '2025-03-31')['net_cents'] == 0


def test_before_receipt_and_invalid_import_rejected(biz):
    pid = receive(biz)
    with pytest.raises(RuleError):
        sell(biz, pid, sale_date='2024-01-01', historical=True)
    with pytest.raises(RuleError):
        biz.import_invoice(fixture_xml(number=2), {'1': 'estoque', '2': 'despesa'}, ownership='consigned')
    with pytest.raises(RuleError):
        biz.import_invoice(fixture_xml(number=2), {'1': 'estoque', '2': 'ignorar'}, ownership='consigned', paid_on='2025-01-20')
    assert len(biz.db.rows('SELECT * FROM invoices')) == 1
    payload = json.loads(reports.export_json(biz.db))
    assert payload['tables']['consignment_lots'][0]['quantity'] == 2


def test_concurrent_sales_last_consigned_piece(biz):
    pid = receive(biz)
    sell(biz, pid, key='first')
    barrier = Barrier(2)
    def attempt(key):
        barrier.wait()
        try:
            return sell(biz, pid, key=key)
        except RuleError:
            return None
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, ['a','b']))
    assert sum(r is not None for r in results) == 1
    assert biz.consignment_lots()[0]['stock'] == 0
    assert len(biz.db.rows('SELECT * FROM expenses')) == 2


def test_upgrade_v2_keeps_existing_owned_data_and_backup(tmp_path):
    from pathlib import Path
    path = tmp_path / 'v2.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.executescript(Path(__file__).with_name('fixtures').joinpath('schema_v2.sql').read_text())
        conn.execute("INSERT INTO products(id,supplier,sku,name,selling_cents) VALUES (1,'Manual','OLD','Peça antiga',23000)")
        conn.execute("INSERT INTO movements(product_id,occurred_on,quantity,cost_cents,kind,source,reason) VALUES (1,'2025-01-01',5,50000,'OPENING','old','Inicial')")
        conn.execute("INSERT INTO expenses(request_key,occurred_on,due_on,paid_on,category,description,amount_cents,affects_result) VALUES ('old','2025-01-01','2025-01-01','2025-01-01','Marketing','Antiga',1000,1)")
    db = Database(path)
    assert db.migration_backup.exists()
    with sqlite3.connect(db.migration_backup) as original:
        assert original.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == '2'
    assert Business(db).product(1)['stock'] == 5
    assert db.rows('SELECT paid_on FROM expenses')[0]['paid_on'] == '2025-01-01'
    assert not Business(db).consignment_lots()
    assert Database(path).migration_backup is None


def test_owned_inventory_hides_only_exclusively_consigned_products(biz):
    pid = receive(biz)
    assert not biz.owned_products()
    assert len(biz.products()) == 1  # Continua disponível no formulário de venda.
    receive(biz, number=2, ownership='own')
    assert biz.owned_products()[0]['stock'] == 2
    sell(biz, pid, lot=None, qty=2)
    assert biz.owned_products()[0]['stock'] == 0  # Próprio esgotado não desaparece.
    assert biz.consignment_lots()[0]['stock'] == 2


def test_cancel_return_restores_stock_once_and_preserves_history(biz):
    pid = receive(biz)
    biz.return_consignment(1, 2, 'Engano', when='2025-02-01')
    row = biz.db.rows("SELECT * FROM consignment_moves WHERE kind='RETURN'")[0]
    assert biz.consignment_lots()[0]['stock'] == 0
    biz.cancel_consignment_return(row['id'], 'Peças ainda estão comigo')
    biz.cancel_consignment_return(row['id'], 'Clique repetido')
    assert biz.consignment_lots()[0]['stock'] == 2
    assert biz.consignment_lots()[0]['returned'] == 0
    assert len(biz.db.rows('SELECT * FROM consignment_return_cancellations')) == 1
    assert biz.db.rows('SELECT * FROM consignment_moves')[0]['quantity'] == -2
    assert reports.summary(biz.db, '2025-02-01', '2025-02-28')['consigned_stock'] == 2
    assert not biz.db.rows('SELECT * FROM expenses')
    sell(biz, pid, qty=2)
    assert biz.consignment_lots()[0]['stock'] == 0
    with pytest.raises(RuleError):
        biz.cancel_consignment_return(biz.db.rows("SELECT id FROM consignment_moves WHERE kind='SALE'")[0]['id'], 'Erro')


def test_upgrade_v3_preserves_returns_and_allows_correction(tmp_path):
    path = tmp_path / 'v3.sqlite3'
    biz = Business(Database(path))
    receive(biz)
    biz.return_consignment(1,1,'Devolução antiga',when='2025-02-01')
    with sqlite3.connect(path) as conn:
        # Construct an actual v3 shape, removing later additions too.
        conn.execute('DROP VIEW active_consignment_moves')
        conn.execute('DROP TABLE stock_losses')
        conn.execute('DROP TABLE sale_locations')
        conn.execute('DROP TABLE location_transfers')
        conn.execute('ALTER TABLE sales DROP COLUMN location_id')
        conn.execute('DROP TABLE locations')
        conn.execute('DROP TABLE commission_settlements')
        conn.execute('DROP TABLE channel_sellers')
        for col in ['operation','customer_id','channel_id','seller_id','channel_name','seller_name','credit_beneficiary_id','credit_cents']:
            conn.execute(f'ALTER TABLE sales DROP COLUMN {col}')
        conn.execute('ALTER TABLE expenses DROP COLUMN beneficiary_id')
        for col in ['cash_effect','method']:
            conn.execute(f'ALTER TABLE receivables DROP COLUMN {col}')
        for table in ['channels','customers','beneficiaries']:
            conn.execute(f'DROP TABLE {table}')
        conn.execute('DROP TABLE consignment_return_cancellations')
        conn.execute("UPDATE metadata SET value='3' WHERE key='schema_version'")
    updated = Database(path)
    assert updated.migration_backup.exists()
    with sqlite3.connect(updated.migration_backup) as conn:
        assert conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == '3'
    biz = Business(updated)
    assert biz.consignment_lots()[0]['stock'] == 1
    biz.cancel_consignment_return(1,'Registro errado')
    assert biz.consignment_lots()[0]['stock'] == 2
