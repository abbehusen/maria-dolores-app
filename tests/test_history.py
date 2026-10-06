from pathlib import Path
import json
import sqlite3
import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError
from flow import reports
from .helpers import fixture_xml
from .test_business import product, sale


@pytest.fixture
def biz(tmp_path):
    return Business(Database(tmp_path / 'flow.sqlite3'))


def purchase(biz, when, cost='200.00', number=1):
    raw = fixture_xml(number=number, date=when).replace(b'<vProd>200.00</vProd><vDesc>20.00</vDesc><vFrete>10.00</vFrete>',
                                                      f'<vProd>{cost}</vProd>'.encode())
    from decimal import Decimal
    raw = raw.replace(b'<vNF>210.00</vNF>', f'<vNF>{Decimal(cost) + 20:.2f}</vNF>'.encode())
    biz.import_invoice(raw, {'1': 'estoque', '2': 'ignorar'})
    return biz.products()[0]['id']


def record(biz, sid):
    return biz.db.rows('SELECT * FROM sales WHERE id=?', (sid,))[0]


def test_monthly_chart_respects_full_interval_and_partial_months(biz):
    pid = product(biz)
    sale(biz, pid, key='before', sale_date='2025-01-05')
    sale(biz, pid, key='inside', sale_date='2025-01-20')
    sale(biz, pid, key='after', sale_date='2025-12-25')
    rows = reports.monthly(biz.db, '2025-01-15', '2025-12-10')
    assert len(rows) == 12
    assert rows[0]['month'] == '2025-01' and rows[-1]['month'] == '2025-12'
    assert rows[0]['revenue_cents'] == 23000
    assert all(r['revenue_cents'] == 0 for r in rows[1:])
    totals = reports.summary(biz.db, '2025-01-15', '2025-12-10')
    for key in ('revenue_cents', 'net_cents'):
        assert sum(r[key] for r in rows) == totals[key]
    assert len(reports.monthly(biz.db, '2025-01-20', '2025-01-20')) == 1
    assert len(reports.monthly(biz.db, '2024-12-20', '2025-02-10')) == 3
    with pytest.raises(RuleError):
        reports.monthly(biz.db, '2025-12-01', '2025-01-01')


def test_all_xmls_then_reversed_sales_recosts_later_sale(biz):
    pid = purchase(biz, '2025-03-01', '400.00', number=2)
    purchase(biz, '2025-01-01', '200.00', number=1)
    march = sale(biz, pid, key='march', sale_date='2025-03-10', paid_on='2025-03-11')
    assert record(biz, march)['cost_cents'] == 15000
    feb = sale(biz, pid, key='feb', sale_date='2025-02-01')
    assert record(biz, feb)['cost_cents'] == 10000
    assert record(biz, march)['cost_cents'] == 16667
    assert biz.product(pid)['stock'] == 2
    assert biz.product(pid)['stock_cents'] == 33333
    assert biz.db.rows('SELECT paid_on FROM receivables WHERE sale_id=?', (march,))[0]['paid_on'] == '2025-03-11'
    assert reports.summary(biz.db, '2025-02-01', '2025-02-28')['net_cents'] == 13000


def test_purchase_inserted_before_existing_sales_recosts(biz):
    pid = purchase(biz, '2025-03-01', '400.00', number=2)
    sid = sale(biz, pid, sale_date='2025-03-10')
    assert record(biz, sid)['cost_cents'] == 20000
    purchase(biz, '2025-01-01', '200.00', number=1)
    assert record(biz, sid)['cost_cents'] == 15000
    assert biz.product(pid)['stock_cents'] == 45000


def test_future_purchase_cannot_price_past_sale_pending_then_resolved(biz):
    pid = purchase(biz, '2025-03-01', '400.00', number=2)
    with pytest.raises(RuleError, match='histórico insuficiente'):
        sale(biz, pid, sale_date='2025-02-01')
    assert not biz.db.rows('SELECT * FROM sales')
    sid = sale(biz, pid, sale_date='2025-02-01', historical=True)
    assert record(biz, sid)['cost_status'] == 'pending'
    assert biz.product(pid)['stock_cents'] is None
    assert biz.product(pid)['stock'] == 1
    feb = reports.summary(biz.db, '2025-02-01', '2025-02-28')
    assert feb['stock'] == -1 and feb['net_cents'] is None and feb['cost_cents'] is None
    assert feb['revenue_cents'] == 23000
    assert 'Em conferência' in reports.csv_bytes([record(biz, sid)]).decode('utf-8-sig')
    exported = json.loads(reports.export_json(biz.db))
    assert exported['tables']['sales'][0]['net_cents'] is None
    purchase(biz, '2025-01-01', '200.00', number=1)
    assert record(biz, sid)['cost_status'] == 'confirmed'
    assert record(biz, sid)['cost_cents'] == 10000
    assert not biz.db.rows('SELECT * FROM history_issues')
    assert biz.product(pid)['stock'] == 3
    assert biz.product(pid)['stock_cents'] == 50000


def test_pending_propagates_to_later_sale_and_resolves(biz):
    pid = purchase(biz, '2025-03-01', '400.00', number=2)
    first = sale(biz, pid, sale_date='2025-02-01', historical=True, key='first')
    second = sale(biz, pid, sale_date='2025-03-05', historical=True, key='second')
    assert record(biz, second)['cost_status'] == 'pending'
    purchase(biz, '2025-01-01', '200.00', number=1)
    assert record(biz, first)['cost_cents'] == 10000
    assert record(biz, second)['cost_cents'] == 16667
    assert record(biz, second)['cost_status'] == 'confirmed'


def test_cancellation_cost_rebuilt_with_original_sale(biz):
    pid = purchase(biz, '2025-03-01', '400.00', number=2)
    sid = sale(biz, pid, sale_date='2025-03-10')
    biz.cancel_sale(sid, 'Cancelamento real', when='2025-04-01')
    purchase(biz, '2025-01-01', '200.00', number=1)
    rows = biz.db.rows("SELECT cost_cents FROM movements WHERE kind IN ('SALE','CANCELLATION') ORDER BY id")
    assert [r['cost_cents'] for r in rows] == [-15000, 15000]
    assert biz.product(pid)['stock_cents'] == 60000
    assert reports.summary(biz.db, '2025-04-01', '2025-04-30')['net_cents'] == -8000


def test_same_day_purchase_before_sale_independent_of_import_order(biz):
    pid = purchase(biz, '2025-03-01', '400.00', number=2)
    sid = sale(biz, pid, sale_date='2025-01-01', historical=True)
    purchase(biz, '2025-01-01', '200.00', number=1)
    assert record(biz, sid)['cost_cents'] == 10000
    assert record(biz, sid)['cost_status'] == 'confirmed'


def test_count_is_absolute_after_inserting_earlier_sale(biz):
    pid = product(biz, qty=5)
    biz.adjust_stock(pid, 3, 'Contagem física', when='2025-03-01', unit_cost='100')
    sale(biz, pid, sale_date='2025-02-01')
    assert biz.product(pid)['stock'] == 3
    assert biz.product(pid)['stock_cents'] == 30000
    adjustment = biz.db.rows("SELECT * FROM movements WHERE kind='ADJUSTMENT'")[0]
    assert adjustment['quantity'] == -1 and adjustment['cost_cents'] == -10000


def test_quote_cost_uses_sale_date_not_current_average(biz):
    pid = purchase(biz, '2025-01-01', '200.00', number=1)
    purchase(biz, '2025-03-01', '400.00', number=2)
    assert biz.quote_cost([{'product_id': pid, 'quantity': 1}], '2025-02-01') == 10000
    assert biz.quote_cost([{'product_id': pid, 'quantity': 1}], '2024-12-01') is None


def test_delete_cancelled_paid_test_removes_cash_and_both_movements(biz):
    pid = product(biz)
    sid = sale(biz, pid, fee='10', paid_on='2025-01-15')
    biz.cancel_sale(sid, 'Teste', when='2025-01-16')
    backup = biz.delete_cancelled_test_sale(sid, confirmation=f'EXCLUIR TESTE #{sid}', reason='Teste fictício')
    assert backup.exists()
    with sqlite3.connect(backup) as conn:
        assert conn.execute('SELECT COUNT(*) FROM sales').fetchone()[0] == 1
    assert biz.product(pid)['stock'] == 5
    assert biz.product(pid)['stock_cents'] == 50000
    for table in ['sales', 'sale_items', 'receivables', 'expenses']:
        assert not biz.db.rows('SELECT * FROM ' + table)
    assert len(biz.db.rows('SELECT * FROM movements')) == 1
    assert reports.summary(biz.db, '2025-01-01', '2025-01-31')['cash_net_cents'] == 0
    assert reports.summary(biz.db, '2025-01-01', '2025-01-31')['net_cents'] == 0
    later = sale(biz, pid, key='another')
    assert later > sid
    with pytest.raises(RuleError, match='teste já excluído'):
        sale(biz, pid)


def test_delete_active_or_unconfirmed_test_rejected(biz):
    pid = product(biz)
    sid = sale(biz, pid)
    with pytest.raises(RuleError, match='Digite'):
        biz.delete_cancelled_test_sale(sid, confirmation='', reason='Teste')
    with pytest.raises(RuleError, match='Cancele'):
        biz.delete_cancelled_test_sale(sid, confirmation=f'EXCLUIR TESTE #{sid}', reason='Teste')
    assert record(biz, sid)


def test_delete_test_with_paid_refund_is_blocked(biz):
    pid = product(biz)
    sid = sale(biz, pid, paid_on='2025-01-15')
    biz.cancel_sale(sid, 'Teste', when='2025-01-16')
    expense = biz.db.rows("SELECT id FROM expenses WHERE category='Reembolso ao cliente'")[0]
    biz.pay_expense(expense['id'], '2025-01-17')
    with pytest.raises(RuleError, match='pagamento vinculado'):
        biz.delete_cancelled_test_sale(sid, confirmation=f'EXCLUIR TESTE #{sid}', reason='Teste')
    assert record(biz, sid)


def test_delete_rolls_back_on_database_failure(biz):
    pid = product(biz)
    sid = sale(biz, pid)
    biz.cancel_sale(sid, 'Teste', when='2025-01-16')
    with biz.db.connect() as conn:
        conn.execute("CREATE TRIGGER block_delete BEFORE DELETE ON sales BEGIN SELECT RAISE(ABORT,'simulated'); END")
    with pytest.raises(sqlite3.IntegrityError):
        biz.delete_cancelled_test_sale(sid, confirmation=f'EXCLUIR TESTE #{sid}', reason='Teste')
    assert record(biz, sid)
    assert len(biz.db.rows('SELECT * FROM movements')) == 3
    assert not biz.db.rows('SELECT * FROM deleted_sales')


def test_delete_after_physical_count_cannot_change_current_balance(biz):
    pid = product(biz)
    sid = sale(biz, pid)
    biz.adjust_stock(pid, 3, 'Conferência', when='2025-01-16', unit_cost='100')
    biz.cancel_sale(sid, 'Teste', when='2025-01-17')
    assert biz.product(pid)['stock'] == 4
    with pytest.raises(RuleError, match='alteraria o saldo'):
        biz.delete_cancelled_test_sale(sid, confirmation=f'EXCLUIR TESTE #{sid}', reason='Teste')
    assert biz.product(pid)['stock'] == 4 and record(biz, sid)


def test_upgrade_real_v1_schema_preserves_rows_and_backup(tmp_path):
    path = tmp_path / 'old.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.executescript(Path(__file__).with_name('fixtures').joinpath('schema_v1.sql').read_text())
        conn.execute("INSERT INTO products(id,supplier,sku,name,selling_cents) VALUES (1,'Manual','OLD','Peça antiga',23000)")
        conn.execute("INSERT INTO movements(product_id,occurred_on,quantity,cost_cents,kind,source,reason) VALUES (1,'2025-01-01',5,50000,'OPENING','old','Inicial')")
        conn.execute("INSERT INTO movements(product_id,occurred_on,quantity,cost_cents,kind,source,reason) VALUES (1,'2025-03-01',-2,-20000,'ADJUSTMENT','count','Contagem')")
    db = Database(path)
    assert db.rows("SELECT value FROM metadata WHERE key='schema_version'")[0]['value'] == '8'
    assert db.migration_backup.exists()
    with sqlite3.connect(db.migration_backup) as original:
        assert original.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == '1'
    movement = db.rows("SELECT * FROM movements WHERE kind='ADJUSTMENT'")[0]
    assert movement['counted_quantity'] == 3
    assert movement['input_unit_cost_cents'] == 10000
    sale(Business(db), 1, sale_date='2025-02-01')
    assert Business(db).product(1)['stock'] == 3
    again = Database(path)
    assert again.migration_backup is None
    assert len(again.rows('SELECT * FROM movements')) == 3
