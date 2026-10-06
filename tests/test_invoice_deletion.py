import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError
from .helpers import fixture_xml
from .test_business import sale

@pytest.fixture
def biz(tmp_path):
    return Business(Database(tmp_path/'flow.sqlite3'))


def test_delete_paid_note_preserves_other_note_and_allows_reimport(biz):
    raw=fixture_xml(number=1)
    iid=biz.import_invoice(raw, {'1':'estoque','2':'despesa'}, paid_on='2025-01-20')
    other=biz.import_invoice(fixture_xml(number=2), {'1':'estoque','2':'despesa'})
    snapshot=biz.invoice_snapshot(other)
    deleted_key=biz.invoice_snapshot(iid)['invoice']['access_key']
    backup=biz.delete_invoice(iid, reason='Duplicação manual', confirmation='EXCLUIR NOTA 1')
    assert backup.exists()
    assert biz.invoice_snapshot(other)==snapshot
    assert biz.products()[0]['stock']==2
    assert not biz.db.rows('SELECT * FROM invoices WHERE access_key=?', (deleted_key,))
    assert len(biz.db.rows('SELECT * FROM invoices'))==1
    assert len(biz.db.rows('SELECT * FROM expenses'))==2
    biz.import_invoice(raw, {'1':'estoque','2':'despesa'})
    assert biz.products()[0]['stock']==4
    assert len(biz.db.rows('SELECT * FROM expenses'))==4


def test_delete_isolated_consignment_and_reimport_reactivates_catalog(biz):
    raw=fixture_xml(number=1)
    iid=biz.import_invoice(raw, {'1':'estoque','2':'ignorar'}, ownership='consigned')
    biz.delete_invoice(iid, reason='Teste', confirmation='EXCLUIR NOTA 1')
    assert not biz.consignment_lots()
    assert not biz.products()[0]['active']
    biz.import_invoice(raw, {'1':'estoque','2':'ignorar'}, ownership='consigned')
    assert biz.products()[0]['active']
    assert biz.consignment_lots()[0]['stock']==2


def test_linked_sale_and_confirmation_block_deletion(biz):
    iid=biz.import_invoice(fixture_xml(number=1), {'1':'estoque','2':'despesa'})
    snapshot=biz.invoice_snapshot(iid)
    with pytest.raises(RuleError, match='Digite'):
        biz.delete_invoice(iid, reason='Teste', confirmation='sim')
    sid=sale(biz, snapshot['items'][0]['product_id'])
    with pytest.raises(RuleError, match=f'venda #{sid}'):
        biz.delete_invoice(iid, reason='Teste', confirmation='EXCLUIR NOTA 1')
    assert biz.invoice_snapshot(iid)==snapshot
    biz.correct_sale(sid,reason='Venda errada')
    biz.delete_invoice(iid,reason='Nota errada',confirmation='EXCLUIR NOTA 1')
    assert not biz.db.rows('SELECT * FROM invoices')


def test_consignment_return_blocks_deletion_even_when_cancelled(biz):
    iid=biz.import_invoice(fixture_xml(number=1), {'1':'estoque','2':'ignorar'}, ownership='consigned')
    biz.return_consignment(1,1,'Retorno')
    mid=biz.db.rows('SELECT id FROM consignment_moves')[0]['id']
    biz.cancel_consignment_return(mid,'Erro')
    before=biz.invoice_snapshot(iid)
    with pytest.raises(RuleError, match='devolução'):
        biz.delete_invoice(iid,reason='Teste',confirmation='EXCLUIR NOTA 1')
    assert biz.invoice_snapshot(iid)==before
    assert biz.consignment_lots()[0]['stock']==2


def test_stale_payment_and_physical_count_block_deletion(biz):
    iid=biz.import_invoice(fixture_xml(number=1), {'1':'estoque','2':'despesa'})
    before=biz.invoice_snapshot(iid)
    biz.pay_expense(before['expenses'][0]['id'],'2025-01-20')
    with pytest.raises(RuleError,match='mudaram'):
        biz.delete_invoice(iid,reason='Teste',confirmation='EXCLUIR NOTA 1',expected=before)
    biz.adjust_stock(before['items'][0]['product_id'],1,'Contagem',when='2025-02-01')
    with pytest.raises(RuleError,match='conferência'):
        biz.delete_invoice(iid,reason='Teste',confirmation='EXCLUIR NOTA 1')
    assert len(biz.db.rows('SELECT * FROM expenses'))==2
