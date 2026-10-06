import pytest
from flow.db import Database
from flow.service import Business
from flow.reports import summary
from flow.money import RuleError
from tests.helpers import fixture_xml

def test_loss_and_recovery_history(tmp_path):
 b=Business(Database(tmp_path/'loss.db'))
 p=b.create_product(dict(sku='X',name='Brinco',location_id=2),quantity=3,unit_cost='100',when='2026-01-01')
 loss=b.record_loss(p,2,1,'Evento',when='2026-01-02',key='x')
 assert b.record_loss(p,2,1,'Evento',when='2026-01-02',key='x')==loss
 assert b.product(p)['stock']==2
 assert b.losses()[0]['cost_cents']==10000
 r=summary(b.db,'2026-01-01','2026-01-31')
 assert r['net_cents']==-10000 and r['revenue_cents']==0 and r['sale_count']==0
 assert not b.db.rows('SELECT * FROM receivables')
 with pytest.raises(RuleError):b.record_loss(p,2,3,'Mais',when='2026-01-03',key='bad')
 assert len(b.losses())==1
 b.reverse_loss(loss,'Encontrada','2026-02-01')
 assert b.product(p)['stock']==3
 assert summary(b.db,'2026-01-01','2026-01-31')['net_cents']==-10000
 assert summary(b.db,'2026-02-01','2026-02-28')['net_cents']==10000
 assert summary(b.db,'2026-01-01','2026-02-28')['net_cents']==0

def test_consigned_loss_and_reverse(tmp_path):
 b=Business(Database(tmp_path/'cons.db'))
 b.import_invoice(fixture_xml(),{'1':'estoque','2':'ignorar'},ownership='consigned',location_id=2)
 lot=b.consignment_lots()[0]
 loss=b.record_loss(lot['product_id'],2,1,'Perdida',lot_id=lot['id'],when='2026-01-02',key='x')
 assert b.consignment_lots()[0]['stock']==1
 r=summary(b.db,'2026-01-01','2026-01-31')
 assert r['loss_cents']==9500 and r['net_cents']==-9500 and r['payable_cents']==9500
 b.reverse_loss(loss,'Encontrada','2026-02-01')
 assert b.consignment_lots()[0]['stock']==2
 assert summary(b.db,'2026-01-01','2026-02-28')['net_cents']==0
 assert summary(b.db,'2026-01-01','2026-02-28')['payable_cents']==0

def test_picker_defaults_transfer_and_loss_ui(tmp_path):
 import asyncio
 from nicegui import ui
 from nicegui.testing import user_simulation
 from flow.ui import register_pages
 async def run():
  b=Business(Database(tmp_path/'ui.db'))
  p=b.create_product(dict(sku='X',name='Brinco'),quantity=3,unit_cost='100',when='2026-01-01')
  b.save_channel(dict(name='AAA Loja',kind='Loja',store_rate='30',channel_receives=True))
  async with user_simulation() as user:
   register_pages(b)
   def el(kind,label):return next(iter(user.find(kind=kind,content=label).elements))
   await user.open('/vendas');user.find(kind=ui.button,content='Registrar venda').click()
   ch=el(ui.select,'Canal de venda')
   assert ch.options[ch.value]=='Direto · Nanda'
   assert el(ui.select,'Local de saída das peças').value==2
   assert float(el(ui.input,'Comissão loja / evento (%)').value)==0
   await user.open('/locais');user.find(kind=ui.button,content='Distribuir / transferir peças').click()
   pick=el(ui.select,'Peça / variante / propriedade');key=next(iter(pick.options))
   with user:pick.set_value(key)
   user.find(kind=ui.button,content='Adicionar peça').click()
   assert key not in pick.options
   await user.should_see('Remover')
   user.find(kind=ui.button,content='Remover').click()
   assert key in pick.options
 asyncio.run(run())

def test_rounded_edit_preserves_cents(tmp_path):
 import asyncio
 from nicegui import ui
 from nicegui.testing import user_simulation
 from flow.ui import register_pages
 async def run():
  b=Business(Database(tmp_path/'edit.db'))
  p=b.create_product(dict(sku='X',name='Brinco'),quantity=2,unit_cost='100',when='2026-01-01')
  sid=b.create_sale([dict(product_id=p,quantity=1,unit_price='2958.99')],dict(sale_date='2026-01-02',method='Pix',seller='147.95',store='739.75'),key='s')
  before=b.db.rows('SELECT seller_cents,store_cents FROM sales')[0]
  async with user_simulation() as user:
   register_pages(b);await user.open('/vendas')
   tbl=next(t for t in user.find(kind=ui.table).elements if any(r.get('sale_date') for r in t.rows))
   with user:tbl.selected=[tbl.rows[0]]
   user.find(kind=ui.button,content='Editar venda').click()
   for label in ['Comissão vendedora (%)','Comissão loja / evento (%)']:
    val=next(iter(user.find(kind=ui.input,content=label).elements)).value
    assert len(str(val).split('.')[-1])==2
   user.find('Motivo da alteração').type('Conferência')
   user.find(kind=ui.button,content='Salvar alterações').click()
   await user.should_see('Venda atualizada e saldos recalculados.')
   assert b.db.rows('SELECT seller_cents,store_cents FROM sales')[0]==before
 asyncio.run(run())
