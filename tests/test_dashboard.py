import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError
from flow.analytics import dashboard, sales_view, allocate
from flow.reports import summary
from .helpers import fixture_xml
from .test_business import product, sale

@pytest.fixture
def biz(tmp_path):
    return Business(Database(tmp_path/'flow.sqlite3'))


def test_mixed_sales_reconcile_origins_discount_cost_and_cash(biz):
    own=product(biz,qty=3)
    biz.import_invoice(fixture_xml(),{'1':'estoque','2':'despesa'})
    biz.import_invoice(fixture_xml(number=2),{'1':'estoque','2':'ignorar'},ownership='consigned')
    lot=biz.consignment_lots()[0]
    sid=biz.create_sale([{'product_id':own,'quantity':1,'unit_price':'200.01'},
                        {'product_id':lot['product_id'],'lot_id':lot['id'],'quantity':1,'unit_price':'300.02'}],
                       {'sale_date':'2025-02-01','method':'Cartão de crédito','discount':'10.01','fee':'7.02','tax':'3','seller':'5', 'installments':2},key='mixed')
    snapshot=biz.sale_snapshot(sid)
    biz.receive(snapshot['receivables'][0]['id'],'2025-02-05')
    biz.pay_expense(snapshot['expenses'][0]['id'],'2025-02-06')
    d=dashboard(biz.db,'2025-02-01','2025-02-28')
    assert d['current']==summary(biz.db,'2025-02-01','2025-02-28')
    own_view=sales_view(d['sales'],'own'); cons=sales_view(d['sales'],'consigned'); all_=sales_view(d['sales'])
    assert all_['count']==1 and own_view['count']==1 and cons['count']==1
    assert all_['pieces']==2
    assert own_view['revenue_cents']+cons['revenue_cents']==d['current']['revenue_cents']
    assert all_['contribution_cents']==d['current']['net_cents']
    assert d['discount_cents']==1001
    assert sum(r['gross_cents']-r['fee_cents'] for r in d['received'])==d['current']['cash_in_cents']
    assert sum(r['amount_cents'] for r in d['paid'])==d['current']['cash_out_cents']
    assert sum(r['gross_cents']-r['fee_cents'] for r in d['receivable'])==d['current']['receivable_cents']
    assert sum(r['amount_cents'] for r in d['payable'])==d['current']['payable_cents']
    assert sum(r['quantity'] for r in d['own'])==d['current']['stock']
    assert sum(r['value_cents'] for r in d['own'])==d['current']['stock_cents']
    assert sum(r['value_cents'] for r in d['lots'])==d['current']['consigned_stock_cents']
    # Baixa futura permanece em aberto na fotografia histórica.
    past=dashboard(biz.db,'2025-02-01','2025-02-04')
    assert past['current']['cash_in_cents']==0
    assert len(past['receivable'])==2


def test_legacy_cancellation_signed_details_match_period(biz):
    pid=product(biz)
    sid=sale(biz,pid,discount='10',paid_on='2025-01-15',fee='2')
    biz.cancel_sale(sid,'Devolução real antiga',when='2025-02-01')
    d=dashboard(biz.db,'2025-02-01','2025-02-28')
    v=sales_view(d['sales'])
    assert v['count']==-1 and v['pieces']==-1
    assert v['revenue_cents']==d['current']['revenue_cents']==-22000
    assert v['ticket_cents'] is None
    assert sum(r['amount_cents'] for r in d['operating'])==d['current']['operating_cents']
    assert v['contribution_cents']-d['current']['operating_cents']==d['current']['net_cents']


def test_pending_costs_not_shown_as_profit(biz):
    pid=product(biz,qty=0)
    sale(biz,pid,historical=True)
    d=dashboard(biz.db,'2025-01-01','2025-01-31')
    assert d['current']['net_cents'] is None
    assert sales_view(d['sales'])['contribution_cents'] is None
    assert d['own'][0]['value_cents'] is None
    assert d['months'][0]['net_cents'] is None


def test_period_comparison_partial_months_empty_and_invalid(biz):
    d=dashboard(biz.db,'2025-02-15','2025-03-05')
    assert d['previous_start']=='2025-01-27' and d['previous_end']=='2025-02-14'
    assert [m['month'] for m in d['months']]==['2025-02','2025-03']
    assert sales_view(d['sales'])['ticket_cents'] is None
    with pytest.raises(RuleError):
        dashboard(biz.db,'2025-03-05','2025-02-15')
    assert dashboard(biz.db,'2000-01-01','2000-01-31')['previous'] is None


def test_rateio_exact_zero_priced_and_consignment_returns(biz):
    assert sum(allocate(1001,[20001,30002]))==1001
    assert sum(allocate(7,[0,0]))==7
    biz.import_invoice(fixture_xml(),{'1':'estoque','2':'ignorar'},ownership='consigned')
    biz.return_consignment(1,1,'Retorno',when='2025-02-01')
    d=dashboard(biz.db,'2025-02-01','2025-02-28')
    assert sum(r['value_cents'] for r in d['returns'])==9500
    mid=d['returns'][0]['id']
    biz.cancel_consignment_return(mid,'Correção')
    assert not dashboard(biz.db,'2025-02-01','2025-02-28')['returns']
