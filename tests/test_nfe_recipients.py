import pytest
from flow.db import Database
from flow.service import Business
from flow.nfe import parse_xml
from flow.money import RuleError
from .helpers import fixture_xml


def cpf_xml(cpf='02194389512'):
    return fixture_xml(recipient=cpf).replace(b'08450759000501', b'08450759000188').replace(
        f'<CNPJ>{cpf}</CNPJ>'.encode(), f'<CPF>{cpf}</CPF>'.encode())


def test_matrix_cpf_import_preserves_document_and_deduplicates(tmp_path):
    raw = cpf_xml()
    invoice = parse_xml(raw)
    assert invoice.issuer == '08450759000188'
    assert invoice.recipient == '02194389512'
    biz = Business(Database(tmp_path / 'test.sqlite3'))
    invoice_id = biz.import_invoice(raw, {'1': 'estoque', '2': 'despesa'})
    row = biz.db.rows('SELECT recipient_cnpj,xml FROM invoices WHERE id=?', (invoice_id,))[0]
    assert row['recipient_cnpj'] == invoice.recipient
    assert row['xml'] == raw
    with pytest.raises(RuleError, match='já foi importada'):
        biz.import_invoice(raw, {'1': 'estoque', '2': 'despesa'})


def test_unknown_cpf_is_rejected():
    with pytest.raises(RuleError, match='Destinatário'):
        parse_xml(cpf_xml('12345678901'))


@pytest.mark.parametrize('recipient', ['63167950000125', '68120276000147'])
def test_existing_cnpj_buyers_remain_supported(recipient):
    assert parse_xml(fixture_xml(recipient=recipient)).recipient == recipient
