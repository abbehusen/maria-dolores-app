from uuid import uuid4
from nicegui import ui
from .money import today,brl
from . import reports


def register_locations(business,shell,heading,field,button,table,perform):
    @ui.page('/locais')
    def page():
        with shell('/estoque','Estoque por local'):
            heading('Onde estão suas peças?','Localização física de peças próprias e consignadas, sem alterar custos ou comissões.')
            ui.link('Voltar ao cadastro de peças','/estoque')
            ui.label('Saldos antigos podem estar em Local a definir. Novas importações XML sugerem Com Nanda. Use Distribuir / transferir para indicar onde as peças estão. Transferências não geram vendas nem despesas.').classes('info-panel')
            with ui.tabs() as tabs:
                stock_tab=ui.tab('Peças por local');manage_tab=ui.tab('Locais e canais');history_tab=ui.tab('Transferências');loss_tab=ui.tab('Peças perdidas')
            with ui.tab_panels(tabs,value=stock_tab).classes('w-full'):
                with ui.tab_panel(stock_tab):
                    local=ui.select({0:'Todos os locais',**{r['id']:r['name'] for r in business.locations()}},value=0,label='Local de estoque').props('outlined')
                    search=field('Buscar peça, código, material, pedra ou tamanho')
                    @ui.refreshable
                    def stock():
                        term=(search.value or '').casefold()
                        rows=[r for r in business.location_stock(local.value) if term in ' '.join(str(r[k]) for k in ['name','sku','material','stone','size']).casefold()]
                        ui.label(f"{sum(r['quantity'] for r in rows)} unidades · Valor de venda {brl(sum(r['sale_value'] for r in rows))}")
                        tbl=table([{**r,'variant':' / '.join(filter(None,[r['material'],r['stone'],r['size']])),'price':brl(r['selling_cents']),'cost':brl(r['cost_value'])} for r in rows],[('location','LOCAL'),('sku','CÓDIGO'),('name','PEÇA'),('variant','VARIANTE'),('ownership','PROPRIEDADE'),('quantity','UNIDADES'),('price','PREÇO DE VENDA'),('cost','CUSTO TOTAL')],selection='single')
                        def count_selected():
                            from .money import RuleError
                            if len(tbl.selected)!=1: raise RuleError('Selecione uma peça na tabela.')
                            r=tbl.selected[0]
                            if r['lot_id']: raise RuleError('Peças consignadas exigem conferência com a matriz. Corrija a entrada, venda ou devolução correspondente.')
                            count_dialog(r,stock.refresh)
                        def loss_selected():
                            from .money import RuleError
                            if len(tbl.selected)!=1: raise RuleError('Selecione a peça e seu local na tabela.')
                            loss_dialog(tbl.selected[0],stock.refresh)
                        button('Registrar peça perdida',lambda:perform(loss_selected,''),icon='report_problem',secondary=True)
                        button('Conferir quantidade no local',lambda:perform(count_selected,''),icon='fact_check',secondary=True)
                        button('Exportar lista do local',lambda:ui.download.content(reports.csv_bytes(rows),'estoque-por-local.csv','text/csv'),icon='download',secondary=True)
                        with ui.expansion('Fotos das peças').classes('w-full'):
                            with ui.row():
                                for r in rows:
                                    if r['image_url']:
                                        with ui.card().style('width:180px'):
                                            ui.image(r['image_url'])
                                            ui.label(f"{r['name']} · {r['location']} · {r['quantity']} un.")
                    local.on_value_change(lambda:stock.refresh());search.on_value_change(lambda:stock.refresh())
                    button('Distribuir / transferir peças',lambda:transfer_dialog(stock.refresh),icon='swap_horiz')
                    stock()
                with ui.tab_panel(manage_tab):
                    @ui.refreshable
                    def management():
                        local.set_options({0:'Todos os locais',**{r['id']:r['name'] for r in business.locations()}},value=local.value)
                        for r in business.locations():
                            with ui.row().classes('items-center'):
                                ui.label(r['name']+(' · inativo' if not r['active'] else ''))
                                if r['id']!=1:
                                    button('Editar',lambda row=r:location_dialog(management.refresh,row),secondary=True)
                        button('Cadastrar local',lambda:location_dialog(management.refresh),icon='add')
                        ui.label('Local sugerido por canal de venda').classes('heading')
                        channel=ui.select({r['id']:r['name'] for r in business.channels()},label='Canal')
                        destination=ui.select({r['id']:r['name'] for r in business.locations() if r['active']},label='Local sugerido')
                        def selected(e):
                            row=next((r for r in business.channels() if r['id']==e.value),{})
                            destination.set_value(row.get('location_id') or 1)
                        channel.on_value_change(selected)
                        button('Salvar vínculo',lambda:perform(lambda:business.set_channel_location(channel.value,destination.value),'Local do canal atualizado.'))
                    management()
                with ui.tab_panel(history_tab):
                    @ui.refreshable
                    def history():
                        table(business.location_history(),[('occurred_on','DATA'),('source','ORIGEM'),('target','DESTINO'),('sku','CÓDIGO'),('name','PEÇA'),('quantity','UNIDADES'),('reason','MOTIVO')])
                        ui.label('Vendas e retiradas aparecem no histórico de vendas, com o local de saída. Para devolver peças entre locais, registre uma transferência inversa.')
                    button('Atualizar histórico',history.refresh,secondary=True)
                    history()

                with ui.tab_panel(loss_tab):
                    @ui.refreshable
                    def loss_history():
                        rows=business.losses()
                        term=loss_search.value.strip().casefold()
                        rows=[r for r in rows if term in (r['name']+' '+r['sku']+' '+r['location']+' '+r['reason']).casefold()]
                        ui.label('Perdas ativas: '+str(sum(r['quantity'] for r in rows if not r['cancelled_on']))+' peças · '+brl(sum(r['cost_cents'] for r in rows if not r['cancelled_on'])))
                        lt=table([dict(r,cost=brl(r['cost_cents']),state='Estornada' if r['cancelled_on'] else 'Perdida') for r in rows],[('occurred_on','DATA'),('sku','CÓDIGO'),('name','PEÇA'),('location','LOCAL'),('quantity','QUANTIDADE'),('cost','CUSTO'),('reason','MOTIVO'),('state','SITUAÇÃO')],selection='single')
                        def undo():
                            from .money import RuleError
                            if len(lt.selected)!=1: raise RuleError('Selecione a perda.')
                            reverse_dialog(lt.selected[0],loss_history.refresh)
                        button('Peça encontrada / estornar perda',lambda:perform(undo,''),secondary=True)
                        button('Exportar perdas',lambda:ui.download.content(reports.csv_bytes(rows),'pecas-perdidas.csv','text/csv'),secondary=True)
                    loss_search=field('Buscar perda por peça, local ou motivo')
                    loss_search.on_value_change(lambda:loss_history.refresh())
                    button('Atualizar perdas',loss_history.refresh,secondary=True)
                    loss_history()

    def loss_dialog(row,refresh):
        key=uuid4().hex
        with ui.dialog() as dialog,ui.card().classes('dialog-card'):
            ui.label('Registrar peça perdida').classes('heading')
            ui.label(f"{row['sku']} · {row['name']} · {row['location']} · saldo {row['quantity']}")
            ui.label('A peça sai do estoque disponível. Não gera receita nem comissão; o custo da perda reduz o resultado gerencial.')
            if row['lot_id']: ui.label('Consignada: ao confirmar, será gerada obrigação de repasse à matriz pelo custo do lote, ainda não paga. Confirme que a perda é de responsabilidade da loja.').classes('info-panel')
            qty=field('Quantidade perdida','1');when=field('Data da perda',today(),kind='date');reason=field('Motivo / evento / observações')
            button('Confirmar perda',lambda:perform(lambda:business.record_loss(row['product_id'],row['location_id'],qty.value,reason.value,when=when.value,lot_id=row['lot_id'],key=key),'Perda registrada.',lambda:(dialog.close(),refresh())))
            button('Voltar',dialog.close,secondary=True)
        dialog.open()

    def reverse_dialog(row,refresh):
        with ui.dialog() as dialog,ui.card():
            ui.label('Estornar perda / peça encontrada').classes('heading')
            ui.label('Devolve toda a quantidade deste registro ao local original. Se foi encontrada em outro lugar, transfira depois.')
            when=field('Data do estorno',today(),kind='date');reason=field('Motivo do estorno')
            button('Confirmar estorno',lambda:perform(lambda:business.reverse_loss(row['id'],reason.value,when.value),'Perda estornada.',lambda:(dialog.close(),refresh())))
            button('Voltar',dialog.close,secondary=True)
        dialog.open()

    def count_dialog(row,refresh):
        key=uuid4().hex
        with ui.dialog() as dialog,ui.card():
            ui.label(f"Conferir {row['name']} · {row['location']}")
            ui.label('Ajuste físico de hoje: altera o estoque total e registra o motivo. Para peças em outro local, use transferência.')
            qty=field('Quantidade contada',str(row['quantity']))
            reason=field('Motivo da diferença')
            cost=field('Custo unitário de unidades adicionais (R$)','0')
            button('Confirmar contagem',lambda:perform(lambda:business.count_location(row['product_id'],row['location_id'],qty.value,reason.value,unit_cost=cost.value,key=key),'Conferência registrada.',lambda:(dialog.close(),refresh())))
            button('Voltar',dialog.close,secondary=True)
        dialog.open()

    def location_dialog(refresh,row=None):
        with ui.dialog() as dialog,ui.card():
            name=field('Nome do local',row['name'] if row else '')
            active=ui.checkbox('Local ativo',value=bool(row['active']) if row else True)
            button('Salvar local',lambda:perform(lambda:business.save_location(name.value,row['id'] if row else None,active.value),'Local salvo.',lambda:(dialog.close(),refresh())))
            button('Voltar',dialog.close,secondary=True)
        dialog.open()

    def transfer_dialog(refresh):
        cart=[];key=uuid4().hex
        with ui.dialog() as dialog,ui.card().classes('dialog-card'):
            ui.label('Distribuir / transferir peças').classes('heading')
            options={r['id']:r['name'] for r in business.locations() if r['active']}
            source=ui.select(options,value=1,label='Origem')
            target=ui.select(options,value=2,label='Destino')
            when=field('Data da transferência',today(),kind='date')
            reason=field('Motivo / referência','Distribuição inicial')
            rows={}
            product=ui.select({},label='Peça / variante / propriedade',with_input=True)
            quantity=field('Quantidade','1')
            def options_changed():
                rows.clear();rows.update({r['id']:r for r in business.location_stock(source.value) if r['quantity']>0 and not any(i['product_id']==r['product_id'] and (i.get('lot_id') or 0)==(r['lot_id'] or 0) for i in cart)})
                product.set_options({k:f"{r['sku']} · {r['name']} · {r['material']} / {r['stone']} / {r['size']} · {r['ownership']} · saldo {r['quantity']}" for k,r in rows.items()},value=None)
            source.on_value_change(options_changed);options_changed()
            @ui.refreshable
            def preview():
                for i in list(cart):
                    with ui.row():
                        ui.label(f"{i['name']} · {i['quantity']} un.")
                        button('Remover',lambda item=i:(cart.remove(item),options_changed(),preview.refresh(),source.enable() if not cart else None),secondary=True)
            def add():
                from .money import RuleError,pieces
                if product.value not in rows: raise RuleError('Selecione uma peça.')
                r=rows[product.value]
                if pieces(quantity.value)>r['quantity']: raise RuleError('Quantidade maior que o saldo disponível na origem.')
                cart.append(dict(product_id=r['product_id'],lot_id=r['lot_id'],quantity=pieces(quantity.value),name=r['name']))
                source.disable();options_changed();preview.refresh()
            button('Adicionar peça',lambda:perform(add,'Peça adicionada.'))
            preview()
            button('Confirmar transferência',lambda:perform(lambda:business.transfer_stock(cart,source.value,target.value,when=when.value,reason=reason.value,key=key),'Transferência registrada.',lambda:(dialog.close(),refresh())))
            button('Voltar',dialog.close,secondary=True)
        dialog.open()
