from decimal import Decimal
import pytest
from flow.db import Database
from flow.service import Business
from flow.money import RuleError
from flow.reports import summary
from flow.analytics import dashboard
from flow.backup_restore import stage_restore,apply_pending_restore


@pytest.fixture
def setup(tmp_path):
    b=Business(Database(tmp_path/'flow.sqlite3'))
    pid=b.create_product({'sku':'TEST','name':'Joia','selling_price':'500'},quantity=20,unit_cost='220',when='2026-01-01')
    shop=b.save_beneficiary('FIAES')
    seller=b.save_beneficiary('Vendedora A')
    channel=b.save_channel(dict(name='FIAES',kind='Loja',store_rate='10',seller_rate='10',store_beneficiary_id=shop))
    b.link_seller(channel,seller)
    return b,pid,shop,seller,channel


def sale(b,pid,key,**changes):
    data=dict(sale_date='2026-01-10',customer='Cliente A',phone='71999990000',method='Pix',paid_on='2026-01-10')
    data.update(changes)
    return b.create_sale([dict(product_id=pid,quantity=1,unit_price='500')],data,key=key)


def test_withdrawal_uses_cost_without_revenue_or_customer(setup):
    b,pid,*_=setup
    sid=sale(b,pid,'personal',operation='personal',customer='Nanda',seller='100',store='100')
    r=b.db.rows('SELECT * FROM sales WHERE id=?',(sid,))[0]
    assert r['revenue_cents']==r['net_cents']==0 and r['cost_cents']==22000
    assert not b.db.rows('SELECT * FROM receivables') and not b.customers()
    assert b.product(pid)['stock']==19
    report=summary(b.db,'2026-01-01','2026-01-31')
    assert report['sale_count']==report['net_cents']==report['cash_in_cents']==0
    assert report['personal_cost_cents']==22000
    assert not dashboard(b.db,'2026-01-01','2026-01-31')['sales']
    b.correct_sale(sid,reason='Devolveu a peça')
    assert b.product(pid)['stock']==20


def test_credit_redemption_and_cash_complement(setup):
    b,pid,shop,seller,channel=setup
    origin=sale(b,pid,'origin',channel_id=channel,seller_id=seller,seller='150',store='50')
    redeem=sale(b,pid,'redeem',sale_date='2026-01-11',paid_on='2026-01-11',customer='Vendedora A',phone='',credit='100',credit_beneficiary_id=seller)
    r=summary(b.db,'2026-01-01','2026-01-31')
    assert r['revenue_cents']==100000 and r['cash_in_cents']==90000
    assert r['net_cents']==36000 and r['payable_cents']==10000
    rows=dashboard(b.db,'2026-01-01','2026-01-31')['payment_methods']
    assert sum(x['sold_cents'] for x in rows)==100000
    assert sum(x['received_cents'] for x in rows)==90000
    assert sum(x['compensated_cents'] for x in rows)==10000
    with pytest.raises(RuleError):b.correct_sale(origin,reason='Não pode apagar crédito usado')
    b.correct_sale(redeem,reason='Resgate incorreto')
    assert sum(x['balance_cents'] for x in b.commission_balances())==20000
    assert b.product(pid)['stock']==19


def test_partial_cash_payment_no_double_expense_and_reverse(setup):
    b,pid,shop,seller,channel=setup
    sid=sale(b,pid,'origin',channel_id=channel,seller_id=seller,seller='100',store='50')
    b.pay_commission(seller,'40','2026-01-12','Pix',key='pay')
    b.pay_commission(seller,'40','2026-01-12','Pix',key='pay')
    r=summary(b.db,'2026-01-01','2026-01-31')
    assert r['net_cents']==13000 and r['cash_out_cents']==4000 and r['payable_cents']==11000
    assert summary(b.db,'2026-01-01','2026-01-11')['payable_cents']==15000
    with pytest.raises(RuleError):b.pay_commission(seller,'61','2026-01-12','Pix',key='excess')
    with pytest.raises(RuleError):b.pay_commission(seller,'1','2026-01-09','Pix',key='early')
    b.reverse_commission_payment('pay','Erro na baixa')
    assert summary(b.db,'2026-01-01','2026-01-31')['cash_out_cents']==0
    b.correct_sale(sid,reason='Correção')
    assert sum(x['balance_cents'] for x in b.commission_balances())==0


def test_su_misura_attribution_without_seller_debt(setup):
    b,pid,shop,seller,channel=setup
    sale(b,pid,'su',channel_id=channel,seller_id=seller,store='100',seller='0')
    balances={r['id']:r['balance_cents'] for r in b.commission_balances()}
    assert balances[shop]==10000 and balances[seller]==0
    assert b.db.rows('SELECT seller_id FROM sales')[0]['seller_id']==seller


def test_customers_history_and_opt_in(setup):
    b,pid,*_=setup
    sid=sale(b,pid,'one');sale(b,pid,'two')
    customers=b.customers()
    assert len(customers)==1 and customers[0]['purchases']==2 and customers[0]['total_cents']==100000
    assert customers[0]['marketing_opt_in']==0
    assert len(b.customer_history(customers[0]['id']))==2
    b.correct_sale(sid,reason='Erro')
    assert b.customers()[0]['purchases']==1
    sale(b,pid,'other',phone='71888880000')
    assert len(b.customers())==2


def test_no_credit_overspend_or_recursive_commission(setup):
    b,pid,shop,seller,channel=setup
    sale(b,pid,'origin',channel_id=channel,seller_id=seller,seller='100')
    for key,changes in [('over',dict(credit='101',credit_beneficiary_id=seller)),('recursive',dict(credit='50',credit_beneficiary_id=seller,seller='10')),('no_person',dict(credit='20'))]:
        with pytest.raises(RuleError):sale(b,pid,key,**changes)
    assert b.product(pid)['stock']==19 and len(b.db.rows('SELECT * FROM sales'))==1


def test_restore_v5_with_commissions(setup,tmp_path):
    b,pid,shop,seller,channel=setup
    sale(b,pid,'origin',channel_id=channel,seller_id=seller,seller='100')
    b.pay_commission(seller,'40','2026-01-11','Pix',key='p')
    dest=Database(tmp_path/'other.sqlite3')
    stage_restore(dest,b.db.backup(tmp_path/'copy.sqlite3').read_bytes())
    apply_pending_restore(dest.path)
    assert Business(dest).commission_balances()==b.commission_balances()


def test_new_pages_and_personal_form(setup):
    import asyncio
    from nicegui import ui
    from nicegui.testing import user_simulation
    from flow.ui import register_pages
    b,pid,*_=setup
    async def run():
        async with user_simulation() as user:
            register_pages(b)
            for route,label in [('/comissoes','Canais, pessoas e comissões.'),('/clientes','Clientes e suas histórias.'),('/relatorios','Formas de pagamento')]:
                await user.open(route)
                await user.should_see(label)
            await user.open('/vendas')
            user.find(kind=ui.button,content='Registrar venda').click()
            op=next(iter(user.find(kind=ui.select,content='Tipo de operação').elements))
            product=next(iter(user.find(kind=ui.select,content='Produto').elements))
            with user:
                next(iter(user.find(kind=ui.select,content='Local de saída das peças').elements)).set_value(1)
                op.set_value('personal');product.set_value(pid)
            user.find(kind=ui.button,content='Adicionar à venda').click()
            user.find(kind=ui.button,content='Confirmar venda').click()
            await user.should_see('Venda registrada e estoque atualizado.')
            assert b.db.rows('SELECT operation FROM sales')[0]['operation']=='personal'
            assert not b.db.rows('SELECT * FROM receivables')
    asyncio.run(run())


def test_channel_and_credit_form(setup):
    import asyncio
    from nicegui import ui
    from nicegui.testing import user_simulation
    from flow.ui import register_pages
    b,pid,shop,seller,channel=setup
    sale(b,pid,'origin',channel_id=channel,seller_id=seller,seller='100')
    async def run():
        async with user_simulation() as user:
            register_pages(b)
            await user.open('/vendas')
            user.find(kind=ui.button,content='Registrar venda').click()
            def select(label,val):
                el=next(iter(user.find(kind=ui.select,content=label).elements))
                with user:el.set_value(val)
            select('Canal de venda',channel);select('Local de saída das peças',1);select('Vendedora',seller);select('Produto',pid)
            user.find(kind=ui.button,content='Adicionar à venda').click()
            user.find(kind=ui.checkbox,content='Usar crédito de comissão').click()
            select('Beneficiário do crédito',seller)
            user.find(kind=ui.input,content='Crédito de comissão a utilizar (R$)').clear().type('100')
            user.find(kind=ui.input,content='Nome do cliente').type('Vendedora A')
            user.find(kind=ui.button,content='Confirmar venda').click()
            await user.should_see('Venda registrada e estoque atualizado.')
            record=b.db.rows('SELECT * FROM sales ORDER BY id DESC')[0]
            assert record['credit_cents']==10000 and record['seller_cents']==record['store_cents']==0
            assert record['channel_id']==channel and record['seller_id']==seller
    asyncio.run(run())


def test_full_credit_sale_has_no_cash_receipt(setup):
    b,pid,shop,seller,channel=setup
    for i in range(5):sale(b,pid,'origin'+str(i),channel_id=channel,seller_id=seller,seller='100')
    sid=sale(b,pid,'allcredit',sale_date='2026-02-01',paid_on='2026-02-01',credit='500',credit_beneficiary_id=seller)
    r=summary(b.db,'2026-02-01','2026-02-28')
    assert r['revenue_cents']==50000 and r['net_cents']==28000 and r['cash_in_cents']==0
    with pytest.raises(RuleError):b.correct_sale(sid,reason='Editar',items=[dict(product_id=pid,quantity=1,unit_price='400')],data=dict(sale_date='2026-02-01',method='Pix'))


def test_withdrawal_from_consigned_stock_creates_repass_only(tmp_path):
    from tests.helpers import fixture_xml
    b=Business(Database(tmp_path/'cons.sqlite3'))
    b.import_invoice(fixture_xml(),{'1':'estoque','2':'ignorar'},ownership='consigned')
    lot=b.consignment_lots()[0]
    sid=b.create_sale([dict(product_id=lot['product_id'],lot_id=lot['id'],quantity=1,unit_price='500')],dict(operation='personal',customer='Nanda',sale_date='2025-02-01'),key='retirada')
    r=summary(b.db,'2025-02-01','2025-02-28')
    assert r['revenue_cents']==r['net_cents']==r['cash_in_cents']==0
    assert r['consignment_payable_cents']==r['personal_cost_cents']==9500
    assert b.consignment_lots()[0]['stock']==1


def test_legacy_paid_commission_assignment_preserves_cash_and_historical_balance(setup):
    b,pid,shop,seller,channel=setup
    sale(b,pid,'legacy',seller='100')
    expense=b.db.rows("SELECT id FROM expenses WHERE category='Comissão vendedora'")[0]['id']
    b.pay_expense(expense,'2026-02-02')
    before=summary(b.db,'2026-01-01','2026-01-31')
    b.assign_legacy_commission(expense,seller)
    after=summary(b.db,'2026-01-01','2026-01-31')
    assert before['payable_cents']==after['payable_cents']==10000
    assert summary(b.db,'2026-02-01','2026-02-28')['cash_out_cents']==10000
    assert sum(r['balance_cents'] for r in b.commission_balances())==0


def test_withdrawal_cost_rebuild_and_restore_old_backup(tmp_path):
    # Genuine v4 database taken from the original shipped code, not a version label change.
    import zipfile,importlib.util
    from pathlib import Path
    archive=Path(__file__).resolve().parents[3]/'upload'/'Fe_Abbehusen_Flow_Python_v0.4.0.zip'
    if not archive.exists():
        pytest.skip('Original distribution not present on this computer')
    with zipfile.ZipFile(archive) as z:
        source=z.read('fe_flow/flow/db.py').decode()
    # Build v4 using a temporary package-relative module so original migrations resolve.
    import types
    module=types.ModuleType('flow.old_db');module.__package__='flow'
    exec(compile(source,'old_db.py','exec'),module.__dict__)
    old=module.Database(tmp_path/'old.sqlite3')
    with old.transaction() as c:
        c.execute("INSERT INTO sales(request_key,sale_date,customer,phone,method,subtotal_cents,discount_cents,revenue_cents,cost_cents,fee_cents,tax_cents,seller_cents,store_cents,net_cents) VALUES('legacy','2026-01-01','Cliente antigo','123','Pix',10000,0,10000,0,0,0,0,0,10000)")
    old.backup(tmp_path/'old-export.sqlite3')
    dest=Database(tmp_path/'dest.sqlite3')
    stage_restore(dest,(tmp_path/'old-export.sqlite3').read_bytes());apply_pending_restore(dest.path)
    assert Business(dest).customers()[0]['name']=='Cliente antigo'
    assert Business(dest).customers()[0]['total_cents']==10000


def test_create_channel_with_inline_beneficiary_from_empty_database(tmp_path):
    import asyncio
    from nicegui import ui
    from nicegui.testing import user_simulation
    from flow.ui import register_pages
    b=Business(Database(tmp_path/'empty.sqlite3'))
    async def run():
        async with user_simulation() as user:
            register_pages(b)
            await user.open('/comissoes')
            user.find(kind=ui.button,content='Novo canal').click()
            user.find(kind=ui.input,content='Nome do canal').type('SU MISURA')
            mode=next(iter(user.find(kind=ui.select,content='Regra de comissão').elements))
            with user:
                mode.set_value('store')
            user.find(kind=ui.input,content='Comissão do canal (%)').clear().type('15')
            with user:
                next(iter(user.find(kind=ui.select,content='Quem recebe a comissão do canal?').elements)).set_value('other')
            user.find(kind=ui.button,content='Cadastrar beneficiário aqui').click()
            person=next(iter(user.find(kind=ui.input,content='Nome da pessoa ou loja').elements))
            assert person.value=='SU MISURA'
            user.find(kind=ui.button,content='Salvar beneficiário').click()
            await user.should_see('Beneficiário salvo.')
            payee=next(iter(user.find(kind=ui.select,content='Quem recebe a parte da loja / canal').elements))
            assert payee.value==b.beneficiaries()[0]['id']
            user.find(kind=ui.button,content='Salvar canal').click()
            await user.should_see('Canal salvo.')
            channel=next(c for c in b.channels() if c['name']=='SU MISURA')
            assert channel['payee']=='SU MISURA'
            assert Decimal(channel['store_rate'])==15
            assert Decimal(channel['seller_rate'])==0
    asyncio.run(run())


def test_delete_unused_and_protect_linked_records(setup):
    b,pid,shop,seller,channel=setup
    unused=b.save_beneficiary('Temporária',channel_id=channel)
    b.delete_beneficiary(unused)
    assert all(r['id']!=unused for r in b.beneficiaries())
    empty=b.save_channel(dict(name='Teste',kind='Evento'))
    b.link_seller(empty,seller)
    b.delete_channel(empty)
    assert not b.sellers(empty)
    sale(b,pid,'linked-delete',channel_id=channel,seller_id=seller,store_cents=5000,seller_cents=5000)
    with pytest.raises(RuleError):b.delete_channel(channel)
    with pytest.raises(RuleError):b.delete_beneficiary(seller)
    with pytest.raises(RuleError):b.delete_beneficiary(shop)
    assert b.channels() and b.sellers(channel)


def test_customer_and_channel_period_aggregation(setup):
    b,pid,shop,seller,channel=setup
    sale(b,pid,'jan',channel_id=channel,seller_id=seller)
    sale(b,pid,'feb',sale_date='2026-02-10',paid_on='2026-02-10',channel_id=channel,seller_id=seller)
    sale(b,pid,'personal',operation='personal',customer='Nanda')
    jan=dashboard(b.db,'2026-01-01','2026-01-31')
    assert sum(r['count'] for r in jan['commercial_groups'])==1
    assert sum(r['revenue_cents'] for r in jan['customer_groups'])==50000
    whole=dashboard(b.db,'2026-01-01','2026-02-28')
    assert len(whole['customer_groups'])==1
    assert whole['customer_groups'][0]['count']==2


def test_commercial_tab_and_month_filter(setup):
    import asyncio
    from nicegui import ui
    from nicegui.testing import user_simulation
    from flow.ui import register_pages
    b,pid,shop,seller,channel=setup
    sale(b,pid,'chart',channel_id=channel,seller_id=seller)
    async def run():
        async with user_simulation() as user:
            register_pages(b)
            await user.open('/relatorios')
            user.find(kind=ui.button,content='Todo o histórico').click()
            user.find(kind=ui.tab,content='Canais e clientes').click()
            await user.should_see('Quantidade de vendas por canal')
            await user.should_see('Quantidade de vendas por vendedora')
            await user.should_see('Valor comprado por cliente')
            month=next(iter(user.find(kind=ui.input,content='Mês específico').elements))
            with user:month.set_value('2026-01')
            user.find(kind=ui.button,content='Aplicar mês').click()
            await user.should_see('Período aplicado: 2026-01-01 a 2026-01-31')
    asyncio.run(run())


def test_channel_auto_recipient_is_atomic_and_reused(tmp_path):
    b=Business(Database(tmp_path/'auto.sqlite3'))
    data=dict(name='Loja nova',kind='Loja',store_rate='30',channel_receives=True)
    cid=b.save_channel(data)
    ch=next(c for c in b.channels() if c['id']==cid)
    assert ch['payee']=='Loja nova'
    b.save_channel(dict(data,store_beneficiary_id=ch['store_beneficiary_id']),cid)
    assert len(b.beneficiaries())==1
    with pytest.raises(RuleError): b.save_channel(data)
    assert len(b.beneficiaries())==1


def test_overview_filters_origin_and_counts_payments_once(setup):
    b,pid,shop,seller,channel=setup
    other=b.save_channel(dict(name='Evento',kind='Evento',seller_rate='10'))
    b.link_seller(other,seller)
    sale(b,pid,'shop-sale',channel_id=channel,seller_id=seller,seller='50',store='50')
    sale(b,pid,'event-sale',channel_id=other,seller_id=seller,seller='80')
    b.pay_commission(seller,'70','2026-01-11','Pix',key='paid')
    rows,balances=b.commission_overview(channel_id=channel)
    person=next(r for r in balances if r['id']==seller)
    assert person['earned_cents']==5000 and person['cash_cents']==5000
    assert 'Evento' in person['channels'] and 'FIAES' in person['channels']
    assert rows[0]['sold_cents']==50000
    _,all_balances=b.commission_overview(seller_query='Vendedora A')
    assert sum(r['cash_cents'] for r in all_balances)==7000
    _,ev=b.commission_overview(kind='Evento')
    assert ev[0]['earned_cents']==8000 and ev[0]['cash_cents']==2000


def test_new_channel_self_recipient_and_dynamic_hint(tmp_path):
    import asyncio
    from nicegui import ui
    from nicegui.testing import user_simulation
    from flow.ui import register_pages
    b=Business(Database(tmp_path/'new-ui.sqlite3'))
    async def scenario():
        async with user_simulation() as user:
            register_pages(b)
            await user.open('/comissoes')
            user.find(kind=ui.button,content='Novo canal').click()
            user.find(kind=ui.input,content='Nome do canal').type('Canal teste')
            mode=next(iter(user.find(kind=ui.select,content='Regra de comissão').elements))
            with user: mode.set_value('seller')
            await user.should_see('Toda a comissão pertence à vendedora selecionada')
            await user.should_not_see('Na SU MISURA')
            with user: mode.set_value('store')
            user.find(kind=ui.input,content='Comissão do canal (%)').clear().type('30')
            user.find(kind=ui.button,content='Salvar canal').click()
            await user.should_see('Canal salvo.')
            ch=next(c for c in b.channels() if c['name']=='Canal teste')
            assert ch['payee']=='Canal teste' and Decimal(ch['store_rate'])==30
            assert next(l for l in b.locations() if l['id']==ch['location_id'])['name']=='Canal teste'
            await user.should_see('Total pago / utilizado:')
            await user.should_see('Filtrar tipo de canal')
    asyncio.run(scenario())


@pytest.mark.parametrize('kind',['Loja','Site','Evento','Direto'])
def test_channel_creates_stock_location_automatically(tmp_path,kind):
    b=Business(Database(tmp_path/'auto-local.sqlite3'))
    cid=b.save_channel(dict(name='Novo canal',kind=kind))
    channel=next(c for c in b.channels() if c['id']==cid)
    loc=next(l for l in b.locations() if l['id']==channel['location_id'])
    assert loc['name']=='Novo canal' and loc['active']==1
    assert not b.location_stock(loc['id'])
    b.save_channel(dict(name='Nome atualizado',kind=kind),cid)
    assert next(c for c in b.channels() if c['id']==cid)['location_id']==loc['id']
    assert len(b.locations())==3


def test_channel_reuses_location_and_preserves_custom_link(tmp_path):
    b=Business(Database(tmp_path/'reuse.sqlite3'))
    loc=b.save_location('Casa FIAES')
    b.save_location('Casa FIAES',loc,False)
    cid=b.save_channel(dict(name='CASA FIAES',kind='Loja'))
    assert next(c for c in b.channels() if c['id']==cid)['location_id']==loc
    assert next(l for l in b.locations() if l['id']==loc)['active']==1
    b.set_channel_location(cid,2)
    b.save_channel(dict(name='Casa FIAES',kind='Loja'),cid)
    assert next(c for c in b.channels() if c['id']==cid)['location_id']==2
    assert len(b.locations())==3
    with pytest.raises(RuleError): b.save_channel(dict(name='Casa FIAES',kind='Loja'))
    assert len(b.locations())==3
