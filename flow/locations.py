"""Physical custody, independent from ownership and financial costing.

Unassigned stock is the residual of the authoritative inventory ledger.
Transfers and located sales describe custody only; never duplicate purchases.
"""
from collections import defaultdict
from decimal import Decimal
from .db import is_integrity_error
from .money import RuleError, day, today, pieces, rounded


def balances(conn, when='9999-12-31'):
    total=defaultdict(int)
    for r in conn.execute('SELECT product_id,SUM(quantity) q FROM movements WHERE occurred_on<=? GROUP BY product_id',(when,)):
        total[(r['product_id'],0)]=r['q']
    for r in conn.execute('SELECT l.id,l.product_id,l.quantity+COALESCE(SUM(m.quantity),0) q FROM consignment_lots l LEFT JOIN active_consignment_moves m ON m.lot_id=l.id AND m.occurred_on<=? WHERE l.received_on<=? GROUP BY l.id',(when,when)):
        total[(r['product_id'],r['id'])]=r['q']
    located=defaultdict(int)
    for r in conn.execute('SELECT * FROM location_transfers WHERE occurred_on<=? ORDER BY id',(when,)):
        for loc,sign in [(r['source_id'],-1),(r['target_id'],1)]:
            if loc!=1: located[(r['product_id'],r['lot_id'] or 0,loc)]+=sign*r['quantity']
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='sale_locations'").fetchone():
        for r in conn.execute('SELECT i.product_id,COALESCE(i.lot_id,0) lot_id,i.location_id,i.quantity FROM sale_locations i JOIN sales s ON s.id=i.sale_id WHERE i.location_id<>1 AND s.sale_date<=? AND (s.cancelled_on IS NULL OR s.cancelled_on>?)',(when,when)):
            located[(r['product_id'],r['lot_id'],r['location_id'])]-=r['quantity']
    else:
        for table in ['sale_items','consignment_sale_items']:
            lot='i.lot_id' if table=='consignment_sale_items' else '0'
            for r in conn.execute(f'SELECT i.product_id,{lot} lot_id,s.location_id,i.quantity FROM {table} i JOIN sales s ON s.id=i.sale_id WHERE s.location_id<>1 AND s.sale_date<=? AND (s.cancelled_on IS NULL OR s.cancelled_on>?)',(when,when)):
                located[(r['product_id'],r['lot_id'],r['location_id'])]-=r['quantity']
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='stock_losses'").fetchone():
        for r in conn.execute('SELECT * FROM stock_losses WHERE location_id<>1 AND occurred_on<=? AND (cancelled_on IS NULL OR cancelled_on>?)',(when,when)):
            located[(r['product_id'],r['lot_id'] or 0,r['location_id'])]-=r['quantity']
    result=dict(located)
    for pid,lot in set(total)|{(p,l) for p,l,_ in located}:
        result[(pid,lot,1)]=total[(pid,lot)]-sum(q for (p,l,_),q in located.items() if (p,l)==(pid,lot))
    return result


def validate_locations(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='location_transfers'").fetchone(): return

    dates=[r[0] for r in conn.execute('SELECT occurred_on FROM location_transfers UNION SELECT sale_date FROM sales UNION SELECT cancelled_on FROM sales WHERE cancelled_on IS NOT NULL UNION SELECT occurred_on FROM movements UNION SELECT occurred_on FROM active_consignment_moves ORDER BY 1')]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='stock_losses'").fetchone():
        dates=sorted(set(dates)|{r[0] for r in conn.execute('SELECT occurred_on FROM stock_losses UNION SELECT cancelled_on FROM stock_losses WHERE cancelled_on IS NOT NULL')})
    for when in dates:
        rows=balances(conn,when)
        for (pid,lot,loc),qty in rows.items():
            allocated=sum(v for (p,l,k),v in rows.items() if (p,l)==(pid,lot) and k!=1)
            if qty<0 and (loc!=1 or allocated>0):
                raise RuleError(f'Movimentação deixaria estoque negativo por local em {when} (produto #{pid}). Confira a data e transfira as peças para o local correto antes de baixar ou alterar entradas.')


class Locations:
    def locations(self):
        return self.db.rows('SELECT * FROM locations ORDER BY id')

    def save_location(self,name,location_id=None,active=True):
        from .service import required,audit
        name=required(name,'o nome do local')
        with self.db.transaction() as c:
            if location_id==1: raise RuleError('Local a definir é um local reservado.')
            if not active and any(q for (p,l,k),q in balances(c).items() if k==location_id):
                raise RuleError('Transfira todas as peças antes de desativar o local.')
            try:
                if location_id:
                    c.execute('UPDATE locations SET name=?,active=? WHERE id=?',(name,int(active),location_id))
                else:
                    location_id=c.execute('INSERT INTO locations(name,active) VALUES(?,?)',(name,int(active))).lastrowid
            except Exception as exc:
                if not is_integrity_error(exc):
                    raise
                raise RuleError('Já existe um local com esse nome.')
            audit(c,'save_location','location',location_id,{'name':name,'active':active})
        return location_id

    def set_channel_location(self,channel_id,location_id):
        with self.db.transaction() as c:
            if not c.execute('SELECT 1 FROM channels WHERE id=?',(channel_id,)).fetchone() or not c.execute('SELECT 1 FROM locations WHERE id=? AND active=1',(location_id,)).fetchone():
                raise RuleError('Selecione um canal e um local ativo.')
            c.execute('UPDATE channels SET location_id=? WHERE id=?',(location_id,channel_id))

    def location_stock(self,location_id=None):
        with self.db.connect() as c:
            rows=balances(c)
            products={r['id']:dict(r) for r in c.execute('SELECT * FROM inventory')}
            locations={r['id']:r['name'] for r in c.execute('SELECT * FROM locations')}
            lots={r['id']:dict(r) for r in c.execute('SELECT * FROM consignment_lots')}
        output=[]
        for (pid,lot,loc),qty in rows.items():
            if not qty or location_id and loc!=location_id: continue
            p=products[pid]
            unit=(lots[lot]['unit_cost_cents'] if lot else (Decimal(p['stock_cents'])/p['stock'] if p['stock'] and p['stock_cents'] is not None else None))
            output.append({**p,'id':f'{pid}:{lot}:{loc}','product_id':pid,'lot_id':lot,'location_id':loc,'location':locations[loc],'quantity':qty,'ownership':f'Consignado · lote {lot}' if lot else 'Próprio','cost_value':None if unit is None else rounded(Decimal(unit)*qty),'sale_value':p['selling_cents']*qty})
        return sorted(output,key=lambda r:(r['location'],r['name'],r['sku']))

    def transfer_stock(self,items,source_id,target_id,*,when=None,reason='',key):
        from .service import required,audit
        when=day(when or today());reason=required(reason,'o motivo / referência da transferência')
        if source_id==target_id: raise RuleError('Origem e destino devem ser diferentes.')
        if not items: raise RuleError('Adicione peças à transferência.')
        with self.db.transaction() as c:
            if c.execute('SELECT 1 FROM location_transfers WHERE batch_key=?',(key,)).fetchone(): return
            for loc in [source_id,target_id]:
                if not c.execute('SELECT 1 FROM locations WHERE id=? AND active=1',(loc,)).fetchone(): raise RuleError('Selecione locais ativos.')
            for item in items:
                pid=item['product_id'];lot=item.get('lot_id') or 0;qty=pieces(item['quantity'])
                if lot and not c.execute('SELECT 1 FROM consignment_lots WHERE id=? AND product_id=?',(lot,pid)).fetchone(): raise RuleError('Lote não corresponde à peça.')
                available=balances(c,when).get((pid,lot,source_id),0)
                if qty>available: raise RuleError(f'Saldo insuficiente na origem: {available} unidade(s) disponíveis na data.')
                c.execute('INSERT INTO location_transfers(product_id,lot_id,source_id,target_id,quantity,occurred_on,reason,batch_key) VALUES(?,?,?,?,?,?,?,?)',(pid,lot or None,source_id,target_id,qty,when,reason,key))
            audit(c,'transfer_stock','location',target_id,{'source':source_id,'items':items,'date':when,'reason':reason})

    def count_location(self,pid,location_id,counted,reason,*,unit_cost='0',key):
        counted=pieces(counted,zero=True)
        with self.db.transaction() as c:
            if c.execute("SELECT 1 FROM movements WHERE kind='ADJUSTMENT' AND source=?",(key,)).fetchone(): return
            if not c.execute('SELECT 1 FROM locations WHERE id=? AND active=1',(location_id,)).fetchone():
                raise RuleError('Selecione um local ativo.')
            current=balances(c).get((pid,0,location_id),0)
            delta=counted-current
            total=c.execute('SELECT stock FROM inventory WHERE id=?',(pid,)).fetchone()['stock']
            self.adjust_stock(pid,total+delta,reason,when=today(),unit_cost=unit_cost,key=key,_conn=c)
            if location_id!=1 and delta:
                c.execute('INSERT INTO location_transfers(product_id,source_id,target_id,quantity,occurred_on,reason,batch_key) VALUES(?,?,?,?,?,?,?)',(pid,1 if delta>0 else location_id,location_id if delta>0 else 1,abs(delta),today(),'Conferência física: '+reason,key))

    def record_loss(self,pid,location_id,quantity,reason,*,when=None,lot_id=None,key):
        from .service import required,move,audit,expense_row
        from .ledger import rebuild_history
        from .consignment import validate_lots
        when=day(when or today());quantity=pieces(quantity);reason=required(reason,'o motivo da perda')
        with self.db.transaction() as c:
            old=c.execute('SELECT id FROM stock_losses WHERE request_key=?',(key,)).fetchone()
            if old: return old['id']
            if quantity>balances(c,when).get((pid,lot_id or 0,location_id),0): raise RuleError('Saldo insuficiente nesse local na data da perda.')
            loss=c.execute('INSERT INTO stock_losses(product_id,lot_id,location_id,quantity,occurred_on,reason,request_key) VALUES(?,?,?,?,?,?,?)',(pid,lot_id or None,location_id,quantity,when,reason,key)).lastrowid
            if lot_id:
                lot=c.execute('SELECT * FROM consignment_lots WHERE id=? AND product_id=?',(lot_id,pid)).fetchone()
                if not lot: raise RuleError('Lote incompatível com a peça.')
                eid=expense_row(c,key='loss-'+str(loss),when=when,amount=quantity*lot['unit_cost_cents'],category='Repasse consignação',description='Perda consignada #'+str(loss)+' · '+reason,affects=0)
                c.execute('UPDATE stock_losses SET expense_id=? WHERE id=?',(eid,loss))
                validate_lots(c,[lot_id])
            else:
                move(c,pid,when,-quantity,0,'LOSS',loss,reason)
                rebuild_history(c,[pid],strict=True)
            audit(c,'record_loss','stock_loss',loss,{'reason':reason,'location_id':location_id})
        return loss

    def losses(self):
        return self.db.rows("SELECT l.*,p.sku,p.name,p.material,p.stone,p.size,k.name location,CASE WHEN l.lot_id IS NULL THEN -m.cost_cents ELSE l.quantity*lot.unit_cost_cents END cost_cents FROM stock_losses l JOIN products p ON p.id=l.product_id JOIN locations k ON k.id=l.location_id LEFT JOIN movements m ON m.kind='LOSS' AND m.source=CAST(l.id AS TEXT) AND m.product_id=l.product_id LEFT JOIN consignment_lots lot ON lot.id=l.lot_id ORDER BY l.occurred_on DESC,l.id DESC")

    def reverse_loss(self,loss_id,reason,when=None):
        from .service import required,move,audit
        from .ledger import rebuild_history
        from .consignment import validate_lots
        when=day(when or today());reason=required(reason,'o motivo do estorno')
        with self.db.transaction() as c:
            row=c.execute('SELECT * FROM stock_losses WHERE id=?',(loss_id,)).fetchone()
            if not row: raise RuleError('Perda não encontrada.')
            if row['cancelled_on']: return
            if when<row['occurred_on']: raise RuleError('O estorno não pode anteceder a perda.')
            if row['expense_id']:
                exp=c.execute('SELECT * FROM expenses WHERE id=?',(row['expense_id'],)).fetchone()
                if exp['paid_on']: raise RuleError('O repasse desta perda já foi pago. Concilie com a matriz antes de estornar.')
                c.execute('UPDATE expenses SET cancelled_on=?,cancel_reason=? WHERE id=?',(when,reason,row['expense_id']))
            c.execute('UPDATE stock_losses SET cancelled_on=?,cancel_reason=? WHERE id=?',(when,reason,loss_id))
            if row['lot_id']: validate_lots(c,[row['lot_id']])
            else:
                move(c,row['product_id'],when,row['quantity'],0,'LOSS_CANCEL',loss_id,reason)
                rebuild_history(c,[row['product_id']],strict=True)
            audit(c,'reverse_loss','stock_loss',loss_id,{'reason':reason,'date':when})

    def location_history(self):
        return self.db.rows('SELECT t.*,p.sku,p.name,s.name source,d.name target FROM location_transfers t JOIN products p ON p.id=t.product_id JOIN locations s ON s.id=t.source_id JOIN locations d ON d.id=t.target_id ORDER BY t.occurred_on DESC,t.id DESC')


def receive_at(conn,pid,lot,quantity,location_id,when,key):
    if not location_id or location_id==1: return
    if not conn.execute('SELECT 1 FROM locations WHERE id=? AND active=1',(location_id,)).fetchone():
        raise RuleError('Selecione um local de recebimento ativo.')
    conn.execute('INSERT INTO location_transfers(product_id,lot_id,source_id,target_id,quantity,occurred_on,reason,batch_key) VALUES(?,?,1,?,?,?, ?,?)',(pid,lot,location_id,quantity,when,'Local de recebimento da entrada',key))


def loss_report(conn,start,end):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='stock_losses'").fetchone(): return []
    result=[]
    rows=conn.execute("SELECT l.*,p.sku,p.name,k.name location,CASE WHEN l.lot_id IS NULL THEN -m.cost_cents ELSE l.quantity*lot.unit_cost_cents END cost_cents FROM stock_losses l JOIN products p ON p.id=l.product_id JOIN locations k ON k.id=l.location_id LEFT JOIN movements m ON m.kind='LOSS' AND m.source=CAST(l.id AS TEXT) AND m.product_id=l.product_id LEFT JOIN consignment_lots lot ON lot.id=l.lot_id WHERE l.occurred_on<=?",(end,))
    for r in rows:
        for when,sign in [(r['occurred_on'],1),(r['cancelled_on'],-1)]:
            if when and start<=when<=end: result.append(dict(r,date=when,cost_cents=sign*r['cost_cents'],quantity=sign*r['quantity'],event='Perda' if sign==1 else 'Estorno'))
    return result
