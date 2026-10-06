"""Clientes, canais e comissões."""
from uuid import uuid4
from decimal import Decimal
from nicegui import ui
from .money import brl, today
from . import reports
from .commerce import commission_open


def register_commerce_pages(business, shell, heading, field, money_field, button, table, choose, perform):
    db=business.db

    def client_dialog(refresh, record=None):
        r=record or {}
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label('Cadastro do cliente').classes('heading')
            fields={}
            with ui.element('div').classes('formgrid'):
                for key,label in [('name','Nome'),('phone','Telefone'),('email','E-mail'),('birthday','Aniversário (dia/mês)'),('city','Cidade'),('address','Endereço')]:
                    fields[key]=field(label,r.get(key,''))
                fields['notes']=ui.textarea('Preferências e observações',value=r.get('notes','')).props('outlined').classes('wide')
            consent=ui.checkbox('Cliente autorizou receber comunicações comerciais',value=bool(r.get('marketing_opt_in',0)))
            ui.label('O cadastro não envia mensagens. A exportação para mala direta inclui apenas quem autorizou.').classes('muted')
            button('Salvar cliente',lambda: perform(lambda:business.save_customer({**{k:v.value for k,v in fields.items()},'marketing_opt_in':consent.value},r.get('id')),'Cliente salvo.',lambda:(dialog.close(),refresh())),icon='save')
            button('Voltar',dialog.close,secondary=True)
        dialog.open()

    def client_history(r):
        with ui.dialog() as dialog,ui.card().classes('dialog-card'):
            ui.label(r['name']).classes('heading')
            ui.label(f"{r['purchases']} compras · Total: {brl(r['total_cents'])} · Última compra: {r['last_purchase'] or '—'}").classes('info-panel')
            table([dict(x,id=f"{x['id']}-{i}",sale_id=x['id']) for i,x in enumerate(business.customer_history(r['id']))],[('sale_id','VENDA'),('sale_date','DATA'),('sku','CÓDIGO'),('name','PEÇA'),('quantity','QUANTIDADE'),('method','PAGAMENTO')])
            ui.label('Inclui compras quitadas com crédito de comissão; exclui retiradas pessoais e vendas canceladas.').classes('muted')
            button('Fechar',dialog.close,secondary=True)
        dialog.open()

    @ui.page('/clientes')
    def clients_page():
        with shell('/clientes','Clientes'):
            heading('Clientes e suas histórias.','Cadastro, preferências e histórico de compras.')
            search=field('Buscar cliente, telefone ou e-mail')
            button('Novo cliente',lambda:client_dialog(body.refresh),icon='person_add')
            @ui.refreshable
            def body():
                records=business.customers()
                term=(search.value or '').casefold()
                rows=[dict(r,total=brl(r['total_cents']),consent='Sim' if r['marketing_opt_in'] else 'Não') for r in records if term in (r['name']+' '+r['phone']+' '+r['email']).casefold()]
                tbl=table(rows,[('name','NOME'),('phone','TELEFONE'),('email','E-MAIL'),('purchases','COMPRAS'),('total','TOTAL COMPRADO'),('last_purchase','ÚLTIMA COMPRA'),('consent','COMUNICAÇÕES')],selection='single')
                button('Editar cliente',lambda:choose(tbl,lambda r:client_dialog(body.refresh,r)),secondary=True)
                button('Histórico e produtos',lambda:choose(tbl,client_history),secondary=True)
                button('Exportar clientes autorizados',lambda:ui.download.content(reports.csv_bytes([r for r in records if r['marketing_opt_in']],['name','phone','email','birthday','city','total_cents','last_purchase']),'clientes-autorizados.csv','text/csv'),secondary=True)
            search.on_value_change(lambda:body.refresh())
            body()

    def channel_dialog(refresh,r=None):
        r=r or {}
        with ui.dialog() as dialog,ui.card().classes('dialog-card'):
            ui.label('Canal de venda').classes('heading')
            name=field('Nome do canal',r.get('name',''))
            ui.label('Ao salvar, um local de estoque com o mesmo nome será criado e vinculado automaticamente. Se ele já existir, será reutilizado e ativado. Um vínculo já configurado será mantido. Nenhuma peça é transferida automaticamente.').classes('info-panel')
            kind=ui.select(['Direto','Loja','Site','Evento'],value=r.get('kind','Loja'),label='Tipo de canal').props('outlined')
            sr,vr=r.get('store_rate','0'),r.get('seller_rate','0')
            initial='split' if Decimal(sr) and Decimal(vr) else 'store' if Decimal(sr) else 'seller' if Decimal(vr) else 'none'
            mode=ui.select({'none':'Sem comissão','store':'Toda a comissão para a loja / canal','seller':'Toda a comissão para a vendedora','split':'Uma parte para o canal e outra para a vendedora'},value=initial,label='Regra de comissão').props('outlined')
            recipient_mode=ui.select({'self':'A própria loja / canal','other':'Outra pessoa / empresa'},value='other' if r.get('store_beneficiary_id') and r.get('payee','').strip().casefold()!=r.get('name','').strip().casefold() else 'self',label='Quem recebe a comissão do canal?').props('outlined')
            payee=ui.select({0:'Selecione o beneficiário',**{b['id']:b['name'] for b in business.beneficiaries()}},value=r.get('store_beneficiary_id') or 0,label='Quem recebe a parte da loja / canal').props('outlined').classes('w-full')
            def beneficiary_saved(beneficiary_id):
                payee.set_options({0:'Selecione o beneficiário',**{b['id']:b['name'] for b in business.beneficiaries()}},value=beneficiary_id)
            add_payee=button('Cadastrar beneficiário aqui',lambda:beneficiary_dialog(refresh,initial_name=name.value,on_saved=beneficiary_saved),icon='person_add',secondary=True)
            payee_hint=ui.label('Cadastre a loja ou pessoa que receberá a comissão. Ela será selecionada automaticamente, sem fechar este canal.').classes('muted')
            store=money_field('Comissão do canal (%)',sr)
            seller=money_field('Comissão da vendedora (%)',vr)
            active=ui.checkbox('Canal ativo',value=bool(r.get('active',1)))
            rule_hint=ui.label('').classes('info-panel')
            def update():
                has_store=mode.value in {'store','split'}
                custom=has_store and recipient_mode.value=='other'
                recipient_mode.set_visibility(has_store)
                for el in [payee,add_payee,payee_hint]: el.set_visibility(custom)
                store.set_visibility(has_store);seller.set_visibility(mode.value in {'seller','split'})
                texts={'none':'Este canal não gera comissão automática.','store':'Toda a comissão pertence à loja / canal. A vendedora pode ser identificada na venda, sem gerar comissão adicional para ela.','seller':'Toda a comissão pertence à vendedora selecionada na venda. A loja / canal não recebe uma parte.','split':'A parte do canal e a parte da vendedora são registradas separadamente.'}
                rule_hint.set_text(texts[mode.value]+' Percentuais sobre a receita após desconto.'+(' O cadastro de quem recebe será criado automaticamente para a própria loja / canal.' if has_store and not custom else ''))
            mode.on_value_change(update);recipient_mode.on_value_change(update);update()
            def save():
                data=dict(channel_receives=recipient_mode.value=='self',name=name.value,kind=kind.value,active=active.value,store_beneficiary_id=(r.get('store_beneficiary_id') if r.get('payee','').strip().casefold()==r.get('name','').strip().casefold() else None) if recipient_mode.value=='self' else payee.value or None,store_rate=store.value if mode.value in {'store','split'} else '0',seller_rate=seller.value if mode.value in {'seller','split'} else '0')
                perform(lambda:business.save_channel(data,r.get('id')),'Canal salvo.',lambda:(dialog.close(),refresh()))
            button('Salvar canal',save,icon='save');button('Voltar',dialog.close,secondary=True)
        dialog.open()

    def beneficiary_dialog(refresh,initial_name='',on_saved=None):
        with ui.dialog() as dialog,ui.card().classes('dialog-card'):
            ui.label('Vendedora ou beneficiário').classes('heading')
            existing=ui.select({0:'Novo cadastro',**{b['id']:b['name'] for b in business.beneficiaries()}},value=0,label='Cadastro existente').props('outlined')
            name=field('Nome da pessoa ou loja',initial_name);phone=field('Telefone')
            channel=ui.select({0:'Sem vínculo de vendedora',**{c['id']:c['name'] for c in business.channels()}},value=0,label='Vincular como vendedora ao canal').props('outlined')
            def picked(e):
                row=next((b for b in business.beneficiaries() if b['id']==e.value),{})
                name.set_value(row.get('name',''));phone.set_value(row.get('phone',''))
            existing.on_value_change(picked)
            ui.label('Uma mesma vendedora pode ser vinculada a vários canais usando seu cadastro existente. A loja também é um beneficiário, com saldo separado.').classes('muted')
            def save_beneficiary():
                saved=[]
                def operation():
                    saved.append(business.save_beneficiary(name.value,phone=phone.value,beneficiary_id=existing.value or None,channel_id=channel.value or None))
                def done():
                    dialog.close()
                    if on_saved:
                        on_saved(saved[0])
                    else:
                        refresh()
                perform(operation,'Beneficiário salvo.',done)
            button('Salvar beneficiário',save_beneficiary,icon='save')
            button('Voltar',dialog.close,secondary=True)
        dialog.open()

    def pay_dialog(r,refresh):
        key=str(uuid4())
        with ui.dialog() as dialog,ui.card().classes('dialog-card'):
            ui.label('Pagar comissão · '+r['name']).classes('section-title')
            ui.label('Saldo total da pessoa / loja em todos os canais: '+brl(r['balance_cents'])).classes('info-panel')
            amount=money_field('Valor do pagamento (R$)',str(Decimal(r['balance_cents'])/100))
            when=field('Data do pagamento',today(),kind='date')
            method=ui.select(['Pix','Dinheiro','Transferência'],value='Pix',label='Forma de pagamento').props('outlined')
            button('Confirmar pagamento',lambda:perform(lambda:business.pay_commission(r['id'],amount.value,when.value,method.value,key=key),'Comissão paga.',lambda:(dialog.close(),refresh())),icon='check')
            button('Voltar',dialog.close,secondary=True)
        dialog.open()

    def statement(r,refresh):
        with ui.dialog() as dialog,ui.card().classes('dialog-card'):
            ui.label('Extrato · '+r['name']).classes('heading')
            with db.connect() as c:earned=commission_open(c,beneficiary_id=r['id'])
            table([dict(x,amount=brl(x['amount_cents']),balance=brl(x['balance_cents'])) for x in earned],[('sale_id','VENDA'),('occurred_on','DATA'),('category','ORIGEM'),('amount','GERADO'),('balance','SALDO')])
            entries=db.rows('SELECT cs.*,e.sale_id FROM commission_settlements cs JOIN expenses e ON e.id=cs.expense_id WHERE e.beneficiary_id=? ORDER BY cs.settled_on DESC,cs.id DESC',(r['id'],))
            tbl=table([dict(x,value=brl(x['amount_cents'])) for x in entries],[('settled_on','DATA'),('method','FORMA'),('value','UTILIZADO'),('sale_id','VENDA DE ORIGEM'),('target_sale_id','VENDA DE RESGATE')],selection='single')
            reason=field('Motivo para desfazer pagamento incorreto')
            button('Desfazer pagamento em dinheiro',lambda:choose(tbl,lambda row:perform(lambda:business.reverse_commission_payment(row['batch_key'],reason.value),'Pagamento desfeito.',lambda:(dialog.close(),refresh()))),secondary=True)
            ui.label('Cada baixa é ligada à venda de origem. Para corrigir resgate em peças, use Editar ou Cancelar venda em Vendas.').classes('muted')
            button('Fechar',dialog.close,secondary=True)
        dialog.open()

    def delete_dialog(record,kind,refresh):
        with ui.dialog() as dialog,ui.card().classes('dialog-card'):
            ui.label('Excluir '+kind+'?').classes('heading')
            ui.label(record['name'])
            ui.label('Cadastros usados em vendas ou comissões são protegidos. Os vínculos de um cadastro sem histórico serão removidos.')
            action=business.delete_channel if kind=='canal' else business.delete_beneficiary
            button('Confirmar exclusão',lambda:perform(lambda:action(record['id']),'Cadastro excluído.',lambda:(dialog.close(),refresh())),icon='delete')
            button('Voltar',dialog.close,secondary=True)
        dialog.open()

    @ui.page('/comissoes')
    def commissions_page():
        with shell('/comissoes','Comissões'):
            heading('Canais, pessoas e comissões.','Créditos separados para cada loja e vendedora, com pagamentos e resgates rastreáveis.')
            with ui.row():
                button('Novo canal',lambda:channel_dialog(body.refresh),icon='storefront')
                button('Cadastrar / vincular vendedora ou loja',lambda:beneficiary_dialog(body.refresh),icon='person_add',secondary=True)
            with ui.row().classes('w-full'):
                channel_filter=ui.select({0:'Todos os canais',**{c['id']:c['name'] for c in business.channels()}},value=0,label='Filtrar canal',with_input=True).props('outlined')
                type_filter=ui.select(['Todos','Direto','Loja','Site','Evento'],value='Todos',label='Filtrar tipo de canal').props('outlined')
                seller_filter=field('Buscar vendedora ou recebedor')
            ui.label('Valores de todo o histórico. Os filtros de canal e tipo recortam as comissões pela venda que as gerou. Uma pessoa pode atuar em vários canais.').classes('muted')
            @ui.refreshable
            def body():
                ui.label('Canais de venda').classes('section-title mt-4')
                channel_filter.set_options({0:'Todos os canais',**{c['id']:c['name'] for c in business.channels()}},value=channel_filter.value if channel_filter.value in [0]+[c['id'] for c in business.channels()] else 0)
                channels,balances=business.commission_overview(channel_filter.value,None if type_filter.value=='Todos' else type_filter.value,seller_filter.value or '')
                locations={r['id']:r['name'] for r in business.locations()}
                rows=[dict(c,stock_location=locations.get(c.get('location_id'),'Sem vínculo'),sold=brl(c['sold_cents']),sellers=', '.join(x['name'] for x in business.sellers(c['id'])),status='Ativo' if c['active'] else 'Inativo') for c in channels]
                ct=table(rows,[('name','CANAL'),('kind','TIPO'),('stock_location','LOCAL DE ESTOQUE'),('payee','QUEM RECEBE PELO CANAL'),('store_rate','CANAL %'),('seller_rate','VENDEDORA %'),('sellers','VENDEDORAS'),('sold','TOTAL VENDIDO'),('status','SITUAÇÃO')],selection='single')
                button('Editar canal',lambda:choose(ct,lambda r:channel_dialog(body.refresh,r)),secondary=True)
                button('Excluir canal',lambda:choose(ct,lambda r:delete_dialog(r,'canal',body.refresh)),icon='delete',secondary=True)
                ui.label('Saldos de comissão').classes('section-title mt-4')
                with ui.row().classes('info-panel w-full'):
                    ui.label('Total pago / utilizado: '+brl(sum(r['settled_cents'] for r in balances)))
                    ui.label('Em dinheiro: '+brl(sum(r['cash_cents'] for r in balances)))
                    ui.label('Em peças: '+brl(sum(r['credit_cents'] for r in balances)))
                    ui.label('Saldo a pagar: '+brl(sum(r['balance_cents'] for r in balances)))
                ui.label('Totais dos recebedores exibidos, incluindo lojas e vendedoras. Total vendido por canal exclui retiradas pessoais e vendas canceladas; a busca por pessoa seleciona seus canais e mantém o total completo de cada canal.').classes('muted')
                bt=table([dict(r,earned=brl(r['earned_cents']),settled=brl(r['settled_cents']),balance=brl(r['balance_cents'])) for r in balances],[('name','QUEM RECEBE'),('channels','CANAIS DE VENDA'),('earned','COMISSÃO GERADA'),('settled','PAGA / UTILIZADA'),('balance','SALDO')],selection='single')
                button('Pagar em dinheiro',lambda:choose(bt,lambda r:pay_dialog(next(b for b in business.commission_balances() if b['id']==r['id']),body.refresh)),secondary=True)
                button('Excluir vendedor(a) / beneficiário',lambda:choose(bt,lambda r:delete_dialog(r,'vendedor(a) / beneficiário',body.refresh)),icon='delete',secondary=True)
                button('Ver extrato',lambda:choose(bt,lambda r:statement(r,body.refresh)),secondary=True)
                ui.label('Para entregar peças, registre uma venda e marque Usar crédito de comissão. O preço é o da venda; o crédito quita a obrigação sem movimentar caixa.').classes('info-panel')
                legacy=db.rows("SELECT * FROM expenses WHERE category IN ('Comissão vendedora','Comissão loja') AND beneficiary_id IS NULL AND cancelled_on IS NULL")
                if legacy:
                    ui.label('Comissões anteriores sem beneficiário').classes('section-title mt-4')
                    lt=table([dict(r,value=brl(r['amount_cents'])) for r in legacy],[('id','REGISTRO'),('sale_id','VENDA'),('category','TIPO'),('value','VALOR'),('paid_on','PAGA EM')],selection='single')
                    dest=ui.select({b['id']:b['name'] for b in business.beneficiaries()},label='Beneficiário da comissão anterior').props('outlined')
                    button('Vincular comissão selecionada',lambda:choose(lt,lambda r:perform(lambda:business.assign_legacy_commission(r['id'],dest.value),'Comissão vinculada.',body.refresh)),secondary=True)
            for control in [channel_filter,type_filter,seller_filter]:
                control.on_value_change(lambda:body.refresh())
            body()
