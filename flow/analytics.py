"""Leitura consistente para o dashboard; todos os valores monetários em centavos."""
from datetime import date, timedelta
from decimal import Decimal
from .money import day, RuleError, split_cents, rounded
from .reports import summary, monthly
from .commerce import commission_open


def allocate(total, weights):
    """Rateio proporcional exato; centavos restantes pela maior fração."""
    denominator = sum(weights)
    if not denominator:
        return split_cents(total, len(weights)) if weights else []
    parts = [total * w // denominator for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (total * weights[i]) % denominator, reverse=True)
    for i in order[:total - sum(parts)]:
        parts[i] += 1
    return parts


def sales_view(lines, origin='all'):
    chosen = [r for r in lines if origin == 'all' or r['origin'] == origin]
    events = {}
    products = {}
    for r in chosen:
        events[r['event_id']] = r['sign']
        key = r['product_id']
        item = products.setdefault(key, dict(product_id=key, sku=r['sku'], name=r['name'], quantity=0, revenue_cents=0, contribution_cents=0))
        for field in ['quantity', 'revenue_cents']:
            item[field] += r[field]
        if r['contribution_cents'] is None:
            item['contribution_cents'] = None
        elif item['contribution_cents'] is not None:
            item['contribution_cents'] += r['contribution_cents']
    revenue = sum(r['revenue_cents'] for r in chosen)
    count = sum(events.values())
    return dict(lines=chosen, count=count, pieces=sum(r['quantity'] for r in chosen), revenue_cents=revenue,
                ticket_cents=rounded(Decimal(revenue)/count) if count > 0 else None,
                contribution_cents=None if any(r['contribution_cents'] is None for r in chosen) else sum(r['contribution_cents'] for r in chosen),
                products=sorted(products.values(), key=lambda r: r['revenue_cents'], reverse=True))


def dashboard(db, start, end):
    start, end = day(start), day(end)
    if start > end:
        raise RuleError('A data inicial deve ser anterior ou igual à final.')
    duration = (date.fromisoformat(end)-date.fromisoformat(start)).days + 1
    previous_end = date.fromisoformat(start)-timedelta(days=1)
    previous_start = previous_end-timedelta(days=duration-1)
    with db.connect() as conn:
        conn.execute('BEGIN')
        current = summary(db, start, end, _conn=conn)
        previous = summary(db, previous_start.isoformat(), previous_end.isoformat(), _conn=conn) if previous_start.year >= 2000 else None
        months = monthly(db, start, end, _conn=conn)
        sales = [dict(r) for r in conn.execute("SELECT * FROM sales WHERE operation='sale' AND sale_date<=? AND (sale_date>=? OR cancelled_on BETWEEN ? AND ?)", (end,start,start,end))]
        lines = []
        discount_cents = 0
        for s in sales:
            items = [dict(r, origin='own') for r in conn.execute('SELECT *,NULL AS lot_id FROM sale_items WHERE sale_id=? ORDER BY id', (s['id'],))]
            items += [dict(r, origin='consigned', cost_status='confirmed') for r in conn.execute('SELECT * FROM consignment_sale_items WHERE sale_id=? ORDER BY id', (s['id'],))]
            weights = [i['unit_price_cents']*i['quantity'] for i in items]
            revenues = allocate(s['revenue_cents'],weights)
            charges = allocate(sum(s[k] for k in ['fee_cents','tax_cents','seller_cents','store_cents']),weights)
            for event_date, sign in [(s['sale_date'],1),(s['cancelled_on'],-1)]:
                if not event_date or not start <= event_date <= end:
                    continue
                discount_cents += sign*s['discount_cents']
                for index, item in enumerate(items):
                    cost = item['cost_cents'] if item['cost_status'] == 'confirmed' else None
                    lines.append(dict(id=f"{s['id']}-{sign}-{index}",event_id=f"{s['id']}-{sign}",sale_id=s['id'],date=event_date,
                        customer=s['customer'],method=s['method'],origin=item['origin'],product_id=item['product_id'],sku=item['sku'],name=item['name'],sign=sign,
                        quantity=sign*item['quantity'],revenue_cents=sign*revenues[index],cost_cents=sign*cost if cost is not None else None,
                        contribution_cents=sign*(revenues[index]-cost-charges[index]) if cost is not None else None))
        received = [dict(r) for r in conn.execute('SELECT r.*,s.customer FROM receivables r JOIN sales s ON s.id=r.sale_id WHERE r.cash_effect=1 AND r.paid_on BETWEEN ? AND ? ORDER BY r.paid_on,r.id',(start,end))]
        paid = [dict(r) for r in conn.execute('SELECT * FROM expenses WHERE cash_effect=1 AND paid_on BETWEEN ? AND ? ORDER BY paid_on,id',(start,end))]
        receivable = [dict(r) for r in conn.execute('SELECT r.*,s.customer FROM receivables r JOIN sales s ON s.id=r.sale_id WHERE s.sale_date<=? AND (r.paid_on IS NULL OR r.paid_on>?) AND (r.voided_on IS NULL OR r.voided_on>?) ORDER BY r.due_on,r.id',(end,end,end))]
        payable = [dict(r) for r in conn.execute('SELECT * FROM expenses WHERE cash_effect=1 AND occurred_on<=? AND (paid_on IS NULL OR paid_on>?) AND (cancelled_on IS NULL OR cancelled_on>?) ORDER BY due_on,id',(end,end,end))]
        for obligation in commission_open(conn,end):
            if obligation['balance_cents']:
                payable.append(dict(obligation,amount_cents=obligation['balance_cents']))
        customer_groups={}
        commercial_groups={}
        for sale in sales:
            sign=int(start<=sale['sale_date']<=end)-int(bool(sale['cancelled_on']) and start<=sale['cancelled_on']<=end)
            key=(sale['channel_name'] or sale['event'] or 'Não informado',sale['seller_name'] or 'Não informada')
            bucket=commercial_groups.setdefault(key,dict(channel=key[0],seller=key[1],count=0,revenue_cents=0,commission_cents=0))
            customer_key=('id',sale['customer_id']) if sale['customer_id'] else ('legacy',sale['customer'].strip().casefold(),sale['phone'])
            customer=customer_groups.setdefault(customer_key,dict(id=str(customer_key),name=sale['customer'] or 'Cliente não informado',count=0,revenue_cents=0))
            customer['count']+=sign
            customer['revenue_cents']+=sign*sale['revenue_cents']
            bucket['count']+=sign
            bucket['revenue_cents']+=sign*sale['revenue_cents']
            bucket['commission_cents']+=sign*(sale['store_cents']+sale['seller_cents'])
        payment_methods = {}
        for sale in sales:
            sign = int(start<=sale['sale_date']<=end) - int(bool(sale['cancelled_on']) and start<=sale['cancelled_on']<=end)
            for rec in conn.execute('SELECT * FROM receivables WHERE sale_id=?',(sale['id'],)):
                label=rec['method'] or sale['method']
                bucket=payment_methods.setdefault(label,dict(method=label,sold_cents=0,received_cents=0,fees_cents=0,compensated_cents=0))
                bucket['sold_cents']+=sign*rec['gross_cents']
        for rec in received:
            bucket=payment_methods.setdefault(rec['method'],dict(method=rec['method'],sold_cents=0,received_cents=0,fees_cents=0,compensated_cents=0))
            bucket['received_cents']+=rec['gross_cents']-rec['fee_cents']
            bucket['fees_cents']+=rec['fee_cents']
        for rec in conn.execute('SELECT * FROM receivables WHERE cash_effect=0 AND paid_on BETWEEN ? AND ?',(start,end)):
            bucket=payment_methods.setdefault(rec['method'],dict(method=rec['method'],sold_cents=0,received_cents=0,fees_cents=0,compensated_cents=0))
            bucket['compensated_cents']+=rec['gross_cents']
        personal = [dict(r) for r in conn.execute("SELECT id,sale_date,customer,cost_cents,cost_status FROM sales WHERE operation='personal' AND cancelled_on IS NULL AND sale_date BETWEEN ? AND ? ORDER BY sale_date,id",(start,end))]
        operating = []
        for r in conn.execute('SELECT * FROM expenses WHERE affects_result=1 AND occurred_on<=?',(end,)):
            for occurred, sign in [(r['occurred_on'],1),(r['cancelled_on'],-1)]:
                if occurred and start <= occurred <= end:
                    operating.append(dict(id=f"{r['id']}-{sign}",date=occurred,category=r['category'],description=r['description'],amount_cents=sign*r['amount_cents']))
        adjustments = [dict(r) for r in conn.execute("SELECT m.id,m.occurred_on AS date,p.sku,p.name,m.quantity,m.cost_cents,m.cost_status,m.reason FROM movements m JOIN products p ON p.id=m.product_id WHERE m.kind='ADJUSTMENT' AND m.occurred_on BETWEEN ? AND ? ORDER BY m.occurred_on,m.id",(start,end))]
        own = [dict(r) for r in conn.execute('SELECT p.id,p.sku,p.name,SUM(m.quantity) AS quantity,SUM(m.cost_cents) AS value_cents,EXISTS(SELECT 1 FROM history_issues h WHERE h.product_id=p.id AND h.occurred_on<=?) AS pending FROM products p JOIN movements m ON m.product_id=p.id WHERE m.occurred_on<=? GROUP BY p.id HAVING SUM(m.quantity)<>0',(end,end))]
        for r in own:
            if r.pop('pending'):
                r['value_cents'] = None
        lots = [dict(r) for r in conn.execute('SELECT l.id,p.sku,p.name,i.number AS invoice_number,l.quantity+COALESCE(SUM(m.quantity),0) AS quantity,(l.quantity+COALESCE(SUM(m.quantity),0))*l.unit_cost_cents AS value_cents FROM consignment_lots l JOIN products p ON p.id=l.product_id JOIN invoice_items ii ON ii.id=l.invoice_item_id JOIN invoices i ON i.id=ii.invoice_id LEFT JOIN active_consignment_moves m ON m.lot_id=l.id AND m.occurred_on<=? WHERE l.received_on<=? GROUP BY l.id HAVING l.quantity+COALESCE(SUM(m.quantity),0)<>0',(end,end))]
        returns = [dict(r) for r in conn.execute("SELECT m.id,m.occurred_on AS date,p.sku,p.name,-m.quantity AS quantity,-m.quantity*l.unit_cost_cents AS value_cents FROM active_consignment_moves m JOIN consignment_lots l ON l.id=m.lot_id JOIN products p ON p.id=l.product_id WHERE m.kind='RETURN' AND m.occurred_on BETWEEN ? AND ? ORDER BY m.occurred_on,m.id",(start,end))]
        conn.rollback()
    return dict(start=start,end=end,current=current,previous=previous,previous_start=previous_start.isoformat(),previous_end=previous_end.isoformat(),
                customer_groups=list(customer_groups.values()),commercial_groups=list(commercial_groups.values()),payment_methods=list(payment_methods.values()),personal=personal,months=months,discount_cents=discount_cents,adjustments=adjustments,sales=lines,received=received,paid=paid,receivable=receivable,payable=payable,operating=operating,own=own,lots=lots,returns=returns)
