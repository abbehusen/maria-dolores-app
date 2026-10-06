import json
import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError
from flow import reports
from .test_consignment import receive, sell
from .test_business import product, sale


@pytest.fixture
def biz(tmp_path):
    return Business(Database(tmp_path / 'flow.sqlite3'))


def test_remove_paid_consignment_restores_reports_and_retains_audit(biz):
    pid = receive(biz)
    baseline = reports.summary(biz.db, '2025-01-01', '2025-12-31')
    sid = sell(biz, pid, paid_on='2025-02-01', tax='5', seller='10', store='3', fee='2')
    for expense in biz.db.rows('SELECT * FROM expenses WHERE sale_id=?', (sid,)):
        biz.pay_expense(expense['id'], '2025-02-02')
    biz.correct_sale(sid, reason='Registro fictício')
    assert reports.summary(biz.db, '2025-01-01', '2025-12-31') == baseline
    assert biz.consignment_lots()[0]['stock'] == 2
    for table in ['sales', 'sale_items', 'consignment_sale_items', 'receivables', 'expenses', 'consignment_moves']:
        assert not biz.db.rows(f'SELECT * FROM {table}')
    log = biz.db.rows("SELECT detail FROM audit WHERE action='remove_wrong_sale'")[0]
    assert all(e['paid_on'] for e in json.loads(log['detail'])['before']['expenses'])
    assert list((biz.db.path.parent / 'backups').glob('antes-corrigir-venda-*.sqlite3'))
    with pytest.raises(RuleError):
        sell(biz, pid)  # request_key antigo não pode ressuscitar a venda removida.


def test_edit_preserves_id_paid_dates_and_recalculates_values(biz):
    pid = receive(biz)
    sid = sell(biz, pid, qty=2, paid_on='2025-02-01')
    expense = biz.db.rows('SELECT * FROM expenses')[0]
    biz.pay_expense(expense['id'], '2025-02-02')
    before = biz.sale_snapshot(sid)
    biz.correct_sale(sid, reason='Quantidade e preço errados', expected=before,
        items=[{'product_id': pid, 'lot_id': 1, 'quantity': 1, 'unit_price': '250'}],
        data={'sale_date': '2025-02-01', 'method': 'Dinheiro'})
    after = biz.sale_snapshot(sid)
    assert after['sale']['id'] == sid
    assert after['sale']['revenue_cents'] == 25000
    assert after['sale']['cost_cents'] == 9500
    assert after['receivables'][0]['paid_on'] == '2025-02-01'
    assert after['receivables'][0]['gross_cents'] == 25000
    assert after['expenses'][0]['amount_cents'] == 9500
    assert after['expenses'][0]['paid_on'] == '2025-02-02'
    assert biz.consignment_lots()[0]['stock'] == 1


def test_invalid_edit_rolls_back_everything_and_stale_form_is_rejected(biz):
    pid = receive(biz)
    sid = sell(biz, pid)
    before = biz.sale_snapshot(sid)
    with pytest.raises(RuleError):
        biz.correct_sale(sid, reason='Quantidade', expected=before,
            items=[{'product_id': pid, 'lot_id': 1, 'quantity': 3, 'unit_price': '200'}],
            data={'sale_date': '2025-02-01', 'method': 'Pix'})
    assert biz.sale_snapshot(sid) == before
    biz.pay_expense(before['expenses'][0]['id'], '2025-02-02')
    with pytest.raises(RuleError, match='mudaram'):
        biz.correct_sale(sid, reason='Antigo', expected=before)
    assert biz.consignment_lots()[0]['stock'] == 1


def test_change_origin_and_installments_explicitly_resets_paid_records(biz):
    pid = receive(biz)
    own = product(biz, qty=1)
    sid = sell(biz, pid, paid_on='2025-02-01')
    biz.pay_expense(biz.db.rows('SELECT id FROM expenses')[0]['id'], '2025-02-02')
    args = dict(reason='Origem e pagamento incorretos',
        items=[{'product_id': own, 'quantity': 1, 'unit_price': '300'}],
        data={'sale_date': '2025-02-01', 'method': 'Cartão de crédito', 'installments': 3})
    before = biz.sale_snapshot(sid)
    with pytest.raises(RuleError, match='Desfazer baixas'):
        biz.correct_sale(sid, **args)
    assert biz.sale_snapshot(sid) == before
    biz.correct_sale(sid, reset_payments=True, **args)
    assert biz.consignment_lots()[0]['stock'] == 2
    assert biz.product(own)['stock'] == 0
    assert not biz.db.rows('SELECT * FROM expenses')
    assert [r['gross_cents'] for r in biz.sale_snapshot(sid)['receivables']] == [10000]*3
    assert all(r['paid_on'] is None for r in biz.sale_snapshot(sid)['receivables'])


def test_price_edit_keeps_movement_order_and_quote_never_commits(biz):
    pid = product(biz, qty=2)
    sid = sale(biz, pid, qty=2)
    before = biz.sale_snapshot(sid)
    moves = biz.db.rows('SELECT * FROM movements')
    assert biz.quote_cost([{'product_id': pid, 'quantity': 2}], '2025-01-15', exclude_sale_id=sid) == 20000
    assert biz.sale_snapshot(sid) == before
    assert biz.db.rows('SELECT * FROM movements') == moves
    biz.correct_sale(sid, reason='Preço', items=[{'product_id': pid, 'quantity': 2, 'unit_price': '250'}],
                     data={'sale_date': '2025-01-15', 'method': 'Pix'})
    assert biz.db.rows('SELECT * FROM movements') == moves
    assert biz.product(pid)['stock'] == 0
