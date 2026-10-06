from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
import json
import sqlite3
import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError, cents, pieces
from flow.nfe import parse_xml
from flow import reports
from flow.benchmarks import compound
from .helpers import fixture_xml


@pytest.fixture
def biz(tmp_path):
    return Business(Database(tmp_path / 'test.sqlite3'))


def product(biz, qty=5, cost='100', price='230', key='initial'):
    return biz.create_product({'sku': key, 'name': 'Peça de teste', 'selling_price': price},
                              quantity=qty, unit_cost=cost, when='2025-01-01', key=key)


def sale(biz, pid, qty=1, price='230', key='sale', **fields):
    return biz.create_sale([{'product_id': pid, 'quantity': qty, 'unit_price': price}],
        {'sale_date': '2025-01-15', 'method': 'Pix', **fields}, key=key)


def test_money_and_piece_validation():
    assert cents('1.234,56') == 123456
    assert cents('0.105') == 11
    for value in ['-1', 'NaN', 'Infinity', 'abc']:
        with pytest.raises(RuleError):
            cents(value)
    for value in ['1.5', '0', '-1']:
        with pytest.raises(RuleError):
            pieces(value)


def test_original_xml_and_full_sku(biz):
    raw = fixture_xml()
    parsed = parse_xml(raw)
    assert parsed.items[0].sku == 'TESTE.001.FO'
    assert parsed.items[0].cost_cents == 19000
    invoice_id = biz.import_invoice(raw, {'1': 'estoque', '2': 'despesa'})
    assert biz.products()[0]['stock'] == 2
    assert biz.products()[0]['stock_cents'] == 19000
    assert biz.db.rows('SELECT xml FROM invoices WHERE id=?', (invoice_id,))[0]['xml'] == raw
    assert reports.summary(biz.db, '2025-01-01', '2025-01-31')['net_cents'] == -2000
    with pytest.raises(RuleError, match='já foi importada'):
        biz.import_invoice(raw, {'1': 'estoque', '2': 'despesa'})
    assert biz.products()[0]['stock'] == 2


def test_expense_only_invoice_deduplicates(biz):
    raw = fixture_xml()
    biz.import_invoice(raw, {'1': 'despesa', '2': 'ignorar'})
    assert biz.products() == []
    with pytest.raises(RuleError):
        biz.import_invoice(raw, {'1': 'estoque', '2': 'estoque'})
    assert len(biz.db.rows('SELECT id FROM invoices')) == 1
    assert len(biz.db.rows('SELECT id FROM expenses')) == 1


def test_invoice_rolls_back_after_first_item(biz):
    raw = fixture_xml(second_quantity='1.5')
    with pytest.raises(RuleError, match='inteiro'):
        biz.import_invoice(raw, {'1': 'estoque', '2': 'estoque'})
    for table in ['products', 'invoices', 'invoice_items', 'expenses', 'movements']:
        assert biz.db.rows('SELECT * FROM ' + table) == []
    biz.import_invoice(raw, {'1': 'estoque', '2': 'despesa'})
    assert len(biz.products()) == 1


@pytest.mark.parametrize('recipient', ['63167950000125', '68120276000147'])
def test_historical_buyer_kept(recipient):
    parsed = parse_xml(fixture_xml(recipient=recipient))
    assert parsed.recipient == recipient


def test_reject_unknown_buyer_and_dtd():
    with pytest.raises(RuleError, match='Destinatário'):
        parse_xml(fixture_xml(recipient='12345678000199'))
    with pytest.raises(RuleError):
        parse_xml(b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>')


def test_invoice_total_mismatch_rejected():
    with pytest.raises(RuleError, match='não fecham'):
        parse_xml(fixture_xml().replace(b'<vNF>210.00', b'<vNF>211.00'))


def test_sale_deductions_and_cash_distinct(biz):
    pid = product(biz)
    sid = sale(biz, pid, qty=2, price='250', fee='10', tax='15', seller='20', store='25', discount='30', paid_on='2025-01-16')
    saved = biz.db.rows('SELECT * FROM sales WHERE id=?', (sid,))[0]
    assert saved['net_cents'] == 20000  # 500 - 30 - 200 - 10 - 15 - 20 - 25
    assert biz.product(pid)['stock'] == 3
    result = reports.summary(biz.db, '2025-01-01', '2025-01-31')
    assert result['net_cents'] == 20000
    assert result['cash_in_cents'] == 46000
    assert result['payable_cents'] == 6000
    for exp in biz.db.rows('SELECT id FROM expenses'):
        biz.pay_expense(exp['id'], '2025-01-20')
    result = reports.summary(biz.db, '2025-01-01', '2025-01-31')
    assert result['net_cents'] == 20000  # Dar baixa não desconta comissões e imposto de novo.
    assert result['cash_net_cents'] == 40000


def test_no_negative_stock_and_no_partial_sale(biz):
    p1, p2 = product(biz, qty=1), product(biz, qty=1, key='other')
    with pytest.raises(RuleError, match='insuficiente'):
        biz.create_sale([{'product_id': p1, 'quantity': 1, 'unit_price': '230'},
                         {'product_id': p2, 'quantity': 2, 'unit_price': '230'}],
                        {'sale_date': '2025-01-15', 'method': 'Pix'}, key='multi')
    assert not biz.db.rows('SELECT * FROM sales')
    assert biz.product(p1)['stock'] == biz.product(p2)['stock'] == 1


def test_db_failure_rolls_back_sale_and_movements(biz):
    pid = product(biz)
    with biz.db.connect() as conn:
        conn.execute("CREATE TRIGGER fail_receivable BEFORE INSERT ON receivables BEGIN SELECT RAISE(ABORT, 'simulated'); END")
    with pytest.raises(sqlite3.IntegrityError):
        sale(biz, pid)
    assert biz.product(pid)['stock'] == 5
    assert not biz.db.rows('SELECT * FROM sales')
    assert not biz.db.rows('SELECT * FROM sale_items')


def test_last_piece_two_concurrent_sales(biz):
    pid = product(biz, qty=1)
    barrier = Barrier(2)
    def attempt(key):
        barrier.wait()
        try:
            sale(biz, pid, key=key)
            return 'sold'
        except RuleError:
            return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['a', 'b']))
    assert sorted(results) == ['blocked', 'sold']
    assert biz.product(pid)['stock'] == 0
    assert len(biz.db.rows('SELECT * FROM sales')) == 1


def test_retry_and_cancel_are_idempotent(biz):
    pid = product(biz)
    sid = sale(biz, pid)
    assert sale(biz, pid) == sid
    assert biz.product(pid)['stock'] == 4
    biz.cancel_sale(sid, 'Teste de cancelamento', when='2025-02-01')
    biz.cancel_sale(sid, 'Segunda tentativa', when='2025-02-01')
    assert biz.product(pid)['stock'] == 5
    assert biz.product(pid)['stock_cents'] == 50000
    assert reports.summary(biz.db, '2025-01-01', '2025-01-31')['net_cents'] == 13000
    assert reports.summary(biz.db, '2025-02-01', '2025-02-28')['net_cents'] == -13000


def test_cancel_paid_sale_creates_refund_and_retains_fee(biz):
    pid = product(biz)
    sid = sale(biz, pid, fee='10', paid_on='2025-01-15')
    biz.cancel_sale(sid, 'Cliente devolveu a peça', when='2025-01-16')
    result = reports.summary(biz.db, '2025-01-01', '2025-01-31')
    assert result['net_cents'] == -1000
    assert result['payable_cents'] == 23000
    refund = biz.db.rows("SELECT id FROM expenses WHERE category='Reembolso ao cliente'")[0]
    biz.pay_expense(refund['id'], '2025-01-17')
    assert reports.summary(biz.db, '2025-01-01', '2025-01-31')['cash_net_cents'] == -1000


def test_catalog_change_cannot_overwrite_sold_stock_or_cost(biz):
    pid = product(biz)
    sid = sale(biz, pid)
    biz.update_catalog(pid, {'name': 'Novo nome', 'selling_price': '999', 'quantity_in_stock': 5, 'purchase_price': '999'})
    biz.update_sale_notes(sid, 'Cliente corrigido', '', '', 'Correção de cadastro')
    assert biz.product(pid)['stock'] == 4
    saved = biz.db.rows('SELECT * FROM sales WHERE id=?', (sid,))[0]
    assert saved['cost_cents'] == 10000
    assert saved['net_cents'] == 13000


def test_weighted_cost_exact_to_last_cent_and_cancel(biz):
    # Total 1,01 / 3 unidades; a última baixa leva o centavo restante.
    raw = fixture_xml(second_quantity='3', second_value='1.01')
    biz.import_invoice(raw, {'1': 'ignorar', '2': 'estoque'})
    pid = biz.products()[0]['id']
    ids = [sale(biz, pid, price='1', key=str(i), sale_date='2025-01-16') for i in range(3)]
    assert [r['cost_cents'] for r in biz.db.rows('SELECT * FROM sale_items ORDER BY id')] == [34, 34, 33]
    assert biz.product(pid)['stock_cents'] == 0
    for sid in ids:
        biz.cancel_sale(sid, 'Devolução', when='2025-01-17')
    assert biz.product(pid)['stock_cents'] == 101


def test_installment_rounding_and_end_of_month(biz):
    pid = product(biz)
    sid = sale(biz, pid, price='100.01', fee='3.01', installments=3, first_due='2025-01-31')
    rows = biz.db.rows('SELECT * FROM receivables WHERE sale_id=? ORDER BY installment', (sid,))
    assert sum(r['gross_cents'] for r in rows) == 10001
    assert sum(r['fee_cents'] for r in rows) == 301
    assert [r['due_on'] for r in rows] == ['2025-01-31', '2025-02-28', '2025-03-31']


def test_backdated_sale_is_accepted_and_rebuilt(biz):
    pid = product(biz)
    sale(biz, pid, sale_date='2025-02-01')
    sale(biz, pid, key='backdated')
    assert biz.product(pid)['stock'] == 3
    assert [r['cost_cents'] for r in biz.db.rows('SELECT * FROM sales')] == [10000, 10000]


def test_local_calendar_month_boundary(biz):
    pid = product(biz)
    sale(biz, pid, sale_date='2025-02-01')
    assert reports.summary(biz.db, '2025-01-01', '2025-01-31')['revenue_cents'] == 0
    assert reports.summary(biz.db, '2025-02-01', '2025-02-28')['revenue_cents'] == 23000


def test_expense_cancel_in_later_month_preserves_history(biz):
    exp = biz.create_expense({'occurred_on': '2025-01-01', 'amount': '75', 'description': 'Evento', 'category': 'Marketing'}, key='expense')
    biz.cancel_expense(exp, 'Evento não realizado', when='2025-02-01')
    assert reports.summary(biz.db, '2025-01-01', '2025-01-31')['net_cents'] == -7500
    assert reports.summary(biz.db, '2025-02-01', '2025-02-28')['net_cents'] == 7500


def test_stock_adjustment_and_snapshot_backup(biz, tmp_path):
    pid = product(biz)
    biz.adjust_stock(pid, 3, 'Perda na conferência', when='2025-01-15', key='adjust')
    assert reports.summary(biz.db, '2025-01-01', '2025-01-31')['net_cents'] == -20000
    backup = Database(biz.db.backup(tmp_path / 'backup.sqlite3'))
    assert backup.rows('SELECT * FROM inventory')[0]['stock'] == 3
    assert json.loads(reports.export_json(biz.db))['tables']['movements']


def test_benchmarks_compound_and_require_full_period():
    observations = [{'data': '01/01/2025', 'valor': '1'}, {'data': '01/02/2025', 'valor': '2'}]
    assert compound(observations, ['2025-01', '2025-02']) == Decimal('0.0302')
    with pytest.raises(RuleError, match='todos os meses'):
        compound(observations, ['2025-01', '2025-02', '2025-03'])
    assert compound([{'data': '01/01/2025', 'valor': '-0.2'}], ['2025-01']) == Decimal('-0.002')


def test_csv_escaping_and_formula_protection():
    content = reports.csv_bytes([{'Nome': '=1+1', 'Nota': 'linha\ncom; separador'}]).decode('utf-8-sig')
    assert "'=1+1" in content
    assert '"linha\ncom; separador"' in content


def test_batch_expense_payments_atomic_and_no_double_payment(biz):
    ids = [biz.create_expense({'occurred_on': when, 'amount': '75', 'description': 'Lote', 'category': 'Marketing'}, key=when)
           for when in ['2025-01-01', '2025-02-01']]
    with pytest.raises(RuleError):
        biz.pay_expenses(ids, '2025-01-15')
    assert all(r['paid_on'] is None for r in biz.db.rows('SELECT paid_on FROM expenses'))
    biz.pay_expenses(ids + ids, '2025-02-02')
    assert all(r['paid_on'] == '2025-02-02' for r in biz.db.rows('SELECT paid_on FROM expenses'))
    assert reports.summary(biz.db, '2025-02-01', '2025-02-28')['cash_out_cents'] == 15000
    with pytest.raises(RuleError):
        biz.pay_expenses(ids, '2025-02-03')
    with pytest.raises(RuleError):
        biz.pay_expenses([], '2025-02-03')
