"""Telas NiceGUI. Os callbacks delegam toda alteração de dados a Business."""
import logging
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from nicegui import ui, app
from .backup_restore import stage_restore, MAX_BACKUP_BYTES
from . import reports
from .benchmarks import fetch_benchmarks
from .money import RuleError, add_months, brl, cents, day, decimal, percent, pieces, rounded, today
from .nfe import MAX_XML_BYTES, DEFAULT_SUPPLIER, parse_xml

NAV = [('/', 'Painel', 'dashboard'), ('/estoque', 'Estoque', 'diamond'),
       ('/compras', 'Compras e XML', 'file_upload'), ('/vendas', 'Vendas', 'shopping_bag'),
       ('/clientes', 'Clientes', 'people'), ('/comissoes', 'Comissões', 'payments'),
       ('/consignacoes', 'Consignação', 'inventory_2'), ('/despesas', 'Despesas', 'account_balance_wallet'), ('/relatorios', 'Relatórios', 'bar_chart')]

CSS = '''
:root {--ink:#213e35;--muted:#738279;--line:#e1e8e3;--paper:#f5f7f4;--green:#11634b;}
body {background:var(--paper);font-family:Inter,Segoe UI,Arial,sans-serif;color:var(--ink);font-size:14px;}
.nicegui-content {padding:0;gap:0;}
.app-shell {width:100%;min-height:100vh;display:flex;}
.sidebar {width:226px;flex-shrink:0;padding:34px 22px;background:#fff;border-right:1px solid var(--line);position:fixed;inset:0 auto 0 0;overflow-y:auto;display:flex;flex-direction:column;gap:10px;}
.brand {font-family:Georgia,serif;font-size:22px;line-height:1.1;letter-spacing:-.5px;}
.brand-small {font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-top:7px;}
.nav-link {display:flex;align-items:center;gap:12px;color:#6d7d75;text-decoration:none;padding:13px 14px;border-radius:9px;font-weight:500;}
.nav-link:hover {background:#f5f8f6;}
.nav-active {background:#e8f2ed;color:#0e634a;font-weight:650;}
.main {margin-left:226px;padding:0 44px 44px;width:calc(100% - 226px);min-width:0;}
.topbar {height:80px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;margin-bottom:34px;}
.top-eyebrow {text-transform:uppercase;letter-spacing:2px;font-size:10px;color:var(--muted);}
.heading {font-family:Georgia,serif;font-size:34px;font-weight:400;letter-spacing:-.7px;line-height:1.2;}
.page-head {display:flex;justify-content:space-between;align-items:center;gap:20px;width:100%;margin-bottom:24px;flex-wrap:wrap;}
.muted {color:var(--muted);font-size:13px;line-height:1.6;}
.surface {background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:none;width:100%;padding:24px;}
.section-title {font-weight:600;font-size:16px;letter-spacing:-.2px;}
.metric-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;width:100%;margin-bottom:24px;}
.metric {background:#fff;border:1px solid var(--line);border-radius:13px;padding:22px;min-width:0;}
.metric-value {font-size:27px;font-weight:600;letter-spacing:-1px;white-space:nowrap;}
.metric-label {font-size:12px;color:#738279;margin-bottom:14px;}
.metric-featured {background:#155b46;color:white;border-color:#155b46;}
.metric-featured .metric-label,.metric-featured .muted {color:#c5dbcf;}
.two-col {display:grid;grid-template-columns:minmax(0,1.8fr) minmax(280px,1fr);gap:22px;width:100%;margin-bottom:24px;}
.formgrid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;width:100%;}
.wide {grid-column:1/-1;}
.q-field {width:100%;}
.q-btn {text-transform:none;letter-spacing:0;border-radius:8px;font-weight:550;}
.q-btn--unelevated {box-shadow:none;}
.q-dialog__inner>.q-card {max-width:94vw;}
.dialog-card {width:790px;padding:28px;max-height:90vh;overflow-y:auto;gap:18px;}
.dialog-small {width:510px;}
.nicegui-table {width:100%;border-radius:10px;box-shadow:none;border:1px solid var(--line);}
.q-table thead tr {background:#f6f8f5;}
.q-table th {font-size:11px;letter-spacing:.4px;color:#718077;white-space:nowrap;}
.q-table td {font-size:13px;height:57px;}
.q-table__container {max-width:100%;}
.product-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;width:100%;}
.product-card {background:white;border:1px solid var(--line);border-radius:13px;overflow:hidden;}
.product-icon {height:102px;background:linear-gradient(130deg,#edf3ec,#f9f7ef);display:flex;align-items:center;justify-content:center;}
.product-body {padding:20px;display:flex;flex-direction:column;gap:12px;}
.pill {background:#edf5f0;color:#28664e;border-radius:20px;padding:4px 10px;font-size:11px;}
.list-line {display:flex;justify-content:space-between;align-items:center;gap:12px;width:100%;padding:12px 0;border-bottom:1px solid #edf0eb;}
.empty {padding:52px 24px;text-align:center;width:100%;align-items:center;gap:10px;}
.mobile-nav {display:none;}
.demo-ribbon {background:#fff4da;border:1px solid #ecddb6;padding:10px 16px;border-radius:8px;margin-bottom:20px;font-size:12px;}
.info-panel {background:#edf4ef;border-radius:10px;padding:16px;width:100%;font-size:13px;line-height:1.65;}
.danger {color:#b74d42;}
.footer-actions {display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap;width:100%;padding-top:8px;}
@media(min-width:1600px){.main{padding-left:64px;padding-right:64px;}}
@media(max-width:1200px){.main{padding:0 25px 30px;}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr));}.product-grid{grid-template-columns:repeat(2,minmax(0,1fr));}.two-col{grid-template-columns:1fr;}}
@media(max-width:850px){.sidebar{display:none;}.main{margin-left:0;width:100%;padding:0 18px 28px;}.mobile-nav{display:flex;overflow:auto;gap:6px;margin:0 -18px 22px;padding:0 14px 12px;border-bottom:1px solid var(--line);}.nav-link{white-space:nowrap;padding:10px;font-size:12px;}.topbar{height:65px;margin-bottom:14px;}.heading{font-size:29px;}.top-eyebrow{font-size:9px;}}
@media(max-width:520px){.metric-grid{gap:10px;}.metric{padding:15px;}.metric-value{font-size:21px;}.metric-label{font-size:11px;}.product-grid{grid-template-columns:1fr;}.formgrid{grid-template-columns:1fr;}.dialog-card{padding:20px;}.surface{padding:18px;}.page-head{gap:14px;}.footer-actions .q-btn{flex:1;}.q-table td{font-size:12px;}}
'''


def field(label, value='', *, kind=None):
    element = ui.input(label, value=str(value if value is not None else '')).props('outlined dense')
    if kind:
        element.props(f'type={kind}')
    return element


def money_field(label, value='0,00'):
    return field(label, value).props('inputmode=decimal')


def button(text, callback, *, icon=None, secondary=False, color=None):
    return ui.button(text, on_click=callback, icon=icon, color=color or 'primary').props('outline' if secondary else 'unelevated')


def perform(action, message, after=None):
    try:
        result = action()
    except RuleError as exc:
        ui.notify(str(exc), type='warning', position='top', timeout=7500, close_button=True)
        return None
    except Exception:
        logging.exception('Falha ao executar operação')
        ui.notify('Não foi possível concluir. A operação não foi confirmada; consulte o terminal.',
                  type='negative', position='top', timeout=7000, close_button=True)
        return None
    ui.notify(message, type='positive', position='top', timeout=2800)
    if after:
        after()
    return result


def empty(title, subtitle='', icon='inventory_2'):
    with ui.column().classes('surface empty'):
        ui.icon(icon, size='38px').style('color:#93ada0')
        ui.label(title).classes('section-title')
        ui.label(subtitle).classes('muted')


def metric(label, value, subtitle, icon, featured=False):
    with ui.element('div').classes('metric' + (' metric-featured' if featured else '')):
        with ui.row().classes('w-full justify-between items-center'):
            ui.label(label).classes('metric-label')
            ui.icon(icon, size='19px').style('opacity:.7;margin-top:-12px')
        ui.label(value).classes('metric-value')
        ui.label(subtitle).classes('muted mt-2')


def table(rows, fields, *, selection=None):
    return ui.table(rows=rows, columns=[{'name': key, 'field': key, 'label': title, 'align': 'left',
                                       'sortable': True} for key, title in fields],
                    row_key='id', pagination=12, selection=selection).props('flat')


def choose(tbl, callback):
    if not tbl.selected:
        ui.notify('Selecione uma linha na tabela.', type='info')
    elif len(tbl.selected) > 1:
        ui.notify('Para esta ação, selecione somente uma linha.', type='info')
    else:
        callback(tbl.selected[0])


def register_pages(business, *, demo=False):
    db = business.db
    ui.add_css(CSS, shared=True)

    def shell(path, eyebrow):
        ui.colors(primary='#11634b', secondary='#6d8b7e', accent='#ad8958', positive='#227653', negative='#bd5147')
        root = ui.element('div').classes('app-shell')
        with root:
            with ui.element('aside').classes('sidebar'):
                with ui.row().classes('items-center gap-3 mb-9'):
                    ui.icon('diamond', size='25px').classes('text-primary')
                    with ui.column().classes('gap-0'):
                        ui.label('Fe Abbehusen').classes('brand')
                        ui.label('FLOW · GESTÃO').classes('brand-small')
                ui.label('SEU NEGÓCIO').classes('top-eyebrow mb-3 ml-3')
                for href, title, icon in NAV:
                    with ui.link(target=href).classes('nav-link' + (' nav-active' if href == path else '')):
                        ui.icon(icon, size='20px')
                        ui.label(title)
                with ui.column().classes('mt-auto gap-1 px-3'):
                    ui.label('Feito para o seu dia a dia.').style('font-family:Georgia,serif;font-size:15px')
                    ui.label('Joias · histórias · resultados').classes('muted').style('font-size:11px')
            main = ui.element('main').classes('main')
            with main:
                with ui.element('div').classes('topbar'):
                    ui.label('FE ABBEHUSEN / ' + eyebrow.upper()).classes('top-eyebrow')
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('calendar_today', size='15px').classes('text-secondary')
                        ui.label(date.fromisoformat(today()).strftime('%d/%m/%Y')).classes('muted')
                with ui.element('nav').classes('mobile-nav'):
                    for href, title, icon in NAV:
                        with ui.link(target=href).classes('nav-link' + (' nav-active' if href == path else '')):
                            ui.icon(icon, size='17px')
                            ui.label(title)
                if demo:
                    ui.label('DEMONSTRAÇÃO · Os dados desta base são fictícios e ficam separados dos seus dados reais.').classes('demo-ribbon')
        return main

    def heading(title, subtitle):
        with ui.element('div').classes('page-head') as row:
            with ui.column().classes('gap-2'):
                ui.label(title).classes('heading')
                ui.label(subtitle).classes('muted')
        return row

    def history_notice():
        issues = db.rows('SELECT detail FROM history_issues ORDER BY occurred_on,movement_id')
        if issues:
            with ui.expansion(f'Histórico em conferência · {len(issues)} pendência(s)', icon='info').classes('info-panel mb-4 w-full'):
                ui.label('Receitas e caixa permanecem registrados. Custos e resultados afetados ficam em conferência '
                         'até corrigir a compra ou a venda de origem.').classes('muted')
                for issue in issues:
                    ui.label(issue['detail']).classes('text-sm py-1')

    @ui.page('/')
    def dashboard():
        with shell('/', 'Visão geral'):
            heading('Seu negócio, em perspectiva.', 'Vendas, estoque e compromissos em um só lugar.')
            with ui.row().classes('w-full items-end gap-3 mb-5'):
                start = field('De', add_months(today()[:7] + '-01', -5), kind='date').style('width:165px')
                end = field('Até', today(), kind='date').style('width:165px')
                button('Aplicar período', lambda: body.refresh(), icon='filter_list', secondary=True)

            @ui.refreshable
            def body():
                history_notice()
                try:
                    result = reports.summary(db, start.value, end.value)
                    months = reports.monthly(db, start.value, end.value)
                except RuleError as exc:
                    ui.label(str(exc)).classes('info-panel')
                    return
                with ui.element('div').classes('metric-grid'):
                    metric('Receita de vendas', brl(result['revenue_cents']), 'Vendas menos cancelamentos', 'shopping_bag')
                    metric('Resultado gerencial', brl(result['net_cents']), 'Após custos, taxas e despesas', 'trending_up', True)
                    metric('Estoque próprio a custo', brl(result['stock_cents']), f"{result['stock']} peças na data final", 'diamond')
                    metric('Movimento do caixa', brl(result['cash_net_cents']), 'Recebimentos menos pagamentos', 'account_balance_wallet')
                ui.label(f"Consignado na data final: {result['consigned_stock']} peças · {brl(result['consigned_stock_cents'])} a repasse · A repassar: {brl(result['consignment_payable_cents'])}").classes('info-panel mb-4')
                with ui.element('div').classes('two-col'):
                    with ui.column().classes('surface gap-1'):
                        ui.label('Como os meses evoluíram').classes('section-title')
                        ui.label(f"De {date.fromisoformat(start.value):%d/%m/%Y} a {date.fromisoformat(end.value):%d/%m/%Y} · valores em R$").classes('muted')
                        ui.echart({
                            'color': ['#bed9c8', '#145f49'], 'tooltip': {'trigger': 'axis'},
                            'legend': {'bottom': 0, 'icon': 'roundRect'},
                            'grid': {'left': 54, 'right': 12, 'top': 24, 'bottom': 64},
                            'xAxis': {'type': 'category', 'data': [m['month'][5:] + '/' + m['month'][2:4] for m in months],
                                      'axisLine': {'lineStyle': {'color': '#dce5dd'}}},
                            'yAxis': {'type': 'value', 'splitLine': {'lineStyle': {'color': '#edf0eb'}}},
                            'series': [
                                {'name': 'Receita', 'type': 'bar', 'barMaxWidth': 30,
                                 'itemStyle': {'borderRadius': [4, 4, 0, 0]}, 'data': [m['revenue_cents'] / 100 for m in months]},
                                {'name': 'Resultado', 'type': 'line', 'smooth': False, 'symbolSize': 7,
                                 'lineStyle': {'width': 3}, 'data': [m['net_cents'] / 100 if m['net_cents'] is not None else None for m in months]},
                            ]}).classes('w-full').style('height:285px')
                    with ui.column().classes('surface gap-3'):
                        ui.label('Para acompanhar').classes('section-title')
                        ui.label('Posição na data final do filtro').classes('muted')
                        for title, value, icon in [('A receber, após taxa', result['receivable_cents'], 'south_west'),
                                                   ('A pagar', result['payable_cents'], 'north_east')]:
                            with ui.element('div').classes('list-line'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon(icon, size='19px').classes('text-secondary')
                                    ui.label(title).classes('muted')
                                ui.label(brl(value)).classes('text-lg font-semibold')
                        ui.label('Compras entram no estoque; o custo vira resultado quando a peça é vendida. '
                                 'O caixa muda nas datas das baixas.').classes('muted mt-3')
                        button('Ver recebimentos', lambda: ui.navigate.to('/vendas'), icon='arrow_forward', secondary=True)
                recent = db.rows("SELECT * FROM sales WHERE operation='sale' AND sale_date BETWEEN ? AND ? ORDER BY sale_date DESC,id DESC LIMIT 5",
                                 (start.value, end.value))
                with ui.column().classes('surface gap-4'):
                    with ui.row().classes('w-full justify-between items-center'):
                        ui.label('Vendas recentes').classes('section-title')
                        ui.link('Ver todas →', '/vendas').classes('text-primary text-sm no-underline')
                    if recent:
                        table([{'id': s['id'], 'date': s['sale_date'], 'customer': s['customer'] or 'Não informado',
                                'value': brl(s['revenue_cents']), 'result': brl(s['net_cents'] if s['cost_status'] == 'confirmed' else None),
                                'status': 'Cancelada' if s['cancelled_on'] else 'Registrada'} for s in recent],
                              [('id', 'VENDA'), ('date', 'DATA'), ('customer', 'CLIENTE'), ('value', 'RECEITA'),
                               ('result', 'RESULTADO DA VENDA'), ('status', 'SITUAÇÃO')])
                    else:
                        ui.label('As primeiras vendas aparecerão aqui.').classes('muted py-5')
            body()

    def product_dialog(refresh, product=None):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label('Editar produto' if product else 'Adicionar produto').classes('heading')
            ui.label('O código completo e a variante identificam a peça.').classes('muted')
            with ui.element('div').classes('formgrid'):
                name = field('Nome do produto', product['name'] if product else '').classes('wide')
                sku = field('Código completo / SKU', product['sku'] if product else '')
                supplier = field('CNPJ ou nome do fornecedor', product['supplier'] if product else DEFAULT_SUPPLIER)
                category = field('Categoria', product['category'] if product else '')
                collection = field('Coleção', product['collection'] if product else '')
                material = field('Material / banho', product['material'] if product else '')
                stone = field('Pedra', product['stone'] if product else '')
                size = field('Tamanho', product['size'] if product else '')
                price = money_field('Preço de venda (R$)', product['selling_cents'] / 100 if product else '0,00')
                if product:
                    for element in [sku, supplier, material, stone, size]:
                        element.props('readonly')
                    active = ui.checkbox('Produto ativo para novas vendas', value=bool(product['active'])).classes('wide')
                else:
                    qty = field('Quantidade de entrada', '0').props('inputmode=numeric')
                    cost = money_field('Custo por peça (R$)')
                    when = field('Data da entrada', today(), kind='date')
                    entry_location=ui.select({r['id']:r['name'] for r in business.locations() if r['active']},value=1,label='Local de recebimento')
                    opening = ui.checkbox('Saldo inicial já conferido', value=True)
                    ui.label('Marque para cadastrar as peças que você já tem. Desmarque para uma compra manual a pagar. '
                             'Não cadastre o saldo inicial e importe as mesmas peças por XML.').classes('muted wide')
            request_key = str(uuid4())

            def save():
                payload = dict(name=name.value, sku=sku.value, supplier=supplier.value, category=category.value,
                               collection=collection.value, material=material.value, stone=stone.value,
                               size=size.value, selling_price=price.value)
                if not product:
                    payload['location_id']=entry_location.value
                if product:
                    payload['active'] = active.value
                perform(lambda: business.update_catalog(product['id'], payload) if product else
                        business.create_product(payload, quantity=qty.value, unit_cost=cost.value, when=when.value,
                                                opening=opening.value, key=request_key),
                        'Produto salvo.', lambda: (dialog.close(), refresh()))
            with ui.element('div').classes('footer-actions'):
                button('Voltar', dialog.close, secondary=True)
                button('Salvar produto', save, icon='check')
        dialog.open()

    def stock_dialog(product, refresh):
        product = business.product(product['id'])
        with ui.dialog() as dialog, ui.card().classes('dialog-card dialog-small'):
            ui.label('Conferir estoque').classes('heading')
            ui.label(f"{product['name']} · saldo atual: {product['stock']} peça(s)").classes('muted')
            counted = field('Quantidade contada', product['stock']).props('inputmode=numeric')
            cost = money_field('Custo unitário das peças adicionadas (R$)',
                               rounded(Decimal(product['stock_cents']) / product['stock']) / 100 if product['stock'] > 0 and product['stock_cents'] is not None else '0,00')
            reason = field('Motivo da diferença')
            ui.label('Uma diferença gera uma movimentação e um ganho ou perda no resultado. '
                     'Para repor mercadorias compradas, use Compras e XML.').classes('muted')
            key = str(uuid4())
            with ui.element('div').classes('footer-actions'):
                button('Voltar', dialog.close, secondary=True)
                button('Registrar conferência', lambda: perform(
                    lambda: business.adjust_stock(product['id'], counted.value, reason.value, unit_cost=cost.value, key=key),
                    'Conferência registrada.', lambda: (dialog.close(), refresh())))
        dialog.open()

    def history_dialog(product):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label('Histórico da peça').classes('heading')
            ui.label(product['name'] + ' · ' + product['sku']).classes('muted')
            movements = db.rows('SELECT * FROM movements WHERE product_id=? ORDER BY occurred_on DESC,id DESC', (product['id'],))
            labels = {'OPENING': 'Saldo inicial', 'PURCHASE': 'Compra', 'SALE': 'Venda',
                      'CANCELLATION': 'Cancelamento', 'ADJUSTMENT': 'Conferência'}
            table([{**m, 'type': labels.get(m['kind'], m['kind']), 'value': brl(m['cost_cents'] if m['cost_status'] == 'confirmed' else None)} for m in movements],
                  [('occurred_on', 'DATA'), ('type', 'MOVIMENTO'), ('quantity', 'PEÇAS'), ('value', 'CUSTO'), ('reason', 'MOTIVO')])
            button('Fechar', dialog.close, secondary=True)
        dialog.open()

    @ui.page('/estoque')
    def inventory():
        with shell('/estoque', 'Estoque'):
            head = heading('Cada peça, no seu lugar.', 'Estoque próprio. Consulte as peças de terceiros na aba Consignação.')
            ui.link('Peças por local · distribuir e transferir', '/locais').classes('text-lg')
            with head:
                button('Adicionar produto', lambda: product_dialog(body.refresh), icon='add')
            with ui.row().classes('w-full gap-3 items-center mb-6'):
                search = field('Buscar nome, código, coleção…').style('max-width:360px')
                status = ui.select(['Todos', 'Disponíveis', 'Sem estoque', 'Arquivados'], value='Todos', label='Situação').props('outlined dense').style('width:185px')
                mode = ui.toggle(['Tabela', 'Catálogo'], value='Tabela')
                button('Atualizar', lambda: body.refresh(), icon='refresh', secondary=True)
            search.on_value_change(lambda: body.refresh())
            status.on_value_change(lambda: body.refresh())
            mode.on_value_change(lambda: body.refresh())

            @ui.refreshable
            def body():
                history_notice()
                rows = business.owned_products()
                term = (search.value or '').strip().casefold()
                rows = [r for r in rows if term in ' '.join(str(r[k]) for k in ['name', 'sku', 'collection']).casefold()
                        and (status.value == 'Todos' or (status.value == 'Disponíveis' and r['stock'] > 0 and r['active'])
                             or (status.value == 'Sem estoque' and r['stock'] == 0 and r['active'])
                             or (status.value == 'Arquivados' and not r['active']))]
                if not rows:
                    empty('Nenhuma peça própria encontrada', 'Peças exclusivamente consignadas aparecem na aba Consignação.', 'diamond')
                    return
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    value = None if any(r['stock_cents'] is None for r in rows) else sum(r['stock_cents'] for r in rows)
                    ui.label(f"{len(rows)} produtos · {sum(r['stock'] for r in rows)} peças · {brl(value)} a custo").classes('muted')
                    if mode.value == 'Catálogo':
                        button('Exportar lista filtrada', lambda: ui.download.content(reports.csv_bytes(rows),
                               f'estoque-{today()}.csv', 'text/csv'), icon='download', secondary=True)
                if mode.value == 'Tabela':
                    formatted = [{**r, 'price': brl(r['selling_cents']), 'cost': 'Em conferência' if r['stock_cents'] is None else brl(rounded(Decimal(r['stock_cents']) / r['stock'])) if r['stock'] else '—',
                                  'variant': ' / '.join(filter(None, [r['material'], r['stone'], r['size']])),
                                  'status': 'Em conferência' if r['history_status'] == 'pending' else 'Arquivado' if not r['active'] else ('Sem estoque' if r['stock'] == 0 else 'Disponível')}
                                 for r in rows]
                    tbl = table(formatted, [('sku', 'CÓDIGO'), ('name', 'PRODUTO'), ('variant', 'VARIANTE'),
                                            ('stock', 'PEÇAS'), ('cost', 'CUSTO MÉDIO'), ('price', 'VENDA'), ('status', 'SITUAÇÃO')], selection='multiple')
                    def toggle_all():
                        tbl.selected = [] if len(tbl.selected) == len(formatted) else list(formatted)
                        tbl.update()
                    def export_selected():
                        if not tbl.selected:
                            raise RuleError('Marque pelo menos um produto para exportar.')
                        ids = {r['id'] for r in tbl.selected}
                        ui.download.content(reports.csv_bytes([r for r in rows if r['id'] in ids]),
                                            f'estoque-{today()}.csv', 'text/csv')
                    ui.label('Marcar tudo seleciona todos os produtos do filtro atual, inclusive de outras páginas. Alterar o filtro limpa a seleção.').classes('muted')
                    with ui.row().classes('mt-4 gap-3'):
                        button('Marcar / Desmarcar tudo', toggle_all, icon='select_all', secondary=True)
                        button('Exportar seleção', lambda: perform(export_selected, ''), icon='download', secondary=True)
                        button('Editar cadastro', lambda: choose(tbl, lambda p: product_dialog(body.refresh, p)), icon='edit', secondary=True)
                        button('Conferir estoque', lambda: choose(tbl, lambda p: stock_dialog(p, body.refresh)), icon='fact_check', secondary=True)
                        button('Ver histórico', lambda: choose(tbl, history_dialog), icon='history', secondary=True)
                else:
                    with ui.element('div').classes('product-grid'):
                        for product in rows:
                            with ui.element('div').classes('product-card'):
                                with ui.element('div').classes('product-icon'):
                                    ui.icon('diamond', size='42px').style('color:#b49b70')
                                with ui.element('div').classes('product-body'):
                                    with ui.row().classes('w-full justify-between items-center'):
                                        ui.label(product['sku']).classes('muted').style('font-size:11px')
                                        ui.label(f"{product['stock']} peças").classes('pill')
                                    ui.label(product['name']).classes('section-title')
                                    ui.label(' · '.join(filter(None, [product['material'], product['stone'], product['collection']])) or 'Sem coleção').classes('muted')
                                    ui.label(brl(product['selling_cents'])).classes('text-xl font-semibold text-primary')
                                    with ui.row().classes('gap-2 mt-1'):
                                        button('Editar', lambda p=product: product_dialog(body.refresh, p), icon='edit', secondary=True)
                                        button('Histórico', lambda p=product: history_dialog(p), secondary=True)
            body()

    def delete_invoice_dialog(row, refresh):
        snapshot = business.invoice_snapshot(row['id'])
        number = snapshot['invoice']['number']
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label(f'Excluir nota importada · NF-e {number}').classes('heading')
            ui.label(f"{snapshot['invoice']['issuer_name']} · {snapshot['invoice']['issued_on']} · Total da nota: {brl(snapshot['invoice']['total_cents'])}").classes('muted')
            table([{**i, 'value': brl(i['cost_cents'])} for i in snapshot['items']],
                  [('line_number', 'ITEM'), ('sku', 'CÓDIGO'), ('name', 'DESCRIÇÃO'), ('quantity', 'QUANTIDADE'), ('destination', 'DESTINO'), ('value', 'VALOR')])
            ui.label(f"Contas vinculadas: {brl(sum(e['amount_cents'] for e in snapshot['expenses']))} · Baixas registradas: {brl(sum(e['amount_cents'] for e in snapshot['expenses'] if e['paid_on']))}").classes('info-panel')
            ui.label('Remove esta nota e o XML do aplicativo, suas entradas próprias ou consignadas, despesas e baixas vinculadas. Não realiza estorno bancário. Produtos compartilhados com outras notas são preservados. Vendas, devoluções ou conferências dependentes bloqueiam a exclusão.').classes('muted')
            ui.label('Um backup completo será criado antes de excluir. Depois será possível importar o XML novamente.').classes('muted')
            reason = field('Motivo da exclusão da nota')
            confirmation = field(f'Digite EXCLUIR NOTA {number}')
            with ui.element('div').classes('footer-actions'):
                button('Manter nota', dialog.close, secondary=True)
                button('Confirmar exclusão da nota', lambda: perform(
                    lambda: business.delete_invoice(row['id'], reason=reason.value, confirmation=confirmation.value, expected=snapshot),
                    'Nota excluída. Saldos recalculados e backup preservado.', lambda: (dialog.close(), refresh())), color='negative')
        dialog.open()

    def correct_invoice_dialog(row, refresh):
        snapshot = business.invoice_snapshot(row['id'])
        consign = snapshot['invoice']['ownership'] == 'consigned'
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label(f"Corrigir importação · NF-e {row['number']}").classes('heading')
            ui.label('O XML original, a data, os valores e a modalidade da nota serão preservados. Altere apenas o destino dos itens.').classes('muted')
            ui.label('Estoque ↔ Despesa preserva vencimento e baixa existentes. Itens antes ignorados gerarão contas em aberto na data da nota; confira e registre o pagamento em Despesas. Ignorar remove a conta não paga. Itens pagos não podem ser ignorados.').classes('info-panel')
            if consign:
                ui.label('Consignação: estoque ou ignorar, sem gerar conta na entrada. Lotes com movimentações não podem ser reclassificados.').classes('muted')
            choices = {}
            options = {'estoque': 'Entrar no estoque', 'ignorar': 'Ignorar item'} if consign else {'estoque': 'Entrar no estoque', 'despesa': 'Lançar despesa', 'ignorar': 'Ignorar item'}
            for item in snapshot['items']:
                with ui.row().classes('w-full items-center gap-3'):
                    ui.label(f"{item['line_number']}. {item['name']} · {item['quantity']} un. · {brl(item['cost_cents'])}").style('flex:1')
                    choices[item['line_number']] = ui.select(options, value=item['destination'], label=f"Destino do item {item['line_number']}").props('outlined dense')
            markup = field('Multiplicador para produtos novos', '2,3')
            reason = field('Motivo da correção da importação')
            with ui.element('div').classes('footer-actions'):
                button('Voltar', dialog.close, secondary=True)
                button('Salvar correção da importação', lambda: perform(
                    lambda: business.correct_invoice(row['id'], {k: v.value for k, v in choices.items()}, reason=reason.value, markup=markup.value, expected=snapshot),
                    'Importação corrigida. Estoque e despesas recalculados.', lambda: (dialog.close(), refresh())), icon='check')
        dialog.open()

    @ui.page('/compras')
    def purchases():
        with shell('/compras', 'Compras'):
            heading('Do XML ao estoque.', 'Revise a compra antes de confirmar a entrada das peças.')
            with ui.column().classes('surface gap-3 mb-6'):
                ui.label('Importar NF-e').classes('section-title')
                ui.label('São aceitos os dois CNPJs de compra cadastrados e o CPF da Nanda. O documento original é preservado.').classes('muted')
                preview = ui.column().classes('w-full')

                async def uploaded(event):
                    try:
                        raw = await event.file.read()
                    except (OSError, ValueError):
                        preview.clear()
                        ui.notify('Não foi possível ler o arquivo enviado. Selecione novamente o XML original.', type='warning')
                        return
                    finally:
                        event.sender.reset()
                    try:
                        invoice = parse_xml(raw)
                        if db.rows('SELECT id FROM invoices WHERE access_key=?', (invoice.key,)):
                            raise RuleError('Esta NF-e já foi importada.')
                    except RuleError as exc:
                        preview.clear()
                        ui.notify(str(exc), type='warning', position='top', timeout=8000)
                        return
                    preview.clear()
                    with preview:
                        ui.separator()
                        ui.label(f'NF-e {invoice.number} · {invoice.issued_on} · {brl(invoice.total_cents)}').classes('section-title')
                        ui.label(f'{invoice.issuer_name} → Destinatário {invoice.recipient}').classes('muted')
                        ui.label('Conferência local dos campos e do protocolo. Não consulta a SEFAZ nem valida a assinatura digital.').classes('muted')
                        with ui.element('div').classes('formgrid mt-3'):
                            entry_location=ui.select({r['id']:r['name'] for r in business.locations() if r['active'] or r['id']==2},value=2,label='Local de recebimento')
                            ownership = ui.select({'own': 'Compra própria', 'consigned': 'Consignação'}, value='own', label='Modalidade da entrada').props('outlined dense')
                            markup = field('Multiplicador de venda para produtos novos', '2,3')
                            due = field('Vencimento da compra', invoice.issued_on, kind='date')
                            paid = ui.checkbox('Compra já paga', value=False)
                            paid_date = field('Data do pagamento', today(), kind='date')
                        ui.label('Custo inclui desconto, frete, seguro, outras despesas e tributos discriminados somados ao total. '
                                 'Produtos existentes mantêm o preço de venda; o custo médio incorpora a nova entrada.').classes('info-panel my-3')
                        ui.label('Consignação: o estoque fica separado e o repasse só nasce na venda. O custo unitário é o custo total do item dividido pela quantidade, arredondado para centavos; confira antes de importar.').classes('muted')
                        due.bind_visibility_from(ownership, 'value', backward=lambda v: v == 'own')
                        paid.bind_visibility_from(ownership, 'value', backward=lambda v: v == 'own')
                        paid_date.bind_visibility_from(ownership, 'value', backward=lambda v: v == 'own')
                        choices = {}
                        for item in invoice.items:
                            with ui.row().classes('w-full items-center gap-3 py-3').style('border-bottom:1px solid #e5ece6'):
                                with ui.column().classes('gap-1').style('flex:1;min-width:170px'):
                                    ui.label(f'{item.number}. {item.name}').classes('font-medium')
                                    ui.label(f'{item.sku} · {item.quantity} un. · custo total {brl(item.cost_cents)} · unitário {brl(rounded(Decimal(item.cost_cents) / item.quantity))}').classes('muted')
                                choices[item.number] = ui.select({'estoque': 'Entrar no estoque', 'despesa': 'Lançar despesa', 'ignorar': 'Ignorar item'},
                                                                 value='estoque').props('outlined dense').style('width:195px')

                        def confirm():
                            perform(lambda: business.import_invoice(raw, {key: select.value for key, select in choices.items()},
                                    markup=markup.value, ownership=ownership.value, location_id=entry_location.value, due_on=due.value, paid_on=paid_date.value if paid.value and ownership.value == 'own' else None),
                                    'Entrada importada. Estoque e contas atualizados conforme a modalidade.', lambda: (preview.clear(), history.refresh()))
                        with ui.row().classes('mt-4 gap-3'):
                            button('Confirmar importação', confirm, icon='check')
                            button('Descartar prévia', preview.clear, secondary=True)
                def rejected_xml(event):
                    reasons = set(event.args or [])
                    if reasons & {'max-file-size', 'max-total-size'}:
                        message = 'O arquivo ultrapassa o limite de 10 MB.'
                    elif 'accept' in reasons:
                        message = 'Selecione o arquivo original com extensão .xml. Uma página salva como .html ou um arquivo .zip não é um XML.'
                    elif reasons & {'duplicate', 'max-files'}:
                        message = 'O arquivo já está na seleção ou há arquivos demais. Remova a seleção anterior e envie uma nota por vez.'
                    else:
                        message = 'O seletor recusou o arquivo. Limpe a seleção e escolha novamente um arquivo .xml de até 10 MB.'
                    ui.notify(message, type='warning', position='top', timeout=10000)
                uploader = ui.upload(label='Selecionar XML da nota fiscal', auto_upload=True, max_file_size=MAX_XML_BYTES,
                                     on_upload=uploaded).props('accept=.xml').classes('w-full')
                uploader.on('rejected', rejected_xml,
                            js_handler='(files) => emit(files.map(file => file.failedPropValidation))')

            @ui.refreshable
            def history():
                history_notice()
                rows = db.rows('SELECT id,number,issued_on,issuer_name,recipient_cnpj,total_cents,ownership FROM invoices ORDER BY issued_on DESC,id DESC')
                if not rows:
                    empty('As compras importadas aparecerão aqui', 'O histórico guarda a nota mesmo quando os itens são despesas.', 'description')
                    return
                ui.label('Compras importadas').classes('section-title mb-4')
                tbl = table([{**r, 'total': brl(r['total_cents']), 'ownership_label': 'Consignação' if r['ownership'] == 'consigned' else 'Compra própria'} for r in rows],
                            [('number', 'NF-e'), ('issued_on', 'EMISSÃO'), ('issuer_name', 'FORNECEDOR'),
                             ('recipient_cnpj', 'DESTINATÁRIO'), ('ownership_label', 'MODALIDADE'), ('total', 'TOTAL')], selection='single')

                def download_original(row):
                    invoice = db.rows('SELECT xml,access_key FROM invoices WHERE id=?', (row['id'],))[0]
                    ui.download.content(invoice['xml'], f"NFe-{invoice['access_key']}.xml", 'application/xml')
                button('Corrigir importação', lambda: choose(tbl, lambda row: correct_invoice_dialog(row, history.refresh)), icon='edit', secondary=True).classes('mt-4')
                button('Excluir nota importada', lambda: choose(tbl, lambda row: delete_invoice_dialog(row, history.refresh)), icon='delete_forever', secondary=True, color='negative').classes('mt-4')
                button('Baixar XML original', lambda: choose(tbl, download_original), icon='download', secondary=True).classes('mt-4')
            history()

    def sale_dialog(refresh, editing=None):
        snapshot = business.sale_snapshot(editing['id']) if editing else None
        if snapshot and snapshot['sale']['cancelled_on']:
            ui.notify('Venda cancelada não pode ser editada.', type='warning')
            return
        original = snapshot['sale'] if snapshot else {}
        products = {p['id']: p for p in business.products() if p['active'] or (snapshot and p['id'] in [i['product_id'] for i in snapshot['sale_items'] + snapshot['consignment_sale_items']])}
        if not products:
            ui.notify('Cadastre ou importe os produtos antes de registrar vendas.', type='info')
            return
        lots = {l['id']: l for l in business.consignment_lots()}
        if snapshot:
            for item in snapshot['sale_items']:
                products[item['product_id']]['stock'] += item['quantity']
            for item in snapshot['consignment_sale_items']:
                lots[item['lot_id']]['stock'] += item['quantity']
        consigned_stock = {pid: sum(l['stock'] for l in lots.values() if l['product_id'] == pid)
                           for pid in products}
        cart=[]
        if snapshot:
            for alloc in snapshot['sale_locations']:
                original_item=next(i for i in snapshot['sale_items']+snapshot['consignment_sale_items'] if i['product_id']==alloc['product_id'] and (i.get('lot_id') or None)==alloc['lot_id'])
                cart.append(dict(product_id=alloc['product_id'],lot_id=alloc['lot_id'],location_id=alloc['location_id'],quantity=alloc['quantity'],unit_price=str(Decimal(original_item['unit_price_cents'])/100)))
        location_options={r['id']:r['name'] for r in business.locations() if r['active'] or any(i['location_id']==r['id'] for i in cart)}
        physical={(r['product_id'],r['lot_id'] or 0,r['location_id']):r['quantity'] for r in business.location_stock()}
        for item in cart:
            identity=(item['product_id'],item.get('lot_id') or 0,item['location_id'])
            physical[identity]=physical.get(identity,0)+item['quantity']
        def available(pid,lot,loc):
            return physical.get((pid,lot or 0,loc),0)-sum(i['quantity'] for i in cart if (i['product_id'],i.get('lot_id') or 0,i['location_id'])==(pid,lot or 0,loc))
        key = str(uuid4())
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label(f"Editar venda #{editing['id']}" if editing else 'Registrar venda').classes('heading')
            operation_select = ui.select({'sale':'Venda','personal':'Retirada para uso pessoal'},value=original.get('operation','sale'),label='Tipo de operação').props('outlined').classes('w-full')
            owner = field('Quem retirou as peças',original.get('customer','Nanda') if original.get('operation')=='personal' else 'Nanda')
            personal_notice=ui.label('Retirada sem pagamento: baixa pelo custo, sem receita, recebimento ou comissão. O custo aparece separado nos relatórios; não entra na margem comercial. Peças consignadas geram o repasse devido à matriz.').classes('info-panel')
            historical = ui.checkbox('Lançamento histórico — permitir pendências de estoque', value=original.get('cost_status') == 'pending')
            ui.label('Use ao reconstruir vendas antigas se ainda faltarem compras. O custo ficará em conferência '
                     'quando não houver entrada suficiente na data da venda.').classes('muted')
            with ui.element('div').classes('formgrid'):
                location=ui.select({0:'Todos os locais',**location_options},value=original.get('location_id') or 1,label='Local de saída das peças').props('outlined dense').classes('wide')
                selected = ui.select({},label='Produto',with_input=True).props('outlined dense').classes('wide')
                source = ui.select({0:'Estoque próprio'},value=0,label='Origem da peça (Estoque próprio ou Consignado)').props('outlined dense').classes('wide')
                qty = field('Quantidade', '1').props('inputmode=numeric')
                unit = money_field('Preço efetivo por peça (R$)')
            def refresh_products():
                options={}
                for pid,p in products.items():
                    for loc,name in location_options.items():
                        if location.value and loc!=location.value: continue
                        total=sum(max(0,available(pid,lot,loc)) for pp,lot,ll in physical if pp==pid and ll==loc)
                        if total<=0 and not (historical.value and loc==1): continue
                        key=pid if location.value else f'{pid}:{loc}'
                        options[key]=f"{p['sku']} · {p['name']} · {' / '.join(filter(None,[p['material'],p['stone'],p['size']]))} · {total} disponíveis"+(f' · {name}' if not location.value else '')
                selected.set_options(options,value=selected.value if selected.value in options else None)
                if selected.value is not None:
                    select_product(type('Selection',(),{'value':selected.value})())
            def select_product(event):
                if isinstance(event.value,str) and ':' in event.value:
                    pid,loc=map(int,event.value.split(':'))
                    location.set_value(loc)
                    selected.set_value(pid)
                    return
                if event.value in products:
                    pid=event.value;loc=location.value
                    unit.set_value(str(Decimal(products[pid]['selling_cents'])/100))
                    own=available(pid,0,loc)
                    options={0:f'Estoque próprio · {own} disponíveis'} if own>0 or historical.value and loc==1 else {}
                    options.update({lid:f"Consignado · NF-e {l['invoice_number']} · lote #{lid} · {available(pid,lid,loc)} disponíveis" for lid,l in lots.items() if l['product_id']==pid and available(pid,lid,loc)>0})
                    source.set_options(options,value=0 if 0 in options else next(iter(options)) if len(options)==1 else None)
                else:
                    source.set_options({},value=None)
            selected.on_value_change(select_product)
            location.on_value_change(lambda:refresh_products())
            historical.on_value_change(lambda:refresh_products())
            refresh_products()
            markup = field('Markup para calcular preço', '2,3')
            def apply_markup():
                try:
                    if selected.value not in products or source.value is None:
                        raise RuleError('Selecione o produto e a origem antes de aplicar o markup.')
                    cost = business.quote_cost([{'product_id': selected.value, 'lot_id': source.value or None, 'quantity': 1}], when.value, exclude_sale_id=editing['id'] if editing else None)
                    if cost is None:
                        raise RuleError('Custo em conferência. Informe o preço efetivo manualmente.')
                    factor = Decimal(str(markup.value).replace(',', '.'))
                    if not factor.is_finite() or factor < 0 or factor > 1000:
                        raise RuleError('Informe um markup entre 0 e 1000.')
                    unit.set_value(str(Decimal(cents(Decimal(cost) / 100 * factor)) / 100))
                except (RuleError, ArithmeticError, ValueError) as exc:
                    ui.notify(str(exc), type='warning')
            button('Aplicar markup ao preço', apply_markup, secondary=True)

            def add_item():
                try:
                    if selected.value not in products:
                        raise RuleError('Selecione um produto.')
                    if source.value is None:
                        raise RuleError('Selecione o lote em Origem da peça.')
                    quantity, value = pieces(qty.value), cents(unit.value)
                    if any(i['product_id'] == selected.value and i.get('lot_id') == (source.value or None) and i['location_id']==location.value for i in cart):
                        raise RuleError('Esta peça já está na venda. Remova a linha e informe a quantidade total.')
                    remaining = available(selected.value,source.value,location.value)
                    if (source.value or not historical.value or location.value!=1) and quantity > remaining:
                        raise RuleError('A quantidade excede o estoque exibido.')
                    cart.append({'location_id':location.value,'product_id': selected.value, 'lot_id': source.value or None, 'quantity': quantity, 'unit_price': str(Decimal(value) / 100)})
                    refresh_products()
                    cart_view.refresh()
                    totals.refresh()
                except RuleError as exc:
                    ui.notify(str(exc), type='warning')
            button('Adicionar à venda', add_item, icon='add', secondary=True)

            @ui.refreshable
            def cart_view():
                if not cart:
                    ui.label('Adicione uma ou mais peças à venda.').classes('muted')
                for item in cart:
                    with ui.element('div').classes('list-line'):
                        ui.label(f"{products[item['product_id']]['name']} · {location_options[item['location_id']]} · {item['quantity']} un. · {('Consignado lote #' + str(item['lot_id'])) if item.get('lot_id') else 'Próprio'}").classes('text-sm')
                        ui.label('Baixa ao custo' if operation_select.value=='personal' else brl(cents(item['unit_price']) * item['quantity'])).classes('font-medium')
                        def remove(line=item):
                            cart.remove(line)
                            refresh_products()
                            cart_view.refresh()
                            totals.refresh()
                        def edit_item(line=item):
                            remove(line)
                            location.set_value(line['location_id'])
                            refresh_products()
                            selected.set_value(line['product_id'])
                            source.set_value(line.get('lot_id') or 0)
                            qty.set_value(str(line['quantity']))
                            unit.set_value(line['unit_price'])
                        button('Alterar peça', edit_item, icon='edit', secondary=True)
                        button('', remove, icon='close', secondary=True).props('round dense').tooltip('Remover peça')
            cart_view()
            with ui.element('div').classes('formgrid'):
                when = field('Data da venda', original.get('sale_date', today()), kind='date')
                known_clients={c['id']:c for c in business.customers()}
                client_select=ui.select({0:'Novo cliente / sem cadastro',**{i:f"{c['name']} · {c['phone']}" for i,c in known_clients.items()}},value=original.get('customer_id') or 0,label='Cliente cadastrado',with_input=True).props('outlined dense').classes('wide')
                customer = field('Nome do cliente', original.get('customer', ''))
                phone = field('Telefone do cliente', original.get('phone', '')).props('type=tel')
                def client_selected(e):
                    c=known_clients.get(e.value)
                    if c:
                        customer.set_value(c['name']);phone.set_value(c['phone'])
                    customer.set_enabled(not bool(c));phone.set_enabled(not bool(c))
                client_select.on_value_change(client_selected)
                channels={c['id']:c for c in business.channels() if c['active'] or c['id']==original.get('channel_id')}
                channel=ui.select({0:'Canal anterior / não informado',**{i:c['name'] for i,c in channels.items()}},value=(original.get('channel_id') or 0) if editing else next((i for i,c in channels.items() if c['kind']=='Direto' and 'nanda' in c['name'].casefold()),0),label='Canal de venda').props('outlined dense')
                seller_options={b['id']:b['name'] for b in business.sellers(channel.value)}
                seller_select=ui.select({0:'Sem vendedora identificada',**seller_options},value=original.get('seller_id') or 0,label='Vendedora').props('outlined dense')
                if not editing:
                    location.set_value(channels.get(channel.value,{}).get('location_id') or (2 if channels.get(channel.value,{}).get('kind')=='Direto' else 1))
                ui.label('Cada peça mantém o local escolhido ao ser adicionada. Alterar o filtro não muda o carrinho.').classes('muted')
                event = field('Evento / canal da venda', original.get('event', ''))
                discount = money_field('Desconto adicional no total (R$)', str(Decimal(original.get('discount_cents', 0)) / 100))
                method = ui.select(['Pix', 'Dinheiro', 'Cartão de crédito', 'Cartão de débito', 'Transferência'], value=original.get('method', 'Pix'), label='Pagamento').props('outlined dense')
                def initial_percent(key):
                    base=original.get('revenue_cents',0)-(original.get('credit_cents',0) if key=='fee_cents' else 0)
                    return format((Decimal(original.get(key,0))*100/base).quantize(Decimal('0.01')),'.2f') if base else '0.00'
                fee = money_field('Taxa do cartão (%)', initial_percent('fee_cents'))
                tax = money_field('Imposto da venda (R$)', str(Decimal(original.get('tax_cents', 0)) / 100))
                seller = money_field('Comissão vendedora (%)', initial_percent('seller_cents'))
                store = money_field('Comissão loja / evento (%)', initial_percent('store_cents'))
                installments = ui.select(list(range(1, 25)), value=max(1,len([r for r in snapshot['receivables'] if r['cash_effect']])) if snapshot else 1, label='Parcelas').props('outlined dense')
                due = field('Vencimento da primeira parcela', next((r['due_on'] for r in snapshot['receivables'] if r['cash_effect']),original['sale_date']) if snapshot else today(), kind='date')
                paid = ui.checkbox('Venda já recebida integralmente', value=False if editing else True)
                paid_date = field('Data do recebimento', today(), kind='date')
                consignment_due = field('Vencimento do repasse consignado', next((e['due_on'] for e in snapshot['expenses'] if e['category'] == 'Repasse consignação'), original['sale_date']) if snapshot else today(), kind='date')
                use_credit=ui.checkbox('Usar crédito de comissão',value=bool(original.get('credit_cents',0)))
                credit_beneficiary=ui.select({b['id']:f"{b['name']} · saldo {brl(b['balance_cents'])}" for b in business.commission_balances()},value=original.get('credit_beneficiary_id'),label='Beneficiário do crédito').props('outlined dense')
                credit_amount=money_field('Crédito de comissão a utilizar (R$)',str(Decimal(original.get('credit_cents',0))/100))
                ui.label('No pagamento misto, Pagamento e Parcelas se referem apenas ao complemento em dinheiro. O crédito é liquidado na data da venda.').classes('muted wide')
                notes = ui.textarea('Observações', value=original.get('notes', '')).props('outlined dense rows=2').classes('wide')
            reset_payments = ui.checkbox('Desfazer baixas anteriores', value=False)
            reset_payments.set_visibility(bool(editing))
            correction_reason = field('Motivo da alteração')
            correction_reason.set_visibility(bool(editing))
            if editing:
                ui.label('As baixas existentes serão mantidas nas parcelas e obrigações correspondentes, com os valores corrigidos. Para corrigir baixas erradas, marque Desfazer baixas anteriores. A opção Venda já recebida informa uma nova baixa integral.').classes('info-panel')
            method.on_value_change(lambda e: paid.set_value(e.value in ['Pix', 'Dinheiro', 'Cartão de débito']))
            installments.on_value_change(lambda e: paid.set_value(False) if e.value > 1 else None)

            def apply_channel_rates():
                c=channels.get(channel.value,{})
                blocked=use_credit.value or operation_select.value=='personal'
                seller.set_value('0' if blocked else c.get('seller_rate','0'))
                store.set_value('0' if blocked else c.get('store_rate','0'))

            def channel_changed(e):
                c=channels.get(e.value,{})
                location.set_value(c.get('location_id') or (2 if c.get('kind')=='Direto' else 1))
                seller_select.set_options({0:'Sem vendedora identificada',**{b['id']:b['name'] for b in business.sellers(e.value)}},value=0)
                credit_state['rates']=(c.get('seller_rate','0'),c.get('store_rate','0'))
                apply_channel_rates()
            channel.on_value_change(channel_changed)
            if not editing:
                c=channels.get(channel.value,{})
                apply_channel_rates()

            def amounts():
                if operation_select.value=='personal':
                    return 0,0,0,0,0
                subtotal = sum(cents(i['unit_price']) * i['quantity'] for i in cart)
                revenue = subtotal - cents(discount.value)
                if revenue < 0:
                    raise RuleError('O desconto excede o valor dos produtos.')
                credit_value=cents(credit_amount.value) if use_credit.value else 0
                def charge(key,field,base):
                    old_base=original.get('revenue_cents',0)-(original.get('credit_cents',0) if key=='fee_cents' else 0)
                    if editing and base==old_base and decimal(field.value)==decimal(initial_percent(key)):
                        return original.get(key,0)
                    return percent(base,field.value)
                return revenue,charge('fee_cents',fee,max(0,revenue-credit_value)),cents(tax.value),charge('seller_cents',seller,revenue),charge('store_cents',store,revenue)

            @ui.refreshable
            def totals():
                try:
                    revenue, fee_value, tax_value, seller_value, store_value = amounts()
                    cost = business.quote_cost(cart, when.value, exclude_sale_id=editing['id'] if editing else None)
                    with ui.column().classes('info-panel gap-1'):
                        if operation_select.value=='personal':
                            ui.label('Retirada ao custo: '+brl(cost)+' · Receita e margem comercial: não se aplicam.').classes('font-semibold')
                            consignment_due.set_visibility(any(i.get('lot_id') for i in cart))
                            return
                        c=channels.get(channel.value,{})
                        if not use_credit.value and ((Decimal(str(c.get('store_rate','0'))) > 0 and Decimal(str(store.value).replace(',','.')) == 0) or (Decimal(str(c.get('seller_rate','0'))) > 0 and Decimal(str(seller.value).replace(',','.')) == 0)):
                            ui.label('Atenção: comissão zerada nesta venda, mas o canal possui percentual cadastrado. Confira ou aplique os percentuais do canal.').classes('text-orange-800')
                        ui.label(f'Receita: {brl(revenue)} · Taxa: {brl(fee_value)} · Comissões: {brl(seller_value + store_value)}')
                        ui.label(f'Resultado previsto da venda: {brl(None if cost is None else revenue - cost - fee_value - tax_value - seller_value - store_value)}').classes('font-semibold')
                        consignment_due.set_visibility(any(i.get('lot_id') for i in cart))
                        ui.label('Próprio: custo reconstruído na data da venda. Consignado: custo fixo do lote selecionado.').classes('muted')
                        ui.label('Percentuais sobre a receita após desconto. Não inclui as despesas gerais do mês.').classes('muted')
                except RuleError as exc:
                    ui.label(str(exc)).classes('muted')
            totals()
            button('Aplicar percentuais do canal', apply_channel_rates, icon='refresh', secondary=True)
            ui.label('Na edição, os valores da venda são preservados. Use o botão acima para aplicar a configuração atual do canal. Resgates com crédito não geram nova comissão.').classes('muted')
            credit_state={'active':use_credit.value,'rates':(seller.value,store.value)}
            def credit_changed():
                if use_credit.value and not credit_state['active']:
                    credit_state['rates']=(seller.value,store.value)
                elif not use_credit.value and credit_state['active']:
                    seller.set_value(credit_state['rates'][0]);store.set_value(credit_state['rates'][1])
                credit_state['active']=use_credit.value
                toggle_operation()

            def toggle_operation():
                personal=operation_select.value=='personal'
                for el in [client_select,customer,phone,channel,seller_select,event,discount,method,fee,tax,seller,store,installments,due,paid,paid_date,use_credit,historical,markup,unit]:
                    el.set_visibility(not personal)
                owner.set_visibility(personal);personal_notice.set_visibility(personal)
                credit_beneficiary.set_visibility(not personal and use_credit.value);credit_amount.set_visibility(not personal and use_credit.value)
                if use_credit.value and not personal:
                    seller.set_value('0');store.set_value('0')
                cart_view.refresh()
                totals.refresh()
            operation_select.on_value_change(toggle_operation);use_credit.on_value_change(credit_changed)
            toggle_operation()
            for element in [discount, fee, tax, seller, store,credit_amount]:
                element.on_value_change(lambda: totals.refresh())
            previous_date = {'value': when.value}
            def date_changed(event):
                old = previous_date['value']
                if event.value:
                    if consignment_due.value == old:
                        consignment_due.set_value(event.value)
                    if due.value == old:
                        due.set_value(event.value)
                    if paid_date.value == old:
                        paid_date.set_value(event.value)
                    previous_date['value'] = event.value
                totals.refresh()
            when.on_value_change(date_changed)

            def save():
                def operation():
                    _, fee_cents, tax_cents, seller_cents, store_cents = amounts()
                    data = dict(location_id=cart[0]['location_id'] if cart else 1,operation=operation_select.value,customer_id=client_select.value or None,channel_id=channel.value or None,seller_id=seller_select.value or None,
                        credit=credit_amount.value if use_credit.value else '0',credit_beneficiary_id=credit_beneficiary.value,
                        sale_date=when.value, customer=owner.value if operation_select.value=='personal' else customer.value,
                        phone=phone.value, event=event.value, method=method.value, notes=notes.value,
                        discount=discount.value, fee=Decimal(fee_cents) / 100, tax=Decimal(tax_cents) / 100,
                        seller=Decimal(seller_cents) / 100, store=Decimal(store_cents) / 100,
                        installments=installments.value, first_due=due.value,
                        paid_on=paid_date.value if paid.value else None, historical=historical.value, consignment_due=consignment_due.value)
                    if editing:
                        return business.correct_sale(editing['id'], reason=correction_reason.value, items=cart, data=data, expected=snapshot, reset_payments=reset_payments.value)
                    return business.create_sale(cart, data, key=key)
                perform(operation, 'Venda atualizada e saldos recalculados.' if editing else 'Venda registrada e estoque atualizado.', lambda: (dialog.close(), refresh()))
            with ui.element('div').classes('footer-actions'):
                button('Voltar', dialog.close, secondary=True)
                button('Salvar alterações' if editing else 'Confirmar venda', save, icon='check')
        dialog.open()

    def sale_details(sale, refresh):
        sale = db.rows('SELECT * FROM sales WHERE id=?', (sale['id'],))[0]
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label(f"Venda #{sale['id']}").classes('heading')
            place_names={r['id']:r['name'] for r in business.locations()}
            allocations=db.rows('SELECT a.*,p.name FROM sale_locations a JOIN products p ON p.id=a.product_id WHERE sale_id=?',(sale['id'],))
            ui.label('Locais de saída: '+', '.join(dict.fromkeys(place_names[a['location_id']] for a in allocations)))
            for allocation in allocations:
                ui.label(f"{allocation['name']} · {place_names[allocation['location_id']]} · {allocation['quantity']} un.").classes('muted')
            ui.label(f"{sale['sale_date']} · {sale['method']}" + (f" · Crédito de comissão: {brl(sale['credit_cents'])}" if sale['credit_cents'] else '') + (' · CANCELADA' if sale['cancelled_on'] else '')).classes('muted')
            rows = [{**r, 'id': f"own-{r['id']}", 'origin': 'Próprio'} for r in db.rows('SELECT * FROM sale_items WHERE sale_id=?', (sale['id'],))]
            rows += [{**r, 'id': f"cons-{r['id']}", 'cost_status': 'confirmed', 'origin': f"Consignado · lote #{r['lot_id']}"} for r in db.rows('SELECT * FROM consignment_sale_items WHERE sale_id=?', (sale['id'],))]
            table([{**r, 'price': brl(r['unit_price_cents']), 'cost': brl(r['cost_cents'] if r['cost_status'] == 'confirmed' else None)} for r in rows],
                  [('sku', 'CÓDIGO'), ('name', 'PRODUTO'), ('origin', 'ORIGEM'), ('quantity', 'PEÇAS'), ('price', 'VENDA / UN.'), ('cost', 'CUSTO TOTAL HISTÓRICO')])
            ui.label(f"Receita {brl(sale['revenue_cents'])} · Cartão {brl(sale['fee_cents'])} · Imposto {brl(sale['tax_cents'])} · "
                     f"Comissões {brl(sale['seller_cents'] + sale['store_cents'])} · Resultado {brl(sale['net_cents'] if sale['cost_status'] == 'confirmed' else None)}").classes('info-panel')
            with ui.element('div').classes('formgrid'):
                customer = field('Cliente', sale['customer'])
                phone = field('Telefone', sale['phone'])
                event = field('Evento / canal', sale['event'])
                notes = field('Observações', sale['notes'])
            with ui.element('div').classes('footer-actions'):
                button('Fechar', dialog.close, secondary=True)
                button('Salvar dados do cliente', lambda: perform(lambda: business.update_sale_notes(
                    sale['id'], customer.value, phone.value, event.value, notes.value), 'Dados atualizados.',
                    lambda: (dialog.close(), refresh())))
        dialog.open()

    def cancel_sale_dialog(sale, refresh):
        snapshot = business.sale_snapshot(sale['id'])
        with ui.dialog() as dialog, ui.card().classes('dialog-card dialog-small'):
            ui.label(f"Cancelar venda #{sale['id']}?").classes('heading')
            ui.label('Correção de lançamento: remove esta venda, seus recebimentos, despesas e repasses, inclusive baixas já registradas. As saídas das peças serão desfeitas na origem própria ou consignada, e o histórico será recalculado.').classes('muted')
            ui.label('Use quando o registro estiver errado. Esta ação não devolve dinheiro ao cliente nem recupera pagamentos bancários. Um backup e a trilha da correção serão preservados.').classes('info-panel')
            reason = field('Motivo do cancelamento')
            with ui.element('div').classes('footer-actions'):
                button('Manter venda', dialog.close, secondary=True)
                button('Confirmar cancelamento', lambda: perform(lambda: business.correct_sale(sale['id'], reason=reason.value, expected=snapshot),
                       'Lançamento removido e saldos recalculados.', lambda: (dialog.close(), refresh())), color='negative')
        dialog.open()

    def settlement_dialog(row, refresh, *, receive=False):
        with ui.dialog() as dialog, ui.card().classes('dialog-card dialog-small'):
            ui.label('Registrar recebimento' if receive else 'Registrar pagamento').classes('heading')
            value = row['gross_cents'] - row['fee_cents'] if receive else row['amount_cents']
            ui.label(brl(value)).classes('text-3xl text-primary font-semibold')
            when = field('Data efetiva', today(), kind='date')
            ui.label('Confirme depois de conferir o valor no banco ou no caixa. A baixa é integral.').classes('muted')
            with ui.element('div').classes('footer-actions'):
                button('Voltar', dialog.close, secondary=True)
                button('Confirmar baixa', lambda: perform(
                    lambda: business.receive(row['id'], when.value) if receive else business.pay_expense(row['id'], when.value),
                    'Baixa registrada.', lambda: (dialog.close(), refresh())), icon='check')
        dialog.open()

    @ui.page('/vendas')
    def sales_page():
        with shell('/vendas', 'Vendas'):
            head = heading('Boas vendas, bem registradas.', 'Peças, clientes, comissões e recebimentos com o mesmo histórico.')
            with head:
                button('Registrar venda', lambda: sale_dialog(body.refresh), icon='add')
            with ui.row().classes('w-full items-center mb-6 gap-3'):
                search = field('Buscar cliente, evento, origem ou peça').style('max-width:340px')
                button('Atualizar', lambda: body.refresh(), icon='refresh', secondary=True)
            search.on_value_change(lambda: body.refresh())

            @ui.refreshable
            def body():
                history_notice()
                sales = db.rows("SELECT s.*,COALESCE((SELECT SUM(quantity) FROM sale_items WHERE sale_id=s.id),0) AS own_pieces,COALESCE((SELECT SUM(quantity) FROM consignment_sale_items WHERE sale_id=s.id),0) AS consigned_pieces,CASE WHEN EXISTS(SELECT 1 FROM consignment_sale_items c WHERE c.sale_id=s.id) THEN CASE WHEN EXISTS(SELECT 1 FROM sale_items o WHERE o.sale_id=s.id) THEN 'Mista' ELSE 'Consignada' END ELSE 'Própria' END AS origin FROM sales s ORDER BY sale_date DESC,id DESC")
                term = (search.value or '').strip().casefold()
                import unicodedata
                def normalize(value):
                    return ''.join(c for c in unicodedata.normalize('NFD', str(value).casefold()) if not unicodedata.combining(c))
                details = {}
                for row in db.rows('SELECT sale_id,sku,name FROM sale_items UNION ALL SELECT sale_id,sku,name FROM consignment_sale_items'):
                    details[row['sale_id']] = details.get(row['sale_id'], '') + ' ' + row['sku'] + ' ' + row['name']
                def searchable(sale):
                    aliases = (' consignada consignado consignação' if sale['consigned_pieces'] else '') + (' própria próprio' if sale['own_pieces'] else '')
                    return normalize(' '.join([sale['customer'], sale['channel_name'], sale['seller_name'], sale['event'], sale['origin'], sale['method'], str(sale['id']), details.get(sale['id'], ''), aliases]))
                sales = [s for s in sales if normalize(term) in searchable(s)]
                active = [s for s in sales if not s['cancelled_on'] and s['operation']=='sale']
                withdrawals = [s for s in sales if not s['cancelled_on'] and s['operation']=='personal']
                ui.label(f'Retiradas pessoais neste filtro: {len(withdrawals)}').classes('muted')
                ui.label(f"Neste filtro: {len(active)} vendas não canceladas · {sum(s['own_pieces'] for s in active)} peças próprias · {sum(s['consigned_pieces'] for s in active)} peças consignadas · {len(sales) - len(active)} vendas canceladas").classes('info-panel mb-4')
                if not sales:
                    empty('Sua próxima venda começa aqui.', 'Use Registrar venda para escolher as peças e a forma de pagamento.', 'shopping_bag')
                else:
                    formatted = [{**s, 'operation_label':'Retirada pessoal' if s['operation']=='personal' else 'Venda', 'value':brl(s['cost_cents'] if s['operation']=='personal' else s['revenue_cents']), 'net':'Não se aplica' if s['operation']=='personal' else brl(s['net_cents'] if s['cost_status'] == 'confirmed' else None),
                                  'status': ('Cancelada' if s['cancelled_on'] else 'Registrada') + (' · Em conferência' if s['cost_status'] == 'pending' else '')} for s in sales]
                    tbl = table(formatted, [('id', 'VENDA'), ('sale_date', 'DATA'), ('customer', 'CLIENTE'),
                                            ('operation_label','OPERAÇÃO'), ('channel_name','CANAL'), ('seller_name','VENDEDORA'), ('event', 'EVENTO'), ('origin', 'ORIGEM'), ('value', 'VENDA / CUSTO DA RETIRADA'), ('net', 'CONTRIBUIÇÃO DA VENDA'), ('status', 'SITUAÇÃO')], selection='single')
                    with ui.row().classes('gap-3 mt-4 mb-8'):
                        button('Detalhes / cliente', lambda: choose(tbl, lambda s: sale_details(s, body.refresh)), icon='receipt_long', secondary=True)
                        button('Cancelar venda', lambda: choose(tbl, lambda s: cancel_sale_dialog(s, body.refresh)), secondary=True, color='negative')
                        button('Editar venda', lambda: choose(tbl, lambda s: sale_dialog(body.refresh, s)), icon='edit', secondary=True)
                        button('Exportar vendas', lambda: ui.download.content(reports.csv_bytes(sales),
                               f'vendas-{today()}.csv', 'text/csv'), icon='download', secondary=True)
                ui.label('Recebimentos a conferir').classes('section-title mt-4 mb-2')
                ui.label('Parcelas abertas, já descontada a taxa do cartão.').classes('muted mb-4')
                receivables = db.rows('SELECT r.*,s.customer FROM receivables r JOIN sales s ON s.id=r.sale_id '
                                      'WHERE r.paid_on IS NULL AND r.voided_on IS NULL ORDER BY r.due_on,r.id')
                if receivables:
                    rec = table([{**r, 'value': brl(r['gross_cents'] - r['fee_cents']),
                                  'status': 'Vencido' if r['due_on'] < today() else 'A receber'} for r in receivables],
                                [('sale_id', 'VENDA'), ('installment', 'PARCELA'), ('customer', 'CLIENTE'),
                                 ('due_on', 'VENCIMENTO'), ('value', 'LÍQUIDO A RECEBER'), ('status', 'SITUAÇÃO')], selection='single')
                    button('Registrar recebimento', lambda: choose(rec, lambda r: settlement_dialog(r, body.refresh, receive=True)),
                           icon='check', secondary=True).classes('mt-4')
                else:
                    ui.label('Nenhum recebimento pendente.').classes('info-panel')
            body()

    def expense_dialog(refresh):
        with ui.dialog() as dialog, ui.card().classes('dialog-card dialog-small'):
            ui.label('Adicionar despesa').classes('heading')
            category = ui.select(['Marketing', 'Embalagens', 'Frete', 'Eventos', 'Salários', 'Aluguel', 'Website',
                                  'Serviços', 'Outras despesas'], value='Outras despesas', label='Categoria').props('outlined dense')
            description = field('Descrição da despesa')
            vendor = field('Fornecedor / favorecido')
            amount = money_field('Valor (R$)')
            with ui.element('div').classes('formgrid'):
                when = field('Data da despesa', today(), kind='date')
                due = field('Vencimento', today(), kind='date')
                paid = ui.checkbox('Já paga', value=False)
                paid_date = field('Data do pagamento', today(), kind='date')
            ui.label('Taxas, impostos e comissões informados na venda já fazem parte do resultado. '
                     'Use as contas vinculadas para dar baixa nesses pagamentos.').classes('muted')
            key = str(uuid4())
            with ui.element('div').classes('footer-actions'):
                button('Voltar', dialog.close, secondary=True)
                button('Salvar despesa', lambda: perform(lambda: business.create_expense(dict(category=category.value,
                       description=description.value, vendor=vendor.value, amount=amount.value, occurred_on=when.value,
                       due_on=due.value, paid_on=paid_date.value if paid.value else None), key=key),
                       'Despesa registrada.', lambda: (dialog.close(), refresh())), icon='check')
        dialog.open()

    def expense_cancel_dialog(expense, refresh):
        with ui.dialog() as dialog, ui.card().classes('dialog-card dialog-small'):
            ui.label('Cancelar despesa avulsa').classes('heading')
            ui.label(expense['description']).classes('muted')
            reason = field('Motivo do cancelamento')
            with ui.element('div').classes('footer-actions'):
                button('Voltar', dialog.close, secondary=True)
                button('Confirmar cancelamento', lambda: perform(lambda: business.cancel_expense(expense['id'], reason.value),
                       'Despesa cancelada.', lambda: (dialog.close(), refresh())), color='negative')
        dialog.open()

    def return_consignment_dialog(lot, refresh):
        key = str(uuid4())
        with ui.dialog() as dialog, ui.card().classes('dialog-card dialog-small'):
            ui.label(f"Devolver consignado · lote #{lot['id']}").classes('heading')
            ui.label(f"{lot['sku']} · {lot['name']} · saldo atual {lot['stock']} peças").classes('muted')
            quantity = field('Quantidade a devolver', '1')
            when = field('Data da devolução', today(), kind='date')
            reason = field('Motivo da devolução')
            ui.label('Registra a devolução física à matriz. Não gera despesa, venda ou documento fiscal.').classes('muted')
            button('Confirmar devolução', lambda: perform(lambda: business.return_consignment(
                lot['id'], quantity.value, reason.value, when=when.value, key=key),
                'Devolução registrada.', lambda: (dialog.close(), refresh())), icon='check')
            button('Voltar', dialog.close, secondary=True)
        dialog.open()

    def cancel_return_dialog(row, refresh):
        if row['cancelled_at']:
            ui.notify('Esta devolução já foi cancelada.', type='info')
            return
        with ui.dialog() as dialog, ui.card().classes('dialog-card dialog-small'):
            ui.label('Cancelar devolução').classes('heading')
            ui.label(f"{row['sku']} · {-row['quantity']} peça(s) · lote #{row['lot_id']}").classes('muted')
            ui.label('Use para corrigir uma devolução lançada por engano. As peças voltam ao saldo e a saída original deixa de contar nos saldos históricos.').classes('info-panel')
            reason = field('Motivo da correção')
            button('Confirmar cancelamento da devolução', lambda: perform(
                lambda: business.cancel_consignment_return(row['id'], reason.value),
                'Devolução cancelada. Saldo consignado restaurado.', lambda: (dialog.close(), refresh())), icon='undo')
            button('Manter devolução', dialog.close, secondary=True)
        dialog.open()

    @ui.page('/consignacoes')
    def consignments_page():
        with shell('/consignacoes', 'Consignação'):
            heading('Peças consignadas, contas separadas.', 'Recebidas da matriz sem compra inicial. O repasse é gerado conforme as vendas.')
            search = field('Buscar peça ou NF-e').classes('mb-4')
            @ui.refreshable
            def body():
                lots = business.consignment_lots()
                with ui.element('div').classes('metric-grid'):
                    metric('Peças consignadas em mãos', str(sum(l['stock'] for l in lots)),
                           'Saldo atual de todos os lotes', 'inventory_2')
                    metric('Valor consignado em mãos', brl(sum(l['stock'] * l['unit_cost_cents'] for l in lots)),
                           'A custo de repasse à matriz', 'diamond', True)
                ui.label('Totais gerais, independentemente da busca. O valor das peças em mãos não é uma dívida: '
                         'o repasse é gerado quando elas são vendidas.').classes('muted mb-4')
                term = (search.value or '').strip().casefold()
                lots = [l for l in lots if term in (l['sku'] + ' ' + l['name'] + ' ' + l['invoice_number']).casefold()]
                ui.label(f"Neste filtro: {sum(l['stock'] for l in lots)} peças · {brl(sum(l['stock'] * l['unit_cost_cents'] for l in lots))} a custo de repasse").classes('info-panel mb-4')
                if not lots:
                    empty('Nenhum lote consignado encontrado.', 'Em Compras e XML, escolha a modalidade Consignação.', 'inventory_2')
                else:
                    rows = [{**l, 'unit_cost': brl(l['unit_cost_cents'])} for l in lots]
                    tbl = table(rows, [('id', 'LOTE'), ('invoice_number', 'NF-e'), ('received_on', 'ENTRADA'), ('sku', 'CÓDIGO'), ('name', 'PEÇA'),
                                      ('quantity', 'RECEBIDAS'), ('sold', 'VENDIDAS LÍQUIDAS'), ('returned', 'DEVOLVIDAS'), ('stock', 'EM MÃOS'), ('unit_cost', 'REPASSE / UN.')], selection='single')
                    button('Devolver peças à matriz', lambda: choose(tbl, lambda l: return_consignment_dialog(l, body.refresh)), secondary=True).classes('my-3')
                    button('Exportar lotes', lambda: ui.download.content(reports.csv_bytes(lots), f'consignacao-{today()}.csv', 'text/csv'), secondary=True)
                ui.label('Repasses por venda').classes('section-title mt-6')
                obligations = db.rows("SELECT * FROM expenses WHERE category='Repasse consignação' ORDER BY occurred_on DESC,id DESC")
                ui.label(f"Pendente: {brl(sum(r['amount_cents'] for r in obligations if not r['paid_on'] and not r['cancelled_on']))} · Pago: {brl(sum(r['amount_cents'] for r in obligations if r['paid_on']))}").classes('muted')
                if obligations:
                    table([{**r, 'value': brl(r['amount_cents']), 'state': 'Cancelado' if r['cancelled_on'] else 'Pago' if r['paid_on'] else 'A pagar'} for r in obligations],
                          [('sale_id', 'VENDA'), ('description', 'REPASSE'), ('due_on', 'VENCIMENTO'), ('value', 'VALOR'), ('paid_on', 'PAGAMENTO'), ('state', 'SITUAÇÃO')])
                button('Registrar pagamentos em Despesas', lambda: ui.navigate.to('/despesas'), secondary=True)
                ui.label('Peças devolvidas à matriz').classes('section-title mt-6')
                returns = db.rows("SELECT m.*,p.sku,p.name,l.unit_cost_cents,c.cancelled_at,c.reason AS cancellation_reason FROM consignment_moves m JOIN consignment_lots l ON l.id=m.lot_id JOIN products p ON p.id=l.product_id LEFT JOIN consignment_return_cancellations c ON c.movement_id=m.id WHERE m.kind='RETURN' ORDER BY m.occurred_on DESC,m.id DESC")
                ui.label(f"Total devolvido ativo: {sum(-r['quantity'] for r in returns if not r['cancelled_at'])} peças · {brl(sum(-r['quantity'] * r['unit_cost_cents'] for r in returns if not r['cancelled_at']))}").classes('info-panel mb-3')
                ui.label('Valores a custo de repasse à matriz. Totais gerais; devoluções canceladas não entram na soma.').classes('muted')
                if returns:
                    return_table = table([{**r, 'pieces': -r['quantity'], 'unit_value': brl(r['unit_cost_cents']), 'total_value': brl(-r['quantity'] * r['unit_cost_cents']), 'state': 'Cancelada' if r['cancelled_at'] else 'Devolvida'} for r in returns],
                        [('occurred_on', 'DATA'), ('lot_id', 'LOTE'), ('sku', 'CÓDIGO'), ('name', 'PEÇA'), ('pieces', 'QUANTIDADE'), ('unit_value', 'VALOR / PEÇA'), ('total_value', 'VALOR TOTAL'), ('reason', 'MOTIVO'), ('state', 'SITUAÇÃO'), ('cancellation_reason', 'MOTIVO DA CORREÇÃO')], selection='single')
                    button('Cancelar devolução', lambda: choose(return_table, lambda r: cancel_return_dialog(r, body.refresh)), secondary=True, icon='undo').classes('my-3')
                else:
                    ui.label('Nenhuma devolução registrada.').classes('muted')
                movements = db.rows("SELECT m.*,p.sku,c.cancelled_at FROM consignment_moves m LEFT JOIN consignment_return_cancellations c ON c.movement_id=m.id JOIN consignment_lots l ON l.id=m.lot_id JOIN products p ON p.id=l.product_id ORDER BY m.occurred_on DESC,m.id DESC")
                with ui.expansion('Histórico de vendas, cancelamentos e devoluções', icon='history').classes('w-full mt-4'):
                    table([{**m, 'kind_label': {'SALE': 'Venda', 'CANCELLATION': 'Cancelamento', 'RETURN': 'Devolução'}[m['kind']] + (' · cancelada' if m['cancelled_at'] else '')} for m in movements],
                          [('occurred_on', 'DATA'), ('lot_id', 'LOTE'), ('sku', 'PEÇA'), ('kind_label', 'MOVIMENTO'), ('quantity', 'QUANTIDADE'), ('sale_id', 'VENDA'), ('reason', 'MOTIVO')])
            search.on_value_change(lambda: body.refresh())
            body()

    def pay_expenses_dialog(selected, refresh):
        if not selected:
            ui.notify('Selecione uma ou mais despesas na tabela.', type='info')
            return
        rows = [dict(r) for r in selected]
        if any(r['paid_on'] or r['cancelled_on'] or not r['cash_effect'] for r in rows):
            ui.notify('Selecione somente despesas pendentes de pagamento.', type='warning')
            return
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label('Pagar despesas selecionadas').classes('heading')
            ui.label(f"{len(rows)} despesa(s) · Total {brl(sum(r['amount_cents'] for r in rows))}").classes('text-xl font-semibold')
            table(rows, [('description', 'DESCRIÇÃO'), ('due_on', 'VENCIMENTO'), ('value', 'VALOR')])
            when = field('Data do pagamento', today(), kind='date')
            ui.label('Esta data será aplicada a todas as despesas selecionadas. Confirme somente os pagamentos já realizados.').classes('muted')
            with ui.element('div').classes('footer-actions'):
                button('Voltar', dialog.close, secondary=True)
                button('Confirmar pagamentos', lambda: perform(
                    lambda: business.pay_expenses([r['id'] for r in rows], when.value),
                    'Pagamentos registrados.', lambda: (dialog.close(), refresh())), icon='check')
        dialog.open()

    @ui.page('/despesas')
    def expenses_page():
        with shell('/despesas', 'Despesas'):
            head = heading('Compromissos sob controle.', 'Despesas, compras e repasses. Saldos individualizados de comissão ficam na aba Comissões.')
            with head:
                button('Adicionar despesa', lambda: expense_dialog(body.refresh), icon='add')
            with ui.row().classes('w-full items-center mb-6 gap-3'):
                status = ui.select(['A pagar', 'Pagas', 'Todas'], value='A pagar', label='Situação').props('outlined dense').style('width:170px')
                search = field('Buscar descrição, categoria, fornecedor').style('max-width:350px')
                button('Atualizar', lambda: body.refresh(), icon='refresh', secondary=True)
            status.on_value_change(lambda: body.refresh())
            search.on_value_change(lambda: body.refresh())

            @ui.refreshable
            def body():
                rows = db.rows('SELECT * FROM expenses WHERE beneficiary_id IS NULL ORDER BY due_on DESC,id DESC')
                term = (search.value or '').strip().casefold()
                rows = [r for r in rows if term in (r['description'] + ' ' + r['category'] + ' ' + r['vendor']).casefold()
                        and (status.value == 'Todas' or (status.value == 'A pagar' and not r['paid_on']
                             and not r['cancelled_on'] and r['cash_effect']) or (status.value == 'Pagas' and r['paid_on']))]
                if not rows:
                    empty('Nenhum lançamento neste filtro.', 'As compras e comissões a pagar também aparecem aqui.', 'account_balance_wallet')
                    return
                def state(row):
                    if row['cancelled_on']:
                        return 'Cancelada'
                    if not row['cash_effect']:
                        return 'Sem nova saída de caixa'
                    return 'Paga' if row['paid_on'] else ('Vencida' if row['due_on'] < today() else 'A pagar')
                formatted = [{**r, 'value': brl(r['amount_cents']), 'status': state(r),
                              'type': 'Despesa' if r['affects_result'] else 'Compra / repasse / reembolso'} for r in rows]
                tbl = table(formatted, [('due_on', 'VENCIMENTO'), ('category', 'CATEGORIA'), ('description', 'DESCRIÇÃO'),
                                        ('value', 'VALOR'), ('status', 'SITUAÇÃO'), ('type', 'NATUREZA')], selection='multiple')
                with ui.row().classes('gap-3 mt-4'):
                    button('Pagar selecionadas', lambda: pay_expenses_dialog(tbl.selected, body.refresh), icon='check', secondary=True)
                    button('Cancelar despesa avulsa', lambda: choose(tbl, lambda r: expense_cancel_dialog(r, body.refresh)), secondary=True, color='negative')
                    button('Exportar seleção', lambda: ui.download.content(reports.csv_bytes(rows),
                           f'despesas-{today()}.csv', 'text/csv'), icon='download', secondary=True)
            body()

    @ui.page('/relatorios')
    def reports_page():
        with shell('/relatorios', 'Relatórios'):
            heading('Números que você consegue explicar.', 'Resultado, caixa, referências econômicas e cópia dos seus dados.')
            with ui.row().classes('items-end gap-3 mb-5 w-full'):
                start = field('De', add_months(today()[:7] + '-01', -5), kind='date').style('width:165px')
                end = field('Até', today(), kind='date').style('width:165px')
                button('Atualizar relatório', lambda: statement.refresh(), secondary=True, icon='refresh')

            def preset(months=None):
                start.set_value(add_months(today()[:7] + '-01', -(months-1)) if months else today()[:4]+'-01-01')
                end.set_value(today())
                statement.refresh()
            with ui.row().classes('gap-2 mb-4'):
                button('Últimos 6 meses', lambda: preset(6), secondary=True)
                button('Últimos 12 meses', lambda: preset(12), secondary=True)
                button('Este ano', lambda: preset(), secondary=True)

            def all_history():
                dates=db.rows("SELECT MIN(d) AS first,MAX(d) AS last FROM (SELECT sale_date AS d FROM sales UNION ALL SELECT cancelled_on FROM sales UNION ALL SELECT occurred_on FROM expenses UNION ALL SELECT paid_on FROM expenses UNION ALL SELECT occurred_on FROM movements UNION ALL SELECT issued_on FROM invoices UNION ALL SELECT paid_on FROM receivables UNION ALL SELECT occurred_on FROM consignment_moves UNION ALL SELECT settled_on FROM commission_settlements)")[0]
                start.set_value(dates['first'] or today())
                end.set_value(max(today(),dates['last'] or today()))
                statement.refresh()
            def select_month():
                import calendar
                if not month.value:
                    return
                first=month.value+'-01'
                try:
                    parsed=__import__('datetime').date.fromisoformat(first)
                except ValueError:
                    ui.notify('Selecione um mês válido.',type='negative');return
                start.set_value(first)
                end.set_value(f'{parsed.year:04d}-{parsed.month:02d}-{calendar.monthrange(parsed.year,parsed.month)[1]}')
                statement.refresh()
            with ui.row().classes('items-end gap-2 mb-4'):
                button('Todo o histórico',all_history,secondary=True)
                month=field('Mês específico',today()[:7],kind='month')
                button('Aplicar mês',select_month,secondary=True)

            @ui.refreshable
            def statement():
                from .analytics import dashboard
                from .dashboard_ui import render_dashboard
                history_notice()
                try:
                    data = dashboard(db, start.value, end.value)
                except RuleError as exc:
                    ui.label(str(exc)).classes('info-panel')
                    return
                from .locations import balances
                with db.connect() as conn:
                    from .locations import loss_report
                    data['losses']=loss_report(conn,start.value,end.value)
                    locs={r['id']:r['name'] for r in conn.execute('SELECT * FROM locations')}
                    data['locations']=[dict(location=locs[k],quantity=q,ownership='Consignado' if l else 'Próprio') for (p,l,k),q in balances(conn,end.value).items() if q]
                render_dashboard(data, metric, table)
            statement()

            with ui.column().classes('surface gap-4 mb-6'):
                ui.label('CDI e inflação como referência').classes('section-title')
                ui.label('Simule o rendimento de um capital em meses completos. A margem das vendas e o valor do '
                         'estoque atual não são uma taxa de retorno do capital investido.').classes('muted')
                with ui.row().classes('w-full items-end gap-3'):
                    first = field('Mês inicial', add_months(today()[:7] + '-01', -12)[:7], kind='month').style('width:170px')
                    last = field('Mês final', add_months(today()[:7] + '-01', -1)[:7], kind='month').style('width:170px')
                    capital = money_field('Capital hipotético (R$)', '10.000,00').style('width:210px')
                result_box = ui.column().classes('w-full')

                async def compare():
                    consult.disable()
                    result_box.clear()
                    with result_box:
                        ui.spinner(size='24px')
                        ui.label('Consultando as séries mensais do Banco Central…').classes('muted')
                    try:
                        amount = cents(capital.value)
                        if amount <= 0:
                            raise RuleError('Informe um capital maior que zero.')
                        result = await fetch_benchmarks(first.value, last.value)
                        result_box.clear()
                        with result_box:
                            for name, rate in result['rates'].items():
                                ui.label(f'{name}: {rate * 100:.2f}% acumulado · variação {brl(rounded(amount * rate))} · '
                                         f'valor final {brl(rounded(amount * (1 + rate)))}').classes('info-panel')
                            ui.label(f"Período {result['start']} a {result['end']} · consulta {result['retrieved_at'][:10]}. "
                                     'Taxas compostas, sem impostos ou custos de uma aplicação. IPCA indica poder de compra, não rendimento financeiro.').classes('muted')
                    except RuleError as exc:
                        result_box.clear()
                        with result_box:
                            ui.label(str(exc)).classes('info-panel')
                    finally:
                        consult.enable()
                consult = button('Consultar e comparar', compare, icon='calculate', secondary=True)
                with ui.row().classes('gap-4'):
                    ui.link('BCB · CDI mensal (4391)', 'https://dadosabertos.bcb.gov.br/dataset/4391-taxa-de-juros---cdi-acumulada-no-mes', new_tab=True).classes('text-xs text-secondary')
                    ui.link('BCB · IPCA (433)', 'https://dadosabertos.bcb.gov.br/dataset/433-indice-nacional-de-precos-ao-consumidor-amplo-ipca', new_tab=True).classes('text-xs text-secondary')

            with ui.column().classes('surface gap-4'):
                ui.label('Seus dados, com você').classes('section-title')
                ui.label('O backup inclui cadastros, movimentos, documentos XML e histórico. Guarde uma cópia fora do computador.').classes('muted')

                def backup():
                    with tempfile.TemporaryDirectory() as directory:
                        requested = Path(directory) / ('flow.json' if getattr(db, 'is_postgres', False) else 'flow.sqlite3')
                        path = db.backup(requested)
                        mime = 'application/json' if path.suffix == '.json' else 'application/octet-stream'
                        ui.download.content(path.read_bytes(), f'fe-flow-backup-{today()}{path.suffix}', mime)
                with ui.row().classes('gap-3'):
                    button('Baixar backup completo', backup, icon='save_alt')
                    button('Exportar dados em JSON', lambda: ui.download.content(reports.export_json(db),
                           f'fe-flow-dados-{today()}.json', 'application/json'), icon='download', secondary=True)

                def restore_dialog():
                    selected = {}
                    with ui.dialog() as dialog, ui.card().classes('dialog-card'):
                        ui.label('Restaurar backup completo').classes('section-title')
                        ui.label('Substitui todos os dados deste computador pelo backup escolhido. Não combina bancos. '
                                 'O banco atual será guardado automaticamente na pasta backups. '
                                 'Após confirmar, o app será encerrado; abra novamente para concluir.').classes('info-panel')
                        status = ui.label('Selecione um backup .sqlite3 de até 100 MB.')
                        async def receive(event):
                            selected['raw'] = await event.file.read()
                            status.set_text('Selecionado: ' + event.file.name)
                        ui.upload(label='Selecionar backup', auto_upload=True, max_files=1,
                                  max_file_size=MAX_BACKUP_BYTES, on_upload=receive,
                                  on_rejected=lambda: ui.notify('Envie um backup de até 100 MB.', type='warning')).props('accept=.sqlite3')
                        confirmation = ui.input('Digite RESTAURAR para confirmar')
                        def restore():
                            if confirmation.value != 'RESTAURAR' or 'raw' not in selected:
                                ui.notify('Selecione o backup e digite RESTAURAR.', type='warning')
                                return
                            try:
                                stage_restore(db, selected['raw'])
                            except Exception:
                                logging.exception('Backup recusado')
                                ui.notify('Backup inválido ou incompatível. Os dados atuais foram preservados.', type='negative')
                                return
                            dialog.close()
                            ui.notify('Backup validado. O app será encerrado. Abra novamente para concluir a restauração.', timeout=0)
                            app.shutdown()
                        button('Confirmar restauração e encerrar', restore, icon='restore')
                        button('Voltar', dialog.close, secondary=True)
                    dialog.open()
                if getattr(db, 'is_postgres', False):
                    ui.label('Online: dados persistidos no PostgreSQL/Supabase. A restauração de arquivo SQLite fica disponível apenas na versão local.').classes('muted')
                else:
                    button('Restaurar backup', restore_dialog, icon='restore', secondary=True)
                    ui.label(f'Pasta dos dados: {db.path.parent}').classes('muted')

    from .locations_ui import register_locations
    register_locations(business,shell,heading,field,button,table,perform)
    from .commerce_ui import register_commerce_pages
    register_commerce_pages(business,shell,heading,field,money_field,button,table,choose,perform)

