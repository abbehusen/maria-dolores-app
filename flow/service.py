"""Operações atômicas do negócio. A interface nunca altera saldos diretamente."""
import json
from contextlib import nullcontext
from decimal import Decimal
from uuid import uuid4
from .db import is_integrity_error
from .money import RuleError, add_months, cents, day, decimal, pieces, rounded, split_cents, today
from .nfe import parse_xml
from .ledger import rebuild_history
from .consignment import validate_lots, recost_sale


def audit(conn, action, entity, entity_id, detail):
    conn.execute('INSERT INTO audit(action,entity,entity_id,detail) VALUES (?,?,?,?)',
                 (action, entity, str(entity_id), json.dumps(detail, ensure_ascii=False)))


def required(value, label):
    value = str(value or '').strip()
    if not value or len(value) > 2000:
        raise RuleError(f'Preencha {label} (até 2.000 caracteres).')
    return value


def stock_row(conn, product_id):
    row = conn.execute('SELECT * FROM inventory WHERE id=?', (product_id,)).fetchone()
    if row is None:
        raise RuleError('Produto não encontrado.')
    return dict(row)


def move(conn, product_id, when, quantity, cost, kind, source, reason, *, counted=None, unit_cost=None, movement_id=None):
    if movement_id is None:
        return conn.execute('INSERT INTO movements(product_id,occurred_on,quantity,cost_cents,kind,source,reason,'
                            'counted_quantity,input_unit_cost_cents) VALUES (?,?,?,?,?,?,?,?,?)',
                            (product_id, when, quantity, cost, kind, str(source), reason, counted, unit_cost)).lastrowid
    return conn.execute('INSERT INTO movements(id,product_id,occurred_on,quantity,cost_cents,kind,source,reason,'
                        'counted_quantity,input_unit_cost_cents) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (movement_id, product_id, when, quantity, cost, kind, str(source), reason, counted, unit_cost)).lastrowid


def expense_row(conn, *, key, when, amount, category, description, vendor='', affects=1,
                sale_id=None, item_id=None, paid=None, due=None, cash=1):
    return conn.execute('INSERT INTO expenses(request_key,occurred_on,due_on,paid_on,category,description,'
                        'vendor,amount_cents,affects_result,sale_id,invoice_item_id,cash_effect) '
                        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (key, when, due or when, paid, category, description, vendor, amount,
                         affects, sale_id, item_id, cash)).lastrowid


from .commerce import Commerce, customer_for, allocate_commission


from .locations import Locations


class Business(Commerce, Locations):
    def __init__(self, db):
        self.db = db

    def products(self):
        return self.db.rows('SELECT * FROM inventory ORDER BY name COLLATE NOCASE, sku')

    def owned_products(self):
        """Oculta cadastros exclusivamente consignados, preservando próprios esgotados."""
        return self.db.rows('SELECT i.* FROM inventory i WHERE EXISTS '
                            '(SELECT 1 FROM movements m WHERE m.product_id=i.id) OR NOT EXISTS '
                            '(SELECT 1 FROM consignment_lots l WHERE l.product_id=i.id) '
                            'ORDER BY i.name COLLATE NOCASE,i.sku')

    def consignment_lots(self):
        return self.db.rows("""SELECT l.*,p.sku,p.name,p.selling_cents,p.active,i.number AS invoice_number,i.issuer_name,
            l.quantity+COALESCE(SUM(m.quantity),0) AS stock,
            -COALESCE(SUM(CASE WHEN m.kind IN ('SALE','CANCELLATION') THEN m.quantity ELSE 0 END),0) AS sold,
            -COALESCE(SUM(CASE WHEN m.kind='RETURN' THEN m.quantity ELSE 0 END),0) AS returned
            FROM consignment_lots l JOIN products p ON p.id=l.product_id
            JOIN invoice_items ii ON ii.id=l.invoice_item_id JOIN invoices i ON i.id=ii.invoice_id
            LEFT JOIN active_consignment_moves m ON m.lot_id=l.id GROUP BY l.id,p.id,i.id ORDER BY l.received_on,l.id""")

    def return_consignment(self, lot_id, quantity, reason, *, when=None, key=None):
        when, quantity = day(when or today()), pieces(quantity)
        reason, key = required(reason, 'o motivo da devolução'), key or str(uuid4())
        with self.db.transaction() as conn:
            if conn.execute('SELECT id FROM consignment_moves WHERE request_key=?', (key,)).fetchone():
                return
            conn.execute("INSERT INTO consignment_moves(lot_id,occurred_on,quantity,kind,request_key,reason) VALUES (?,?,?,'RETURN',?,?)",
                         (lot_id, when, -quantity, key, reason))
            validate_lots(conn, [lot_id])
            audit(conn, 'return_consignment', 'lot', lot_id, {'quantity': quantity, 'when': when, 'reason': reason})

    def cancel_consignment_return(self, movement_id, reason):
        reason = required(reason, 'o motivo da correção')
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM consignment_moves WHERE id=? AND kind='RETURN'", (movement_id,)).fetchone()
            if not row:
                raise RuleError('Devolução não encontrada.')
            if conn.execute('SELECT 1 FROM consignment_return_cancellations WHERE movement_id=?', (movement_id,)).fetchone():
                return
            conn.execute('INSERT INTO consignment_return_cancellations(movement_id,reason) VALUES (?,?)', (movement_id, reason))
            validate_lots(conn, [row['lot_id']])
            audit(conn, 'cancel_consignment_return', 'movement', movement_id, {'reason': reason, 'quantity_restored': -row['quantity']})

    def product(self, product_id):
        with self.db.connect() as conn:
            return stock_row(conn, product_id)

    def quote_cost(self, items, when, *, exclude_sale_id=None):
        """Prévia na data escolhida; o lançamento revalida sob transação exclusiva."""
        when = day(when)
        grouped={}
        for item in items:
            identity=(item['product_id'],item.get('lot_id') or None)
            if identity not in grouped:
                grouped[identity]=dict(item,quantity=0)
            grouped[identity]['quantity']+=pieces(item['quantity'])
        items=list(grouped.values())
        total = 0
        with self.db.connect() as conn:
            conn.execute('BEGIN')
            if exclude_sale_id is not None:
                pids, _ = self._remove_sale_records(conn, exclude_sale_id)
                rebuild_history(conn, pids)
            for item in items:
                if item.get('lot_id'):
                    lot = conn.execute('SELECT * FROM consignment_lots WHERE id=? AND product_id=?', (item['lot_id'], item['product_id'])).fetchone()
                    if not lot or when < lot['received_on']:
                        return None
                    balance = lot['quantity'] + conn.execute('SELECT COALESCE(SUM(quantity),0) FROM active_consignment_moves WHERE lot_id=? AND occurred_on<=?', (lot['id'], when)).fetchone()[0]
                    if pieces(item['quantity']) > balance:
                        return None
                    total += pieces(item['quantity']) * lot['unit_cost_cents']
                    continue
                if conn.execute('SELECT 1 FROM history_issues WHERE product_id=? AND occurred_on<=?',
                                (item['product_id'], when)).fetchone():
                    return None
                qty, value = conn.execute('SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(cost_cents),0) FROM movements '
                                         'WHERE product_id=? AND occurred_on<=?', (item['product_id'], when)).fetchone()
                needed = pieces(item['quantity'])
                if needed > qty:
                    return None
                total += rounded(Decimal(value) * needed / qty)
        return total

    def create_product(self, data, *, quantity=0, unit_cost='0', when=None, opening=True, key=None):
        key = key or str(uuid4())
        when = day(when or today())
        quantity, unit_cost = pieces(quantity, zero=True), cents(unit_cost)
        with self.db.transaction() as conn:
            previous = conn.execute("SELECT entity_id FROM audit WHERE action='create_product' AND detail=?",
                                    (json.dumps({'request_key': key}, ensure_ascii=False),)).fetchone()
            if previous:
                return int(previous[0])
            try:
                product_id = conn.execute('INSERT INTO products(supplier,sku,name,category,material,stone,size,'
                                          'collection,selling_cents) VALUES (?,?,?,?,?,?,?,?,?)',
                                          (required(data.get('supplier', 'Manual'), 'o fornecedor'),
                                           required(data.get('sku'), 'o código completo'),
                                           required(data.get('name'), 'o nome do produto'),
                                           data.get('category', ''), data.get('material', ''), data.get('stone', ''),
                                           data.get('size', ''), data.get('collection', ''),
                                           cents(data.get('selling_price', '0')))).lastrowid
            except Exception as exc:
                if not is_integrity_error(exc):
                    raise
                raise RuleError('Este código e variante já estão cadastrados para o fornecedor.') from exc
            if quantity:
                move(conn, product_id, when, quantity, quantity * unit_cost,
                     'OPENING' if opening else 'PURCHASE', key,
                     'Saldo inicial conferido' if opening else 'Compra manual')
                if not opening:
                    expense_row(conn, key=key, when=when, amount=quantity * unit_cost,
                                category='Compra de estoque', description='Compra manual: ' + data['name'],
                                vendor=data.get('supplier', 'Manual'), affects=0)
            if quantity:
                from .locations import receive_at
                receive_at(conn,product_id,None,quantity,data.get('location_id'),when,key)
            audit(conn, 'create_product', 'product', product_id, {'request_key': key})
            rebuild_history(conn, [product_id])
            return product_id

    def update_catalog(self, product_id, data):
        """Lista de campos explícita: catálogo jamais escreve quantidade ou custo histórico."""
        price = cents(data['selling_price'])
        with self.db.transaction() as conn:
            before = stock_row(conn, product_id)
            name = required(data.get('name'), 'o nome do produto')
            conn.execute('UPDATE products SET name=?,category=?,collection=?,selling_cents=?,active=? WHERE id=?',
                         (name, data.get('category', ''), data.get('collection', ''), price,
                          int(bool(data.get('active', True))), product_id))
            audit(conn, 'update_catalog', 'product', product_id,
                  {'before': {k: before[k] for k in ['name', 'selling_cents', 'category', 'collection', 'active']},
                   'after': data})

    def adjust_stock(self, product_id, counted, reason, *, when=None, unit_cost='0', key=None, _conn=None):
        when, counted = day(when or today()), pieces(counted, zero=True)
        reason = required(reason, 'o motivo da conferência')
        key = key or str(uuid4())
        with (self.db.transaction() if _conn is None else nullcontext(_conn)) as conn:
            if conn.execute("SELECT id FROM movements WHERE kind='ADJUSTMENT' AND source=?", (key,)).fetchone():
                return
            row = stock_row(conn, product_id)
            if row['history_status'] == 'pending':
                raise RuleError('Complete as compras/vendas pendentes antes de conferir fisicamente este produto.')
            delta = counted - row['stock']
            if delta == 0:
                raise RuleError('A contagem coincide com o saldo atual; não há ajuste a registrar.')
            if delta < 0:
                cost = -rounded(Decimal(row['stock_cents']) * -delta / row['stock'])
            else:
                cost = cents(unit_cost) * delta
            move(conn, product_id, when, delta, cost, 'ADJUSTMENT', key, reason,
                 counted=counted, unit_cost=cents(unit_cost))
            rebuild_history(conn, [product_id], strict=True)
            audit(conn, 'adjust_stock', 'product', product_id,
                  {'counted': counted, 'previous': row['stock'], 'reason': reason})

    def import_invoice(self, raw, choices, *, markup='2.3', paid_on=None, due_on=None, ownership='own', location_id=1):
        if ownership not in {'own', 'consigned'}:
            raise RuleError('Modalidade de entrada inválida.')
        if ownership == 'consigned' and paid_on:
            raise RuleError('A entrada consignada não gera pagamento. Registre o repasse após a venda.')
        invoice = parse_xml(raw)  # Revalida no momento de gravar, não confia só na prévia.
        markup = decimal(markup)
        if not 0 < markup <= 100:
            raise RuleError('Informe um multiplicador de venda entre 0 e 100.')
        paid = day(paid_on) if paid_on else None
        due = day(due_on, future=True) if due_on else invoice.issued_on
        if paid and paid < invoice.issued_on:
            raise RuleError('O pagamento não pode anteceder a data desta compra nesta versão.')
        if set(choices) != {item.number for item in invoice.items}:
            raise RuleError('Revise o destino de todos os itens da nota.')
        with self.db.transaction() as conn:
            if conn.execute('SELECT id FROM invoices WHERE access_key=?', (invoice.key,)).fetchone():
                raise RuleError('Esta NF-e já foi importada. Nenhum saldo foi alterado.')
            invoice_id = conn.execute('INSERT INTO invoices(access_key,number,issued_on,issuer_cnpj,issuer_name,'
                                      'recipient_cnpj,total_cents,xml,sha256) VALUES (?,?,?,?,?,?,?,?,?)',
                                      (invoice.key, invoice.number, invoice.issued_on, invoice.issuer,
                                       invoice.issuer_name, invoice.recipient, invoice.total_cents,
                                       invoice.raw, invoice.sha256)).lastrowid
            conn.execute('UPDATE invoices SET ownership=? WHERE id=?', (ownership, invoice_id))
            affected = set()
            for item in invoice.items:
                destination = choices[item.number]
                if ownership == 'consigned' and destination == 'despesa':
                    raise RuleError('Na consignação, escolha estoque ou ignorar; despesas avulsas devem ser registradas separadamente.')
                if destination not in {'estoque', 'despesa', 'ignorar'}:
                    raise RuleError('Destino de item inválido.')
                product_id = None
                if destination == 'estoque':
                    quantity = pieces(item.quantity)  # Nunca arredonda unidades fracionárias silenciosamente.
                    found = conn.execute('SELECT id FROM products WHERE supplier=? AND sku=? AND material=? '
                                         'AND stone=? AND size=?',
                                         (invoice.issuer, item.sku, item.material, item.stone, item.size)).fetchone()
                    if found:
                        product_id = found['id']
                        conn.execute('UPDATE products SET active=1 WHERE id=?', (product_id,))
                    else:
                        product_id = conn.execute('INSERT INTO products(supplier,sku,name,category,material,stone,size,'
                                                  'selling_cents) VALUES (?,?,?,?,?,?,?,?)',
                                                  (invoice.issuer, item.sku, item.name, item.category, item.material,
                                                   item.stone, item.size,
                                                   rounded(Decimal(item.cost_cents) * markup / quantity))).lastrowid
                item_id = conn.execute('INSERT INTO invoice_items(invoice_id,line_number,sku,name,quantity,'
                                       'cost_cents,destination,product_id) VALUES (?,?,?,?,?,?,?,?)',
                                       (invoice_id, item.number, item.sku, item.name, str(item.quantity),
                                        item.cost_cents, destination, product_id)).lastrowid
                description = f'NF-e {invoice.number} · item {item.number} · {item.name}'
                if destination == 'estoque' and ownership == 'consigned':
                    conn.execute('INSERT INTO consignment_lots(invoice_item_id,product_id,received_on,quantity,unit_cost_cents) VALUES (?,?,?,?,?)',
                                 (item_id, product_id, invoice.issued_on, quantity, rounded(Decimal(item.cost_cents) / quantity)))
                if destination == 'estoque' and ownership == 'own':
                    move(conn, product_id, invoice.issued_on, quantity, item.cost_cents,
                         'PURCHASE', f'nfe-{item_id}', description)
                    affected.add(product_id)
                if destination == 'estoque':
                    from .locations import receive_at
                    lot=conn.execute('SELECT id FROM consignment_lots WHERE invoice_item_id=?',(item_id,)).fetchone()
                    receive_at(conn,product_id,lot['id'] if lot else None,quantity,location_id,invoice.issued_on,f'receive-{invoice_id}')
                if destination != 'ignorar' and ownership == 'own':
                    expense_row(conn, key=f'nfe-{item_id}', when=invoice.issued_on, due=due,
                                amount=item.cost_cents, category='Compra de estoque' if destination == 'estoque'
                                else 'Outras despesas', description=description, vendor=invoice.issuer_name,
                                affects=int(destination == 'despesa'), item_id=item_id, paid=paid)
            audit(conn, 'import_invoice', 'invoice', invoice_id, {'key': invoice.key, 'choices': choices, 'ownership': ownership})
            rebuild_history(conn, affected)
            return invoice_id

    def invoice_snapshot(self, invoice_id, conn=None):
        with (self.db.connect() if conn is None else nullcontext(conn)) as connection:
            row = connection.execute('SELECT * FROM invoices WHERE id=?', (invoice_id,)).fetchone()
            if not row:
                raise RuleError('Nota não encontrada.')
            return {'invoice': {k: row[k] for k in row.keys() if k != 'xml'},
                    'items': [dict(r) for r in connection.execute('SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id', (invoice_id,))],
                    'expenses': [dict(r) for r in connection.execute('SELECT * FROM expenses WHERE invoice_item_id IN (SELECT id FROM invoice_items WHERE invoice_id=?) ORDER BY id', (invoice_id,))]}

    def delete_invoice(self, invoice_id, *, reason, confirmation, expected=None):
        reason = required(reason, 'o motivo da exclusão')
        def validate(conn):
            snapshot = self.invoice_snapshot(invoice_id, conn)
            if expected is not None and snapshot != expected:
                raise RuleError('A nota ou seus pagamentos mudaram. Feche e abra novamente a exclusão.')
            number = snapshot['invoice']['number']
            if confirmation != f'EXCLUIR NOTA {number}':
                raise RuleError(f'Digite EXCLUIR NOTA {number} para confirmar.')
            blockers = []
            for item in snapshot['items']:
                pid = item['product_id']
                if not pid:
                    continue
                if snapshot['invoice']['ownership'] == 'own':
                    rows = conn.execute("SELECT kind,source,occurred_on FROM movements WHERE product_id=? AND kind IN ('SALE','CANCELLATION','ADJUSTMENT') ORDER BY occurred_on,id", (pid,)).fetchall()
                    for row in rows:
                        label = f"conferência em {row['occurred_on']}" if row['kind'] == 'ADJUSTMENT' else f"venda #{row['source']}"
                        blockers.append(f"item {item['line_number']} ({item['sku']}): {label}")
                else:
                    rows = conn.execute('SELECT m.* FROM consignment_moves m JOIN consignment_lots l ON l.id=m.lot_id WHERE l.invoice_item_id=? ORDER BY m.id', (item['id'],)).fetchall()
                    for row in rows:
                        label = f"venda #{row['sale_id']}" if row['sale_id'] else f"devolução #{row['id']} em {row['occurred_on']}"
                        blockers.append(f"item {item['line_number']} ({item['sku']}): {label}")
            if blockers:
                raise RuleError('Exclusão bloqueada. Corrija os registros vinculados antes: ' + '; '.join(dict.fromkeys(blockers)))
            return snapshot
        with self.db.connect() as conn:
            validate(conn)
        backup = self.db.backup(self.db.path.parent / 'backups' / f'antes-excluir-nota-{invoice_id}-{uuid4().hex[:12]}.sqlite3')
        with self.db.transaction() as conn:
            before = validate(conn)
            pids = {i['product_id'] for i in before['items'] if i['product_id']}
            for item in before['items']:
                conn.execute("DELETE FROM movements WHERE kind='PURCHASE' AND source=?", (f"nfe-{item['id']}",))
                conn.execute('DELETE FROM consignment_lots WHERE invoice_item_id=?', (item['id'],))
                conn.execute('DELETE FROM expenses WHERE invoice_item_id=?', (item['id'],))
            conn.execute('DELETE FROM invoice_items WHERE invoice_id=?', (invoice_id,))
            conn.execute('DELETE FROM invoices WHERE id=?', (invoice_id,))
            rebuild_history(conn, pids)
            for pid in pids:
                if not any(conn.execute(f'SELECT 1 FROM {table} WHERE product_id=? LIMIT 1', (pid,)).fetchone() for table in ['movements', 'consignment_lots', 'invoice_items', 'sale_items', 'consignment_sale_items']):
                    conn.execute('UPDATE products SET active=0 WHERE id=?', (pid,))
            audit(conn, 'delete_invoice', 'invoice', invoice_id,
                  {'reason': reason, 'backup': backup.name, 'before': before})
        return backup

    def correct_invoice(self, invoice_id, choices, *, reason, markup='2.3', expected=None):
        reason = required(reason, 'o motivo da correção')
        multiplier = decimal(markup)
        if not 0 < multiplier <= 100:
            raise RuleError('Informe um multiplicador de venda entre 0 e 100.')
        backup = self.db.backup(self.db.path.parent / 'backups' / f'antes-corrigir-nota-{invoice_id}-{uuid4().hex[:12]}.sqlite3')
        with self.db.transaction() as conn:
            before = self.invoice_snapshot(invoice_id, conn)
            if expected is not None and before != expected:
                raise RuleError('A nota ou seus pagamentos mudaram. Feche e abra novamente a correção.')
            original = conn.execute('SELECT xml FROM invoices WHERE id=?', (invoice_id,)).fetchone()[0]
            invoice = parse_xml(original)
            items = {i.number: i for i in invoice.items}
            if set(choices) != set(items):
                raise RuleError('Revise o destino de todos os itens da nota.')
            ownership = before['invoice']['ownership']
            affected = set()
            for row in before['items']:
                destination = choices[row['line_number']]
                if destination not in {'estoque', 'despesa', 'ignorar'}:
                    raise RuleError('Destino de item inválido.')
                if ownership == 'consigned' and destination == 'despesa':
                    raise RuleError('Esta nota é consignada: use estoque ou ignorar. Registre despesas avulsas separadamente.')
                if destination == row['destination']:
                    continue
                item = items[row['line_number']]
                expense = conn.execute('SELECT * FROM expenses WHERE request_key=?', (f"nfe-{row['id']}",)).fetchone()
                if destination == 'ignorar' and expense and expense['paid_on']:
                    raise RuleError(f'Item {item.number}: já existe pagamento. Use Despesa para reclassificar sem apagar a baixa; não é possível ignorar este item pago.')
                pid = row['product_id']
                if row['destination'] == 'estoque':
                    if ownership == 'consigned':
                        lot = conn.execute('SELECT * FROM consignment_lots WHERE invoice_item_id=?', (row['id'],)).fetchone()
                        if lot and conn.execute('SELECT 1 FROM consignment_moves WHERE lot_id=? LIMIT 1', (lot['id'],)).fetchone():
                            raise RuleError(f'Item {item.number}: o lote tem venda ou devolução vinculada. Corrija esses registros antes de alterar a entrada.')
                        conn.execute('DELETE FROM consignment_lots WHERE invoice_item_id=?', (row['id'],))
                    else:
                        if conn.execute("SELECT 1 FROM movements WHERE product_id=? AND kind IN ('SALE','CANCELLATION','ADJUSTMENT') LIMIT 1", (pid,)).fetchone():
                            raise RuleError(f'Item {item.number}: o produto tem vendas ou conferências de estoque vinculadas. Corrija esses registros antes de alterar a entrada.')
                        conn.execute("DELETE FROM movements WHERE kind='PURCHASE' AND source=?", (f"nfe-{row['id']}",))
                        affected.add(pid)
                new_pid = None
                if destination == 'estoque':
                    quantity = pieces(item.quantity)
                    found = conn.execute('SELECT id FROM products WHERE supplier=? AND sku=? AND material=? AND stone=? AND size=?',
                                         (invoice.issuer, item.sku, item.material, item.stone, item.size)).fetchone()
                    if found:
                        new_pid = found['id']
                        conn.execute('UPDATE products SET active=1 WHERE id=?', (new_pid,))
                    else:
                        new_pid = conn.execute('INSERT INTO products(supplier,sku,name,category,material,stone,size,selling_cents) VALUES (?,?,?,?,?,?,?,?)',
                            (invoice.issuer, item.sku, item.name, item.category, item.material, item.stone, item.size, rounded(Decimal(item.cost_cents)*multiplier/quantity))).lastrowid
                    if ownership == 'own':
                        move(conn, new_pid, invoice.issued_on, quantity, item.cost_cents, 'PURCHASE', f"nfe-{row['id']}", f'NF-e {invoice.number} · item {item.number} · {item.name}')
                        affected.add(new_pid)
                    else:
                        conn.execute('INSERT INTO consignment_lots(invoice_item_id,product_id,received_on,quantity,unit_cost_cents) VALUES (?,?,?,?,?)',
                                     (row['id'], new_pid, invoice.issued_on, quantity, rounded(Decimal(item.cost_cents)/quantity)))
                conn.execute('UPDATE invoice_items SET destination=?,product_id=? WHERE id=?', (destination, new_pid, row['id']))
                if ownership == 'own':
                    if destination == 'ignorar':
                        conn.execute('DELETE FROM expenses WHERE request_key=?', (f"nfe-{row['id']}",))
                    elif expense:
                        conn.execute('UPDATE expenses SET category=?,affects_result=? WHERE id=?',
                                     ('Compra de estoque' if destination == 'estoque' else 'Outras despesas', int(destination == 'despesa'), expense['id']))
                    else:
                        expense_row(conn, key=f"nfe-{row['id']}", when=invoice.issued_on, amount=item.cost_cents,
                                    category='Compra de estoque' if destination == 'estoque' else 'Outras despesas',
                                    description=f'NF-e {invoice.number} · item {item.number} · {item.name}', vendor=invoice.issuer_name,
                                    affects=int(destination == 'despesa'), item_id=row['id'])
            for old in before['items']:
                old_pid = old['product_id']
                if old_pid and not any(conn.execute(f'SELECT 1 FROM {table} WHERE product_id=? LIMIT 1', (old_pid,)).fetchone() for table in ['movements', 'consignment_lots', 'invoice_items', 'sale_items', 'consignment_sale_items']):
                    conn.execute('UPDATE products SET active=0 WHERE id=?', (old_pid,))
            rebuild_history(conn, affected)
            audit(conn, 'correct_invoice', 'invoice', invoice_id,
                  {'reason': reason, 'backup': backup.name, 'before': before, 'after': self.invoice_snapshot(invoice_id, conn)})
        return invoice_id

    def create_sale(self, items, data, *, key, _conn=None, _sale_id=None, _movement_ids=None, _allowed_archived=()):
        required(key, 'a identificação da operação')
        data = dict(data)
        operation = data.get('operation', 'sale')
        if operation not in {'sale','personal'}:
            raise RuleError('Tipo de operação inválido.')
        personal = operation == 'personal'
        if personal:
            data.update(discount='0',fee='0',tax='0',seller='0',store='0',installments=1,paid_on=None,method='Retirada pessoal',historical=False,credit='0',channel_id=None,seller_id=None,customer_id=None)
            data['customer'] = required(data.get('customer'), 'quem retirou as peças')
            items = [dict(i, unit_price='0') for i in items]
        when = day(data.get('sale_date', today()))
        historical = data.get('historical') is True
        if not items:
            raise RuleError('Adicione pelo menos um produto à venda.')
        allocations=[];grouped={}
        for item in items:
            loc=item.get('location_id') or data.get('location_id') or 1
            allocations.append(dict(product_id=item['product_id'],lot_id=item.get('lot_id') or None,location_id=loc,quantity=pieces(item['quantity'])))
            identity=(item['product_id'],item.get('lot_id') or None)
            if identity in grouped:
                if cents(grouped[identity]['unit_price'])!=cents(item['unit_price']):
                    raise RuleError('A mesma peça deve usar o mesmo preço unitário nos diferentes locais.')
                grouped[identity]['quantity']+=pieces(item['quantity'])
            else:
                grouped[identity]=dict(item,quantity=pieces(item['quantity']))
        items=list(grouped.values())
        installments = pieces(data.get('installments', 1))
        if installments > 24:
            raise RuleError('O limite é de 24 parcelas.')
        first_due = day(data.get('first_due', when), future=True)
        paid = day(data['paid_on']) if data.get('paid_on') else None
        if first_due < when or (paid and paid < when):
            raise RuleError('Vencimento e recebimento não podem anteceder a venda nesta versão.')
        if paid and installments != 1:
            raise RuleError('Registre a baixa de cada parcela na lista de recebimentos.')
        with (self.db.transaction() if _conn is None else nullcontext(_conn)) as conn:
            if conn.execute('SELECT id FROM deleted_sales WHERE request_key=?', (key,)).fetchone():
                raise RuleError('Este formulário pertence a um teste já excluído. Abra uma nova venda.')
            previous = conn.execute('SELECT id FROM sales WHERE request_key=?', (key,)).fetchone()
            if previous:
                return previous['id']
            cid, customer_name, customer_phone = (None, data.get('customer',''), '') if personal else customer_for(conn,data.get('customer',''),data.get('phone',''),data.get('customer_id'))
            channel = conn.execute('SELECT * FROM channels WHERE id=?',(data.get('channel_id'),)).fetchone() if data.get('channel_id') else None
            if data.get('channel_id') and (not channel or not channel['active']):
                raise RuleError('Selecione um canal ativo.')
            seller_row = conn.execute('SELECT b.* FROM beneficiaries b JOIN channel_sellers cs ON cs.beneficiary_id=b.id WHERE b.id=? AND cs.channel_id=?',(data.get('seller_id'),data.get('channel_id'))).fetchone() if data.get('seller_id') else None
            if data.get('seller_id') and not seller_row:
                raise RuleError('A vendedora não está vinculada ao canal selecionado.')
            lines = []
            for item in items:
                product = stock_row(conn, item['product_id'])
                qty, price = pieces(item['quantity']), cents(item['unit_price'])
                if not product['active'] and product['id'] not in _allowed_archived:
                    raise RuleError(f"{product['name']} está arquivado.")
                if item.get('lot_id'):
                    lot = conn.execute('SELECT * FROM consignment_lots WHERE id=? AND product_id=?', (item['lot_id'], product['id'])).fetchone()
                    if not lot:
                        raise RuleError('Lote consignado incompatível com o produto.')
                    product['lot_id'] = lot['id']
                    product['consignment_unit_cost'] = lot['unit_cost_cents']
                if not item.get('lot_id') and not historical and qty > product['stock']:
                    raise RuleError(f"Estoque insuficiente de {product['name']}: {product['stock']} peça(s) disponível(is).")
                cost = qty * product['consignment_unit_cost'] if item.get('lot_id') else 0  # Calculado pelo histórico após inserir todos os itens, na mesma transação.
                lines.append((product, qty, price, cost))
            subtotal = sum(qty * price for _, qty, price, _ in lines)
            discount = cents(data.get('discount', '0'))
            if discount > subtotal:
                raise RuleError('O desconto não pode exceder o valor dos produtos.')
            revenue = subtotal - discount
            costs = sum(cost for _, _, _, cost in lines)
            fee, tax, seller, store = [cents(data.get(k, '0')) for k in ['fee', 'tax', 'seller', 'store']]
            if fee > revenue:
                raise RuleError('A taxa retida do cartão não pode exceder a receita.')
            credit = cents(data.get('credit','0'))
            if credit > revenue or fee > revenue-credit:
                raise RuleError('Crédito ou taxa excede o valor a receber em dinheiro.')
            if credit and (seller or store):
                raise RuleError('O resgate de comissão não gera novas comissões. Zere os percentuais.')
            if channel:
                if seller and not seller_row:
                    raise RuleError('Selecione a vendedora beneficiária da comissão.')
                if store and not channel['store_beneficiary_id']:
                    raise RuleError('Configure o beneficiário da comissão do canal.')
            net = revenue - costs - fee - tax - seller - store
            next_id = conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM '
                                   '(SELECT id FROM sales UNION ALL SELECT id FROM deleted_sales)').fetchone()[0]
            sale_id = conn.execute('INSERT INTO sales(id,request_key,sale_date,customer,phone,event,method,notes,'
                                   'subtotal_cents,discount_cents,revenue_cents,cost_cents,fee_cents,tax_cents,'
                                   'seller_cents,store_cents,net_cents) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                   (_sale_id if _sale_id is not None else next_id, key, when, data.get('customer', ''), data.get('phone', ''), data.get('event', ''),
                                    required(data.get('method'), 'a forma de pagamento'), data.get('notes', ''),
                                    subtotal, discount, revenue, costs, fee, tax, seller, store, net)).lastrowid
            conn.execute('UPDATE sales SET operation=?,customer_id=?,customer=?,phone=?,channel_id=?,seller_id=?,channel_name=?,seller_name=?,credit_beneficiary_id=?,credit_cents=? WHERE id=?',
                (operation,cid,customer_name,customer_phone,data.get('channel_id'),data.get('seller_id'),channel['name'] if channel else '',seller_row['name'] if seller_row else '',data.get('credit_beneficiary_id') if credit else None,credit,sale_id))
            location_id=data.get('location_id') or 1
            if not conn.execute('SELECT 1 FROM locations WHERE id=? AND active=1',(location_id,)).fetchone():
                raise RuleError('Selecione um local de estoque ativo.')
            conn.execute('UPDATE sales SET location_id=? WHERE id=?',(location_id,sale_id))
            for allocation in allocations:
                if not conn.execute('SELECT 1 FROM locations WHERE id=? AND active=1',(allocation['location_id'],)).fetchone():
                    raise RuleError('Selecione um local de estoque ativo para cada peça.')
                conn.execute('INSERT INTO sale_locations(sale_id,product_id,lot_id,location_id,quantity) VALUES(?,?,?,?,?)',(sale_id,allocation['product_id'],allocation['lot_id'],allocation['location_id'],allocation['quantity']))
            for product, qty, price, cost in lines:
                if product.get('lot_id'):
                    lot_id = product['lot_id']
                    conn.execute('INSERT INTO consignment_sale_items(sale_id,lot_id,product_id,sku,name,quantity,unit_price_cents,cost_cents) VALUES (?,?,?,?,?,?,?,?)',
                                 (sale_id, lot_id, product['id'], product['sku'], product['name'], qty, price, cost))
                    historical_movement_id = (_movement_ids or {}).get(('cons', lot_id))
                    if historical_movement_id is None:
                        conn.execute("INSERT INTO consignment_moves(lot_id,occurred_on,quantity,kind,sale_id,request_key,reason) VALUES (?,?,?,'SALE',?,?,?)",
                                     (lot_id, when, -qty, sale_id, f'cons-sale-{sale_id}-{lot_id}', f'Venda #{sale_id}'))
                    else:
                        conn.execute("INSERT INTO consignment_moves(id,lot_id,occurred_on,quantity,kind,sale_id,request_key,reason) VALUES (?,?,?,?,'SALE',?,?,?)",
                                     (historical_movement_id, lot_id, when, -qty, sale_id, f'cons-sale-{sale_id}-{lot_id}', f'Venda #{sale_id}'))
                    lot_info = conn.execute('SELECT l.invoice_item_id,i.issuer_name FROM consignment_lots l JOIN invoice_items ii ON ii.id=l.invoice_item_id JOIN invoices i ON i.id=ii.invoice_id WHERE l.id=?', (lot_id,)).fetchone()
                    expense_row(conn, key=f'consignment-{sale_id}-{lot_id}', when=when,
                                due=day(data.get('consignment_due', when), future=True), amount=cost,
                                category='Repasse consignação', description=f"Consignado · venda #{sale_id} · lote #{lot_id} · {product['sku']}",
                                vendor=lot_info['issuer_name'], affects=0, sale_id=sale_id, item_id=lot_info['invoice_item_id'])
                    continue
                conn.execute('INSERT INTO sale_items(sale_id,product_id,sku,name,quantity,unit_price_cents,cost_cents) '
                             'VALUES (?,?,?,?,?,?,?)', (sale_id, product['id'], product['sku'], product['name'], qty, price, cost))
                move(conn, product['id'], when, -qty, -cost, 'SALE', sale_id, f'Venda #{sale_id}', movement_id=(_movement_ids or {}).get(('own', product['id'])))
            if not personal:
                remaining = revenue-credit
                gross_parts, fee_parts = split_cents(remaining, installments), split_cents(fee, installments)
                if remaining or not credit:
                    for i in range(installments):
                        conn.execute('INSERT INTO receivables(sale_id,installment,due_on,gross_cents,fee_cents,paid_on,method) VALUES(?,?,?,?,?,?,?)',
                            (sale_id,i+1,add_months(first_due,i),gross_parts[i],fee_parts[i],paid,data['method']))
                if credit:
                    allocate_commission(conn,data.get('credit_beneficiary_id'),credit,when,'redemption-'+key,sale_id=sale_id)
                    conn.execute("INSERT INTO receivables(sale_id,installment,due_on,gross_cents,fee_cents,paid_on,method,cash_effect) VALUES(?,0,?,?,0,?,'Crédito de comissão',0)",(sale_id,when,credit,when))
                for name, amount, beneficiary in [('Impostos da venda', tax,None), ('Comissão vendedora', seller,data.get('seller_id')), ('Comissão loja', store,channel['store_beneficiary_id'] if channel else None)]:
                    if amount:
                        eid = expense_row(conn, key=f'sale-{sale_id}-{name}', when=when, amount=amount, category=name,
                                    description=f'{name} · venda #{sale_id}', affects=0, sale_id=sale_id)
                        if beneficiary:
                            conn.execute('UPDATE expenses SET beneficiary_id=?,cash_effect=0,vendor=(SELECT name FROM beneficiaries WHERE id=?) WHERE id=?',(beneficiary,beneficiary,eid))
            validate_lots(conn, [p['lot_id'] for p, _, _, _ in lines if p.get('lot_id')])
            rebuild_history(conn, [p['id'] for p, _, _, _ in lines if not p.get('lot_id')], strict=not historical)
            recost_sale(conn, sale_id)
            audit(conn, 'create_sale', 'sale', sale_id, {'request_key': key, 'historical': historical})
            return sale_id

    def sale_snapshot(self, sale_id, conn=None):
        with (self.db.connect() if conn is None else nullcontext(conn)) as connection:
            sale = connection.execute('SELECT * FROM sales WHERE id=?', (sale_id,)).fetchone()
            if not sale:
                raise RuleError('Venda inexistente ou já removida.')
            snapshot = {'sale': dict(sale)}
            snapshot['commission_settlements'] = [dict(r) for r in connection.execute('SELECT cs.* FROM commission_settlements cs LEFT JOIN expenses e ON e.id=cs.expense_id WHERE cs.target_sale_id=? OR e.sale_id=? ORDER BY cs.id',(sale_id,sale_id))]
            for table in ['sale_items', 'consignment_sale_items', 'sale_locations', 'receivables', 'expenses']:
                snapshot[table] = [dict(r) for r in connection.execute(
                    f'SELECT * FROM {table} WHERE sale_id=? ORDER BY id', (sale_id,))]
            return snapshot

    def _remove_sale_records(self, conn, sale_id):
        if conn.execute('SELECT 1 FROM commission_settlements cs JOIN expenses e ON e.id=cs.expense_id WHERE e.sale_id=?',(sale_id,)).fetchone():
            raise RuleError('Esta venda gerou comissão já utilizada. Desfaça os pagamentos ou as vendas de resgate vinculadas antes de corrigir.')
        conn.execute('DELETE FROM commission_settlements WHERE target_sale_id=?',(sale_id,))
        pids = [r[0] for r in conn.execute('SELECT product_id FROM sale_items WHERE sale_id=?', (sale_id,))]
        lots = [r[0] for r in conn.execute('SELECT lot_id FROM consignment_sale_items WHERE sale_id=?', (sale_id,))]
        conn.execute("DELETE FROM history_issues WHERE movement_id IN (SELECT id FROM movements WHERE kind IN ('SALE','CANCELLATION') AND source=?)", (str(sale_id),))
        conn.execute("DELETE FROM movements WHERE kind IN ('SALE','CANCELLATION') AND source=?", (str(sale_id),))
        conn.execute('DELETE FROM consignment_moves WHERE sale_id=?', (sale_id,))
        for table in ['sale_items', 'consignment_sale_items', 'sale_locations', 'receivables', 'expenses']:
            conn.execute(f'DELETE FROM {table} WHERE sale_id=?', (sale_id,))
        conn.execute('DELETE FROM sales WHERE id=?', (sale_id,))
        return pids, lots

    def correct_sale(self, sale_id, *, reason, items=None, data=None, expected=None, reset_payments=False):
        """Remove um lançamento errado ou substitui a venda inteira, atomicamente.

        Baixas são registros locais. O snapshot conserva a trilha completa da
        correção; não há operação bancária nem criação de reembolso fictício.
        """
        reason = required(reason, 'o motivo da correção')
        backup = self.db.backup(self.db.path.parent / 'backups' /
                               f'antes-corrigir-venda-{sale_id}-{uuid4().hex[:12]}.sqlite3')
        with self.db.transaction() as conn:
            before = self.sale_snapshot(sale_id, conn)
            if expected is not None and before != expected:
                raise RuleError('A venda ou suas baixas mudaram. Feche e abra novamente o formulário.')
            if items is not None and before['sale']['credit_cents'] and not reset_payments:
                raise RuleError('Para editar um resgate, marque Desfazer baixas anteriores e confira novamente o crédito utilizado.')
            if items is not None and before['sale']['cancelled_on']:
                raise RuleError('Uma venda já cancelada não pode ser editada. Remova o lançamento errado e registre novamente.')
            movement_ids = {}
            movement_created = {r['id']: r['created_at'] for r in conn.execute("SELECT id,created_at FROM movements WHERE kind='SALE' AND source=?", (str(sale_id),))}
            if items is not None:
                for table, kind, field in [('movements', 'own', 'product_id'), ('consignment_moves', 'cons', 'lot_id')]:
                    link = 'source' if kind == 'own' else 'sale_id'
                    old = {r[field]: r['id'] for r in conn.execute(f"SELECT * FROM {table} WHERE {link}=? AND kind='SALE'", (str(sale_id),))}
                    maximum = conn.execute(f'SELECT COALESCE(MAX(id),0) FROM {table}').fetchone()[0]
                    for item in items:
                        if bool(item.get('lot_id')) != (kind == 'cons'):
                            continue
                        identity = item[field]
                        maximum += 1
                        movement_ids[(kind, identity)] = old.get(identity, maximum)
            pids, lots = self._remove_sale_records(conn, sale_id)
            rebuild_history(conn, pids)
            if items is None:
                validate_lots(conn, lots)
                conn.execute('INSERT INTO deleted_sales(id,request_key,reason) VALUES (?,?,?)',
                             (sale_id, before['sale']['request_key'], reason))
            else:
                self.create_sale(items, data, key=before['sale']['request_key'], _conn=conn, _sale_id=sale_id, _movement_ids=movement_ids, _allowed_archived=[i['product_id'] for i in before['sale_items'] + before['consignment_sale_items']])
                conn.execute('UPDATE sales SET created_at=? WHERE id=?', (before['sale']['created_at'], sale_id))
                for mid, created_at in movement_created.items():
                    conn.execute("UPDATE movements SET created_at=? WHERE id=? AND kind='SALE' AND source=?", (created_at, mid, str(sale_id)))
                if not reset_payments:
                    old_receipts = before['receivables']
                    new_receipts = conn.execute('SELECT * FROM receivables WHERE sale_id=? ORDER BY installment', (sale_id,)).fetchall()
                    if any(r['paid_on'] for r in old_receipts) and len(old_receipts) != len(new_receipts):
                        raise RuleError('Para mudar o parcelamento com baixas existentes, marque Desfazer baixas anteriores e informe os novos recebimentos.')
                    for old, new in zip(old_receipts, new_receipts):
                        if old['paid_on']:
                            if old['paid_on'] < data['sale_date']:
                                raise RuleError('A venda não pode ficar após um recebimento mantido. Corrija a data ou desfaça as baixas anteriores.')
                            conn.execute('UPDATE receivables SET paid_on=? WHERE id=?', (old['paid_on'], new['id']))
                    for old in before['expenses']:
                        if old['paid_on']:
                            new = conn.execute('SELECT * FROM expenses WHERE request_key=?', (old['request_key'],)).fetchone()
                            if new is None:
                                raise RuleError('A edição remove uma obrigação já paga. Marque Desfazer baixas anteriores para corrigir esses pagamentos.')
                            if old['paid_on'] < data['sale_date']:
                                raise RuleError('A venda não pode ficar após um pagamento mantido. Corrija a data ou desfaça as baixas anteriores.')
                            conn.execute('UPDATE expenses SET paid_on=? WHERE id=?', (old['paid_on'], new['id']))
                validate_lots(conn, lots)
                rebuild_history(conn, pids)
            audit(conn, 'correct_sale' if items is not None else 'remove_wrong_sale', 'sale', sale_id,
                  {'reason': reason, 'backup': backup.name, 'before': before,
                   'after': self.sale_snapshot(sale_id, conn) if items is not None else None,
                   'reset_payments': reset_payments})
        return sale_id

    def cancel_sale(self, sale_id, reason, *, when=None):
        when, reason = day(when or today()), required(reason, 'o motivo do cancelamento')
        with self.db.transaction() as conn:
            if conn.execute('SELECT 1 FROM commission_settlements cs JOIN expenses e ON e.id=cs.expense_id WHERE e.sale_id=? OR cs.target_sale_id=?',(sale_id,sale_id)).fetchone():
                raise RuleError('Há comissões vinculadas. Use a correção da venda.')
            row = conn.execute('SELECT * FROM sales WHERE id=?', (sale_id,)).fetchone()
            if not row:
                raise RuleError('Venda não encontrada.')
            if row['cancelled_on']:
                return
            if when < row['sale_date']:
                raise RuleError('O cancelamento não pode anteceder a venda.')
            paid_obligations = conn.execute('SELECT id FROM expenses WHERE sale_id=? AND paid_on IS NOT NULL '
                                            'AND cancelled_on IS NULL', (sale_id,)).fetchone()
            if paid_obligations:
                raise RuleError('Esta venda tem repasse, comissão ou imposto já pago. Concilie a devolução desses valores '
                                'antes do cancelamento; a versão inicial não automatiza essa recuperação.')
            received = conn.execute('SELECT COALESCE(SUM(gross_cents),0),COALESCE(SUM(fee_cents),0),MAX(paid_on) '
                                    'FROM receivables WHERE sale_id=? AND paid_on IS NOT NULL', (sale_id,)).fetchone()
            if received[2] and when < received[2]:
                raise RuleError('O cancelamento não pode anteceder o último recebimento.')
            for item in conn.execute('SELECT * FROM sale_items WHERE sale_id=?', (sale_id,)).fetchall():
                move(conn, item['product_id'], when, item['quantity'], item['cost_cents'],
                     'CANCELLATION', sale_id, reason)
            lots = conn.execute('SELECT lot_id,quantity FROM consignment_sale_items WHERE sale_id=?', (sale_id,)).fetchall()
            for item in lots:
                conn.execute("INSERT INTO consignment_moves(lot_id,occurred_on,quantity,kind,sale_id,request_key,reason) VALUES (?,?,?,'CANCELLATION',?,?,?)",
                             (item['lot_id'], when, item['quantity'], sale_id, f"cons-cancel-{sale_id}-{item['lot_id']}", reason))
            validate_lots(conn, [r['lot_id'] for r in lots])
            conn.execute('UPDATE sales SET cancelled_on=?,cancel_reason=? WHERE id=?', (when, reason, sale_id))
            conn.execute('UPDATE receivables SET voided_on=? WHERE sale_id=? AND paid_on IS NULL', (when, sale_id))
            conn.execute('UPDATE expenses SET cancelled_on=?,cancel_reason=? WHERE sale_id=? AND paid_on IS NULL',
                         (when, reason, sale_id))
            if received[0]:
                expense_row(conn, key=f'refund-{sale_id}', when=when, amount=received[0], category='Reembolso ao cliente',
                            description=f'Reembolsar venda #{sale_id} cancelada', affects=0, sale_id=sale_id)
            if received[1]:
                expense_row(conn, key=f'fee-loss-{sale_id}', when=when, amount=received[1], category='Taxa não devolvida',
                            description=f'Taxa já retida da venda #{sale_id} cancelada', affects=1, cash=0, sale_id=sale_id)
            rebuild_history(conn, [r[0] for r in conn.execute('SELECT product_id FROM sale_items WHERE sale_id=?', (sale_id,))])
            audit(conn, 'cancel_sale', 'sale', sale_id, {'reason': reason, 'when': when})

    def delete_cancelled_test_sale(self, sale_id, *, confirmation, reason):
        """Limpeza explícita de testes; não é estorno de uma venda real.

        Remove também recebimentos simulados, encargos e reembolso ainda não pago.
        Pagamentos vinculados já baixados bloqueiam a limpeza. Guarda backup e
        apenas o identificador/motivo no registro de exclusões, sem reutilizar ids.
        """
        if confirmation != f'EXCLUIR TESTE #{sale_id}':
            raise RuleError(f'Digite EXCLUIR TESTE #{sale_id} para confirmar a exclusão definitiva do teste.')
        reason = required(reason, 'o motivo da exclusão')

        def validate(conn):
            row = conn.execute('SELECT * FROM sales WHERE id=?', (sale_id,)).fetchone()
            if not row:
                raise RuleError('Venda inexistente ou já excluída.')
            if not row['cancelled_on']:
                raise RuleError('Cancele a venda fictícia antes de excluir o registro.')
            if conn.execute('SELECT id FROM expenses WHERE sale_id=? AND paid_on IS NOT NULL', (sale_id,)).fetchone():
                raise RuleError('Há pagamento vinculado já baixado (repasse, comissão, imposto ou reembolso). A exclusão foi bloqueada.')
            return row

        with self.db.connect() as conn:
            validate(conn)
        backup = self.db.backup(self.db.path.parent / 'backups' /
                               f'antes-excluir-teste-{sale_id}-{uuid4().hex[:12]}.sqlite3')
        with self.db.transaction() as conn:
            row = validate(conn)  # Revalida sob bloqueio.
            if conn.execute('SELECT 1 FROM commission_settlements cs JOIN expenses e ON e.id=cs.expense_id WHERE e.sale_id=? OR cs.target_sale_id=?',(sale_id,sale_id)).fetchone():
                raise RuleError('Há comissões vinculadas. Use a correção da venda.')
            pids = [r[0] for r in conn.execute('SELECT product_id FROM sale_items WHERE sale_id=?', (sale_id,))]
            before = {pid: stock_row(conn, pid)['stock'] for pid in pids}
            conn.execute("DELETE FROM history_issues WHERE movement_id IN (SELECT id FROM movements "
                         "WHERE kind IN ('SALE','CANCELLATION') AND source=?)", (str(sale_id),))
            conn.execute("DELETE FROM movements WHERE kind IN ('SALE','CANCELLATION') AND source=?", (str(sale_id),))
            lots = [r[0] for r in conn.execute('SELECT lot_id FROM consignment_sale_items WHERE sale_id=?', (sale_id,))]
            conn.execute('DELETE FROM consignment_moves WHERE sale_id=?', (sale_id,))
            conn.execute('DELETE FROM consignment_sale_items WHERE sale_id=?', (sale_id,))
            validate_lots(conn, lots)
            conn.execute('DELETE FROM receivables WHERE sale_id=?', (sale_id,))
            conn.execute('DELETE FROM expenses WHERE sale_id=?', (sale_id,))
            conn.execute('DELETE FROM sale_items WHERE sale_id=?', (sale_id,))
            conn.execute('DELETE FROM sales WHERE id=?', (sale_id,))
            rebuild_history(conn, pids)
            if any(stock_row(conn, pid)['stock'] != before[pid] for pid in pids):
                raise RuleError('O teste afetou uma conferência física posterior. A exclusão alteraria o saldo atual e foi desfeita.')
            conn.execute('INSERT INTO deleted_sales(id,request_key,reason) VALUES (?,?,?)', (sale_id, row['request_key'], reason))
            audit(conn, 'delete_test_sale', 'sale', sale_id, {'reason': reason, 'backup': backup.name})
        return backup

    def update_sale_notes(self, sale_id, customer, phone, event, notes):
        with self.db.transaction() as conn:
            before = conn.execute('SELECT * FROM sales WHERE id=?', (sale_id,)).fetchone()
            if not before:
                raise RuleError('Venda não encontrada.')
            cid,customer,phone = (None,customer,phone) if before['operation']=='personal' else customer_for(conn,customer,phone)
            conn.execute('UPDATE sales SET customer=?,phone=?,event=?,notes=?,customer_id=? WHERE id=?',
                         (customer, phone, event, notes,cid,sale_id))
            audit(conn, 'update_sale_notes', 'sale', sale_id,
                  {'before': {k: before[k] for k in ['customer', 'phone', 'event', 'notes']},
                   'after': {'customer': customer, 'phone': phone, 'event': event, 'notes': notes}})

    def receive(self, receivable_id, when=None):
        when = day(when or today())
        with self.db.transaction() as conn:
            row = conn.execute('SELECT r.*,s.sale_date FROM receivables r JOIN sales s ON s.id=r.sale_id WHERE r.id=?',
                               (receivable_id,)).fetchone()
            if not row or row['voided_on']:
                raise RuleError('Recebimento inexistente ou cancelado.')
            if row['paid_on']:
                return
            if when < row['sale_date']:
                raise RuleError('O recebimento não pode anteceder a venda nesta versão.')
            conn.execute('UPDATE receivables SET paid_on=? WHERE id=?', (when, receivable_id))
            audit(conn, 'receive', 'receivable', receivable_id, {'paid_on': when})

    def create_expense(self, data, *, key):
        amount, when = cents(data['amount']), day(data.get('occurred_on', today()))
        if amount == 0:
            raise RuleError('A despesa precisa ter valor maior que zero.')
        due = day(data.get('due_on', when), future=True)
        paid = day(data['paid_on']) if data.get('paid_on') else None
        if paid and paid < when:
            raise RuleError('O pagamento não pode anteceder o lançamento nesta versão.')
        with self.db.transaction() as conn:
            previous = conn.execute('SELECT id FROM expenses WHERE request_key=?', (key,)).fetchone()
            if previous:
                return previous['id']
            expense_id = expense_row(conn, key=key, when=when, due=due, paid=paid, amount=amount,
                                     category=required(data['category'], 'a categoria'),
                                     description=required(data['description'], 'a descrição'), vendor=data.get('vendor', ''))
            audit(conn, 'create_expense', 'expense', expense_id, {'request_key': key})
            return expense_id

    def pay_expense(self, expense_id, when=None):
        when = day(when or today())
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM expenses WHERE id=?', (expense_id,)).fetchone()
            if not row or row['cancelled_on'] or not row['cash_effect']:
                raise RuleError('Esta obrigação não está disponível para pagamento.')
            if row['paid_on']:
                return
            if when < row['occurred_on']:
                raise RuleError('O pagamento não pode anteceder o lançamento nesta versão.')
            conn.execute('UPDATE expenses SET paid_on=? WHERE id=?', (when, expense_id))
            audit(conn, 'pay', 'expense', expense_id, {'paid_on': when})

    def pay_expenses(self, expense_ids, when=None):
        """Valida todo o lote antes de baixar; uma falha preserva todas as contas."""
        ids = list(dict.fromkeys(expense_ids))
        if not ids:
            raise RuleError('Selecione pelo menos uma despesa.')
        when = day(when or today())
        with self.db.transaction() as conn:
            for expense_id in ids:
                row = conn.execute('SELECT * FROM expenses WHERE id=?', (expense_id,)).fetchone()
                if not row or row['cancelled_on'] or not row['cash_effect'] or row['paid_on']:
                    raise RuleError(f'A despesa #{expense_id} não está disponível para pagamento. Atualize a lista e revise a seleção.')
                if when < row['occurred_on']:
                    raise RuleError(f'O pagamento da despesa #{expense_id} não pode anteceder seu lançamento.')
            for expense_id in ids:
                conn.execute('UPDATE expenses SET paid_on=? WHERE id=?', (when, expense_id))
                audit(conn, 'pay', 'expense', expense_id, {'paid_on': when, 'batch_ids': ids})

    def cancel_expense(self, expense_id, reason, when=None):
        when, reason = day(when or today()), required(reason, 'o motivo do cancelamento')
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM expenses WHERE id=?', (expense_id,)).fetchone()
            if not row:
                raise RuleError('Despesa não encontrada.')
            if row['cancelled_on']:
                return
            if row['paid_on'] or row['sale_id'] or row['invoice_item_id']:
                raise RuleError('O cancelamento direto vale para despesas avulsas ainda não pagas. '
                                'Lançamentos vinculados devem ser conciliados pela operação de origem.')
            if when < row['occurred_on']:
                raise RuleError('O cancelamento não pode anteceder a despesa.')
            conn.execute('UPDATE expenses SET cancelled_on=?,cancel_reason=? WHERE id=?', (when, reason, expense_id))
            audit(conn, 'cancel_expense', 'expense', expense_id, {'reason': reason, 'when': when})
