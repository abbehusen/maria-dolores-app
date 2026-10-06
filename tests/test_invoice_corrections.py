import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError
from flow import reports
from .helpers import fixture_xml
from .test_business import sale

@pytest.fixture
def biz(tmp_path):
    return Business(Database(tmp_path/'flow.sqlite3'))


def test_paid_stock_to_expense_preserves_xml_payment_and_no_duplicate(biz):
    raw=fixture_xml()
    iid=biz.import_invoice(raw, {'1':'estoque','2':'estoque'}, paid_on='2025-01-20', due_on='2025-01-30')
    before=biz.invoice_snapshot(iid)
    pid=before['items'][1]['product_id']
    biz.correct_invoice(iid, {'1':'estoque','2':'despesa'}, reason='Sacola', expected=before)
    after=biz.invoice_snapshot(iid)
    assert after['invoice']==before['invoice']
    assert biz.db.rows('SELECT xml FROM invoices')[0]['xml']==raw
    assert after['expenses'][0]==before['expenses'][0]
    expected=dict(before['expenses'][1], category='Outras despesas', affects_result=1)
    assert after['expenses'][1]==expected
    assert biz.product(pid)['stock']==0 and not biz.product(pid)['active']
    result=reports.summary(biz.db,'2025-01-01','2025-12-31')
    assert result['cash_out_cents']==21000
    biz.correct_invoice(iid, {'1':'estoque','2':'estoque'}, reason='Reverter')
    assert biz.product(pid)['stock']==1 and biz.product(pid)['active']
    assert len(biz.db.rows('SELECT * FROM expenses'))==2
    assert list((biz.db.path.parent/'backups').glob('antes-corrigir-nota-*.sqlite3'))


def test_ignored_items_can_be_added_and_unpaid_removed(biz):
    iid=biz.import_invoice(fixture_xml(), {'1':'ignorar','2':'ignorar'})
    biz.correct_invoice(iid, {'1':'estoque','2':'despesa'}, reason='Itens esquecidos')
    assert biz.products()[0]['stock']==2
    assert len(biz.db.rows('SELECT * FROM expenses'))==2
    assert all(e['paid_on'] is None for e in biz.db.rows('SELECT * FROM expenses'))
    biz.correct_invoice(iid, {'1':'ignorar','2':'ignorar'}, reason='Remover')
    assert not biz.db.rows('SELECT * FROM expenses')
    assert biz.products()[0]['stock']==0


def test_linked_sale_blocks_atomically_and_stale_payment_rejected(biz):
    iid=biz.import_invoice(fixture_xml(), {'1':'estoque','2':'despesa'})
    before=biz.invoice_snapshot(iid)
    sale(biz,before['items'][0]['product_id'])
    with pytest.raises(RuleError, match='vendas'):
        biz.correct_invoice(iid, {'1':'despesa','2':'estoque'}, reason='Correção')
    assert biz.invoice_snapshot(iid)==before
    biz.pay_expense(before['expenses'][1]['id'], '2025-01-20')
    with pytest.raises(RuleError, match='mudaram'):
        biz.correct_invoice(iid, {'1':'estoque','2':'estoque'}, reason='Antigo', expected=before)
    with pytest.raises(RuleError, match='pagamento'):
        biz.correct_invoice(iid, {'1':'estoque','2':'ignorar'}, reason='Ignorar pago')


def test_consignment_reclassification_respects_movements(biz):
    iid=biz.import_invoice(fixture_xml(), {'1':'estoque','2':'ignorar'}, ownership='consigned')
    biz.correct_invoice(iid, {'1':'ignorar','2':'estoque'}, reason='Troca')
    assert len(biz.consignment_lots())==1
    assert not biz.db.rows('SELECT * FROM expenses')
    lot=biz.consignment_lots()[0]
    biz.return_consignment(lot['id'], 1, 'Devolvido')
    with pytest.raises(RuleError, match='devolução'):
        biz.correct_invoice(iid, {'1':'ignorar','2':'ignorar'}, reason='Não pode')
    with pytest.raises(RuleError, match='consignada'):
        biz.correct_invoice(iid, {'1':'despesa','2':'estoque'}, reason='Não pode')


def test_fractional_stock_correction_rolls_back(biz):
    iid=biz.import_invoice(fixture_xml(second_quantity='0.5'), {'1':'despesa','2':'despesa'})
    before=biz.invoice_snapshot(iid)
    with pytest.raises(RuleError):
        biz.correct_invoice(iid, {'1':'estoque','2':'estoque'}, reason='Quantidade fracionária')
    assert biz.invoice_snapshot(iid)==before
    assert not biz.products()
