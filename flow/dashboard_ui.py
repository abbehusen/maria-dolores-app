"""Dashboard de relatórios: renderização sem alterar registros."""
from datetime import date, timedelta
from nicegui import ui
from .money import brl
from .analytics import sales_view
from .reports import csv_bytes


def render_dashboard(data, metric, table):
    values, previous = data['current'], data['previous']
    start, end = data['start'], data['end']
    def money(value):
        return 'Em conferência' if value is None else f'{value/100:.2f}'.replace('.', ',')
    def export(label, rows, filename):
        ui.button(label, icon='download', on_click=lambda: ui.download.content(csv_bytes(rows), f'{filename}-{start}-{end}.csv', 'text/csv')).props('outline').classes('my-3')
    def comparison(key):
        current = values[key]
        old = previous[key] if previous else None
        if current is None or old is None:
            return 'Comparação indisponível'
        delta = current-old
        change = f"{'+' if delta>0 else ''}{brl(delta)} vs. anterior"
        if old > 0:
            change += f' ({delta/old*100:+.1f}%)'
        elif old == 0:
            change += ' · base anterior zero'
        return change
    def line_chart(title, series):
        with ui.column().classes('surface w-full gap-2'):
            ui.label(title).classes('section-title')
            ui.echart({'color':['#11634b','#ad8958','#82afa0'], 'tooltip':{'trigger':'axis'}, 'legend':{'bottom':0},
                'grid':{'left':65,'right':20,'top':25,'bottom':65},
                'xAxis':{'type':'category','data':[r['month'][5:]+'/'+r['month'][:4] for r in data['months']]},
                'yAxis':{'type':'value','name':'R$'},
                'series':[{'name':label,'type':kind,'data':[r[key]/100 if r[key] is not None else None for r in data['months']], 'connectNulls':False} for label,key,kind in series]}).classes('w-full').style('height:320px')
    def bars(title, rows, label_key, value_key, unit='R$', limit=10):
        with ui.column().classes('surface w-full gap-2'):
            ui.label(title).classes('section-title')
            if not rows:
                ui.label('Sem lançamentos neste período.').classes('muted')
                return
            ranked = sorted(rows,key=lambda r:r[value_key],reverse=True)
            ranked = (ranked[:limit] if limit else ranked)[::-1]
            ui.echart({'color':['#11634b'],'tooltip':{'trigger':'axis'},'grid':{'left':150,'right':25,'top':20,'bottom':40},
                'xAxis':{'type':'value','name':unit,'minInterval':1 if unit=='Vendas' else 0},'yAxis':{'type':'category','data':[r[label_key] for r in ranked], 'axisLabel':{'width':130,'overflow':'truncate'}},
                'series':[{'type':'bar','data':[r[value_key]/(100 if unit=='R$' else 1) for r in ranked]}]}).classes('w-full').style(f'height:{max(320,len(ranked)*32+80)}px')
    def details(title, rows, columns):
        with ui.expansion(title,icon='table_rows').classes('w-full surface my-3'):
            if rows:
                table(rows,columns)
            else:
                ui.label('Nenhum registro neste recorte.').classes('muted')
    ui.label(f'Período aplicado: {start} a {end}').classes('section-title')
    ui.label(f"Comparação: {data['previous_start']} a {data['previous_end']} · mesma quantidade de dias. Meses nas extremidades podem ser parciais.").classes('muted mb-4')
    with ui.tabs().classes('w-full') as tabs:
        result_tab=ui.tab('Resultado',icon='insights')
        cash_tab=ui.tab('Caixa',icon='account_balance_wallet')
        sales_tab=ui.tab('Vendas',icon='shopping_bag')
        stock_tab=ui.tab('Estoque e consignação',icon='inventory_2')
        commercial_tab=ui.tab('Canais e clientes',icon='groups')
    with ui.tab_panels(tabs,value=result_tab).classes('w-full bg-transparent'):
        with ui.tab_panel(result_tab).classes('px-0 space-y-5'):
            with ui.element('div').classes('metric-grid'):
                metric('Receita após descontos',brl(values['revenue_cents']),comparison('revenue_cents'),'payments')
                metric('Resultado gerencial',brl(values['net_cents']),comparison('net_cents'),'trending_up',True)
                metric('Margem do resultado',f"{values['net_cents']/values['revenue_cents']*100:.1f}%" if values['net_cents'] is not None and values['revenue_cents']>0 else '—','Resultado ÷ receita após descontos','percent')
                metric('Despesas gerais',brl(values['operating_cents']),comparison('operating_cents'),'receipt_long')
            line_chart('Receita e resultado ao longo do período',[('Receita','revenue_cents','bar'),('Resultado','net_cents','line')])
            with ui.element('div').classes('two-col'):
                with ui.column().classes('surface gap-2'):
                    ui.label('Resultado gerencial do período').classes('section-title')
                    lines=[('Valor das peças antes do desconto',values['revenue_cents']+data['discount_cents']),('Descontos concedidos',-data['discount_cents']),('Receita após descontos',values['revenue_cents']),('Custo das peças vendidas',None if values['cost_cents'] is None else -values['cost_cents']),('Taxas de cartão',-values['fee_cents']),('Impostos das vendas',-values['tax_cents']),('Comissões vendedoras',-values['seller_cents']),('Comissões lojas / eventos',-values['store_cents']),('Despesas gerais',-values['operating_cents']),('Perdas de peças (menos estornos)',-values.get('loss_cents',0)),('Ganhos / perdas de conferência',values['adjustment_cents']),('Resultado',values['net_cents'])]
                    for label,value in lines:
                        with ui.element('div').classes('list-line'):
                            ui.label(label)
                            ui.label(brl(value)).classes('font-semibold')
                    export('Exportar resultado em CSV',[{'Linha':label,'Valor (R$)':money(value)} for label,value in lines],'resultado')
                grouped={}
                for row in data['operating']:
                    grouped[row['category']]=grouped.get(row['category'],0)+row['amount_cents']
                bars('Top 10 despesas gerais por categoria',[{'category':k,'amount':v} for k,v in grouped.items()],'category','amount')
            ui.label('Resultado considera a data das vendas e despesas. Compras de estoque e pagamentos de repasse não são descontados novamente: o custo da peça entra quando ela é vendida. Custos pendentes aparecem como Em conferência.').classes('info-panel')
            details('Despesas que compõem o resultado',[{**r,'value':brl(r['amount_cents'])} for r in data['operating']], [('date','DATA'),('category','CATEGORIA'),('description','DESCRIÇÃO'),('value','VALOR')])
            details('Perdas de peças e estornos',[{**r,'value':brl(r['cost_cents'])} for r in data.get('losses',[])],[('date','DATA'),('event','OPERAÇÃO'),('sku','CÓDIGO'),('location','LOCAL'),('quantity','PEÇAS'),('value','CUSTO'),('reason','MOTIVO')])
            details('Conferências que afetam o resultado',[{**r,'value':brl(r['cost_cents'] if r['cost_status']=='confirmed' else None)} for r in data['adjustments']],[('date','DATA'),('sku','CÓDIGO'),('quantity','AJUSTE DE PEÇAS'),('reason','MOTIVO'),('value','GANHO / PERDA')])
            details('Evolução mensal detalhada',[{'id':r['month'],'month':r['month'],'revenue':brl(r['revenue_cents']),'cost':brl(r['cost_cents']),'net':brl(r['net_cents'])} for r in data['months']], [('month','MÊS'),('revenue','RECEITA'),('cost','CUSTO DAS PEÇAS'),('net','RESULTADO')])
        with ui.tab_panel(cash_tab).classes('px-0 space-y-5'):
            with ui.element('div').classes('metric-grid'):
                metric('Recebido no período',brl(values['cash_in_cents']),comparison('cash_in_cents'),'south_west')
                metric('Pago no período',brl(values['cash_out_cents']),comparison('cash_out_cents'),'north_east')
                metric('Variação do caixa',brl(values['cash_net_cents']),comparison('cash_net_cents'),'account_balance_wallet',True)
                metric('A receber na data final',brl(values['receivable_cents']),f"A pagar: {brl(values['payable_cents'])}",'event')
            ui.label('Caixa mostra as datas efetivas de recebimento e pagamento, após taxas retidas. A variação não é o saldo bancário: não inclui saldo inicial, aportes ou retiradas.').classes('info-panel')
            line_chart('Entradas e saídas efetivas',[('Recebimentos','cash_in_cents','bar'),('Pagamentos','cash_out_cents','bar'),('Variação','cash_net_cents','line')])
            until=(date.fromisoformat(end)+timedelta(days=30)).isoformat()
            overdue_in=sum(r['gross_cents']-r['fee_cents'] for r in data['receivable'] if r['due_on']<end)
            overdue_out=sum(r['amount_cents'] for r in data['payable'] if r['due_on']<end)
            due_in=sum(r['gross_cents']-r['fee_cents'] for r in data['receivable'] if end<=r['due_on']<=until)
            due_out=sum(r['amount_cents'] for r in data['payable'] if end<=r['due_on']<=until)
            with ui.element('div').classes('metric-grid'):
                metric('Recebimentos vencidos',brl(overdue_in),f'Em aberto em {end}','schedule')
                metric('Pagamentos vencidos',brl(overdue_out),f'Em aberto em {end}','schedule')
                metric('A receber até +30 dias',brl(due_in),f'De {end} a {until}','event_available')
                metric('A pagar até +30 dias',brl(due_out),'Somente obrigações já registradas até a data final','event_busy')
            cash_rows=[dict(id=f"r-{r['id']}",date=r['paid_on'],kind='Recebimento',description=f"Venda #{r['sale_id']} · parcela {r['installment']} · {r['customer']}",value=r['gross_cents']-r['fee_cents']) for r in data['received']]
            cash_rows += [dict(id=f"p-{r['id']}",date=r['paid_on'],kind=r['category'],description=r['description'],value=-r['amount_cents']) for r in data['paid']]
            cash_rows.sort(key=lambda r:r['date'])
            details('Movimentações que compõem o caixa',[{**r,'amount':brl(r['value'])} for r in cash_rows],[('date','DATA EFETIVA'),('kind','TIPO'),('description','DESCRIÇÃO'),('amount','ENTRADA / SAÍDA')])
            export('Exportar movimentações de caixa',[{'Data':r['date'],'Tipo':r['kind'],'Descrição':r['description'],'Valor (R$)':money(r['value'])} for r in cash_rows],'caixa')
            details('Contas a receber na data final',[{**r,'amount':brl(r['gross_cents']-r['fee_cents'])} for r in data['receivable']],[('sale_id','VENDA'),('installment','PARCELA'),('customer','CLIENTE'),('due_on','VENCIMENTO'),('amount','LÍQUIDO')])
            details('Contas a pagar na data final',[{**r,'amount':brl(r['amount_cents'])} for r in data['payable']],[('description','DESCRIÇÃO'),('category','CATEGORIA'),('due_on','VENCIMENTO'),('amount','VALOR')])
        with ui.tab_panel(sales_tab).classes('px-0 space-y-5'):
            origin=ui.select({'all':'Todas as origens','own':'Peças próprias','consigned':'Peças consignadas'},value='all',label='Origem das peças — somente Vendas').props('outlined dense')
            ui.label('Em vendas mistas, o filtro considera só as peças da origem escolhida. Desconto e encargos são rateados pelo valor dos itens, com ajuste exato de centavos. Vendas e peças são líquidas dos cancelamentos antigos no período.').classes('muted')
            @ui.refreshable
            def sale_body():
                view=sales_view(data['sales'],origin.value)
                with ui.element('div').classes('metric-grid'):
                    metric('Vendas líquidas',str(view['count']),'Transações com peças da origem escolhida','shopping_bag')
                    metric('Peças vendidas líquidas',str(view['pieces']),'Vendas menos cancelamentos no período','diamond')
                    metric('Receita das peças',brl(view['revenue_cents']),'Após o desconto rateado','payments')
                    metric('Ticket das peças por venda',brl(view['ticket_cents']) if view['ticket_cents'] is not None else '—','Receita filtrada ÷ vendas líquidas','receipt')
                ui.label(f"Contribuição das vendas: {brl(view['contribution_cents'])} · Após custo, taxas, impostos e comissões; antes das despesas gerais.").classes('info-panel')
                bars('Top 10 produtos por receita',view['products'],'name','revenue_cents')
                details('Produtos vendidos',[{**r,'id':r['product_id'],'revenue':brl(r['revenue_cents']),'contribution':brl(r['contribution_cents'])} for r in view['products']],[('sku','CÓDIGO'),('name','PRODUTO'),('quantity','PEÇAS'),('revenue','RECEITA'),('contribution','CONTRIBUIÇÃO')])
                formatted=[{**r,'origin_label':'Própria' if r['origin']=='own' else 'Consignada','revenue':brl(r['revenue_cents']),'cost':brl(r['cost_cents']),'contribution':brl(r['contribution_cents'])} for r in view['lines']]
                details('Itens e vendas que compõem os indicadores',formatted,[('sale_id','VENDA'),('date','DATA'),('customer','CLIENTE'),('origin_label','ORIGEM'),('sku','CÓDIGO'),('quantity','PEÇAS'),('revenue','RECEITA'),('cost','CUSTO'),('contribution','CONTRIBUIÇÃO')])
                export('Exportar vendas deste filtro',[{'Venda':r['sale_id'],'Data':r['date'],'Cliente':r['customer'],'Origem':r['origin_label'],'Código':r['sku'],'Quantidade':r['quantity'],'Receita (R$)':money(r['revenue_cents']),'Contribuição (R$)':money(r['contribution_cents'])} for r in formatted],'vendas-relatorio')
            origin.on_value_change(lambda: sale_body.refresh())
            sale_body()
        with ui.tab_panel(stock_tab).classes('px-0 space-y-5'):
            ui.label(f'Posição em {end}. Os saldos consideram todas as entradas e saídas até essa data, independentemente do início do período.').classes('info-panel')
            with ui.element('div').classes('metric-grid'):
                metric('Estoque próprio a custo',brl(values['stock_cents']),f"{values['stock']} peças próprias",'diamond')
                metric('Consignado em mãos',brl(values['consigned_stock_cents']),f"{values['consigned_stock']} peças · custo de repasse",'inventory_2')
                metric('Repasse pendente',brl(values['consignment_payable_cents']),'Obrigação por consignados vendidos','payments')
                metric('Devolvido no período',brl(sum(r['value_cents'] for r in data['returns'])),f"{sum(r['quantity'] for r in data['returns'])} peças · exclui devoluções canceladas",'assignment_return')
            ui.label(f"Pagamentos no período · Compras próprias: {brl(values['own_purchase_paid_cents'])} · Repasses à matriz: {brl(values['consignment_paid_cents'])}").classes('muted')
            groups={}
            for r in data.get('locations',[]):
                g=groups.setdefault(r['location'],dict(location=r['location'],quantity=0,own=0,consigned=0))
                g['quantity']+=r['quantity'];g['consigned' if r['ownership']=='Consignado' else 'own']+=r['quantity']
            bars('Unidades por local na data final',list(groups.values()),'location','quantity',unit='Peças',limit=None)
            details('Estoque por local',list(groups.values()),[('location','LOCAL'),('own','PRÓPRIAS'),('consigned','CONSIGNADAS'),('quantity','TOTAL')])
            ui.link('Consultar peças e valores por local (saldo atual)','/locais')
            own=[{**r,'value':brl(r['value_cents'])} for r in data['own']]
            lots=[{**r,'value':brl(r['value_cents'])} for r in data['lots']]
            details('Peças próprias na data final',own,[('sku','CÓDIGO'),('name','PRODUTO'),('quantity','PEÇAS'),('value','CUSTO TOTAL')])
            details('Lotes consignados na data final',lots,[('invoice_number','NF-e'),('sku','CÓDIGO'),('name','PRODUTO'),('quantity','PEÇAS'),('value','VALOR DE REPASSE')])
            details('Devoluções do período',[{**r,'value':brl(r['value_cents'])} for r in data['returns']],[('date','DATA'),('sku','CÓDIGO'),('name','PRODUTO'),('quantity','PEÇAS'),('value','VALOR')])
            export('Exportar posição de estoque',[{'Origem':origin_label,'Código':r['sku'],'Produto':r['name'],'Peças':r['quantity'],'Valor (R$)':money(r['value_cents'])} for origin_label,rows in [('Própria',data['own']),('Consignada',data['lots'])] for r in rows],'estoque-posicao')
        with ui.tab_panel(commercial_tab).classes('px-0 space-y-5'):
            ui.label('Use De / Até, o seletor de mês ou Todo o histórico no topo. Quantidade representa registros de venda, não peças. Retiradas pessoais ficam fora; cancelamentos históricos são descontados na data do cancelamento.').classes('info-panel')
            for label,key in [('canal','channel'),('vendedora','seller')]:
                groups={}
                for row in data['commercial_groups']:
                    group=groups.setdefault(row[key],dict(name=row[key],count=0,revenue_cents=0))
                    group['count']+=row['count'];group['revenue_cents']+=row['revenue_cents']
                rows=list(groups.values())
                bars('Quantidade de vendas por '+label,rows,'name','count',unit='Vendas',limit=None)
                details('Detalhes por '+label,[dict(r,id=r['name'],value=brl(r['revenue_cents'])) for r in rows],[('name',label.upper()),('count','VENDAS'),('value','VALOR VENDIDO')])
                export('Exportar por '+label,rows,'vendas-por-'+label)
            customers=data['customer_groups']
            ui.label('Compras por cliente: valor das vendas após descontos, independentemente do recebimento. Inclui compras quitadas com comissão. Clientes sem identificação ficam agrupados.').classes('muted')
            bars('Valor comprado por cliente',customers,'name','revenue_cents',limit=None)
            details('Todos os clientes do período',[dict(r,value=brl(r['revenue_cents'])) for r in customers],[('name','CLIENTE'),('count','VENDAS'),('value','VALOR COMPRADO')])
            export('Exportar compras por cliente',customers,'compras-por-cliente')
    ui.label('Resultado e Caixa abrangem todas as origens. Correções e exclusões de lançamentos recalculam os períodos originais; cancelamentos antigos mantidos no histórico aparecem na data em que foram registrados.').classes('muted my-4')

    with ui.column().classes('surface gap-4 mt-4'):
        ui.label('Formas de pagamento').classes('section-title')
        ui.label('Vendido usa a data da venda; recebido e taxas usam a data da baixa. Crédito de comissão é compensação, sem entrada no caixa.').classes('muted')
        rows=[dict(r,id=r['method'],sold=brl(r['sold_cents']),received=brl(r['received_cents']),fees=brl(r['fees_cents']),compensated=brl(r['compensated_cents'])) for r in data['payment_methods']]
        table(rows,[('method','FORMA'),('sold','VALOR VENDIDO'),('received','RECEBIDO LÍQUIDO'),('fees','TAXAS RETIDAS'),('compensated','COMPENSADO')])
        bars('Valor vendido por forma de pagamento',data['payment_methods'],'method','sold_cents')
        export('Exportar formas de pagamento',data['payment_methods'],'formas-pagamento.csv')
        ui.label('Retiradas para uso pessoal').classes('section-title')
        ui.label('Custo retirado no período: '+brl(data['current']['personal_cost_cents'])+'. Não integra receita, despesas operacionais ou margem comercial.').classes('info-panel')
        table([dict(r,cost=brl(r['cost_cents'] if r['cost_status']=='confirmed' else None)) for r in data['personal']],[('id','REGISTRO'),('sale_date','DATA'),('customer','RESPONSÁVEL'),('cost','CUSTO RETIRADO')])

        ui.label('Vendas por canal e vendedora').classes('section-title')
        table([dict(r,id=i,revenue=brl(r['revenue_cents']),commission=brl(r['commission_cents'])) for i,r in enumerate(data['commercial_groups'])],[('channel','CANAL'),('seller','VENDEDORA'),('count','VENDAS'),('revenue','RECEITA'),('commission','COMISSÕES')])
