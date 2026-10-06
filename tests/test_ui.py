"""Integração das telas com o simulador oficial do NiceGUI (sem navegador gráfico)."""
import asyncio
import logging
from nicegui import ui
from nicegui.testing import user_simulation
from flow.db import Database
from flow.service import Business
from flow.ui import register_pages
from flow.demo import seed


def test_all_pages_and_dialogs(tmp_path, caplog):
    async def scenario():
        business = Business(Database(tmp_path / 'demo.sqlite3'))
        seed(business)
        async with user_simulation() as user:
            register_pages(business, demo=True)
            await user.open('/')
            from flow.money import today, add_months
            initial = next(iter(user.find(kind=ui.input, content='De').elements))
            assert initial.value == add_months(today()[:7] + '-01', -5)
            user.find(kind=ui.input, content='De').clear().type('2025-01-01')
            user.find(kind=ui.input, content='Até').clear().type('2025-12-31')
            user.find(kind=ui.button, content='Aplicar período').click()
            await user.should_see('De 01/01/2025 a 31/12/2025 · valores em R$')
            chart = next(iter(user.find(kind=ui.echart).elements))
            assert len(chart.options['xAxis']['data']) == 12
            for route, title in [('/', 'Seu negócio, em perspectiva.'),
                                 ('/estoque', 'Cada peça, no seu lugar.'),
                                 ('/compras', 'Do XML ao estoque.'),
                                 ('/vendas', 'Boas vendas, bem registradas.'),
                                 ('/despesas', 'Compromissos sob controle.'),
                                 ('/relatorios', 'Números que você consegue explicar.')]:
                await user.open(route)
                await user.should_see(title)
            await user.open('/estoque')
            user.find(kind=ui.button, content='Adicionar produto').click()
            await user.should_see('Código completo / SKU')
            await user.open('/vendas')
            user.find(kind=ui.button, content='Registrar venda').click()
            await user.should_see('Preço efetivo por peça (R$)')
            await user.open('/despesas')
            user.find(kind=ui.button, content='Adicionar despesa').click()
            await user.should_see('Descrição da despesa')
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_pending_history_pages_and_delete_cancelled_test(tmp_path, caplog):
    from .test_history import purchase
    from .test_business import sale

    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        pid = purchase(business, '2025-03-01', '400.00')
        sid = sale(business, pid, sale_date='2025-02-01', historical=True)
        async with user_simulation() as user:
            register_pages(business)
            for route in ['/', '/estoque', '/compras', '/vendas', '/relatorios']:
                await user.open(route)
                await user.should_see('Histórico em conferência · 1 pendência(s)')
            business.cancel_sale(sid, 'Teste fictício', when='2025-03-02')
            await user.open('/vendas')
            tbl = next(t for t in user.find(kind=ui.table).elements
                       if any(r.get('sale_date') for r in t.rows))
            with user:
                tbl.selected = [next(r for r in tbl.rows if r['id'] == sid)]
            user.find(kind=ui.button, content='Cancelar venda').click()
            user.find('Motivo do cancelamento').type('Lançamento incorreto')
            user.find(kind=ui.button, content='Confirmar cancelamento').click()
            await user.should_see('Lançamento removido e saldos recalculados.')
            assert not business.db.rows('SELECT * FROM sales')
            assert business.product(pid)['stock'] == 2
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_create_product_sale_and_expense_through_ui(tmp_path, caplog):
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/estoque')
            user.find(kind=ui.button, content='Adicionar produto').click()
            user.find('Nome do produto').type('Brinco de teste da interface')
            user.find('Código completo / SKU').type('UI-001')
            user.find('Quantidade de entrada').clear().type('3')
            user.find('Custo por peça (R$)').clear().type('100')
            user.find('Preço de venda (R$)').clear().type('230')
            user.find(kind=ui.button, content='Salvar produto').click()
            await user.should_see('Produto salvo.')
            product = business.products()[0]
            assert product['stock'] == 3
            await user.open('/vendas')
            user.find(kind=ui.button, content='Registrar venda').click()
            selected = next(iter(user.find(kind=ui.select, content='Produto').elements))
            with user:
                next(iter(user.find(kind=ui.select, content='Local de saída das peças').elements)).set_value(1)
                selected.set_value(product['id'])
            user.find(kind=ui.button, content='Adicionar à venda').click()
            user.find('Nome do cliente').type('Cliente UI')
            user.find(kind=ui.button, content='Confirmar venda').click()
            await user.should_see('Venda registrada e estoque atualizado.')
            assert business.product(product['id'])['stock'] == 2
            assert business.db.rows('SELECT customer FROM sales')[0]['customer'] == 'Cliente UI'
            await user.open('/despesas')
            user.find(kind=ui.button, content='Adicionar despesa').click()
            user.find('Descrição da despesa').type('Teste de embalagem')
            user.find('Valor (R$)').clear().type('35,90')
            user.find(kind=ui.button, content='Salvar despesa').click()
            await user.should_see('Despesa registrada.')
            assert business.db.rows('SELECT amount_cents FROM expenses')[0]['amount_cents'] == 3590
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_batch_payment_through_ui(tmp_path, caplog):
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        for i in range(2):
            business.create_expense({'occurred_on': '2025-01-01', 'amount': '25', 'description': f'Despesa {i}', 'category': 'Marketing'}, key=str(i))
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/despesas')
            tbl = next(iter(user.find(kind=ui.table).elements))
            assert tbl.selection == 'multiple'
            with user:
                tbl.selected = list(tbl.rows)
            user.find(kind=ui.button, content='Pagar selecionadas').click()
            await user.should_see('2 despesa(s) · Total R$ 50,00')
            user.find('Data do pagamento').clear().type('2025-02-01')
            user.find(kind=ui.button, content='Confirmar pagamentos').click()
            await user.should_see('Pagamentos registrados.')
            assert all(r['paid_on'] == '2025-02-01' for r in business.db.rows('SELECT paid_on FROM expenses'))
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_consignment_sale_and_return_through_ui(tmp_path, caplog):
    from .helpers import fixture_xml
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        business.import_invoice(fixture_xml(), {'1': 'estoque', '2': 'ignorar'}, ownership='consigned')
        pid = business.products()[0]['id']
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/consignacoes')
            await user.should_see('Peças consignadas, contas separadas.')
            await user.open('/vendas')
            user.find(kind=ui.button, content='Registrar venda').click()
            selected = next(iter(user.find(kind=ui.select, content='Produto').elements))
            with user:
                next(iter(user.find(kind=ui.select, content='Local de saída das peças').elements)).set_value(1)
                selected.set_value(pid)
            source = next(iter(user.find(kind=ui.select, content='Origem da peça').elements))
            assert '2 disponíveis' in selected.options[pid]
            assert source.value == 1  # Único lote disponível é selecionado automaticamente.
            user.find('Preço efetivo por peça (R$)').clear().type('210')
            user.find(kind=ui.button, content='Adicionar à venda').click()
            user.find(kind=ui.button, content='Confirmar venda').click()
            await user.should_see('Venda registrada e estoque atualizado.')
            assert business.consignment_lots()[0]['stock'] == 1
            assert business.product(pid)['stock'] == 0
            assert business.db.rows('SELECT amount_cents FROM expenses')[0]['amount_cents'] == 9500
            await user.open('/consignacoes')
            tbl = next(t for t in user.find(kind=ui.table).elements if any('invoice_number' in r for r in t.rows))
            with user:
                tbl.selected = [tbl.rows[0]]
            user.find(kind=ui.button, content='Devolver peças à matriz').click()
            user.find('Motivo da devolução').type('Fim da consignação')
            user.find(kind=ui.button, content='Confirmar devolução').click()
            await user.should_see('Devolução registrada.')
            assert business.consignment_lots()[0]['stock'] == 0
            await user.open('/consignacoes')
            returns = next(t for t in user.find(kind=ui.table).elements if any('cancellation_reason' in r for r in t.rows))
            with user:
                returns.selected = [returns.rows[0]]
            user.find(kind=ui.button, content='Cancelar devolução').click()
            user.find('Motivo da correção').type('Peça ainda está comigo')
            user.find(kind=ui.button, content='Confirmar cancelamento da devolução').click()
            await user.should_see('Devolução cancelada. Saldo consignado restaurado.')
            assert business.consignment_lots()[0]['stock'] == 1
            assert business.consignment_lots()[0]['returned'] == 0
            for route in ['/', '/estoque', '/relatorios', '/compras']:
                await user.open(route)
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_consignment_xml_preview_and_import(tmp_path, caplog):
    from .helpers import fixture_xml
    from nicegui.elements.upload_files import SmallFileUpload
    from nicegui import app, events
    app.config.reconnect_timeout = 3
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/compras')
            upload = next(iter(user.find(kind=ui.upload).elements))
            with user:
                await upload.handle_uploads([SmallFileUpload('teste.xml', 'application/xml', fixture_xml())])
            await user.should_see('Modalidade da entrada')
            modality = next(iter(user.find(kind=ui.select, content='Modalidade da entrada').elements))
            with user:
                modality.set_value('consigned')
            button = next(iter(user.find(kind=ui.button, content='Confirmar importação').elements))
            # A prévia remove o próprio botão; usa cópia dos listeners no simulador.
            with user:
                for listener in list(button._event_listeners.values()):
                    events.handle_event(listener.handler, events.GenericEventArguments(sender=button, client=user.client, args=None))
            await user.should_see('Entrada importada. Estoque e contas atualizados conforme a modalidade.')
            assert len(business.consignment_lots()) == 2
            assert not business.db.rows('SELECT * FROM expenses')
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_consignment_totals_remain_global_when_searching(tmp_path, caplog):
    from .helpers import fixture_xml
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        business.import_invoice(fixture_xml(), {'1': 'estoque', '2': 'ignorar'}, ownership='consigned')
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/estoque')
            await user.should_see('Nenhuma peça própria encontrada')
            await user.open('/consignacoes')
            await user.should_see('Peças consignadas em mãos')
            await user.should_see('Valor consignado em mãos')
            user.find('Buscar peça ou NF-e').type('inexistente')
            await user.should_see('Neste filtro: 0 peças · R$ 0,00 a custo de repasse')
            await user.should_see('R$ 190,00')
            await user.should_see('2')
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_return_values_and_sales_origin_search(tmp_path, caplog):
    from .test_consignment import receive, sell
    from .test_business import product, sale
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        pid = receive(business)
        business.return_consignment(1, 2, 'Devolução', when='2025-01-20')
        returned = business.db.rows("SELECT id FROM consignment_moves WHERE kind='RETURN'")[0]['id']
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/consignacoes')
            await user.should_see('Total devolvido ativo: 2 peças · R$ 190,00')
            tbl = next(t for t in user.find(kind=ui.table).elements if any('unit_value' in r for r in t.rows))
            assert tbl.rows[0]['unit_value'] == 'R$ 95,00'
            assert tbl.rows[0]['total_value'] == 'R$ 190,00'
            business.cancel_consignment_return(returned, 'Erro de lançamento')
            await user.open('/consignacoes')
            await user.should_see('Total devolvido ativo: 0 peças · R$ 0,00')
            own = product(business)
            sale(business, own, key='own', customer='Cliente exclusivo')
            cancelled = sell(business, pid, key='cancelled')
            business.cancel_sale(cancelled, 'Teste', when='2025-02-01')
            consigned = sell(business, pid, key='consigned')
            mixed = business.create_sale([
                {'product_id': own, 'quantity': 1, 'unit_price': '230'},
                {'product_id': pid, 'lot_id': 1, 'quantity': 1, 'unit_price': '210'},
            ], {'sale_date': '2025-02-02', 'method': 'Pix'}, key='mixed')
            for term in ['CONSIG', 'Consignada', 'consignacao']:
                await user.open('/vendas')
                user.find('Buscar cliente, evento, origem ou peça').type(term)
                await user.should_see('Neste filtro: 2 vendas não canceladas · 1 peças próprias · 2 peças consignadas · 1 vendas canceladas')
                tbl = next(t for t in user.find(kind=ui.table).elements if any('sale_date' in r for r in t.rows))
                assert {r['id'] for r in tbl.rows} == {cancelled, consigned, mixed}
            await user.open('/vendas')
            user.find('Buscar cliente, evento, origem ou peça').type('Cliente exclusivo')
            await user.should_see('Neste filtro: 1 vendas não canceladas · 1 peças próprias · 0 peças consignadas · 0 vendas canceladas')
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_edit_and_remove_paid_consignment_sale_ui(tmp_path, caplog):
    from .test_consignment import receive, sell
    from nicegui import events
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        pid = receive(business)
        sid = sell(business, pid, qty=2, paid_on='2025-02-01')
        business.pay_expense(business.db.rows('SELECT id FROM expenses')[0]['id'], '2025-02-02')
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/vendas')
            await user.should_not_see('Excluir teste cancelado')
            tbl = next(t for t in user.find(kind=ui.table).elements if any('sale_date' in r for r in t.rows))
            with user:
                tbl.selected = [tbl.rows[0]]
            user.find(kind=ui.button, content='Editar venda').click()
            await user.should_see(f'Editar venda #{sid}')
            # Alterar peça remove a linha da prévia e seu próprio botão.
            edit_button = next(iter(user.find(kind=ui.button, content='Alterar peça').elements))
            with user:
                for listener in list(edit_button._event_listeners.values()):
                    events.handle_event(listener.handler, events.GenericEventArguments(sender=edit_button, client=user.client, args=None))
            user.find('Quantidade').clear().type('1')
            user.find('Markup para calcular preço').clear().type('3')
            user.find(kind=ui.button, content='Aplicar markup ao preço').click()
            assert next(iter(user.find('Preço efetivo por peça (R$)').elements)).value == '285'
            user.find(kind=ui.button, content='Adicionar à venda').click()
            user.find('Motivo da alteração').type('Corrigir quantidade e preço')
            user.find(kind=ui.button, content='Salvar alterações').click()
            await user.should_see('Venda atualizada e saldos recalculados.')
            result = business.sale_snapshot(sid)
            assert result['sale']['revenue_cents'] == 28500
            assert result['expenses'][0]['amount_cents'] == 9500
            assert result['expenses'][0]['paid_on'] == '2025-02-02'
            assert business.consignment_lots()[0]['stock'] == 1
            await user.open('/vendas')
            tbl = next(t for t in user.find(kind=ui.table).elements if any('sale_date' in r for r in t.rows))
            with user:
                tbl.selected = [tbl.rows[0]]
            user.find(kind=ui.button, content='Cancelar venda').click()
            user.find('Motivo do cancelamento').type('Venda fictícia')
            user.find(kind=ui.button, content='Confirmar cancelamento').click()
            await user.should_see('Lançamento removido e saldos recalculados.')
            assert business.consignment_lots()[0]['stock'] == 2
            assert not business.db.rows('SELECT * FROM sales')
            assert not business.db.rows('SELECT * FROM expenses')
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_correct_invoice_destinations_ui(tmp_path, caplog):
    from .helpers import fixture_xml
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        iid = business.import_invoice(fixture_xml(), {'1': 'estoque', '2': 'estoque'}, paid_on='2025-01-20')
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/compras')
            tbl = next(t for t in user.find(kind=ui.table).elements if any('number' in r for r in t.rows))
            with user:
                tbl.selected = [tbl.rows[0]]
            user.find(kind=ui.button, content='Corrigir importação').click()
            selector = next(iter(user.find(kind=ui.select, content='Destino do item 2').elements))
            assert selector.value == 'estoque'
            with user:
                selector.set_value('despesa')
            user.find('Motivo da correção da importação').type('Embalagem não é peça de revenda')
            user.find(kind=ui.button, content='Salvar correção da importação').click()
            await user.should_see('Importação corrigida. Estoque e despesas recalculados.')
            result = business.invoice_snapshot(iid)
            assert result['items'][1]['destination'] == 'despesa'
            assert len(result['expenses']) == 2
            assert result['expenses'][1]['paid_on'] == '2025-01-20'
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_delete_imported_invoice_ui(tmp_path, caplog):
    from .helpers import fixture_xml
    async def scenario():
        business = Business(Database(tmp_path / 'flow.sqlite3'))
        business.import_invoice(fixture_xml(number=123), {'1':'estoque','2':'despesa'}, paid_on='2025-01-20')
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/compras')
            tbl = next(t for t in user.find(kind=ui.table).elements if any('number' in r for r in t.rows))
            with user:
                tbl.selected = [tbl.rows[0]]
            user.find(kind=ui.button, content='Excluir nota importada').click()
            await user.should_see('Contas vinculadas: R$ 210,00 · Baixas registradas: R$ 210,00')
            user.find('Motivo da exclusão da nota').type('Importação de teste')
            user.find('Digite EXCLUIR NOTA 123').type('EXCLUIR NOTA 123')
            user.find(kind=ui.button, content='Confirmar exclusão da nota').click()
            await user.should_see('Nota excluída. Saldos recalculados e backup preservado.')
            assert not business.db.rows('SELECT * FROM invoices')
            assert not business.db.rows('SELECT * FROM expenses')
            assert business.products()[0]['stock']==0
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_dashboard_report_tabs_period_and_origin_filter(tmp_path, caplog):
    from .test_consignment import receive, sell
    from .test_business import product, sale
    async def scenario():
        business=Business(Database(tmp_path/'flow.sqlite3'))
        pid=receive(business)
        sell(business,pid,paid_on='2025-02-01')
        own=product(business)
        sale(business,own)
        async with user_simulation() as user:
            register_pages(business)
            await user.open('/relatorios')
            user.find(kind=ui.input,content='De').clear().type('2025-01-01')
            user.find(kind=ui.input,content='Até').clear().type('2025-12-31')
            user.find(kind=ui.button,content='Atualizar relatório').click()
            await user.should_see('Período aplicado: 2025-01-01 a 2025-12-31')
            charts=list(user.find(kind=ui.echart).elements)
            trends=[c for c in charts if c.options.get('xAxis',{}).get('type')=='category']
            assert len(trends)==2
            assert all(len(c.options['xAxis']['data'])==12 for c in trends)
            for name in ['Caixa','Vendas','Estoque e consignação','Resultado']:
                user.find(kind=ui.tab,content=name).click()
            user.find(kind=ui.tab,content='Vendas').click()
            selector=next(iter(user.find(kind=ui.select,content='Origem das peças — somente Vendas').elements))
            with user:
                selector.set_value('consigned')
            await user.should_see('Contribuição das vendas: R$ 115,00 · Após custo, taxas, impostos e comissões; antes das despesas gerais.')
            tables=list(user.find(kind=ui.table).elements)
            sale_table=next(t for t in tables if t.rows and 'origin_label' in t.rows[0])
            assert len(sale_table.rows)==1 and sale_table.rows[0]['origin_label']=='Consignada'
            assert sale_table.rows[0]['revenue']=='R$ 210,00'
            user.find(kind=ui.button,content='Últimos 12 meses').click()
            from flow.money import today, add_months
            await user.should_see(f"Período aplicado: {add_months(today()[:7]+'-01',-11)} a {today()}")
            user.find(kind=ui.input,content='De').clear().type('2025-12-31')
            user.find(kind=ui.input,content='Até').clear().type('2025-01-01')
            user.find(kind=ui.button,content='Atualizar relatório').click()
            await user.should_see('A data inicial deve ser anterior ou igual à final.')
    asyncio.run(scenario())
    assert not [r.message for r in caplog.records if r.levelno>=logging.ERROR]


def test_shop_rates_credit_toggle_and_edit(tmp_path):
    async def scenario():
        b=Business(Database(tmp_path/'comm.sqlite3'))
        pid=b.create_product({'sku':'SM','name':'Joia SM','selling_price':'1325.47'},quantity=2,unit_cost='200',when='2026-01-01')
        payee=b.save_beneficiary('Su Misura')
        cid=b.save_channel(dict(name='Su Misura',kind='Loja',store_rate='30',seller_rate='0',store_beneficiary_id=payee))
        async with user_simulation() as user:
            register_pages(b)
            await user.open('/vendas')
            user.find(kind=ui.button,content='Registrar venda').click()
            def element(kind,label): return next(iter(user.find(kind=kind,content=label).elements))
            with user:
                element(ui.select,'Canal de venda').set_value(cid)
                element(ui.select,'Local de saída das peças').set_value(1)
                element(ui.select,'Produto').set_value(pid)
            store=element(ui.input,'Comissão loja / evento (%)')
            credit=element(ui.checkbox,'Usar crédito de comissão')
            assert str(store.value)=='30'
            with user: credit.set_value(True)
            assert str(store.value)=='0'
            user.find(kind=ui.button,content='Aplicar percentuais do canal').click()
            assert str(store.value)=='0'
            with user: credit.set_value(False)
            assert str(store.value)=='30'
            user.find(kind=ui.button,content='Adicionar à venda').click()
            user.find(kind=ui.button,content='Confirmar venda').click()
            await user.should_see('Venda registrada e estoque atualizado.')
            row=b.db.rows('SELECT * FROM sales')[0]
            assert row['store_cents']==39764 and row['seller_id'] is None
            assert next(x for x in b.commission_balances() if x['id']==payee)['balance_cents']==39764
            b.correct_sale(row['id'],reason='Teste de percentual antigo',items=[dict(product_id=pid,quantity=1,unit_price='1325.47')],data=dict(sale_date=row['sale_date'],channel_id=cid,method='Pix',store='0'))
            await user.open('/vendas')
            tbl=next(t for t in user.find(kind=ui.table).elements if any(r.get('sale_date') for r in t.rows))
            with user: tbl.selected=[next(r for r in tbl.rows if r['id']==row['id'])]
            user.find(kind=ui.button,content='Editar venda').click()
            assert str(element(ui.input,'Comissão loja / evento (%)').value)=='0.00'
            await user.should_see('Atenção: comissão zerada nesta venda')
            user.find(kind=ui.button,content='Aplicar percentuais do canal').click()
            assert str(element(ui.input,'Comissão loja / evento (%)').value)=='30'
            user.find('Motivo da alteração').type('Aplicar comissão Su Misura')
            user.find(kind=ui.button,content='Salvar alterações').click()
            await user.should_see('Venda atualizada e saldos recalculados.')
            assert b.db.rows('SELECT store_cents FROM sales')[0]['store_cents']==39764
    asyncio.run(scenario())


def test_locations_page_batch_transfer_and_channel_sale(tmp_path):
    async def scenario():
        from flow.money import today
        b=Business(Database(tmp_path/'locui.sqlite3'))
        pid=b.create_product(dict(name='Anel local',sku='LOC',selling_price='100'),quantity=3,unit_cost='20',when=today())
        loc=b.save_location('SU MISURA')
        cid=b.save_channel(dict(name='SU MISURA',kind='Loja'))
        b.set_channel_location(cid,loc)
        async with user_simulation() as user:
            register_pages(b)
            await user.open('/locais')
            await user.should_see('Onde estão suas peças?')
            user.find(kind=ui.button,content='Distribuir / transferir peças').click()
            def el(kind,label): return next(iter(user.find(kind=kind,content=label).elements))
            with user:
                el(ui.select,'Destino').set_value(loc)
                piece=el(ui.select,'Peça / variante / propriedade')
                piece.set_value(next(iter(piece.options)))
            user.find(kind=ui.button,content='Adicionar peça').click()
            user.find(kind=ui.button,content='Confirmar transferência').click()
            await user.should_see('Transferência registrada.')
            assert b.location_stock(loc)[0]['quantity']==1
            await user.open('/vendas')
            user.find(kind=ui.button,content='Registrar venda').click()
            with user: el(ui.select,'Canal de venda').set_value(cid)
            assert el(ui.select,'Local de saída das peças').value==loc
            with user: el(ui.select,'Produto').set_value(pid)
            user.find(kind=ui.button,content='Adicionar à venda').click()
            user.find(kind=ui.button,content='Confirmar venda').click()
            await user.should_see('Venda registrada e estoque atualizado.')
            assert not b.location_stock(loc)
            await user.open('/relatorios')
            await user.should_see('Unidades por local na data final')
    asyncio.run(scenario())


def test_sale_filter_all_locations_and_mixed_cart(tmp_path):
    async def scenario():
        from flow.money import today
        b=Business(Database(tmp_path/'mixed.sqlite3'))
        pid=b.create_product(dict(sku='MIX',name='Brinco misto',selling_price='100'),quantity=3,unit_cost='20',when=today())
        other=b.create_product(dict(sku='OTHER',name='Peça somente Nanda',selling_price='100',location_id=2),quantity=1,unit_cost='20',when=today())
        loc=b.save_location('Casa FIAES')
        b.transfer_stock([dict(product_id=pid,quantity=1)],1,loc,reason='Loja',key='loja')
        b.transfer_stock([dict(product_id=pid,quantity=1)],1,2,reason='Nanda',key='nanda')
        async with user_simulation() as user:
            register_pages(b)
            await user.open('/vendas')
            user.find(kind=ui.button,content='Registrar venda').click()
            def el(kind,label): return next(iter(user.find(kind=kind,content=label).elements))
            location=el(ui.select,'Local de saída das peças');product=el(ui.select,'Produto')
            await user.should_see('Origem da peça (Estoque próprio ou Consignado)')
            with user: location.set_value(loc)
            assert pid in product.options and other not in product.options
            with user: product.set_value(pid)
            user.find(kind=ui.button,content='Adicionar à venda').click()
            assert pid not in product.options
            with user: location.set_value(0)
            assert f'{pid}:2' in product.options and f'{pid}:{loc}' not in product.options
            with user: product.set_value(f'{pid}:2')
            assert location.value==2 and product.value==pid
            user.find(kind=ui.button,content='Adicionar à venda').click()
            # Changing a filter must not change items already in the cart.
            with user: location.set_value(1)
            user.find(kind=ui.button,content='Confirmar venda').click()
            await user.should_see('Venda registrada e estoque atualizado.')
            sid=b.db.rows('SELECT id FROM sales')[0]['id']
            alloc=b.sale_snapshot(sid)['sale_locations']
            assert {(a['location_id'],a['quantity']) for a in alloc}=={(loc,1),(2,1)}
            await user.open('/vendas')
            tbl=next(t for t in user.find(kind=ui.table).elements if any(r.get('sale_date') for r in t.rows))
            with user: tbl.selected=[next(r for r in tbl.rows if r['id']==sid)]
            user.find(kind=ui.button,content='Editar venda').click()
            user.find('Motivo da alteração').type('Conferência dos locais')
            user.find(kind=ui.button,content='Salvar alterações').click()
            await user.should_see('Venda atualizada e saldos recalculados.')
            assert {(a['location_id'],a['quantity']) for a in b.sale_snapshot(sid)['sale_locations']}=={(loc,1),(2,1)}
    asyncio.run(scenario())
