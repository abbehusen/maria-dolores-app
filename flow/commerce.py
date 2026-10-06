"""Cadastros comerciais e compensação rastreável de comissões."""
import re
from uuid import uuid4
from decimal import Decimal
from .money import RuleError, cents, day, today, percent


def customer_for(conn, name, phone='', customer_id=None):
    name, phone = str(name or '').strip(), str(phone or '').strip()
    if customer_id:
        row = conn.execute('SELECT * FROM customers WHERE id=?', (customer_id,)).fetchone()
        if not row:
            raise RuleError('Cliente não encontrado.')
        return row['id'], row['name'], row['phone']
    if not name:
        return None, '', phone
    key = ' '.join(name.casefold().split()) + '|' + re.sub(r'\D', '', phone)
    row = conn.execute('SELECT id FROM customers WHERE identity_key=?', (key,)).fetchone()
    if row:
        return row[0], name, phone
    cid = conn.execute('INSERT INTO customers(name,phone,identity_key) VALUES(?,?,?)', (name,phone,key)).lastrowid
    return cid, name, phone


def commission_open(conn, end=None, beneficiary_id=None):
    end = end or today()
    rows = conn.execute('SELECT e.*,b.name AS beneficiary_name FROM expenses e JOIN beneficiaries b ON b.id=e.beneficiary_id '
        'WHERE e.occurred_on<=? AND (e.cancelled_on IS NULL OR e.cancelled_on>?) ORDER BY e.occurred_on,e.id',(end,end)).fetchall()
    result=[]
    for r in rows:
        if beneficiary_id is not None and r['beneficiary_id'] != beneficiary_id:
            continue
        paid=conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM commission_settlements WHERE expense_id=? AND settled_on<=?',(r['id'],end)).fetchone()[0]
        result.append(dict(r, settled_cents=paid, balance_cents=r['amount_cents']-paid))
    return result


def allocate_commission(conn, beneficiary_id, amount, when, batch, *, sale_id=None, cash_expense_id=None, method='Crédito de comissão'):
    if not beneficiary_id or not conn.execute('SELECT 1 FROM beneficiaries WHERE id=?',(beneficiary_id,)).fetchone():
        raise RuleError('Selecione o beneficiário do crédito.')
    rows=commission_open(conn,when,beneficiary_id)
    # Future settlements must also be reserved when posting backdated operations.
    for r in rows:
        total=conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM commission_settlements WHERE expense_id=?',(r['id'],)).fetchone()[0]
        r['available']=r['amount_cents']-total
    if amount <= 0 or sum(r['available'] for r in rows)<amount:
        raise RuleError('Saldo de comissão insuficiente na data informada. Confira o beneficiário e as baixas já registradas.')
    remaining=amount
    for r in rows:
        value=min(remaining,r['available'])
        if value>0:
            conn.execute('INSERT INTO commission_settlements(expense_id,amount_cents,settled_on,method,target_sale_id,cash_expense_id,batch_key) VALUES(?,?,?,?,?,?,?)',
                         (r['id'],value,when,method,sale_id,cash_expense_id,batch))
            remaining-=value
        if not remaining:
            break


class Commerce:
    def channels(self):
        return self.db.rows('SELECT c.*,b.name AS payee FROM channels c LEFT JOIN beneficiaries b ON b.id=c.store_beneficiary_id ORDER BY c.name')

    def beneficiaries(self):
        return self.db.rows('SELECT * FROM beneficiaries ORDER BY name')

    def sellers(self, channel_id):
        return self.db.rows('SELECT b.* FROM beneficiaries b JOIN channel_sellers s ON s.beneficiary_id=b.id WHERE s.channel_id=? ORDER BY b.name',(channel_id,))

    def delete_channel(self, channel_id):
        from .service import audit
        with self.db.transaction() as c:
            if c.execute('SELECT 1 FROM sales WHERE channel_id=?',(channel_id,)).fetchone():
                raise RuleError('Este canal tem vendas registradas. Preserve o histórico: use Editar canal e desmarque Canal ativo.')
            c.execute('DELETE FROM channel_sellers WHERE channel_id=?',(channel_id,))
            c.execute('DELETE FROM channels WHERE id=?',(channel_id,))
            audit(c,'delete_channel','channel',channel_id,{})

    def delete_beneficiary(self, beneficiary_id):
        from .service import audit
        with self.db.transaction() as c:
            checks=[('SELECT 1 FROM sales WHERE seller_id=? OR credit_beneficiary_id=?',(beneficiary_id,beneficiary_id)),
                    ('SELECT 1 FROM expenses WHERE beneficiary_id=?',(beneficiary_id,)),
                    ('SELECT 1 FROM channels WHERE store_beneficiary_id=?',(beneficiary_id,))]
            if any(c.execute(sql,args).fetchone() for sql,args in checks):
                raise RuleError('Este cadastro está vinculado a vendas, comissões ou ao recebimento de um canal e não pode ser excluído. O histórico deve ser preservado.')
            c.execute('DELETE FROM channel_sellers WHERE beneficiary_id=?',(beneficiary_id,))
            c.execute('DELETE FROM beneficiaries WHERE id=?',(beneficiary_id,))
            audit(c,'delete_beneficiary','beneficiary',beneficiary_id,{})

    def save_channel(self, data, channel_id=None):
        from .service import required, audit
        name=required(data.get('name'),'o nome do canal')
        kind=data.get('kind','Loja')
        if kind not in {'Direto','Loja','Site','Evento'}:
            raise RuleError('Tipo de canal inválido.')
        sr,vr=str(data.get('store_rate','0')).replace(',','.'),str(data.get('seller_rate','0')).replace(',','.')
        percent(10000,sr);percent(10000,vr)
        if Decimal(sr)+Decimal(vr)>100:
            raise RuleError('A soma das comissões não pode exceder 100%.')
        with self.db.transaction() as c:
            payee=data.get('store_beneficiary_id') or None
            if data.get('channel_receives') and Decimal(sr)>0:
                old=c.execute('SELECT store_beneficiary_id FROM channels WHERE id=?',(channel_id,)).fetchone() if channel_id else None
                # Preserve the existing recipient identity and all its balances on edits.
                if old and old[0] and data.get('store_beneficiary_id')==old[0]:
                    payee=old[0]
                else:
                    matches=c.execute('SELECT id FROM beneficiaries WHERE lower(trim(name))=lower(trim(?))',(name,)).fetchall()
                    if len(matches)>1:
                        raise RuleError('Há mais de um recebedor com esse nome. Escolha Outra pessoa / empresa e selecione o cadastro correto.')
                    payee=matches[0][0] if matches else c.execute('INSERT INTO beneficiaries(name) VALUES(?)',(name,)).lastrowid

            if payee and not c.execute('SELECT 1 FROM beneficiaries WHERE id=?',(payee,)).fetchone():
                raise RuleError('Beneficiário não encontrado.')
            if Decimal(sr)>0 and not payee:
                raise RuleError('Selecione quem recebe a comissão do canal.')
            values=(name,kind,sr,vr,payee,int(data.get('active',True)))
            try:
                if channel_id:
                    c.execute('UPDATE channels SET name=?,kind=?,store_rate=?,seller_rate=?,store_beneficiary_id=?,active=? WHERE id=?',values+(channel_id,))
                else:
                    channel_id=c.execute('INSERT INTO channels(name,kind,store_rate,seller_rate,store_beneficiary_id,active) VALUES(?,?,?,?,?,?)',values).lastrowid
            except __import__('sqlite3').IntegrityError:
                raise RuleError('Já existe um canal com esse nome.')
            current=c.execute('SELECT location_id FROM channels WHERE id=?',(channel_id,)).fetchone()
            if current and not current['location_id']:
                matches=[r for r in c.execute('SELECT * FROM locations') if r['name'].strip().casefold()==name.casefold()]
                if len(matches)>1:
                    raise RuleError('Há locais com nomes equivalentes. Renomeie os locais duplicados antes de salvar o canal.')
                if matches:
                    location_id=matches[0]['id']
                    c.execute('UPDATE locations SET active=1 WHERE id=?',(location_id,))
                else:
                    location_id=c.execute('INSERT INTO locations(name) VALUES(?)',(name,)).lastrowid
                c.execute('UPDATE channels SET location_id=? WHERE id=?',(location_id,channel_id))
                audit(c,'link_channel_location','channel',channel_id,{'location_id':location_id,'automatic':True})
            audit(c,'save_channel','channel',channel_id,data)
        return channel_id

    def save_beneficiary(self, name, *, channel_id=None, beneficiary_id=None, phone=''):
        from .service import required, audit
        name=required(name,'o nome do beneficiário')
        with self.db.transaction() as c:
            if beneficiary_id:
                c.execute('UPDATE beneficiaries SET name=?,phone=? WHERE id=?',(name,phone,beneficiary_id))
            else:
                beneficiary_id=c.execute('INSERT INTO beneficiaries(name,phone) VALUES(?,?)',(name,phone)).lastrowid
            if channel_id:
                c.execute('INSERT OR IGNORE INTO channel_sellers(channel_id,beneficiary_id) VALUES(?,?)',(channel_id,beneficiary_id))
            audit(c,'save_beneficiary','beneficiary',beneficiary_id,{'name':name,'channel':channel_id})
        return beneficiary_id

    def link_seller(self, channel_id, beneficiary_id):
        with self.db.transaction() as c:
            c.execute('INSERT OR IGNORE INTO channel_sellers VALUES(?,?)',(channel_id,beneficiary_id))

    def customers(self):
        return self.db.rows("SELECT c.*,COUNT(s.id) AS purchases,COALESCE(SUM(s.revenue_cents),0) AS total_cents,MAX(s.sale_date) AS last_purchase FROM customers c LEFT JOIN sales s ON s.customer_id=c.id AND s.operation='sale' AND s.cancelled_on IS NULL GROUP BY c.id ORDER BY c.name")

    def save_customer(self, data, customer_id=None):
        from .service import required, audit
        name=required(data.get('name'),'o nome do cliente')
        phone=str(data.get('phone','')).strip()
        key=' '.join(name.casefold().split())+'|'+re.sub(r'\D','',phone)
        with self.db.transaction() as c:
            if not customer_id:
                customer_id,_,_=customer_for(c,name,phone)
            try:
                c.execute('UPDATE customers SET name=?,phone=?,email=?,birthday=?,city=?,address=?,notes=?,marketing_opt_in=?,identity_key=? WHERE id=?',
                    (name,phone,data.get('email',''),data.get('birthday',''),data.get('city',''),data.get('address',''),data.get('notes',''),int(bool(data.get('marketing_opt_in'))),key,customer_id))
            except __import__('sqlite3').IntegrityError:
                raise RuleError('Já existe outro cliente com esse nome e telefone. Selecione o cadastro existente.')
            audit(c,'save_customer','customer',customer_id,{'name':name,'marketing_opt_in':bool(data.get('marketing_opt_in'))})
        return customer_id

    def customer_history(self, customer_id):
        return self.db.rows("SELECT s.id,s.sale_date,CASE WHEN s.credit_cents=s.revenue_cents AND s.credit_cents>0 THEN 'Crédito de comissão' WHEN s.credit_cents>0 THEN 'Crédito + '||s.method ELSE s.method END AS method,s.event,s.revenue_cents,i.sku,i.name,i.quantity FROM sales s JOIN (SELECT sale_id,sku,name,quantity FROM sale_items UNION ALL SELECT sale_id,sku,name,quantity FROM consignment_sale_items) i ON i.sale_id=s.id WHERE s.customer_id=? AND s.operation='sale' AND s.cancelled_on IS NULL ORDER BY s.sale_date DESC,s.id DESC",(customer_id,))

    def commission_balances(self):
        with self.db.connect() as c:
            result=[]
            for b in c.execute('SELECT * FROM beneficiaries ORDER BY name'):
                rows=commission_open(c,beneficiary_id=b['id'])
                result.append(dict(b,earned_cents=sum(r['amount_cents'] for r in rows),settled_cents=sum(r['settled_cents'] for r in rows),balance_cents=sum(r['balance_cents'] for r in rows)))
            return result

    def commission_overview(self,channel_id=None,kind=None,seller_query=''):
        """Filter monetary totals by originating channel, not only recipient membership."""
        term=seller_query.strip().casefold()
        channels=self.channels()
        memberships={b['id']:set() for b in self.beneficiaries()}
        for ch in channels:
            for seller in self.sellers(ch['id']): memberships[seller['id']].add(ch['id'])
            if ch['store_beneficiary_id']: memberships[ch['store_beneficiary_id']].add(ch['id'])
        for r in self.db.rows('SELECT DISTINCT e.beneficiary_id,s.channel_id FROM expenses e JOIN sales s ON s.id=e.sale_id WHERE e.beneficiary_id IS NOT NULL AND s.channel_id IS NOT NULL'):
            memberships[r['beneficiary_id']].add(r['channel_id'])
        chosen=[ch for ch in channels if (not channel_id or ch['id']==channel_id) and (not kind or ch['kind']==kind)]
        allowed={ch['id'] for ch in chosen}
        names={ch['id']:ch['name'] for ch in channels}
        filtered=bool(channel_id or kind)
        balances=[]
        with self.db.connect() as c:
            for b in self.beneficiaries():
                if term and term not in b['name'].casefold(): continue
                if filtered and not memberships[b['id']] & allowed: continue
                entries=commission_open(c,beneficiary_id=b['id'])
                entries=[r for r in entries if not filtered or c.execute('SELECT channel_id FROM sales WHERE id=?',(r['sale_id'],)).fetchone() and c.execute('SELECT channel_id FROM sales WHERE id=?',(r['sale_id'],)).fetchone()[0] in allowed]
                ids={r['id'] for r in entries}
                settlements=[dict(r) for r in c.execute('SELECT cs.* FROM commission_settlements cs JOIN expenses e ON e.id=cs.expense_id WHERE e.beneficiary_id=?',(b['id'],)) if r['expense_id'] in ids]
                balances.append(dict(b,channels=', '.join(names[i] for i in sorted(memberships[b['id']])) or 'Sem canal vinculado',earned_cents=sum(r['amount_cents'] for r in entries),settled_cents=sum(r['settled_cents'] for r in entries),balance_cents=sum(r['balance_cents'] for r in entries),cash_cents=sum(r['amount_cents'] for r in settlements if r['cash_expense_id']),credit_cents=sum(r['amount_cents'] for r in settlements if r['target_sale_id'])))
        if term:
            matched={b['id'] for b in balances}
            chosen=[ch for ch in chosen if any(ch['id'] in memberships[b] for b in matched)]
        for ch in chosen:
            ch['sold_cents']=self.db.rows("SELECT COALESCE(SUM(revenue_cents),0) amount FROM sales WHERE channel_id=? AND operation='sale' AND cancelled_on IS NULL",(ch['id'],))[0]['amount']
        return chosen,balances

    def pay_commission(self, beneficiary_id, amount, when, method, *, key):
        from .service import expense_row, audit
        when=day(when);amount=cents(amount)
        if method not in {'Pix','Dinheiro','Transferência'}:
            raise RuleError('Escolha Pix, Dinheiro ou Transferência para a saída de caixa.')
        with self.db.transaction() as c:
            if c.execute('SELECT 1 FROM commission_settlements WHERE batch_key=?',(key,)).fetchone():
                return
            b=c.execute('SELECT * FROM beneficiaries WHERE id=?',(beneficiary_id,)).fetchone()
            if not b:raise RuleError('Beneficiário não encontrado.')
            eid=expense_row(c,key='commission-payment-'+key,when=when,paid=when,amount=amount,category='Pagamento de comissão',description=f"Comissão · {b['name']} · {method}",vendor=b['name'],affects=0)
            allocate_commission(c,beneficiary_id,amount,when,key,cash_expense_id=eid,method=method)
            audit(c,'pay_commission','beneficiary',beneficiary_id,{'amount':amount,'date':when,'method':method})

    def reverse_commission_payment(self, batch_key, reason):
        from .service import required,audit
        reason=required(reason,'o motivo da correção')
        self.db.backup(self.db.path.parent/'backups'/f'antes-corrigir-comissao-{uuid4().hex}.sqlite3')
        with self.db.transaction() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM commission_settlements WHERE batch_key=?',(batch_key,))]
            if not rows or any(r['target_sale_id'] for r in rows):
                raise RuleError('Para desfazer um resgate em peças, corrija ou cancele a venda de resgate.')
            c.execute('DELETE FROM commission_settlements WHERE batch_key=?',(batch_key,))
            for eid in {r['cash_expense_id'] for r in rows}:
                c.execute('DELETE FROM expenses WHERE id=?',(eid,))
            audit(c,'reverse_commission_payment','commission',batch_key,{'reason':reason,'before':rows})

    def assign_legacy_commission(self, expense_id, beneficiary_id):
        from .service import audit
        with self.db.transaction() as c:
            if not beneficiary_id or not c.execute('SELECT 1 FROM beneficiaries WHERE id=?',(beneficiary_id,)).fetchone():
                raise RuleError('Selecione um beneficiário.')
            r=c.execute("SELECT * FROM expenses WHERE id=? AND category IN ('Comissão vendedora','Comissão loja') AND beneficiary_id IS NULL AND cancelled_on IS NULL",(expense_id,)).fetchone()
            if not r:raise RuleError('Comissão indisponível para vinculação.')
            c.execute('UPDATE expenses SET beneficiary_id=?,cash_effect=0 WHERE id=?',(beneficiary_id,expense_id))
            if r['paid_on']:
                from .service import expense_row
                eid=expense_row(c,key=f'legacy-payment-{expense_id}',when=r['paid_on'],paid=r['paid_on'],amount=r['amount_cents'],category='Pagamento de comissão',description=r['description'],affects=0)
                c.execute('INSERT INTO commission_settlements(expense_id,amount_cents,settled_on,method,cash_expense_id,batch_key) VALUES(?,?,?,?,?,?)',(expense_id,r['amount_cents'],r['paid_on'],'Forma não informada',eid,f'legacy-{expense_id}'))
            audit(c,'assign_commission','expense',expense_id,{'beneficiary':beneficiary_id})
